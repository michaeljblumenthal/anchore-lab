# sbom-mcp-server

An MCP server that lets any MCP-capable client (Claude Code, Claude Desktop,
etc.) run Anchore's open source scanning pipeline — Syft, then Grype, then
Grant — against an arbitrary target, conversationally.

This is Phase 5 of the lab (agentic interface), but it also doubles as the
Phase 1 "real application with a messy dependency tree" target: its own
`pyproject.toml` pulls in the `mcp` SDK plus a real transitive tree (jsonschema,
cryptography, httpx-style HTTP stacks, JWT, starlette/uvicorn for the SSE
transport). See `requirements-freeze.txt` for the resolved set.

## Tools exposed

- `generate_sbom(target, output_format)` — Syft. Formats: `syft-json`,
  `spdx-json`, `cyclonedx-json`.
- `scan_vulnerabilities(sbom_path, fail_on)` — Grype against a Syft SBOM file.
- `scan_target(target, fail_on)` — Grype directly against an image/dir, no
  separate SBOM step.
- `check_licenses(sbom_path)` — Grant against a Syft SBOM file.
- `full_scan(target, fail_on)` — chains all three: generates the SBOM once,
  writes it to a temp workdir, then reuses that single artefact for both the
  Grype and Grant passes. This mirrors the lab's "the SBOM is the unit of
  work" principle rather than re-pulling/re-analysing the target per tool.

All three underlying binaries (`syft`, `grype`, `grant`) are resolved from
`PATH` at call time — no hardcoded install location.

## Install

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run standalone (stdio transport)

```sh
source .venv/bin/activate
sbom-mcp-server
```

## Connect from Claude Code

Add to your MCP config:

```json
{
  "mcpServers": {
    "sbom-scan": {
      "command": "/absolute/path/to/.venv/bin/sbom-mcp-server"
    }
  }
}
```

Then ask things like "run a full scan on this repo" or "which licences does
this project pull in".

## Known findings from building this

- **Grant's default policy is empty-allow, not empty-deny.** With no policy
  file, `grant check` denies every package because nothing is on the allow
  list — including permissive licences like BSD-3-Clause and MIT. This reads
  as "everything is noncompliant" on a first run, which is misleading until
  you realise you need to author a policy (`grant.yaml`) that explicitly
  allows the licence families you accept. Worth calling out to anyone trying
  Grant for the first time expecting an opinionated default.
- **PATH resolution matters more than it looks.** `grant` installed via
  Anchore's `install.sh` script landed in `~/bin`, which is only on PATH for
  interactive shells that source `~/.zshrc` — not for subprocess/agent
  invocations. Symlinked into `/opt/homebrew/bin` (already first on PATH via
  Homebrew) to fix it. Any MCP client or CI runner that inherits a minimal
  PATH will hit the same problem with a script-installed binary.
