# Phase 5: Agentic interface — checklist

Status legend: `[x]` done and verified, `[ ]` not started, `[~]` in progress.

## Checklist

- [x] Install `anchore/grype-mcp` and connect it to an MCP-capable client.
  `install-grype-mcp.sh`, wired into `.mcp.json` as `grype-mcp`. Verified
  with a real MCP `initialize` + `tools/list` handshake (no client
  required — piped raw JSON-RPC into the process over stdio): 9 tools
  (`find_grype`, `update_grype`, `scan_dir`, `scan_purl`, `scan_image`,
  `search_vulns`, `get_vuln_details`, `get_db_info`, `update_db`).
- [x] `sbom-mcp-server` (this repo's own MCP server, built in Phase 1 —
  see `sbom-mcp-server/README.md`) — a broader complement to grype-mcp:
  orchestrates Syft -> Grype -> Grant as one pipeline, where grype-mcp is
  Grype-only but has a richer standalone query surface (`scan_purl`,
  `search_vulns`, `get_vuln_details` — CVE lookups sbom-mcp-server
  doesn't offer). Both wired into `.mcp.json`, complementary rather than
  redundant.
- [x] Pre-push gate: SBOM generation and scanning run before anything
  reaches the remote, driven from the project's git configuration.
  `pre-push-gate.sh` + `install-pre-push-gate.sh` (installs a real
  `.git/hooks/pre-push` hook, not just a script that has to be remembered).
  Policy: blocks the push only on Critical-severity findings; High/Medium/Low
  are reported but don't block (see rationale below). Verified running
  locally: 83 packages, 0 findings against `sbom-mcp-server`'s current
  state.
- [~] Stretch: expose the Phase 3 catalogue over MCP so "which running
  images contain this package" can be asked conversationally against real
  cluster data. Not started — natural follow-on to `sbom-mcp-server`
  (add a `query_catalogue` tool backed by the same Postgres the runtime
  pipeline already writes to) rather than a new server.

## Findings

1. **`anchore/grype-mcp` 0.4.0, as published, doesn't run against a fresh
   `pip install`.** Its own dependency declaration is unpinned
   (`Requires: mcp`, no version ceiling), so a plain
   `pip install grype-mcp` pulls the latest `mcp` SDK (2.2.0 at the time of
   this build) and crashes on import:
   `ModuleNotFoundError: No module named 'mcp.server.fastmcp'`. `FastMCP`
   was renamed to `MCPServer` in `mcp` 2.x, and `grype-mcp`'s `server.py`
   still imports the old path — a real upstream packaging gap, not a local
   environment issue. The error message itself names the fix
   (`pin 'mcp<2'`); confirmed working with `mcp==1.30.0` pinned
   afterward — real MCP `initialize`/`tools/list` handshake succeeded.
   Baked the pin into `install-grype-mcp.sh` rather than leaving it as a
   one-off manual fix. **Worth flagging in the write-up**: anyone following
   the plan's own "pip install grype-mcp, connect it" instructions verbatim
   today would hit this immediately, with no indication from the install
   step itself about why.
2. **Pre-push gate policy: block on Critical only, not High.** Considered
   matching the CI workflow's `severity-cutoff: high` (Phase 4) exactly,
   and deliberately didn't. A client-side hook that's too strict trains
   people to reach for `git push --no-verify`, which defeats the entire
   point of having the gate — the loosest useful threshold that still
   catches something real (Critical) is more valuable in practice than a
   stricter one that gets routinely bypassed. CI, which nothing can skip
   with a local flag, is where the stricter cutoff actually belongs. This
   is a real judgment call worth stating explicitly rather than silently
   picking a number.
