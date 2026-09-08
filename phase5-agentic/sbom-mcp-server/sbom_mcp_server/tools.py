"""Subprocess wrappers around syft, grype and grant.

Each function shells out to the corresponding Anchore CLI and returns parsed
JSON. Binaries are resolved from PATH so this works with any local install
(Homebrew, the install.sh scripts, whatever) rather than a pinned location.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from sbom_mcp_server.git_clone import cloned_repo


class ToolNotFoundError(RuntimeError):
    pass


class ToolExecutionError(RuntimeError):
    def __init__(self, tool: str, returncode: int, stderr: str):
        self.tool = tool
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"{tool} exited {returncode}: {stderr.strip()[:2000]}")


def _require(binary: str) -> str:
    path = shutil.which(binary)
    if not path:
        raise ToolNotFoundError(
            f"'{binary}' not found on PATH. Install it and retry "
            f"(see https://oss.anchore.com/docs/projects/)."
        )
    return path


def _run(binary: str, args: list[str], timeout: int = 600) -> str:
    exe = _require(binary)
    proc = subprocess.run(
        [exe, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode not in (0, 1):
        # syft/grype/grant use 1 for "findings present" in some modes, not
        # only real failure; treat anything else as a hard error.
        raise ToolExecutionError(binary, proc.returncode, proc.stderr)
    return proc.stdout


def generate_sbom(target: str, output_format: str = "syft-json") -> dict[str, Any]:
    """Run syft against a target (image ref, dir path, or archive).

    output_format: one of syft-json, spdx-json, cyclonedx-json.
    """
    stdout = _run("syft", ["scan", target, "-o", output_format])
    return json.loads(stdout)


def scan_sbom(sbom_path: str, fail_on: str | None = None) -> dict[str, Any]:
    """Run grype against a previously generated SBOM file."""
    args = [f"sbom:{sbom_path}", "-o", "json"]
    if fail_on:
        args += ["--fail-on", fail_on]
    stdout = _run("grype", args)
    return json.loads(stdout)


def scan_target_direct(target: str, fail_on: str | None = None) -> dict[str, Any]:
    """Run grype directly against a target without a separate SBOM step."""
    args = [target, "-o", "json"]
    if fail_on:
        args += ["--fail-on", fail_on]
    stdout = _run("grype", args)
    return json.loads(stdout)


def check_licenses(sbom_path: str) -> dict[str, Any]:
    """Run grant against a generated SBOM file, requesting JSON output."""
    stdout = _run("grant", ["check", sbom_path, "-o", "json"])
    return json.loads(stdout)


def full_scan(target: str, workdir: str, fail_on: str | None = None) -> dict[str, Any]:
    """Chain syft -> grype -> grant against a single target.

    Writes the intermediate SBOM to <workdir>/<safe-name>.sbom.json so the
    same artefact is reused for both the vulnerability and licence passes,
    matching the "SBOM is the unit of work" principle from the lab plan.
    """
    out_dir = Path(workdir)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c if c.isalnum() else "_" for c in target).strip("_") or "target"
    sbom_path = out_dir / f"{safe_name}.sbom.json"

    sbom = generate_sbom(target, output_format="syft-json")
    sbom_path.write_text(json.dumps(sbom))

    vulns = scan_sbom(str(sbom_path), fail_on=fail_on)

    try:
        licenses = check_licenses(str(sbom_path))
        license_error = None
    except (ToolNotFoundError, ToolExecutionError) as exc:
        licenses = None
        license_error = str(exc)

    return {
        "target": target,
        "sbom_path": str(sbom_path),
        "package_count": len(sbom.get("artifacts", [])),
        "vulnerabilities": vulns,
        "licenses": licenses,
        "license_error": license_error,
    }


def scan_git_repo(
    git_url: str, workdir: str, ref: str | None = None, fail_on: str | None = None
) -> dict[str, Any]:
    """Clone a public git repo and run the full Syft -> Grype -> Grant pipeline
    against it.

    This is the fully-containerized "scan a repo" path: unlike full_scan's
    `dir:` targets, which only work when the caller and the server share a
    filesystem (the host-side stdio server), this clones the repo itself --
    so it works identically whether the server is running on a laptop or in
    a Kubernetes pod with no access to anyone's local filesystem. The
    clone is temporary and deleted after the scan; nothing about the
    repo's contents persists beyond the SBOM the scan produces.
    """
    with cloned_repo(git_url, ref=ref) as repo_path:
        result = full_scan(f"dir:{repo_path}", workdir, fail_on=fail_on)
    result["git_url"] = git_url
    result["ref"] = ref
    return result
