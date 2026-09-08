# Phase 1: Toolchain baseline — checklist

Status legend: `[x]` done and verified, `[ ]` not started, `[~]` in progress.

## Setup

- [x] **Install Syft, Grype, Grant, kubectl, helm, k3d, k9s, Docker runtime.**
  Run `make toolchain` (wraps `install.sh`).
  Expect: version banners for all seven tools printed at the end, no errors.
  Verify: `syft version && grype version && grant version && docker info`
  all exit 0.
  - Deviation: Docker Desktop's cask postflight needs an interactive sudo
    prompt; used Colima instead. Grant's Homebrew tap needs a newer Xcode
    CLT; used Anchore's own `install.sh` script instead. Both documented in
    `docs/build-log/2026-09-08.md`.

## SBOM generation across target types

- [x] Generate an SBOM for a real application with a messy dependency tree.
  Target used: `phase5-agentic/sbom-mcp-server` itself (mcp SDK + 26
  transitive deps — cryptography, PyJWT, starlette/uvicorn, jsonschema).
  Command: `make mcp-server-scan TARGET=dir:.` (run from repo root; cds into
  the server dir).
  Result: 75 packages catalogued, 0 Grype matches, Grant report generated.
- [x] Generate an SBOM for a container image.
  Target: `python:3.12-slim` (pulled via Colima's Docker socket).
  Command: `syft scan docker:python:3.12-slim -o syft-json`.
  Result: 95 artifacts, 2.3s scan time (image already local).
- [x] Generate an SBOM for a source repository (git clone, not just a local dir).
  Target: `github.com/anchore/grype-mcp`, shallow clone into `repos/`.
  Command: `syft scan dir:repos/grype-mcp -o syft-json`.
  Result: only 5 artifacts (4 GitHub Actions, 1 python package entry) despite
  a `requirements.txt` naming 3 direct dependencies. **Finding below.**

## Format comparison

- [x] Generate SPDX, CycloneDX, and Syft-native JSON for the same artefact
  (`python:3.12-slim`). All three in `sboms/`.
- [x] Record where the three formats disagree and what each drops.
  - **File size is not a proxy for content.** cyclonedx-json (940KB) is a
    third the size of syft-json (2.8MB) despite reporting *more* top-level
    entries (2747 vs 95), because CycloneDX emits one `component` per
    catalogued *file* (2651 of them — path + hash, minimal metadata) in
    addition to 88 `library` components. Comparing "package count" across
    formats requires filtering CycloneDX by `type: library`/`application`
    first, or the numbers look wildly inconsistent when they aren't.
  - **spdx-json and syft-json agree on package identity** (95 vs 96, off by
    one because SPDX adds an explicit root package for the image itself).
    License data is present in both but under different fields — Syft's
    native format nests `licenses[].value`, SPDX splits `licenseDeclared`
    vs `licenseConcluded` (Syft only ever populates `licenseDeclared`,
    never asserts `concluded`). A same-package spot check (`adduser`)
    confirmed the data matches once you read the right field — first pass
    at this comparison wrongly concluded SPDX drops license info, which was
    a bug in the comparison script (reading `licenseConcluded` instead of
    `licenseDeclared`), not a real gap between formats. Worth flagging in
    the write-up as a reminder to verify field semantics before publishing
    a cross-format claim.

## Licence scan

- [x] Run Grant against a generated SBOM and read the compliance report.
  Finding: Grant's **default policy denies everything** — it has an empty
  allow-list, not an empty deny-list. A first run against a completely
  ordinary Python project (MIT/BSD-3-Clause packages) reports "noncompliant"
  for every package with a known licence. This is worth a callout in the
  write-up: it will surprise anyone trying Grant without first authoring a
  `grant.yaml` policy.

## VEX suppression

- [x] Produce a VEX document suppressing a finding present in the SBOM but
  not reachable in the running application.
  Target: `python:3.12-slim`'s `perl-base` package (5 Critical/High CVEs:
  CVE-2026-8376, -13221, -42496, -12087, -57433). Perl ships transitively
  via the debian:trixie base layer; nothing in this lab invokes it.
  Document: `vex/python-3.12-slim.openvex.json` (OpenVEX v0.2.0,
  `not_affected` / `vulnerable_code_not_in_execute_path`).
