#!/usr/bin/env bash
# Phase 1 toolchain bootstrap. Idempotent: safe to re-run, skips anything
# already installed. macOS/Homebrew only — see README.md for why (Docker
# Desktop's postflight needs an interactive sudo prompt this can't supply,
# so this installs Colima instead).
set -euo pipefail

log() { printf '\n\033[1;34m==>\033[0m %s\n' "$1"; }
have() { command -v "$1" >/dev/null 2>&1; }

if ! have brew; then
  echo "Homebrew is required: https://brew.sh" >&2
  exit 1
fi

log "Container runtime (Colima + Docker CLI)"
if have colima && have docker; then
  echo "colima and docker already installed, skipping"
else
  brew install colima docker
fi

log "Kubernetes tooling (kubectl, helm, k3d, k9s, crane)"
# crane (go-containerregistry): used instead of `docker push` for pushing to
# the in-cluster registry. `docker push` ignores insecure-registries under
# Colima for this lab's setup (see phase3-inventory/README.md finding #2)
# — crane takes an explicit --insecure flag per invocation instead of
# relying on daemon-wide config, which sidesteps the bug entirely.
for f in kubernetes-cli helm k3d k9s crane; do
  if brew list --formula "$f" >/dev/null 2>&1; then
    echo "$f already installed, skipping"
  else
    brew install "$f"
  fi
done

log "Anchore scanning tools (syft, grype via brew; grant via install script)"
for f in syft grype; do
  if brew list --formula "$f" >/dev/null 2>&1; then
    echo "$f already installed, skipping"
  else
    brew install "$f"
  fi
done

if have grant; then
  echo "grant already on PATH, skipping"
else
  # NOT via `brew install anchore/grant/grant`: that tap builds from source
  # and needs a newer Xcode CLT than ships by default, which itself needs an
  # interactive sudo/System Settings step. The install.sh script pulls a
  # prebuilt binary instead.
  mkdir -p "$HOME/bin"
  curl -sSfL https://raw.githubusercontent.com/anchore/grant/main/install.sh | sh -s -- -b "$HOME/bin"
  # `~/bin` is only on PATH in interactive shells that source ~/.zshrc.
  # Subprocess/agent/CI invocations won't see it, so symlink into a
  # first-on-PATH Homebrew dir too.
  ln -sf "$HOME/bin/grant" /opt/homebrew/bin/grant
fi

log "Starting Colima (6 vCPU / 12GB / 60GB, Rosetta acceleration on)"
# --vz-rosetta: harmless to leave on even though the registry choice
# (Zot, see phase3-inventory/README.md finding #1) turned out to be
# arm64-native — some other image pulled later in the lab may still be
# amd64-only, and Rosetta-accelerated emulation is strictly better than
# plain QEMU for those cases at no real cost.
if colima status >/dev/null 2>&1; then
  echo "colima already running, skipping"
else
  colima start --cpu 6 --memory 12 --disk 60 --vz-rosetta
fi

log "Configuring insecure registry for the in-cluster Harbor (Phase 3)"
# Colima manages /etc/docker/daemon.json from its own config and overwrites
# manual edits on restart — this must go through `colima.yaml`, not a direct
# daemon.json edit (learned the hard way: a direct edit survived until the
# next `colima restart`, then silently reverted).
COLIMA_CONF="$HOME/.colima/default/colima.yaml"
if [ -f "$COLIMA_CONF" ] && ! grep -q "harbor.lab.localhost:8080" "$COLIMA_CONF"; then
  python3 - "$COLIMA_CONF" <<'PYEOF'
import sys
path = sys.argv[1]
with open(path) as f:
    content = f.read()
if "harbor.lab.localhost:8080" not in content:
    content = content.replace(
        "docker: {}",
        "docker:\n  insecure-registries:\n    - harbor.lab.localhost:8080\n",
        1,
    )
    with open(path, "w") as f:
        f.write(content)
PYEOF
  echo "added insecure-registries entry; run 'colima restart' for it to take effect"
else
  echo "insecure-registries already configured, skipping"
fi

log "Verifying"
syft version
grype version
grant version
kubectl version --client
helm version
k3d version
docker info --format 'docker server: {{.ServerVersion}}'

log "Toolchain baseline ready."

cat <<'EOF'

NOTE: syft's `docker:` source does not read the active `docker context` (it
only checks $DOCKER_HOST / the default socket). With Colima instead of
Docker Desktop, export this before running `syft scan docker:...`:

    export DOCKER_HOST="unix://$HOME/.colima/default/docker.sock"

Add it to your shell profile if you'll be doing this repeatedly.
EOF
