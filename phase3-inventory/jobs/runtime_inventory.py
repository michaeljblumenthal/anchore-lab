"""Runtime inventory job.

Lists every image actually running in the cluster (all namespaces, via the
Kubernetes API) and upserts each into the `images` table with its running
locations. This is the mechanism that closes the "registry knows about it"
vs "actually deployed" gap the lab plan calls out.

Runs as a CronJob under the `runtime-inventory` ServiceAccount, which has a
ClusterRole scoped to get/list on pods only (see manifests/rbac-inventory.yaml).
"""

from __future__ import annotations

import json
import os
from collections import defaultdict

import psycopg
from kubernetes import client, config


def list_running_images() -> dict[str, list[dict]]:
    """Return {image_ref: [{namespace, pod, container}, ...]}."""
    config.load_incluster_config()
    v1 = client.CoreV1Api()

    running: dict[str, list[dict]] = defaultdict(list)
    pods = v1.list_pod_for_all_namespaces(watch=False)
    for pod in pods.items:
        if pod.status.phase not in ("Running", "Pending"):
            continue
        containers = (pod.spec.containers or []) + (pod.spec.init_containers or [])
        for c in containers:
            running[c.image].append(
                {
                    "namespace": pod.metadata.namespace,
                    "pod": pod.metadata.name,
                    "container": c.name,
                }
            )
    return running


def upsert_images(conn: psycopg.Connection, running: dict[str, list[dict]]) -> int:
    count = 0
    with conn.cursor() as cur:
        for image_ref, locations in running.items():
            # image_ref here is repo:tag or repo@digest as reported by the
            # kubelet, not always a resolvable digest — real digest
            # resolution happens in the SBOM generation job when it pulls
            # the image. This job's job is presence + location, not content.
            repository, _, tag = image_ref.rpartition(":")
            if "@" in image_ref:
                repository, _, digest_part = image_ref.partition("@")
                digest = digest_part
                tag = None
            else:
                digest = image_ref  # fallback identity when no digest is known yet
            cur.execute(
                """
                INSERT INTO images (digest, repository, tag, running_in)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (digest) DO UPDATE
                SET last_seen = now(), running_in = EXCLUDED.running_in
                """,
                (digest, repository or image_ref, tag, json.dumps(locations)),
            )
            count += 1
    conn.commit()
    return count


def main() -> None:
    dsn = os.environ["CATALOGUE_DSN"]
    running = list_running_images()
    with psycopg.connect(dsn) as conn:
        count = upsert_images(conn, running)
    print(f"runtime-inventory: {count} distinct images across the cluster")


if __name__ == "__main__":
    main()
