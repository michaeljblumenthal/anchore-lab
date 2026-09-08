#!/usr/bin/env bash
# Regenerates manifests/grafana-dashboard-configmap.yaml from
# helm-values/grafana-dashboard-catalogue.json. Keeping the dashboard as a
# standalone JSON file (rather than hand-indenting it inside a ConfigMap
# YAML) makes it editable and diffable on its own.
set -euo pipefail
cd "$(dirname "$0")"

kubectl create configmap grafana-dashboard-catalogue \
  --namespace anchore-lab-system \
  --from-file=catalogue.json=helm-values/grafana-dashboard-catalogue.json \
  --dry-run=client -o yaml > manifests/grafana-dashboard-configmap.yaml

echo "Wrote manifests/grafana-dashboard-configmap.yaml"
