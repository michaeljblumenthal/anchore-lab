# Phase 3: Continuous inventory — checklist

Status legend: `[x]` done and verified, `[ ]` not started, `[~]` in progress.

## Registry

- [x] Registry, self-hosted in cluster, with images pushed to it.
  **Deviation from the plan: Zot, not Harbor.** See finding #1.
  Command: `make phase3` (in progress) / manually:
  `helm upgrade --install zot zot/zot -n anchore-lab-system --values helm-values/zot.yaml`
  Push: `./push-to-registry.sh <local-image> [remote-repo:tag]` — see finding #2
  for why this isn't a plain `docker push`.
  Verified: pushed `python:3.12-slim` to `zot.lab.localhost:8080/lab/python:3.12-slim`,
  confirmed present via `/v2/_catalog` and `/v2/lab/python/tags/list`.

## Findings

1. **Harbor doesn't run on Apple Silicon without real engineering effort —
   this is a substantial, unplanned finding in its own right.**
   The plan names Harbor as the registry. Its official images
   (`goharbor/harbor-core` at minimum) are amd64-only — no arm64 manifest
   published — and crash with a Go nil-pointer panic
   (`invalid memory address or nil pointer dereference` deep in
   `encoding/gob` decoding an embedded OpenAPI spec, during
   `RegisterRoutes()`) when run emulated via QEMU on an arm64 k3d node.
   Confirmed via `docker manifest inspect` (single-manifest, arch: amd64)
   and `docker image inspect --format '{{.Architecture}}'`.
   Attempted fix: force the whole k3d cluster to run as amd64
   (`DOCKER_DEFAULT_PLATFORM=linux/amd64`, plus `colima --vz-rosetta` for
   accelerated emulation). This **did not work** — k3d has no `--platform`
   flag and does not honour `DOCKER_DEFAULT_PLATFORM` when creating node
   containers (verified: nodes came up arm64 regardless). Forcing amd64
   properly would need per-pod `runtimeClass`/containerd platform
   configuration inside every k3d node — real infrastructure work, not a
   quick flag.
   **Resolution: switched to Zot** (`ghcr.io/project-zot/zot`), a
   CNCF/goharbor-ecosystem-adjacent OCI-distribution-spec registry that
   publishes genuine multi-arch images including arm64 (confirmed via the
   same `docker manifest inspect` check). Lighter besides — no bundled
   Trivy/Notary/UI/database to run alongside it. Trade-off: lost Harbor's
   project/UI/RBAC layer, which this lab doesn't otherwise exercise, so the
   loss is mostly cosmetic for this build. **This is worth its own line in
   the write-up**: a customer evaluating this exact stack on an M-series
   Mac hits this wall on day one, before any Anchore tooling is even
   involved — a real, generalizable finding about the open source
   ecosystem's Apple Silicon readiness, not a lab-specific quirk.
2. **`docker push` silently ignores `insecure-registries` for this
   registry, `crane push --insecure` does not.** After getting Zot running,
   `docker push zot.lab.localhost:8080/...` failed with
   `unexpected status ... POST https://zot.lab.localhost:8080/...`, always
   choosing HTTPS, even though: (a) `docker info` correctly listed
   `zot.lab.localhost:8080` under Insecure Registries, (b) the daemon had
   been restarted after the config change, (c) `curl http://...` and
   `openssl s_client` both confirmed the registry answers correctly on
   plain HTTP on that exact port, and (d) retrying against a bare
   `127.0.0.1:8080` (eliminating any hostname/DNS ambiguity) failed
   identically. This looks like a genuine Docker registry-client bug/quirk
   under Colima + a k3d loadbalancer in front of the registry, not a
   config mistake — spent real time ruling out DNS dual-stack resolution
   (`.localhost` resolves to both `127.0.0.1` and `::1`) as the cause
   before concluding it wasn't that either. Fixed by routing around Docker's
   registry client entirely: `crane` (go-containerregistry) takes
   `--insecure` as an explicit per-call flag rather than relying on
   daemon-wide config, and pushed successfully on the first try once the
   image was in OCI (not docker-schema2) format. `push-to-registry.sh`
   wraps `crane pull --format oci` + `crane push --insecure` as the
   standing way to get anything into this lab's registry from here on.
   **Practical lesson for the write-up**: "insecure registry" configuration
   in Docker is less reliable than it looks, worth verifying with a raw
   HTTP client (curl) before trusting `docker push`'s error message about
   *why* it failed.
