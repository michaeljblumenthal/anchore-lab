# In-cluster MCP server image. Includes syft/grype/grant (needed for
# generate_sbom/scan_target/full_scan against registry: targets), git
# (needed for scan_git_repo -- the fully-containerized "scan a repo"
# path, which clones the repo itself rather than relying on a local
# filesystem mount), plus the Python package itself. Same install.sh
# pattern as phase3-inventory/jobs/Dockerfile.sbom-jobs, no compiler needed.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git \
    && rm -rf /var/lib/apt/lists/*

RUN curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh | sh -s -- -b /usr/local/bin \
    && curl -sSfL https://raw.githubusercontent.com/anchore/grype/main/install.sh | sh -s -- -b /usr/local/bin \
    && curl -sSfL https://raw.githubusercontent.com/anchore/grant/main/install.sh | sh -s -- -b /usr/local/bin

WORKDIR /app
COPY pyproject.toml .
COPY sbom_mcp_server ./sbom_mcp_server
RUN pip install --no-cache-dir .

ENV MCP_TRANSPORT=streamable-http
ENV MCP_MODE=cluster
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8000
EXPOSE 8000

CMD ["sbom-mcp-server"]
