#!/usr/bin/env bash
# Phase 3: the continuous inventory stack. Installs in dependency order —
# registry and storage before anything that pushes to or reads from them,
# the catalogue DB before the jobs that write to it, job images pushed
# before the CronJobs that reference them. Idempotent per step (helm
# upgrade --install, kubectl apply).
#
# Prerequisite: phase2-cluster/bootstrap.sh must have been run with the
# CURRENT phase2-cluster/registries.yaml (it's baked in at cluster-create
# time and can't be changed on a running cluster — see that file's own
# comments and phase3-inventory/README.md finding #7 for why).
set -euo pipefail

NAMESPACE="anchore-lab-system"
cd "$(dirname "$0")"

log() { printf '\n\033[1;34m==>\033[0m %s\n' "$1"; }

for bin in helm kubectl syft grype crane; do
  command -v "$bin" >/dev/null 2>&1 || { echo "$bin not found on PATH" >&2; exit 1; }
done
docker buildx version >/dev/null 2>&1 || { echo "docker buildx plugin not found (brew install docker-buildx)" >&2; exit 1; }

kubectl get namespace anchore-lab-system >/dev/null 2>&1 || {
  echo "anchore-lab-system namespace not found; run phase2-cluster/bootstrap.sh first" >&2
  exit 1
}

for repo_url in "harbor https://helm.goharbor.io" "bitnami https://charts.bitnami.com/bitnami" \
                "grafana https://grafana.github.io/helm-charts" "kyverno https://kyverno.github.io/kyverno" \
                "zot https://zotregistry.dev/helm-charts"; do
  set -- $repo_url
  helm repo add "$1" "$2" >/dev/null 2>&1 || true
done
helm repo update >/dev/null

log "1/8 Zot (registry — see README.md finding #1 for why Zot, not Harbor)"
helm upgrade --install zot zot/zot \
  --namespace "$NAMESPACE" \
  --values helm-values/zot.yaml \
  --wait --timeout 5m

log "2/8 MinIO (SBOM object storage)"
helm upgrade --install minio bitnami/minio \
  --namespace "$NAMESPACE" \
  --values helm-values/minio.yaml \
  --wait --timeout 5m

log "3/8 Postgres (catalogue database)"
helm upgrade --install catalogue-db bitnami/postgresql \
  --namespace "$NAMESPACE" \
  --values helm-values/postgres.yaml \
  --wait --timeout 5m

log "4/8 Catalogue schema"
kubectl apply -f manifests/catalogue-schema-job.yaml
kubectl wait --for=condition=complete job/catalogue-schema -n "$NAMESPACE" --timeout=120s

log "5/8 RBAC + job images (built locally, pushed via buildx+crane — see README.md finding #6)"
kubectl apply -f manifests/rbac-inventory.yaml
./push-to-registry.sh jobs/Dockerfile.runtime-inventory jobs lab/runtime-inventory:0.1.0
./push-to-registry.sh jobs/Dockerfile.sbom-jobs jobs lab/sbom-jobs:0.1.0

log "6/8 Runtime inventory + SBOM generate/rescan CronJobs"
kubectl apply -f manifests/runtime-inventory-cronjob.yaml
kubectl apply -f manifests/sbom-generate-cronjob.yaml

log "7/8 Kyverno (admission control, audit mode)"
helm upgrade --install kyverno kyverno/kyverno \
  --namespace kyverno --create-namespace \
  --values helm-values/kyverno.yaml \
  --wait --timeout 5m
kubectl apply -f manifests/kyverno-policies.yaml

log "8/9 Grafana (visibility)"
helm upgrade --install grafana grafana/grafana \
  --namespace "$NAMESPACE" \
  --values helm-values/grafana.yaml \
  --wait --timeout 5m

log "9/9 MCP servers (in-cluster — see phase5-agentic/README.md)"
./push-to-registry.sh ../phase5-agentic/sbom-mcp-server/Dockerfile ../phase5-agentic/sbom-mcp-server lab/mcp-server:0.1.0
kubectl apply -f ../phase5-agentic/manifests/mcp-server.yaml
kubectl rollout status deployment/mcp-server -n "$NAMESPACE" --timeout=90s
./push-to-registry.sh ../phase5-agentic/grype-mcp-container/Dockerfile ../phase5-agentic/grype-mcp-container lab/grype-mcp:0.1.0
kubectl apply -f ../phase5-agentic/manifests/grype-mcp.yaml
kubectl rollout status deployment/grype-mcp -n "$NAMESPACE" --timeout=90s

log "Everything ready. sbom-scan: http://mcp.lab.localhost:8080/mcp | grype-mcp: kubectl exec (see phase5-agentic/connect-grype-mcp.sh)"
kubectl get pods -n "$NAMESPACE"
kubectl get pods -n kyverno
