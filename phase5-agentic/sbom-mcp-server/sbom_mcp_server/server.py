"""MCP server exposing syft/grype/grant as tools for any MCP client.

Usage (stdio transport, e.g. from Claude Code's MCP config):

    sbom-mcp-server

or during development:

    python -m sbom_mcp_server.server
"""

from __future__ import annotations

import json
import tempfile
from typing import Any

from mcp.server.fastmcp import FastMCP

from sbom_mcp_server import tools

mcp = FastMCP("sbom-mcp-server")


@mcp.tool()
def generate_sbom(target: str, output_format: str = "syft-json") -> str:
    """Generate an SBOM for a target with Syft.

    Args:
        target: image reference (docker:name:tag), directory path (dir:./path),
            or a bare path/image ref (syft infers the scheme).
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
        target: image reference, directory (prefix with dir:), or archive.
        fail_on: optional severity threshold passed to Grype.
    """
    workdir = tempfile.mkdtemp(prefix="sbom-mcp-")
    result: dict[str, Any] = tools.full_scan(target, workdir, fail_on=fail_on)
    return json.dumps(result)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
