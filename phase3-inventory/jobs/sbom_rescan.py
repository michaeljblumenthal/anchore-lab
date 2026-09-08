"""Continuous re-matching job.

Refreshes the Grype vulnerability database once, then re-scans every stored
SBOM against it — no image is re-pulled or re-analysed. This is the
measurable claim the whole lab plan is built around: re-matching stored
SBOMs should be materially cheaper than re-scanning every running image from
scratch. Records timing so that comparison is a real number, not an
assertion.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time

import psycopg
from minio import Minio


def grype_db_update() -> None:
    subprocess.run(["grype", "db", "update"], check=True, capture_output=True, text=True)


def grype_version_info() -> dict:
    out = subprocess.run(["grype", "version", "-o", "json"], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def rescan_sbom(sbom_path: str) -> dict:
    result = subprocess.run(
        ["grype", f"sbom:{sbom_path}", "-o", "json"],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(f"grype failed: {result.stderr[:2000]}")
    return json.loads(result.stdout)


def severity_counts(matches: list[dict]) -> dict[str, int]:
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "negligible": 0}
    for m in matches:
        sev = m["vulnerability"]["severity"].lower()
        if sev in counts:
            counts[sev] += 1
    return counts


def fetch_sboms(conn: psycopg.Connection) -> list[tuple[int, int, str, str]]:
    with conn.cursor() as cur:
        cur.execute("SELECT id, image_id, minio_bucket, minio_key FROM sboms WHERE format = 'syft-json'")
        return cur.fetchall()


def store_scan_result(
    conn: psycopg.Connection,
    sbom_id: int,
    image_id: int,
    grype_ver: dict,
    grype_result: dict,
) -> None:
    matches = grype_result.get("matches", [])
    counts = severity_counts(matches)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO scan_results
                (sbom_id, grype_version, grype_db_built, total_matches,
                 critical_count, high_count, medium_count, low_count, negligible_count, raw_result)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                sbom_id,
                grype_ver.get("version"),
                grype_result.get("descriptor", {}).get("db", {}).get("built"),
                len(matches),
                counts["critical"],
                counts["high"],
                counts["medium"],
                counts["low"],
                counts["negligible"],
                json.dumps(grype_result),
            ),
        )
        scan_result_id = cur.fetchone()[0]

        for m in matches:
            v = m["vulnerability"]
            a = m["artifact"]
            cur.execute(
                """
                INSERT INTO findings
                    (scan_result_id, image_id, vulnerability_id, severity,
                     package_name, package_version, fix_state)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    scan_result_id,
                    image_id,
                    v["id"],
                    v["severity"],
                    a["name"],
                    a.get("version"),
                    v.get("fix", {}).get("state"),
                ),
            )
    conn.commit()


def main() -> None:
    dsn = os.environ["CATALOGUE_DSN"]
    minio_endpoint = os.environ["MINIO_ENDPOINT"]
    minio_access_key = os.environ["MINIO_ACCESS_KEY"]
    minio_secret_key = os.environ["MINIO_SECRET_KEY"]

    minio_client = Minio(
        minio_endpoint,
        access_key=minio_access_key,
        secret_key=minio_secret_key,
        secure=False,
    )

    t0 = time.monotonic()
    grype_db_update()
    db_update_seconds = time.monotonic() - t0
    grype_ver = grype_version_info()

    scanned = 0
    total_bytes = 0
    t_scan_start = time.monotonic()

    with psycopg.connect(dsn) as conn:
        for sbom_id, image_id, bucket, key in fetch_sboms(conn):
            with tempfile.NamedTemporaryFile(suffix=".json") as f:
                minio_client.fget_object(bucket, key, f.name)
                total_bytes += os.path.getsize(f.name)
                result = rescan_sbom(f.name)
            store_scan_result(conn, sbom_id, image_id, grype_ver, result)
            scanned += 1

    scan_seconds = time.monotonic() - t_scan_start

    print(
        f"sbom-rescan: db_update={db_update_seconds:.1f}s, "
        f"{scanned} SBOMs re-matched in {scan_seconds:.1f}s "
        f"({total_bytes/1024:.0f} KiB read from MinIO, "
        f"no images pulled or re-analysed)"
    )


if __name__ == "__main__":
    main()
