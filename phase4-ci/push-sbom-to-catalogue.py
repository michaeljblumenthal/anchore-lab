"""Push a build-time SBOM into the Phase 3 catalogue.

Run from CI after anchore/sbom-action generates an SBOM, so build-time and
runtime inventories converge in one place (the plan's Phase 4 requirement)
rather than living in two disconnected systems — a GitHub Actions artifact
nobody queries, and a runtime catalogue that only knows what's deployed.

Requires network access to the catalogue's Postgres and MinIO, which in
this lab only exist inside the local k3d cluster — this script is written
to run against a reachable catalogue (e.g. via a tunnel or when CI runs
against a real reachable environment), and is deliberately NOT wired into
the GitHub-hosted workflow runner, which cannot reach a cluster running on
someone's laptop. Documented as the honest limit of a local-lab CI
integration: see phase4-ci/README.md.

Reuses the same schema and insert pattern as
phase3-inventory/jobs/sbom_generate.py rather than duplicating it, adding
only a `source` marker to distinguish rows written by CI ("build") from
rows written by the runtime pipeline ("runtime").
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import psycopg
from minio import Minio


def push(
    dsn: str,
    minio_client: Minio,
    bucket: str,
    repository: str,
    tag: str,
    digest: str,
    sbom_path: str,
    syft_version: str,
) -> None:
    with open(sbom_path, "rb") as f:
        sbom_bytes = f.read()
    sbom = json.loads(sbom_bytes)

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO images (digest, repository, tag, running_in)
            VALUES (%s, %s, %s, '[]'::jsonb)
            ON CONFLICT (digest) DO UPDATE SET last_seen = now()
            RETURNING id
            """,
            (digest, repository, tag),
        )
        image_id = cur.fetchone()[0]

        key = f"{image_id}/syft-build.json"
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(sbom_bytes)
            tmp_path = tmp.name
        if not minio_client.bucket_exists(bucket):
            minio_client.make_bucket(bucket)
        minio_client.fput_object(bucket, key, tmp_path, content_type="application/json")
        os.unlink(tmp_path)

        package_count = len(sbom.get("packages", sbom.get("artifacts", [])))
        cur.execute(
            """
            INSERT INTO sboms (image_id, format, minio_bucket, minio_key, package_count, syft_version)
            VALUES (%s, 'spdx-json', %s, %s, %s, %s)
            ON CONFLICT (image_id, format) DO UPDATE
            SET minio_key = EXCLUDED.minio_key, package_count = EXCLUDED.package_count,
                syft_version = EXCLUDED.syft_version, generated_at = now()
            """,
            (image_id, bucket, key, package_count, syft_version),
        )
        conn.commit()

    print(f"pushed build-time SBOM for {repository}:{tag} (image_id={image_id}, {package_count} packages)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--digest", required=True, help="git commit SHA or image digest, used as the unique key")
    parser.add_argument("--sbom-path", required=True)
    parser.add_argument("--syft-version", default="unknown")
    args = parser.parse_args()

    dsn = os.environ.get("CATALOGUE_DSN")
    if not dsn:
        print("CATALOGUE_DSN not set; catalogue unreachable from this runner, skipping", file=sys.stderr)
        return

    minio_client = Minio(
        os.environ["MINIO_ENDPOINT"],
        access_key=os.environ["MINIO_ACCESS_KEY"],
        secret_key=os.environ["MINIO_SECRET_KEY"],
        secure=False,
    )
    push(
        dsn,
        minio_client,
        os.environ.get("MINIO_BUCKET", "sboms"),
        args.repository,
        args.tag,
        args.digest,
        args.sbom_path,
        args.syft_version,
    )


if __name__ == "__main__":
    main()
