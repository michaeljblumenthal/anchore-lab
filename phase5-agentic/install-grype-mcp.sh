#!/usr/bin/env bash
# Installs anchore/grype-mcp (the official Grype-only MCP server named
# directly in the plan, distinct from this repo's own sbom-mcp-server,
# which wraps the full Syft->Grype->Grant pipeline).
#
# Pins `mcp<2`: as published, grype-mcp 0.4.0's own dependency declaration
# is unpinned ("Requires: mcp", no ceiling), so a plain `pip install
# grype-mcp` pulls the latest mcp SDK (2.x) and crashes on import —
# `ModuleNotFoundError: No module named 'mcp.server.fastmcp'` — because
# FastMCP was renamed to MCPServer in mcp 2.x and grype-mcp's server.py
# still imports the old path. This is a real upstream packaging bug, not a
# local environment issue: confirmed by pinning mcp<2 (1.30.0 installed
# cleanly) and getting a real MCP initialize/tools-list handshake back. See
# phase5-agentic/README.md for the finding written up in full.
set -euo pipefail
cd "$(dirname "$0")"

python3 -m venv grype-mcp-install/.venv
source grype-mcp-install/.venv/bin/activate
pip install -q --upgrade pip
pip install -q grype-mcp "mcp<2"

echo "grype-mcp installed: $(grype-mcp-install/.venv/bin/pip show grype-mcp | grep Version)"
echo "Add to .mcp.json (already done in this repo) to connect it to an MCP client."
