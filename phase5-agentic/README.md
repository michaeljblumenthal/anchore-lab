# Phase 5: Agentic interface — checklist

Status legend: `[x]` done and verified, `[ ]` not started, `[~]` in progress.

## Checklist

- [x] Install `anchore/grype-mcp` and connect it to an MCP-capable client.
  Two ways, both working: `install-grype-mcp.sh` for a host-side stdio
  install, and — see "In-cluster deployment" below — a real in-cluster
  deployment reached via `kubectl exec -i`, since the package hardcodes
  the stdio transport. `.mcp.json`'s `grype-mcp` entry currently points at
  the in-cluster connection (`connect-grype-mcp.sh`). Verified with a real
  MCP `initialize` + `tools/list` handshake in both modes: 9 tools
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
- [x] Stretch: expose the Phase 3 catalogue over MCP so "which running
  images contain this package" can be asked conversationally against real
  cluster data. Done as an in-cluster deployment of `sbom-mcp-server`
  itself, not a new server — see "In-cluster deployment" below.

## In-cluster deployment

Originally, both MCP servers ran only as host-side stdio subprocesses,
launched by Claude Code from `.mcp.json`. That's a real limit on the "this
whole solution deploys to any Kubernetes" claim the lab otherwise makes: an
MCP server that only exists as a venv next to wherever `kubectl` happens to
point isn't actually part of the deployable system, it's a client-side
convenience.

`sbom-mcp-server` now runs both ways from one codebase:

- **stdio** (unchanged): host-side, launched locally, full tool surface
  including local-filesystem targets (`dir:./path`) — meaningful here
  because the caller's own machine *is* the filesystem being scanned.
- **streamable-http, in-cluster** (`phase5-agentic/manifests/mcp-server.yaml`):
  a real Deployment + Service + Traefik Ingress at `mcp.lab.localhost`,
  reachable from the host over the network like every other service in
  this lab. Registry/image targets only — a `dir:` target has no meaning
  running as a pod, the pod's filesystem isn't the caller's laptop — and
  three new tools backed directly by the Phase 3 Postgres catalogue:
  `query_images_by_package`, `get_image_findings`, `get_catalogue_summary`.

Verified end to end, not just deployed: a real `tools/call` for
`get_catalogue_summary`, made from the host through
`http://mcp.lab.localhost:8080/mcp`, returned
`{"images_tracked": 19, "sboms_stored": 19, "total_packages": 5099, "total_findings": 2406}`
— live data, matching Phase 6's numbers exactly, reached over the network
rather than a local file. `query_images_by_package("stdlib")` returned the
same base-image-commonality data Phase 6 found by direct SQL, now
answerable conversationally against a running cluster.

`grype-mcp` (the third-party official Anchore server) runs in-cluster too,
but by a different mechanism, because its `server.py` hardcodes
`mcp.run(transport='stdio')` — confirmed by reading the installed
package's source — so unlike `sbom-mcp-server` it can't simply be told to
listen on HTTP without patching Anchore's own code, which is out of scope
here. Instead: `phase5-agentic/manifests/grype-mcp.yaml` deploys it as an
always-on pod (entrypoint `sleep infinity`, the actual `grype-mcp` process
started per-connection), and `connect-grype-mcp.sh` relays an MCP client's
stdio into that pod via `kubectl exec -i` — from the client's point of
view this is indistinguishable from a local stdio process; the bytes just
happen to be relayed through the Kubernetes API server into a pod instead
of a local fork. No Service or Ingress needed, `kubectl exec` talks to the
API server directly. Verified with the same `initialize`/`tools/list`
handshake used for the host-side install, all 9 tools present, running
against the pod on `agent-1`.

**Known gap, stated plainly rather than half-solved**: the in-cluster
endpoint has no authentication in front of it. Anyone who can reach
`mcp.lab.localhost` can call every tool, catalogue reads included. That's
an acceptable posture for a single-operator local lab and not for anything
beyond it. `MCPServer`'s constructor already accepts a `token_verifier`
for exactly this (see `sbom_mcp_server/server.py`), so the extension point
exists — building real auth (OAuth token verification, or an
authenticating proxy in front of the Ingress) is scoped out of this pass
deliberately, not overlooked. A real multi-tenant or internet-facing
deployment needs it before going any further than this lab's own cluster.