3. **Colima restarts can wedge the k3d cluster's API server — rebuild
   rather than debug indefinitely.** Mid-session, resizing Colima
   (`colima stop` / `colima start --cpu 6 --memory 12`) once left the k3d
   server-0 container running but its embedded k3s API server never came
   back up (`docker logs` showed an endless `connection refused
   127.0.0.1:6443` retry loop from the container's own healthcheck). A
   second Colima restart (this time changing only `--vz-rosetta`) left a
   *different* pod (Zot) stuck in a `Pod sandbox changed, it will be killed
   and re-created` cycle that self-resolved within ~30s. Conclusion: Colima
   VM restarts are somewhat disruptive to whatever's running inside its
   Docker, and the fix for a genuinely wedged cluster was `k3d cluster
   delete` + `phase2-cluster/bootstrap.sh` rather than trying to diagnose a
   container stuck retrying against itself — matches the plan's own
   "diagnose real breakage" principle, and matters practically because a
   from-scratch rebuild took under a minute thanks to the earlier
   reproducibility work.
4. **Colima's `/etc/docker/daemon.json` must be edited through
   `~/.colima/default/colima.yaml`, never directly.** A direct edit to
   `daemon.json` (adding `insecure-registries` before Zot was even
   installed, while still debugging the Harbor push) survived until the
   next `colima restart`, then silently reverted with no warning. Colima
   regenerates that file from its own YAML config on every start. Baked the
   correct mechanism into `phase1-toolchain/install.sh`.

5. **Bitnami removed its free-tier images from Docker Hub (Aug 2025) —
   pinned chart values silently stopped resolving.** `helm-values/minio.yaml`
   pinned `bitnami/minio:2025.7.23-debian-12-r3` (the chart's own default at
   the version installed); it 404'd entirely — not just that tag, the whole
   `bitnami/minio` repository is gone from the free tier, moved behind a
   paid "Bitnami Secure Images" subscription. `bitnami/postgresql` still
   resolves under `:latest` (inconsistent — some repos got a slim
   latest-only allowance, others didn't). Fixed by repointing
   `image.repository` (and the MinIO chart's separate console image) at
   `bitnamilegacy/*`, an unsupported, frozen mirror Bitnami left up — same
   tags, same digests, just relocated. Both charts print their own
   "Substituted images detected" / "SECURITY WARNING" banner once
   repointed, confirming the diagnosis. **Practical lesson**: pinning an
   image tag by digest-equivalent version number is not durable against a
   vendor unilaterally pulling the whole repository — worth a line in the
   write-up about supply-chain risk that has nothing to do with
   vulnerabilities in the image content itself.
6. **`crane push` on a `docker save` tarball fails with `MANIFEST_INVALID`
   against Zot — needed `docker buildx build --output type=oci` instead.**
   For images built locally in this repo (the runtime-inventory and
   sbom-jobs job images), `docker build` + `docker save` produces a
   docker-schema2-format tarball; `crane push` on it uploads all blobs
   successfully but Zot rejects the manifest outright
   (`MANIFEST_INVALID ... mediaType:application/vnd.docker.distribution.manifest.v2+json`).
   The same `crane push --insecure` against an OCI-format tarball (from
   `crane pull ... --format oci`, used for upstream images) worked on the
   first try. Fixed by installing the `docker-buildx` Homebrew formula (not
   present by default under Colima's Docker CLI — needed a
   `cliPluginsExtraDirs` entry in `~/.docker/config.json` to be found) and
   building locally-authored Dockerfiles with
   `docker buildx build --output type=oci,dest=...` instead of
   `docker build` + `docker save`. `push-to-registry.sh` (local Dockerfile
   builds) and `mirror-to-registry.sh` (upstream image pulls) are the two
   resulting scripts — deliberately separate rather than one script
   branching on image origin, since the two paths genuinely produce
   different artefact formats going in.
7. **A pod pulling an image and a host pushing one need different
   addresses for the same registry — this is not optional/cosmetic.**
   `zot.lab.localhost:8080` (used by `push-to-registry.sh` from the host)
   resolves to `127.0.0.1` via macOS's `.localhost` TLD handling and reaches
   Zot through the k3d loadbalancer's host port mapping. That address is
   meaningless *inside* the cluster: `127.0.0.1` inside a node's network
   namespace is the node itself, not the loadbalancer, so a pod referencing
   `zot.lab.localhost:8080/...` in its manifest got
   `dial tcp 127.0.0.1:8080: connect: connection refused` even with the
   registries.yaml insecure-registry config from finding #2 already in
   place. Fixed by making `registries.yaml`'s *mirror* rewrite
   `zot.lab.localhost:8080` to Zot's in-cluster Service DNS
   (`zot.anchore-lab-system.svc.cluster.local:5000`) rather than pointing
   both host and pod traffic at the same literal endpoint — so manifests
   and push commands can keep using one consistent-looking image reference,
   and only the containerd mirror config needs to know the two paths are
   different. This is exactly the kind of registry/DNS split that is easy
   to get wrong once and invisible until the first real pull happens —
   worth flagging explicitly for the write-up as a "the docs make this look
   like one hostname, it isn't" gotcha.

8. **Syft, calling the registry directly from inside a job pod, hit the
   host-vs-pod addressing split a third time — and then Syft's own
   HTTP/TLS default a fourth.** `sbom_generate.py` calls `syft scan
   registry:<image_ref>` directly (not through containerd's pull path,
   which finding #7 already fixed) — so it needed its own translation from
   the catalogue's stored `zot.lab.localhost:8080/...` references to the
   in-cluster-resolvable `zot.anchore-lab-system.svc.cluster.local:5000`
   form (`resolve_for_pod()` in `jobs/sbom_generate.py`). Confirmed via
   `kubectl run ... nslookup` that pod-network DNS *does* resolve
   `.svc.cluster.local` correctly (unlike containerd's node-level resolver
   in finding #7) — this was purely about the image reference string, not
   DNS reachability. Once that was fixed, Syft still failed with
   `http: server gave HTTP response to HTTPS client`: same insecure-registry
   default-to-HTTPS pattern as Docker (finding #2) and containerd
   (finding #7), this time inside Syft's own registry client, fixed with
   `SYFT_REGISTRY_INSECURE_USE_HTTP=true` /
   `SYFT_REGISTRY_INSECURE_SKIP_TLS_VERIFY=true` as CronJob env vars. Four
   separate tools (Docker CLI, containerd, and now Syft) each needed their
   own insecure-registry opt-in for the exact same self-signed/no-TLS
   registry — there is no single setting that covers "this registry is
   plain HTTP" across a toolchain, each client's config surface is its own.
9. **A `:0.1.0`-tagged CronJob image silently kept running the OLD digest
   after a rebuild.** After fixing finding #8, re-pushed `lab/sbom-jobs`
   under the same tag and re-ran the job — it still hit the old bug.
   `kubectl get pod ... -o jsonpath='{.status.containerStatuses[0].imageID}'`
   showed the stale digest: Kubernetes' default `imagePullPolicy` is
   `IfNotPresent` for any non-`:latest` tag, so the node happily reused its
   cached (old) image rather than checking whether `0.1.0` now points
   somewhere else. Added `imagePullPolicy: Always` to both SBOM job
   containers — the right trade-off during active lab iteration (always
   verify freshness) even though a real deployment would prefer pinning by
   digest instead of relying on `Always` re-checking a mutable tag every
   run.

## Colima resize (capacity note)

Resized Colima from 4 vCPU/8GB (Phase 1/2 sizing) to 6 vCPU/12GB partway
through Phase 3 to give Zot + MinIO + Postgres + Grafana headroom, plus
`--vz-rosetta` for faster emulation of any amd64-only image encountered
later (harmless to leave on even after Zot replaced Harbor). Host has 24GB
RAM / 15 CPUs, so ample room. Baked into `phase1-toolchain/install.sh` as
the new default sizing.

## Status: core pipeline complete and measured

- [x] MinIO (SBOM object storage) — `bitnamilegacy/minio`, see finding #5.
- [x] Postgres (catalogue database) + schema — 4 tables (`images`, `sboms`,
      `scan_results`, `findings`), applied via a one-shot Job reading a
      ConfigMap-mounted `schema.sql`.
- [x] Runtime inventory CronJob — every 10 minutes, lists all pods
      cluster-wide via a ClusterRole scoped to `get`/`list` on pods only,
      upserts into `images`. Verified: found 11 distinct images across the
      cluster on first run (K8s system images, platform services, and the
      lab's own job images alike).
- [x] SBOM generation job — Syft against each image missing an SBOM,
      uploads to MinIO, records `image_id -> minio_key` + package count in
      `sboms`. Verified: 11/11 images SBOM'd once the findings below were
      fixed (first pass: 10/11, the lab's own `runtime-inventory` image
      failed — see finding #8).
- [x] Continuous re-matching job — refreshes the Grype DB once, re-scans
      every stored SBOM, records severity-bucketed counts in
      `scan_results` and per-finding rows in `findings`. **This is the
      lab's core measurable claim, and it now has a real number**: see
      "Measured results" below.
- [x] Admission control — Kyverno (audit mode), two ClusterPolicies
      (approved registries, required resource limits). Already caught a
      real self-inflicted violation on first run — see "Self-compliance"
      below, a preview of the Phase 6 exercise.
- [x] Grafana dashboard over the catalogue — Postgres datasource + a
      provisioned dashboard (`helm-values/grafana-dashboard-catalogue.json`)
      with images/SBOMs/findings stat panels, a per-image severity table,
      and a most-common-CVEs table, all querying the catalogue directly.

## Measured results (the plan's central claim)

Full re-match run against all 11 tracked images, single run:

- **Grype DB refresh: 34.8s** (one-time cost per rescan cycle, not
  per-image — the plan's premise is this cost is amortized across however
  many images are tracked).
- **Re-matching 11 stored SBOMs: 16.8s, 20,092 KiB read from MinIO, zero
  images pulled or re-analysed.**
- **Total findings: 1,604** across the 11 images (124 Critical, 672 High) —
  before any VEX triage. This number is itself the finding the plan
  predicts: eleven images, mostly small platform/utility images, and the
  raw count is already unmanageable to read by hand. A queryable catalogue
  (this one) rather than a report is the only way this scales — exactly the
  argument the plan wants demonstrated, now with a real figure instead of
  an assertion. (A rigorous full-image-repull-and-rescan baseline to
  compare against wasn't run in this session — that's the natural next
  measurement, and belongs with Phase 6's "test that matters" once the
  self-scan is in scope.)

## Self-compliance (a live preview of Phase 6)

Kyverno's audit-mode policies flagged this repo's own `catalogue-schema`
Job on its very first evaluation: `PolicyReport` showed 0 pass / 2 fail.
Root causes, both genuinely this repo's own bugs, not the policy being
wrong:
1. The job's `postgres:16-alpine` image has no registry prefix, which
   Docker/Kubernetes resolve to `docker.io/library/postgres` implicitly —
   the Kyverno pattern's `docker.io/*` glob didn't match the *implicit*
   form, only an explicit `docker.io/...` reference.
2. The job sets no `resources.limits`.
Left both violations in place rather than quietly patching them away: audit
mode exists precisely to surface this kind of thing before flipping to
Enforce, and "the lab fails its own gate on day one" is exactly the honest
Phase 6 finding the plan predicts, arriving three phases early. Fixing the
implicit-registry-name gap and adding limits is tracked as real remaining
work, not silently resolved.

## Findings
