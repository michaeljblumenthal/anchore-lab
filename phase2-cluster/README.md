# Phase 2: Kubernetes cluster — checklist

Status legend: `[x]` done and verified, `[ ]` not started, `[~]` in progress.

## Cluster

- [x] Multiple nodes, real scheduling/affinity.
  `k3d cluster create anchore-lab --servers 1 --agents 2` — 1 control-plane
  + 2 agent nodes, all as Docker containers inside the Colima VM.
  1 server rather than 3: k3d/k3s's embedded sqlite datastore doesn't do HA
  below 3 servers without extra flags, and HA isn't the thing this lab is
  testing — 2 agents is enough for scheduling to be real.
  Command: `make cluster` (wraps `bootstrap.sh`).
  Verify: `kubectl get nodes -o wide` shows 3 Ready nodes.
- [x] Configured storage class, PVCs confirmed bound.
  k3d ships `local-path` (rancher.io/local-path) as default. Confirmed with
  a throwaway PVC + consuming pod (see finding #1 below for why the pod is
  required in the test).
- [x] Ingress controller with a real hostname resolving.
  Kept k3d's default Traefik (ADR: no reason to add ingress-nginx's extra
  moving parts when Traefik already ships wired to k3d's load balancer).
  Test target: `traefik/whoami` behind `lab.localhost`, k3d LB mapped to
  host ports 8080/8443.
  Verify: `curl http://lab.localhost:8080/` returns the whoami response
  with `Host: lab.localhost` in the echoed request — **no /etc/hosts entry
  needed**, see finding #2.
- [x] Namespaces, RBAC, dedicated service accounts. Nothing as cluster-admin.
  `anchore-lab` (workloads) and `anchore-lab-system` (reserved for Phase 3's
  platform services — Harbor, MinIO, Postgres, catalogue jobs).
  `lab-workload` ServiceAccount + namespaced Role (not ClusterRole) scoped to
  read pods/services/configmaps/PVCs and create jobs/cronjobs — nothing
  broader granted ahead of actually needing it.
- [x] Tooling: kubectl, helm, k9s installed (Phase 1). k9s not yet driven
  interactively in this session — noted as a to-do for hands-on cluster
  inspection during Phase 3 build/debug work.

## Deliberate breakage (plan requirement: record real diagnoses)

1. **PVC stuck `Pending` — misconfigured test, not a broken storage class.**
   First attempt applied a bare PVC with no consuming pod and waited for
   `Bound`. It never binds: `local-path`'s `VolumeBindingMode` is
   `WaitForFirstConsumer`, so the provisioner correctly waits until it knows
   which node the volume needs to be local to before creating anything.
   `kubectl describe pvc` showed exactly this in the Events
   (`WaitForFirstConsumer: waiting for first consumer to be created before
   binding`) — the diagnosis was immediate once looked at, the bug was in
   the test's assumption, not the cluster. Fixed by adding a pod that
   mounts the PVC; bound within ~2s of the pod scheduling.
2. **Ingress "hostname resolving" needed zero DNS setup on macOS.**
   Expected to need an `/etc/hosts` entry for `lab.localhost`, and wrote the
   bootstrap script assuming that. It turned out `curl http://lab.localhost/`
   resolves without one — macOS's resolver treats the entire `.localhost`
   TLD as `127.0.0.1` per RFC 6761, handled by the OS, not by any config in
   this repo. Confirmed via `dscacheutil` and a real `ping`. Corrected the
   script's echoed guidance, which originally claimed a hosts-file edit was
   required. On Linux this may not hold (depends on nss/systemd-resolved
   config) — worth a footnote if this lab is ever rebuilt off macOS.
3. **A missing Secret does not produce `CrashLoopBackOff`.**
   The plan names `CrashLoopBackOff` from a malformed secret as an example
   diagnosis exercise. Reproducing it literally (pod referencing a
   non-existent `Secret` via `envFrom.secretRef`) instead produces
   `CreateContainerConfigError` — the kubelet refuses to even start the
   container because it cannot resolve the env source, so there is no
   process to crash and no restart loop. `CrashLoopBackOff` specifically
   means the container **did** start and then exited nonzero repeatedly.
   Reproduced that separately with `sh -c "sleep 2; exit 1"` under
   `restart: Always`, confirmed via `kubectl describe pod` showing repeated
   `Started` → `BackOff: Back-off restarting failed container` events and a
   climbing restart count. **Practical takeaway for the write-up**: these
   are two distinct, commonly conflated failure modes with different root
   causes and different fixes (fix the Secret reference vs. fix what's
   inside the container) — a customer support engineer needs to
   distinguish `CreateContainerConfigError` from `CrashLoopBackOff` at a
   glance, not diagnose both as "the pod is broken."

4. **k3d's serverlb container intermittently fails to boot — confd can't
   find its own generated config file.** Roughly half the `k3d cluster
   create` runs in this session (both with and without `--registry-config`,
   so it isn't specific to that flag) left
   `k3d-<cluster>-serverlb` stuck in Docker state `Created` (never
   `Up`), with its logs showing `confd: FATAL stat /etc/confd/values.yaml:
   no such file or directory` in a tight retry loop — the container that's
   supposed to generate that file never gets far enough to write it.
   `docker start` on the stuck container doesn't recover it (retries the
   same failure). The only reliable fix found: `k3d cluster delete` +
   `k3d cluster create` again — no code or config change, just retrying.
   This looks like a race in k3d's own LB bootstrap sequence, not anything
   under this repo's control. Practical takeaway: `k3d cluster create
   --wait` can report success (or the whole cluster can otherwise look
   healthy — server/agents Ready) while the loadbalancer, which owns all of
   port 80/443 ingress traffic, is silently dead — always verify
   `docker ps` shows the serverlb container `Up`, not just that
   `kubectl get nodes` returns Ready, before trusting a fresh cluster.

## Notes for later phases

- `anchore-lab-system` namespace exists but is empty — Phase 3 platform
  services land there.
- `lab-workload` ServiceAccount's Role currently only grants namespaced
  access. Phase 3's runtime-inventory CronJob will need to *list images
  running across the whole cluster*, which requires a ClusterRole — add it
  then, scoped to exactly what that job reads (pods, not secrets), not
  broadened speculatively now.
