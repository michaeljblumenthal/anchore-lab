#!/usr/bin/env bash
# Connects an MCP client's stdio to grype-mcp running inside the cluster,
# via `kubectl exec -i` into the always-on grype-mcp pod
# (manifests/grype-mcp.yaml). This is what .mcp.json's "grype-mcp" entry
# actually launches -- from the client's point of view it's indistinguishable
# from a local stdio process; the JSON-RPC bytes just happen to be relayed
# through the Kubernetes API server into a pod instead of a local fork.
set -euo pipefail

NAMESPACE="anchore-lab-system"
POD=$(kubectl get pods -n "$NAMESPACE" -l app=grype-mcp -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

if [ -z "$POD" ]; then
  echo "No grype-mcp pod found in $NAMESPACE. Run: kubectl apply -f phase5-agentic/manifests/grype-mcp.yaml" >&2
  exit 1
fi

exec kubectl exec -i -n "$NAMESPACE" "$POD" -- grype-mcp
