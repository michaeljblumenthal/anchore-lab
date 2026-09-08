"""Grant across every SBOM in the catalogue, not just the interesting ones.

Downloads each stored SBOM from MinIO (via a port-forward run separately,
see license-inventory.sh) and runs Grant against it locally, producing a
per-component license summary and a combined total. Reuses the same
Postgres/MinIO the runtime pipeline writes to -- no special path for the
self-scan, per the plan's own principle.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import psycopg
from minio import Minio

OUT_DIR = Path(__file__).parent / "license-results"


def fetch_sbom_list(dsn: str) -> list[tuple[str, str, str, str]]:
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT i.repository, i.tag, s.minio_bucket, s.minio_key FROM sboms s JOIN images i ON i.id = s.image_id"
        )
        return cur.fetchall()


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    dsn = "postgresql://catalogue:cataloguepassword123@localhost:5433/catalogue"
    minio_client = Minio("localhost:9002", access_key="labadmin", secret_key="labpassword123", secure=False)

    rows = fetch_sbom_list(dsn)
    print(f"{len(rows)} SBOMs to check.\n")

    totals = {"packages": 0, "allowed": 0, "denied": 0, "unlicensed": 0}
    results = []

    for repository, tag, bucket, key in rows:
        label = f"{repository}:{tag}"
        with tempfile.NamedTemporaryFile(suffix=".json") as f:
            minio_client.fget_object(bucket, key, f.name)
            grant_proc = subprocess.run(
                ["grant", "check", f.name, "-o", "json"],
                capture_output=True,
                text=True,
            )
            try:
                r = json.loads(grant_proc.stdout)
                s = r["run"]["targets"][0]["evaluation"]["summary"]["packages"]
                print(
                    f"{label}: packages={s['cataloged']} allowed={s['allowed']} "
                    f"denied={s['denied']} unlicensed={s['unlicensed']}"
                )
                totals["packages"] += s["cataloged"]
                totals["allowed"] += s["allowed"]
                totals["denied"] += s["denied"]
                totals["unlicensed"] += s["unlicensed"]
                results.append({"image": label, **s})
            except (json.JSONDecodeError, KeyError, IndexError) as exc:
                print(f"{label}: could not parse grant output ({exc})")

    print(f"\n=== Totals across {len(rows)} images ===")
    print(
        f"packages={totals['packages']} allowed={totals['allowed']} "
        f"denied={totals['denied']} unlicensed={totals['unlicensed']}"
    )

    with open(OUT_DIR / "summary.json", "w") as f:
        json.dump({"totals": totals, "per_image": results}, f, indent=2)
    print(f"\nWrote {OUT_DIR / 'summary.json'}")


if __name__ == "__main__":
    main()
