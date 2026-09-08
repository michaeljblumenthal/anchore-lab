#!/usr/bin/env bash
# Mirror an existing upstream image (e.g. python:3.12-slim) into the lab's
# Zot registry. For locally-built Dockerfiles, use push-to-registry.sh
# instead — this script pulls from the image's own registry, it doesn't
# build anything.
set -euo pipefail

IMAGE="${1:?usage: mirror-to-registry.sh <upstream-image:tag> <remote-repo:tag>}"
REMOTE="${2:?usage: mirror-to-registry.sh <upstream-image:tag> <remote-repo:tag>}"
REGISTRY="${REGISTRY:-zot.lab.localhost:8080}"

command -v crane >/dev/null 2>&1 || { echo "crane not found; run phase1-toolchain/install.sh" >&2; exit 1; }

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

echo "==> pulling $IMAGE as OCI layout"
crane pull "$IMAGE" "$TMP/oci.tar" --format oci

echo "==> pushing to $REGISTRY/$REMOTE"
crane push "$TMP/oci.tar" "$REGISTRY/$REMOTE" --insecure

echo "Pushed: $REGISTRY/$REMOTE"
