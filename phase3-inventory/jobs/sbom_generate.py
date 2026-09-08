"""SBOM generation job.

Reads every image row from the `images` table that doesn't yet have a
stored SBOM, runs `syft` against it, uploads the resulting SBOM JSON to
MinIO, and records the object's location + package count in the `sboms`
table. Deliberately generates the SBOM once and stores it — the whole point
of the lab is that re-matching (sbom_rescan.py) works off this stored
artefact rather than re-pulling/re-analysing the image each time.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile

import psycopg
from minio import Minio


def syft_version() -> str:
    out = subprocess.run(["syft", "version", "-o", "json"], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)["version"]


IN_CLUSTER_REGISTRY_HOST = os.environ.get(
    "IN_CLUSTER_REGISTRY_HOST", "zot.anchore-lab-system.svc.cluster.local:5000"
)
HOST_FACING_REGISTRY_HOST = os.environ.get("HOST_FACING_REGISTRY_HOST", "zot.lab.localhost:8080")


def resolve_for_pod(image_ref: str) -> str:
    """Rewrite the lab's own registry host to its in-cluster Service DNS name.

    Everything in this catalogue — pushed images, runtime-inventory's
    records — uses "zot.lab.localhost:8080" as the canonical reference, since
    that's what host-side tooling (push-to-registry.sh) and Kubernetes
    manifests both use for a consistent, single-looking image name. But a
    pod's own network namespace has no idea what "zot.lab.localhost" means
    (it's an OS-level .localhost-TLD trick on the host, not a real DNS
    record cluster DNS knows about) — same underlying class of host-vs-pod
    addressing split as the containerd registries.yaml mirror (see
    phase3-inventory/README.md finding #7), just hit again here because this
    job calls syft directly rather than going through containerd's pull
    path. Third-party images (docker.io/..., ghcr.io/..., etc.) need no
    rewrite, they're real DNS everywhere.
    """
    if image_ref.startswith(HOST_FACING_REGISTRY_HOST):
        return IN_CLUSTER_REGISTRY_HOST + image_ref[len(HOST_FACING_REGISTRY_HOST):]
    return image_ref


def generate_sbom(image_ref: str) -> dict:
    """Run syft against an image reference, pulling through the in-cluster
    registry. Returns the parsed syft-json SBOM."""
    pull_ref = resolve_for_pod(image_ref)
    result = subprocess.run(
        ["syft", "scan", f"registry:{pull_ref}", "-o", "syft-json"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(f"syft failed for {image_ref}: {result.stderr[:2000]}")
    return json.loads(result.stdout)


def fetch_pending_images(conn: psycopg.Connection) -> list[tuple[int, str, str]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT i.id, i.repository, i.tag
            FROM images i
            LEFT JOIN sboms s ON s.image_id = i.id AND s.format = 'syft-json'
            WHERE s.id IS NULL
            """
        )
        return cur.fetchall()


def store_sbom(
    conn: psycopg.Connection,
    minio_client: Minio,
    bucket: str,
    image_id: int,
    image_ref: str,
    sbom: dict,
    version: str,
) -> None:
    key = f"{image_id}/syft.json"
    payload = json.dumps(sbom).encode()
    with tempfile.NamedTemporaryFile() as f:
        f.write(payload)
        f.flush()
        minio_client.fput_object(bucket, key, f.name, content_type="application/json")

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sboms (image_id, format, minio_bucket, minio_key, package_count, syft_version)
            VALUES (%s, 'syft-json', %s, %s, %s, %s)
            ON CONFLICT (image_id, format) DO UPDATE
            SET minio_key = EXCLUDED.minio_key, package_count = EXCLUDED.package_count,
                syft_version = EXCLUDED.syft_version, generated_at = now()
            """,
            (image_id, bucket, key, len(sbom.get("artifacts", [])), version),
        )
    conn.commit()


def main() -> None:
    dsn = os.environ["CATALOGUE_DSN"]
    minio_endpoint = os.environ["MINIO_ENDPOINT"]
    minio_access_key = os.environ["MINIO_ACCESS_KEY"]
    minio_secret_key = os.environ["MINIO_SECRET_KEY"]
    bucket = os.environ.get("MINIO_BUCKET", "sboms")

    minio_client = Minio(
        minio_endpoint,
        access_key=minio_access_key,
        secret_key=minio_secret_key,
        secure=False,  # in-cluster, plain HTTP — see registry insecure-endpoint findings
    )
    if not minio_client.bucket_exists(bucket):
        minio_client.make_bucket(bucket)

    version = syft_version()
    generated = 0
    failed = 0

    with psycopg.connect(dsn) as conn:
        for image_id, repository, tag in fetch_pending_images(conn):
            image_ref = f"{repository}:{tag}" if tag else repository
            try:
                sbom = generate_sbom(image_ref)
                store_sbom(conn, minio_client, bucket, image_id, image_ref, sbom, version)
                generated += 1
            except Exception as exc:  # noqa: BLE001 — one bad image shouldn't kill the batch
                print(f"FAILED {image_ref}: {exc}")
                failed += 1

    print(f"sbom-generate: {generated} generated, {failed} failed")


if __name__ == "__main__":
    main()
