# ADR 0001: How the lab's build process is tracked and made repeatable

Date: 2026-09-08
Status: Accepted

## Context

The lab's stated purpose is to produce evidence of hands-on platform
engineering, not just a working end state. That means the *process* needs to
survive independently of this conversation and of any one machine: someone
(including future me, on a clean laptop) should be able to rebuild the lab
and see the same decisions and the same dead ends.

Three candidate mechanisms were built and exercised against real state:

1. **Per-phase shell scripts** (`phase1-toolchain/install.sh`) — idempotent,
   re-runnable, does the actual work.
2. **A root Makefile** — `make toolchain`, `make mcp-server`,
   `make mcp-server-scan` — a single discoverable entrypoint wrapping the
   scripts.
3. **Per-phase checklist READMEs** (`phase1-toolchain/README.md`) — literal
   checklist of commands, expected output, and verification steps, readable
   without running anything.

## Decision

**Use all three, layered, not as alternatives:**

- The **script** is the source of truth for what actually happens. It is
  idempotent and does real work.
- The **Makefile** is the entrypoint a human (or CI) actually types. It
  should never contain logic beyond "cd here, run that" — any real logic
  belongs in the script or the Python package, not the Makefile.
- The **checklist README** is the audit trail: plan-item-by-plan-item status,
  with the *why* behind every deviation from the plan (e.g. Colima instead of
  Docker Desktop, Anchore's install.sh instead of the Homebrew tap for
  Grant), plus a running "process findings" section that feeds Phase 7
  directly.

Rejected: picking only one.
- Script-only fails the "readable without running anything" requirement —
  nobody reviewing the repo (Lester, or future me) wants to read bash to find
  out what's done.
- Makefile-only is not idempotent or self-documenting on its own; it's a thin
  wrapper and needs something underneath it anyway.
- Checklist-only is not enforceable — a checklist can silently drift from
  reality if nothing actually re-runs the commands it claims work.

The overhead of maintaining three artefacts per phase is real but small: the
checklist is largely a by-product of the build log narrative, and the
Makefile target is usually one line per script.

## Consequence

Every future phase (2 through 6) gets the same three-part structure:
`phaseN-*/setup.sh` (or equivalent), a `make <phase>` target, and a
`phaseN-*/README.md` checklist. The build log
(`docs/build-log/YYYY-MM-DD.md`) stays as the narrative/timestamped account
of what happened in what order and why — it is not replaced by any of the
above, it's the fourth layer: the *story*, where the checklist is the
*status*.
