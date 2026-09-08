#!/usr/bin/env bash
# Push a local Dockerfile build into the lab's Zot registry as an OCI image.
#
# Uses `docker buildx build --output type=oci` + `crane push`, not
# `docker build` + `docker push`. Two separate bugs made that the only
# reliable path (both documented in phase3-inventory/README.md):
#   - `docker push` against this registry always attempts HTTPS and fails,
#     regardless of insecure-registries config (finding #2) — crane's
#     explicit --insecure flag sidesteps it.
#   - `docker save`'s tarball format produces a docker-schema2 manifest that
#     Zot rejects outright (MANIFEST_INVALID), even via crane. buildx's
#     native `--output type=oci` exporter produces a genuine OCI manifest
#     that Zot accepts (finding #6).
set -euo pipefail

DOCKERFILE="${1:?usage: push-to-registry.sh <Dockerfile> <build-context-dir> <remote-repo:tag>}"
CONTEXT="${2:?usage: push-to-registry.sh <Dockerfile> <build-context-dir> <remote-repo:tag>}"
REMOTE="${3:?usage: push-to-registry.sh <Dockerfile> <build-context-dir> <remote-repo:tag>}"
REGISTRY="${REGISTRY:-zot.lab.localhost:8080}"
export DOCKER_HOST="${DOCKER_HOST:-unix://$HOME/.colima/default/docker.sock}"

command -v crane >/dev/null 2>&1 || { echo "crane not found; run phase1-toolchain/install.sh" >&2; exit 1; }
docker buildx version >/dev/null 2>&1 || { echo "docker buildx plugin not found (brew install docker-buildx)" >&2; exit 1; }

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

echo "==> building $DOCKERFILE -> OCI layout"
docker buildx build -f "$DOCKERFILE" -t "lab/$(basename "$REMOTE")" \
  --output "type=oci,dest=$TMP/image.tar" "$CONTEXT"

mkdir -p "$TMP/oci"
tar -xf "$TMP/image.tar" -C "$TMP/oci"

echo "==> pushing to $REGISTRY/$REMOTE"
crane push "$TMP/oci" "$REGISTRY/$REMOTE" --insecure

echo "Pushed: $REGISTRY/$REMOTE"
