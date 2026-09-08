"""MCP server exposing syft/grype/grant as tools for any MCP client.

Two deployment modes, one codebase:

- **stdio** (default, unchanged from the original build): launched as a
  local subprocess by an MCP client (Claude Code's .mcp.json). Full tool
  surface, including local-filesystem targets (dir:./path) -- the caller's
  own machine is the filesystem being scanned, so that's meaningful here.

    sbom-mcp-server

- **streamable-http** (in-cluster deployment, see phase5-agentic/manifests/):
  runs as a long-lived service other machines connect to over the network.
  A "dir:" target has no meaning in this mode -- the pod's filesystem isn't
  the caller's -- so MCP_MODE=cluster additionally exposes the catalogue
  query tools (backed by the Phase 3 Postgres catalogue) and is meant to be
  used with registry image references, not local paths. Set
  MCP_TRANSPORT=streamable-http to select this mode; MCP_HOST/MCP_PORT
  configure the listener (defaults 0.0.0.0:8000).

    MCP_TRANSPORT=streamable-http MCP_MODE=cluster sbom-mcp-server

`scan_git_repo` is available in both modes and is the way to scan an
arbitrary repository fully in-cluster, with no dependency on the caller's
local filesystem: it clones the repo itself (like a CI runner would),
scans the clone, and deletes it afterwards. This is the containerized
alternative to a `dir:` target for anyone who wants "the whole solution,
tools included, running only in Kubernetes" rather than relying on a
host-side install.
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any

from mcp.server.mcpserver import MCPServer

from sbom_mcp_server import catalogue, tools

mcp = MCPServer("sbom-mcp-server")


@mcp.tool()
def generate_sbom(target: str, output_format: str = "syft-json") -> str:
    """Generate an SBOM for a target with Syft.

    Args:
        target: image reference (docker:name:tag or registry:name:tag), or
            in stdio mode only, a directory path (dir:./path).
        output_format: syft-json, spdx-json, or cyclonedx-json.
    """
    result = tools.generate_sbom(target, output_format)
    return json.dumps(result)


@mcp.tool()
def scan_vulnerabilities(sbom_path: str, fail_on: str | None = None) -> str:
    """Scan a previously generated SBOM file for vulnerabilities with Grype.

    Args:
        sbom_path: path to a Syft-generated SBOM JSON file on disk.
        fail_on: optional severity threshold (negligible, low, medium, high, critical).
    """
    result = tools.scan_sbom(sbom_path, fail_on=fail_on)
    return json.dumps(result)


@mcp.tool()
def scan_target(target: str, fail_on: str | None = None) -> str:
    """Scan a target directly with Grype (no separate SBOM step, image or dir)."""
    result = tools.scan_target_direct(target, fail_on=fail_on)
    return json.dumps(result)


@mcp.tool()
def check_licenses(sbom_path: str) -> str:
    """Check licence compliance for a Syft SBOM file with Grant."""
    result = tools.check_licenses(sbom_path)
    return json.dumps(result)


@mcp.tool()
def full_scan(target: str, fail_on: str | None = None) -> str:
    """Run the full Syft -> Grype -> Grant pipeline against a target.

    Generates an SBOM, scans it for vulnerabilities, and checks licences,
    reusing the same SBOM artefact for both downstream steps. Intermediate
    SBOMs are written to a temp directory whose path is returned in the result.

    Args:
        target: image reference, or in stdio mode only, a directory
            (prefix with dir:) or archive.
        fail_on: optional severity threshold passed to Grype.
    """
    workdir = tempfile.mkdtemp(prefix="sbom-mcp-")
    result: dict[str, Any] = tools.full_scan(target, workdir, fail_on=fail_on)
    return json.dumps(result)


@mcp.tool()
def scan_git_repo(git_url: str, ref: str | None = None, fail_on: str | None = None) -> str:
    """Clone a public git repository and run the full Syft -> Grype -> Grant
    pipeline against it -- entirely inside this server, no access to the
    caller's local filesystem needed. This is what lets a repo be scanned
    fully in-cluster: the server clones the repo itself (like a CI runner
    would), scans the clone, and deletes it afterwards.

    Args:
        git_url: a git URL Syft's environment can clone without extra
            credentials -- a public HTTPS URL (https://github.com/org/repo)
            or an SSH URL if this server's environment has a deploy key
            configured (none is configured by default in this lab).
        ref: branch, tag, or commit to check out. Defaults to the repo's
            default branch.
        fail_on: optional severity threshold passed to Grype.
    """
    workdir = tempfile.mkdtemp(prefix="sbom-mcp-git-")
    result: dict[str, Any] = tools.scan_git_repo(git_url, workdir, ref=ref, fail_on=fail_on)
    return json.dumps(result)


def _register_catalogue_tools() -> None:
    """Registered only when running in cluster mode -- these read from the
    Phase 3 Postgres catalogue, which is only reachable in-cluster."""

    @mcp.tool()
    def query_images_by_package(package_name: str) -> str:
        """Which tracked images contain a package matching this name, and at what severity.

        Answers the Phase 5 stretch goal directly: "which running images
        contain this package" against real, current cluster data -- not a
        fresh scan, the existing catalogue the runtime pipeline maintains.

        Args:
            package_name: package name to search for (substring match).
        """
        return json.dumps(catalogue.images_containing_package(package_name))

    @mcp.tool()
    def get_image_findings(repository: str, tag: str | None = None) -> str:
        """All current vulnerability findings for a specific tracked image.

        Args:
            repository: image repository (substring match), e.g. "grafana".
            tag: exact tag to narrow to, optional.
        """
        return json.dumps(catalogue.findings_for_image(repository, tag))

    @mcp.tool()
    def get_catalogue_summary() -> str:
        """Aggregate counts across the whole catalogue right now: images
        tracked, SBOMs stored, packages catalogued, total findings."""
        return json.dumps(catalogue.catalogue_summary())


def main() -> None:
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    mode = os.environ.get("MCP_MODE", "local")

    if mode == "cluster":
        _register_catalogue_tools()

    if transport == "streamable-http":
        mcp.run(
            transport="streamable-http",
            host=os.environ.get("MCP_HOST", "0.0.0.0"),
            port=int(os.environ.get("MCP_PORT", "8000")),
        )
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
