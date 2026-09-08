#!/usr/bin/env bash
# Phase 2: bring up a multi-node k3d cluster with real scheduling, a bound
# storage class, ingress with a resolving hostname, and least-privilege
# RBAC. Idempotent: safe to re-run against an existing cluster.
set -euo pipefail

CLUSTER_NAME="anchore-lab"
export DOCKER_HOST="${DOCKER_HOST:-unix://$HOME/.colima/default/docker.sock}"

log() { printf '\n\033[1;34m==>\033[0m %s\n' "$1"; }
have() { command -v "$1" >/dev/null 2>&1; }

for bin in k3d kubectl helm; do
  have "$bin" || { echo "$bin not found on PATH; run phase1-toolchain/install.sh first" >&2; exit 1; }
done

log "Cluster: $CLUSTER_NAME (1 server, 2 agents)"
if k3d cluster list "$CLUSTER_NAME" >/dev/null 2>&1; then
  echo "cluster $CLUSTER_NAME already exists, skipping create"
else
  # --servers 1: k3d's embedded etcd (sqlite) doesn't support HA below 3
  # servers without extra config, and this is a lab, not an HA exercise.
  # --agents 2: enough to make scheduling/affinity real without exceeding
  # the 4 vCPU / 8GB Colima budget.
  # Port 8080/8443 on the host map to the k3d load balancer's 80/443, which
  # forwards into Traefik (k3d's built-in ingress controller, kept per
  # ADR — see phase2-cluster/README.md).
  # --registry-config: without this, containerd inside every node defaults
  # to HTTPS for zot.lab.localhost:8080 (Phase 3's registry) and image pulls
  # fail — same class of insecure-registry problem as Docker's daemon.json,
  # just at the containerd layer, and it must be set at cluster-create time
  # (k3d has no way to mutate it into a running cluster). See
  # phase3-inventory/README.md finding #2.
  # k3d's serverlb container intermittently fails to boot (confd can't find
  # its own generated config, container stuck in Docker state "Created" —
  # see README.md finding #4). No known root cause or config fix; retrying
  # the whole create is the only reliable recovery found. Verify the LB
  # container is actually Up, not just that the cluster nominally exists.
  for attempt in 1 2 3; do
    k3d cluster create "$CLUSTER_NAME" \
      --servers 1 \
      --agents 2 \
      --port "8080:80@loadbalancer" \
      --port "8443:443@loadbalancer" \
      --registry-config ./registries.yaml \
      --wait
    lb_status=$(docker inspect -f '{{.State.Status}}' "k3d-${CLUSTER_NAME}-serverlb" 2>/dev/null || echo "missing")
    if [ "$lb_status" = "running" ]; then
      break
    fi
    echo "serverlb didn't come up (status: $lb_status), retrying create (attempt $attempt/3)..." >&2
    k3d cluster delete "$CLUSTER_NAME" >/dev/null 2>&1 || true
    if [ "$attempt" = 3 ]; then
      echo "serverlb failed to start after 3 attempts; giving up" >&2
      exit 1
    fi
  done
fi

log "Cluster nodes"
kubectl get nodes -o wide

log "Namespaces"
kubectl apply -f manifests/namespaces.yaml

log "RBAC: dedicated service accounts, no cluster-admin"
kubectl apply -f manifests/rbac.yaml

log "Storage class (k3d ships local-path-provisioner by default)"
kubectl get storageclass

log "Verifying PVC binds against the default storage class"
kubectl apply -f manifests/test-pvc.yaml
kubectl wait --for=condition=Ready pod/test-pvc-consumer -n anchore-lab --timeout=60s
kubectl wait --for=jsonpath='{.status.phase}'=Bound pvc/test-pvc -n anchore-lab --timeout=10s
kubectl delete -f manifests/test-pvc.yaml

log "Ingress: confirming Traefik is up and a hostname resolves"
kubectl apply -f manifests/whoami.yaml
kubectl wait --for=condition=available deployment/whoami -n anchore-lab --timeout=90s
echo "Testing http://lab.localhost:8080"
curl -sS -m 10 http://lab.localhost:8080/ || echo "(curl failed — see README troubleshooting)"

log "Phase 2 baseline ready."
kubectl get all -n anchore-lab