Also fixed along the way: `sbom-mcp-server`'s own `pyproject.toml` had the
same unpinned-`mcp`-dependency bug documented for `grype-mcp` below
(`mcp>=1.2.0`, no ceiling) — a fresh install had silently drifted to `mcp`
2.2.0, which broke the `FastMCP` import the same way. Migrated properly to
`mcp` 2.x's `MCPServer` API (not re-pinned backward) and pinned
`mcp>=2.0.0` explicitly, closing the same bug class for good rather than
patching around it a second time.

## Connecting to the in-cluster `sbom-scan` server

Prerequisite: the cluster is up (`make cluster`, then
`phase3-inventory/bootstrap.sh` — both MCP servers are now step 9/9 of
that script, not a separate deploy step; see the top-level README's
quickstart). Then, from any MCP-capable client on the same machine as the
cluster (the ingress hostname `mcp.lab.localhost` resolves to `127.0.0.1`
— see `phase2-cluster/README.md` for why that needs no `/etc/hosts` entry
on macOS), add this to the client's MCP config:

```json
{
  "mcpServers": {
    "sbom-scan-cluster": {
      "type": "http",
      "url": "http://mcp.lab.localhost:8080/mcp"
    }
  }
}
```

(Claude Code specifically: this is the `.mcp.json` shape for a remote
streamable-HTTP server — `type` also accepts `streamable-http` as an
alias, since that's the MCP spec's own name for the transport; an entry
with `url` but no `type` is read as stdio and will fail to connect.)

This repo's own root `.mcp.json` deliberately keeps `sbom-scan` pointed at
the **host-side stdio** binary instead — faster to start, and doesn't
require the cluster to be running just to work on this repo day to day.
The HTTP config above is what a *separate* client, on a different
project, or someone else entirely, would use to reach this same running
pipeline instead of installing anything locally. Verified working with
the config above against the live cluster: a `tools/call` for
`get_catalogue_summary` returned real data (see "In-cluster deployment"
above for the exact response).

`grype-mcp`'s in-cluster deployment has no equivalent HTTP config — it's
only reachable via `connect-grype-mcp.sh` (`kubectl exec`), which means a
client connecting to it needs `kubectl` access to this specific cluster,
not just network reachability. That's an inherent limit of the
exec-based approach, not an oversight: a genuinely remote MCP client
(not running `kubectl` against this cluster) cannot reach `grype-mcp`
in-cluster at all today, only `sbom-scan`'s HTTP endpoint.

## Connecting from Claude Desktop (a local app, not this repo's own client)

Claude Desktop's Settings → Connectors "Add custom connector" UI does
**not** work for this: that path sends the URL to Anthropic's cloud, and
the cloud (not your machine) opens the connection — so `mcp.lab.localhost`
is unreachable from it, same as it would be for any other localhost-only
address. This is not specific to this lab; it's how that UI is built.

The path that does work is editing the config file directly, which runs
entirely on your machine with no cloud round-trip, and bridging HTTP with
[`mcp-remote`](https://www.npmjs.com/package/mcp-remote) (an `npx`
package, no install step — confirmed working against this exact cluster
before writing this down):

1. Quit Claude Desktop if it's running.
2. Edit (or create)
   `~/Library/Application Support/Claude/claude_desktop_config.json`
   (macOS) and add:

   ```json
   {
     "mcpServers": {
       "anchore-lab-sbom-scan": {
         "command": "npx",
         "args": ["-y", "mcp-remote", "http://mcp.lab.localhost:8080/mcp", "--allow-http"]
       }
     }
   }
   ```

   (`--allow-http` is required: `mcp-remote` refuses plain HTTP by default
   for anything that isn't `localhost` itself, and `mcp.lab.localhost`,
   while it resolves to `127.0.0.1`, isn't the literal string
   `localhost`.)
3. Restart Claude Desktop. The five `sbom-scan` tools (plus the three
   catalogue tools, since this server is deployed in cluster mode) appear
   under the MCP tools menu.

Verified directly (not just documented from the package's own claims):
ran `npx -y mcp-remote http://mcp.lab.localhost:8080/mcp --allow-http`
by hand, piped a raw `initialize` request in, got a real response back
from `sbom-mcp-server` through the bridge before writing this section.

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
