#!/usr/bin/env bash
# Grant across the whole lab, not just the interesting components.
# Port-forwards Postgres and MinIO, then runs license_inventory.py, which
# downloads every stored SBOM and runs Grant against each -- reusing the
# Phase 3 artefacts rather than regenerating anything.
set -euo pipefail
cd "$(dirname "$0")"

kubectl port-forward -n anchore-lab-system svc/catalogue-db-postgresql 5433:5432 > /tmp/pf-pg-license.log 2>&1 &
PG_PID=$!
kubectl port-forward -n anchore-lab-system svc/minio 9002:9000 > /tmp/pf-minio-license.log 2>&1 &
MINIO_PID=$!
trap 'kill $PG_PID $MINIO_PID 2>/dev/null || true' EXIT
sleep 3

python3 license_inventory.py
