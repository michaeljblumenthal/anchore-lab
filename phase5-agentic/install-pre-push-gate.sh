#!/usr/bin/env bash
# Installs pre-push-gate.sh as a real git pre-push hook. Idempotent.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK="$REPO_ROOT/.git/hooks/pre-push"

cat > "$HOOK" <<EOF
#!/usr/bin/env bash
exec "$REPO_ROOT/phase5-agentic/pre-push-gate.sh"
EOF
chmod +x "$HOOK"

echo "Installed pre-push gate at $HOOK"
echo "It will run automatically on every 'git push' from this clone."
