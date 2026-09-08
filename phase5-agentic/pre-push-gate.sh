#!/usr/bin/env bash
# Pre-push gate: runs SBOM generation + vulnerability/licence scanning on
# sbom-mcp-server before anything reaches the remote. Installed as a real
# git hook (see install-pre-push-gate.sh) so it runs automatically on every
# `git push`, not just when remembered.
#
# Policy: fail the push on any Critical severity finding. High/Medium/Low
# are reported but don't block — this matches the CI workflow's
# severity-cutoff choice (phase4-ci) at the loosest end deliberately: a
# pre-push gate that's too strict trains people to use --no-verify, which
# defeats the point. CI (which nothing can skip via a client-side flag) is
# where the stricter high-severity cutoff actually lives.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="$REPO_ROOT/phase5-agentic/sbom-mcp-server"
VENV="$TARGET/.venv"

if [ ! -x "$VENV/bin/python3" ]; then
  echo "pre-push-gate: sbom-mcp-server venv not found, skipping scan (run 'make mcp-server' to enable this gate)" >&2
  exit 0
fi

echo "pre-push-gate: scanning sbom-mcp-server before push..."

"$VENV/bin/python3" - "$TARGET" <<'PYEOF'
import json
import sys
sys.path.insert(0, sys.argv[1])
from sbom_mcp_server import tools

target = sys.argv[1]
result = tools.full_scan(f"dir:{target}", workdir="/tmp/pre-push-gate")

matches = result["vulnerabilities"].get("matches", [])
critical = [m for m in matches if m["vulnerability"]["severity"] == "Critical"]

print(f"pre-push-gate: {result['package_count']} packages, {len(matches)} findings, {len(critical)} Critical")

if critical:
    print("pre-push-gate: BLOCKING push — Critical findings present:")
    for m in critical:
        v, a = m["vulnerability"], m["artifact"]
        print(f"  {v['id']} ({v['severity']}) in {a['name']}@{a.get('version')}")
    sys.exit(1)

sys.exit(0)
PYEOF

exit $?
