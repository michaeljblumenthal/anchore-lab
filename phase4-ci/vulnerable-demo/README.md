# vulnerable-demo

A single-file fixture, not a real project. Its only purpose is to give the
Phase 4 CI workflow a genuine, reproducible policy violation to fail on and
then fix — the plan asks specifically for both states to be documented, and
the real `sbom-mcp-server` project's dependencies are clean (0 Grype
findings as of this build), so there was nothing legitimate to fail on
there.

`requirements.txt` originally pinned `pyjwt==1.7.1`, which Grype reliably
flags with 3 High-severity findings (GHSA-ffqj-6fqr-9h24,
GHSA-xgmm-8j9v-c9wx, GHSA-752w-5fwx-jx9f — confirmed locally before wiring
into CI). The `vulnerable-demo` CI job in
`.github/workflows/sbom-scan.yml` scans this directory with
`severity-cutoff: high`, and did fail on that commit — see
`phase4-ci/README.md` for the run link.

The pin is now `pyjwt==2.13.0` (current latest, 0 findings, confirmed
locally before pushing), and the same job now passes — see
`phase4-ci/README.md` for that run link too. Both states are real,
recorded GitHub Actions runs, not local reasoning about what would happen.
