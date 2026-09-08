# Bootstrap ordering, exemptions, and where trust has to start

The plan asks this to be documented honestly: admission control cannot
gate the admission controller into existence, and the inventory job cannot
scan the storage layer it depends on before that layer is running. This
lab's actual dependency chain, traced end to end:

## The real chain

1. **k3s itself** (server + agent nodes, containerd, CoreDNS,
   local-path-provisioner, Traefik, metrics-server) — installed by k3d
   before any of this repo's own manifests are applied. Nothing in this
   repo scans or gates these until after they're already running and
   serving the cluster that everything else depends on. This is the
   deepest exemption: the platform this lab's tooling runs *on* is
   necessarily trusted before the tooling can say anything about it.
2. **Namespaces + RBAC** (`phase2-cluster/manifests/`) — no scanning
   dependency, pure Kubernetes objects.
3. **Zot (registry)** — the first thing genuinely gated by
   `phase2-cluster/registries.yaml`'s config, but that config exists to let
   containerd pull *from* Zot, not to police what Zot itself is. Zot's own
   image is pulled from ghcr.io before Zot exists to scan anything, and
   before Kyverno exists to admission-check it.
4. **MinIO, Postgres, the catalogue schema** — depend on Zot only in that
   later self-scan pulls their images through it; their initial install
   pulls from Docker Hub/bitnamilegacy directly, same as Zot.
5. **The runtime-inventory CronJob** — the first component that can
   actually see and record what's running, but by the time it runs, steps
   1-4 are already live and already trusted. It scans the cluster
   *including itself*, after the fact.
6. **sbom-generate / sbom-rescan** — depend on the catalogue (step 4) and
   the registry (step 3) both being up. Cannot run first.
7. **Kyverno (admission control)** — the actual gate. But Kyverno's own
   four controller pods are pulled and scheduled *before* Kyverno exists
   to validate them — an admission controller cannot admission-control its
   own installation. Confirmed directly: Kyverno's audit-mode
   PolicyReports only start appearing *after* `kubectl apply` of both
   Kyverno itself and the ClusterPolicies (see phase3-inventory/README.md's
   "Self-compliance" section) — there is no report for Kyverno's own pods
   at all, since nothing was watching yet when they were admitted.
8. **Grafana** — purely a consumer, no ordering constraint of its own.

## Where trust has to start

There is no version of this stack where step 0 is scanned before it runs —
something has to be trusted first, unconditionally, for anything after it
to exist at all. In this lab that's the k3d/k3s node images and the Zot/
MinIO/Postgres images pulled to bootstrap the catalogue that later scans
everything else, Kyverno included. This is not a flaw specific to this
build; it is a structural property of any admission-control or
scan-before-run system: the control plane that enforces policy is itself
unenforced at the moment of its own installation. The honest statement for
the write-up is naming this precisely, not claiming the system scans "everything."

## Practical consequence

Because of this ordering, the aggregate report in
`aggregate-report.sh` necessarily includes components that were running
*before* Kyverno's policies existed to flag them, and the "images tracked
but never SBOM'd" query in that same script is the direct, queryable
signature of this gap — anything caught in that state either hasn't had a
sbom-generate cycle reach it yet, or (for a few unavoidable cases) never
will, because it stopped running before a cycle got to it.
