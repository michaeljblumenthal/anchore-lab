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
- [ ] Fail the build on a policy violation, then fix it, both documented.
  `vulnerable-demo` job is expected to fail on push (pinned to
  `pyjwt==1.7.1`, confirmed locally: 3 High findings via
  GHSA-ffqj-6fqr-9h24, GHSA-xgmm-8j9v-c9wx, GHSA-752w-5fwx-jx9f). Once the
  failing run is confirmed on GitHub Actions, a follow-up commit bumps the
  pin and the same job is confirmed passing. **Both run links will be
  recorded here once the workflow has actually executed on GitHub** — not
  claimed from local reasoning alone.
- [ ] SBOM published as a build artifact (per commit).
  `upload-artifact: true` default on sbom-action; `artifact-name` set
  explicitly per job so the two SBOMs (real project vs. demo fixture)
  don't collide in the same workflow run.
- [ ] Push build-time SBOMs into the Phase 3 catalogue, converging build-time
  and runtime inventories in one place. Not yet implemented — needs a step
  (or separate job) that pushes the generated SBOM into MinIO and inserts
  the corresponding `images`/`sboms` rows, reusing `phase3-inventory/jobs/`
  code rather than duplicating the insert logic. Tracked as remaining work.

## Findings

(populated once the workflow has run at least once on GitHub Actions)