- [x] Confirm Grype respects it.
  `grype sbom:... --vex vex/python-3.12-slim.openvex.json` — match count
  187 → 182, all 5 perl-base CVEs moved into `ignoredMatches`. Critical
  count dropped 7 → 2. Confirms the plan's framing: the present/exploitable
  distinction is exactly what a 24-hour reporting clock needs, and VEX is
  how you encode the judgement so tooling enforces it instead of a human
  re-deciding it on every scan.
  - Gotcha worth recording: the VEX `products[].@id` purl must match
    Grype's *exact* purl for the package, including qualifiers
    (`?arch=arm64&distro=debian-13.6&upstream=perl`). A purl without those
    qualifiers silently matches nothing — Grype doesn't warn, the finding
    just doesn't get suppressed. Always pull the purl from a prior scan's
    JSON output rather than hand-constructing it.

## Metrics recorded for the write-up

- [x] Scan duration vs. artefact size/type:
  - `python:3.12-slim` image (local, cached): ~2.3s per format, 95 packages.
  - `sbom-mcp-server` installed venv (dir scan): ~1-2s, 75 packages.
  - `grype-mcp` git clone (dir scan, no installed env): <1s, 5 artifacts.
  Duration scales with what's actually on disk to walk, not nominally with
  "one target" — an installed venv with hundreds of files takes longer per
  package found than a lean source checkout, but a source checkout finds far
  fewer packages in the first place (see below).
- [x] What Syft missed: **installed vs. declared dependencies are not the
  same target.** Scanning `grype-mcp`'s git checkout directly
  (`dir:repos/grype-mcp`) found only 5 artifacts, even though
  `requirements.txt` names 3 direct dependencies (click, mcp, pytest) which
  themselves pull in a real transitive tree. Syft's `dir:` cataloguer reads
  manifest files it recognizes but does not resolve version ranges or walk
  an uninstalled dependency graph — there is no lockfile and no `site-packages`
  to walk. Compare: scanning `sbom-mcp-server`'s *installed* `.venv` found 75
  packages for a comparable manifest. **This is a real gap to flag in the
  write-up**: "scan the repo" and "scan what actually runs" give
  meaningfully different answers, and a CI pipeline that only scans source
  checkouts (Phase 4 territory) will under-report supply chain exposure
  unless it scans the built/installed artefact too.
- [x] What Grype flagged that was noise (candidate, not yet triaged in
  depth): the 45 "Negligible" severity matches on `python:3.12-slim` — worth
  a proper VEX/triage pass in Phase 6 rather than here, since Phase 1's job
  was proving the mechanism works, not fully triaging one image.

## Process findings (feed into Phase 7 write-up)

1. Grant's empty-allow-list default policy (above).
2. `install.sh`-installed binaries (grant) land in `~/bin`, which only
   resolves on PATH in interactive shells sourcing `~/.zshrc` — not for
   subprocess/CI/agent invocations. Fixed by symlinking into
   `/opt/homebrew/bin`. General lesson: verify PATH visibility from the
   actual invocation context (subprocess, cron, CI), not just an interactive
   terminal.
3. **Syft's `docker:` source does not read the active `docker context`.**
   With Colima (not Docker Desktop) as the runtime, `docker info` and
   `docker context ls` both correctly show `colima` as current and reachable,
   but `syft scan docker:<image>` failed with "docker not available" until
   `DOCKER_HOST` was exported explicitly to Colima's socket path
   (`unix://~/.colima/default/docker.sock`). Anyone running Syft against a
   non-Docker-Desktop runtime needs this exported, and it's easy to miss
   since every other Docker-aware tool in this session picked up the context
   fine. Baked into `install.sh`'s printed guidance — see next point.
4. **Installed-vs-declared dependency gap** (detailed above under Syft
   missed) — arguably the most important single Phase 1 finding, since it
   bears directly on how Phase 4's CI integration should be scoped: scanning
   the checked-out repo alone is not sufficient evidence of what a shipped
   artefact actually contains.
5. Cross-format comparisons need care: CycloneDX's file-level component
   inflation and SPDX's declared/concluded license split both look like
   "missing data" bugs at first glance and are actually correct,
   spec-conformant behaviour once you read the right field. Caught this
   before writing it up as a false finding — worth stating as a process
   lesson on its own: verify a suspicious cross-tool discrepancy against the
   spec before reporting it as a gap.
