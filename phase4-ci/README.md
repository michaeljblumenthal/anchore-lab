# Phase 4: CI integration — checklist

Status legend: `[x]` done and verified, `[ ]` not started, `[~]` in progress.

Workflow: `.github/workflows/sbom-scan.yml`, runs on push/PR to `main` and
on manual dispatch. Two jobs:
- `sbom-and-scan` — the real target: generates an SBOM for
  `phase5-agentic/sbom-mcp-server` (a genuine Python project with a real
  dependency tree — mcp SDK, cryptography, PyJWT, starlette/uvicorn) and
  scans it with Grype, `severity-cutoff: high`.
- `vulnerable-demo` — see `vulnerable-demo/README.md`: a small fixture
  pinned to a known-vulnerable dependency, kept separate because the real
  project's dependencies are clean and there was nothing legitimate to fail
  on there.

## Verified input names against upstream (per the plan's own principle)

Fetched `action.yml` directly from `anchore/sbom-action` and
`anchore/scan-action` on `main` rather than assuming from memory or an old
example — the action is `anchore/sbom-action`, not `anchore/syft-action` as
the plan's own prose suggested (the plan describes it as "syft-action" in
one place; the actual GitHub Marketplace name is `sbom-action`). Confirmed
current inputs: `path`/`file`/`image` (mutually exclusive), `format`,
`artifact-name`, `output-file` for sbom-action; `sbom`/`image`/`path`
(mutually exclusive), `fail-build`, `severity-cutoff`, `output-format`,
`vex` for scan-action.

## Checklist

- [x] `syft-action`/`scan-action` (actually `anchore/sbom-action` +
  `anchore/scan-action` — see above) wired into a real workflow.
- [x] Fail the build on a policy violation, then fix it, both documented,
  both real GitHub Actions runs:
  - **Failing run** (commit `59468bc`, `pyjwt==1.7.1`, 3 High findings —
    GHSA-ffqj-6fqr-9h24, GHSA-xgmm-8j9v-c9wx, GHSA-752w-5fwx-jx9f):
    https://github.com/michaeljblumenthal/anchore-lab/actions/runs/34225517136/job/102058554770
  - **Fixed, passing run** (commit `678c77a`, bumped to `pyjwt==2.13.0`, 0
    findings, confirmed locally before pushing):
    https://github.com/michaeljblumenthal/anchore-lab/actions/runs/34225696387
  - The real project's own job (`sbom-and-scan`) passed on both runs — it
    was never the thing under test, `vulnerable-demo` was.
- [x] SBOM published as a build artifact (per commit).
  `upload-artifact: true` default on sbom-action; `artifact-name` set
  explicitly per job so the two SBOMs (real project vs. demo fixture)
  don't collide in the same workflow run. Confirmed present on run
  34225517136: `sbom-mcp-server.spdx.json`, `vulnerable-demo.spdx.json`.
- [x] Push build-time SBOMs into the Phase 3 catalogue, converging build-time
  and runtime inventories in one place.
  `phase4-ci/push-sbom-to-catalogue.py` reuses the Phase 3 schema/insert
  pattern (not duplicated — same `images`/`sboms` tables, a `syft-build.json`
  MinIO key rather than `syft.json` so build-time and runtime SBOMs for the
  same image don't collide). **Verified locally** via `kubectl port-forward`
  to the cluster's Postgres/MinIO: pushed a build-time SBOM for
  `sbom-mcp-server` at commit `678c77a`, 76 packages, `image_id=48` —
  visible in the same catalogue the runtime pipeline writes to.
  **Not wired into the actual GitHub-hosted workflow run** — see the
  finding below for why, and what a real deployment would need instead.

## Findings

1. **The plan's own prose names the wrong GitHub Action.** It says
   "syft-action" — the actual Marketplace/GitHub name is
   `anchore/sbom-action`. Confirmed by fetching `action.yml` directly from
   both `anchore/sbom-action` and `anchore/scan-action` on `main` rather
   than trusting the plan's wording or a search summary — exactly the
   plan's own stated principle ("verify command syntax and configuration
   against current upstream documentation before running anything").
2. **The real project had nothing to legitimately fail CI on.**
   `sbom-mcp-server`'s actual dependency tree is clean (0 Grype findings).
   Rather than force an artificial failure into the real project's history,
   built a separate, clearly-labeled `vulnerable-demo` fixture — a decision
   worth stating plainly rather than quietly picking whichever project
   happened to have a vulnerability to point at.
3. **A GitHub-hosted CI runner cannot reach a laptop-local Kubernetes
   cluster — the "push build-time SBOMs into the catalogue" step is
   necessarily a local-only demonstration in this lab, not something the
   pushed workflow actually does.** `push-sbom-to-catalogue.py` works and
   is verified end-to-end via a port-forward from this machine, but
   `.github/workflows/sbom-scan.yml` does not call it, because `catalogue-db-postgresql`
   and `minio` only exist inside k3d, on `127.0.0.1`, on this specific Mac.
   This is an honest architectural limit of a lab that runs entirely
   locally, not a shortcut taken to save time: a real deployment would need
   either a cloud-reachable catalogue (defeating "the whole thing is
   self-hosted, local, and free") or a self-hosted GitHub Actions runner
   inside the same network as the cluster. Worth stating explicitly in the
   Phase 7 write-up as one of the differences between a lab and a
   production system the plan itself asks to be honest about.
