# grype-mcp is a third-party stdio-only MCP server (Anchore's own package)
# -- its server.py hardcodes mcp.run(transport='stdio'), confirmed by
# reading the installed source, so unlike sbom-mcp-server it can't simply
# be told to listen on HTTP without patching Anchore's code. Keeping it
# stdio and running it in-cluster instead: this image's entrypoint is a
# long-lived sleep, and the actual MCP process is started per-connection
# via `kubectl exec -i` (see connect-grype-mcp.sh), the same way anyone
# would reach a stdio-only tool that has to live inside a cluster boundary
# (near the registry, near the vuln DB cache) rather than on a laptop.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl -sSfL https://raw.githubusercontent.com/anchore/grype/main/install.sh | sh -s -- -b /usr/local/bin

# mcp<2 pin: see phase5-agentic/README.md finding #1 -- grype-mcp's own
# dependency declaration has no ceiling on mcp, and a fresh install pulls
# the mcp 2.x SDK, which renamed FastMCP and breaks grype-mcp's import.
RUN pip install --no-cache-dir grype-mcp "mcp<2"

CMD ["sleep", "infinity"]
