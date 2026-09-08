# anchore-lab

A hands-on lab reconstructing continuous, SBOM-based vulnerability
management on Kubernetes using Anchore's open source tooling (Syft, Grype,
Grant), built from scratch to find out what the approach costs and where it
breaks.

See [anchore-lab-plan.md](anchore-lab-plan.md) for the full plan and
motivation, and `docs/build-log/` for a day-by-day account of what was
built, what broke, and how it was fixed — kept from the first command, not
written up after the fact.

## Status

- **Phase 1 — Toolchain baseline**: complete. See
  [phase1-toolchain/README.md](phase1-toolchain/README.md).
- **Phase 2 — Kubernetes cluster**: complete. See
  [phase2-cluster/README.md](phase2-cluster/README.md).
- **Phase 3 — Continuous inventory**: core pipeline complete and measured.
  See [phase3-inventory/README.md](phase3-inventory/README.md).
- **Phase 4 — CI integration**: complete. See
  [phase4-ci/README.md](phase4-ci/README.md).
- **Phase 5 — Agentic interface**: complete. See
  [phase5-agentic/README.md](phase5-agentic/README.md).
- **Phase 6 — Turn the system on itself**: not started.

## Quickstart

```sh
make toolchain      # install syft, grype, grant, docker(colima), kubectl, helm, k3d, k9s
make cluster         # bring up the k3d cluster
cd phase3-inventory && ./bootstrap.sh   # registry, storage, catalogue, jobs, admission control, dashboard
```

`make help` lists all available targets.

## Repository layout

- `phase1-toolchain/` — Syft/Grype/Grant install, format comparison, VEX
  suppression exercise.
- `phase2-cluster/` — k3d cluster bootstrap: multi-node, storage class,
  ingress, namespaces, RBAC.
- `phase3-inventory/` — the substance of the lab: registry, runtime
  inventory, SBOM generation/storage, continuous re-matching, admission
  control, dashboard.
- `phase4-ci/` — GitHub Actions integration.
- `phase5-agentic/` — an MCP server exposing Syft/Grype/Grant as tools for
  any MCP client.
- `phase6-self-scan/` — the lab pointed at itself.
- `docs/build-log/` — the honest, chronological account of the build.
- `docs/decisions/` — ADRs for non-trivial process/architecture decisions.

## A note on the lab defaults

Manifests in this repo contain plaintext default credentials (e.g.
`Harbor12345`-style lab passwords for MinIO/Postgres/Grafana). These are
intentional, local-only lab defaults for a cluster that never leaves
`127.0.0.1` — not a security posture recommendation, and not reused
anywhere outside this lab.

## Scope

This is a lab, not a production system. It is deliberately open source
only — no Anchore Enterprise license was used — because that is the path
Anchore's actual customers take before ever evaluating the commercial
product. The build log records every place a self-assembled open source
stack strained or broke, since that is the actual point of the exercise.
