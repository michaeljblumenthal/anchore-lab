#!/usr/bin/env bash
# Run a single SQL statement against the catalogue DB from a throwaway pod.
# Usage: ./psql.sh "SELECT ..."
set -euo pipefail
SQL="${1:?usage: psql.sh <sql>}"
NAME="psql-oneshot-$RANDOM"

kubectl run "$NAME" --restart=Never -n anchore-lab-system --image postgres:16-alpine \
  --command -- psql "postgresql://catalogue:cataloguepassword123@catalogue-db-postgresql:5432/catalogue" -c "$SQL" \
  >/dev/null

# Wait for the pod to finish (Succeeded or Failed), not an arbitrary sleep.
kubectl wait --for=jsonpath='{.status.phase}'=Succeeded "pod/$NAME" -n anchore-lab-system --timeout=30s >/dev/null 2>&1 || true
kubectl logs "$NAME" -n anchore-lab-system 2>&1
kubectl delete pod "$NAME" -n anchore-lab-system >/dev/null 2>&1
