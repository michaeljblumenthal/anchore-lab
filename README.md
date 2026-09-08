# anchore-lab

SBOM-first continuous vulnerability management on Kubernetes, built from
scratch with Anchore's open source tooling — Syft, Grype, and Grant — to
find out what the approach actually costs and where it actually breaks.
Built and written up over one week, September 2026.

## What this is, and isn't

Most container vulnerability scanning happens once, at build time, against
a registry. That leaves two gaps: images already running in a cluster
drift out of scope, and a vulnerability disclosed after the scan is
invisible until something triggers a rescan. The SBOM-first alternative
catalogues what's in each artefact once and re-matches that catalogue
against a refreshed vulnerability database on a schedule — no re-pull, no
re-analysis, just a lookup.

Commercial platforms sell this. This lab builds a working version of it
out of open source parts, on purpose, to see where a self-assembled stack
strains. It is deliberately open source only — no Anchore Enterprise
licence was used anywhere in this build — because that is the path
Anchore's actual customers take before anyone evaluates the commercial
product: find Syft and Grype, build something around them, hit a wall,
then look for what solves it. Walking that path myself means naming the
wall precisely instead of reciting it from a datasheet.

This is a lab, not a production system, and the differences matter. They
are called out explicitly throughout, not left for the reader to infer.

## What's actually running

A multi-node k3d cluster with real storage, ingress, and RBAC; a
self-hosted OCI registry; a runtime-inventory job that enumerates every
image actually running in the cluster; SBOM generation into object
storage; a continuous re-matching job that refreshes the vulnerability
database and re-scans stored SBOMs on a schedule; Kyverno admission
control in audit mode; a Grafana dashboard over the whole catalogue; a
CI pipeline that generates and scans SBOMs on every push; two MCP servers
exposing this tooling to an AI assistant conversationally; and a pre-push
git hook that runs a real scan before code leaves the machine.

Everything below is measured against that running system, not described
from the plan.

## The headline number

Pointing the finished pipeline at the cluster running it — including its
own registry, its own database, its own admission controller, no
exemptions for "that's just infrastructure" — produced:

**19 images. 5,099 packages catalogued. 2,406 findings before any
triage: 185 Critical, 1,012 High, 774 Medium, 78 Low, 241 Negligible.**

That number is the argument for the whole approach, made concretely rather
than asserted. Nineteen images — mostly small platform and utility
components, nothing exotic — and the raw finding count is already far
beyond anything a person reads by hand. A queryable catalogue that can
answer "which images, which package, which severity" is not a
nice-to-have at this scale; it's the only way the number means anything.

One data point makes that concrete: the Go standard library, statically
compiled into 14 of the 19 images (everything written in Go — Traefik,
CoreDNS, metrics-server, Zot, all four Kyverno controllers, this lab's own
job images), accounts for **573 of the 2,406 findings on its own** — a
quarter of the total, from a single shared dependency. That is the actual
shape of "one base image update clears N findings," not a hypothetical.

And the continuous re-matching claim held at that scale: refreshing the
Grype database and re-matching all 19 stored SBOMs took 35.1 seconds
(database refresh) plus 30.4 seconds (re-match), reading 30MB from object
storage, pulling zero images. The same mechanism, first validated at 11
images in the core build, showed no material change in per-SBOM cost once
scaled to cover the whole cluster including itself.

Given a real, already-catalogued Critical CVE, a single SQL query against
the catalogue named every affected image, the exact package version, and
fix availability — timed at **2.58 seconds wall-clock**, including the
overhead of spinning up a throwaway pod to run it. That's the "present"
half of the plan's central test answered in real time. The honest
companion fact: answering "reachable" for a specific finding is a
security-engineering judgement a database can't make on its own — see
"What VEX triage actually costs" below.

## What broke, and what it means

The build log (`docs/build-log/`) keeps every dead end in order, including
the ones that cost hours before they resolved cleanly. The four that
matter most for anyone evaluating this stack:

**Harbor doesn't run on Apple Silicon.** The plan named Harbor as the
registry. Its official images are amd64-only, with no arm64 manifest
published anywhere, and crash with a Go runtime panic when run emulated
under QEMU on an arm64 Kubernetes node. There is no clean way to force a
k3d cluster to run amd64 nodes — no flag, no honoured environment
variable. The registry was rebuilt on Zot, a genuinely multi-arch,
OCI-native alternative, at the cost of Harbor's UI and project/RBAC layer,
which this lab never used anyway. This is the finding worth leading with
in any conversation about evaluating this stack today: a customer on an
M-series Mac hits a wall before any Anchore tooling is even involved.

**Getting one pod to pull one image from an in-cluster HTTP registry
needed four separate insecure-registry configurations** — one each for
the Docker CLI, containerd (which resolves images at the node network
level, outside the pod network where cluster DNS lives, so a Kubernetes
Service DNS name doesn't even work there — a fixed ClusterIP was needed
instead), Syft's own registry client, and, separately, `docker push`
itself turned out to silently ignore its own insecure-registry
configuration and had to be routed around entirely with a different tool
(`crane`). No single setting covers "this registry is plain HTTP" across a
real toolchain. This is unglamorous, and it is exactly the kind of cost a
datasheet never mentions.

**Bitnami pulled its free-tier container images from Docker Hub while
this lab was mid-build.** A Helm chart pinned to a specific, valid
`bitnami/minio` tag stopped resolving entirely — not a stale version, the
whole repository moved behind a paid tier in August 2025, leaving only an
explicitly unsupported mirror as the free fallback. This has nothing to do
with vulnerability content and everything to do with supply-chain
fragility: a chart pinned by version number is not durable against a
vendor pulling the repository out from under it.

**The stack failed its own admission-control policy on first evaluation,
and the fix mattered as much as the failure.** A full cluster-wide Kyverno
audit found 8 rule failures, all traced to one root cause recurring across
two of this repo's own manifests: an image reference with no explicit
registry prefix (`postgres:16-alpine`, `traefik/whoami:v1.10`) resolves
implicitly to Docker Hub but never contains the literal string
`docker.io`, so it slipped past a registry allowlist that only matched
explicit prefixes. The tempting fix — a bare wildcard added to the
policy — would have cleared every failure in one line while making the
entire policy meaningless, since a wildcard matches anything including a
genuinely malicious reference. The actual fix named the specific bare
references this repo uses, explicitly, with the ongoing maintenance cost
of that choice written down rather than hidden. Re-audited clean: 72
passes, 0 failures, confirmed with a second real audit run, not assumed
from the diff.

## What VEX triage actually costs

The plan asks for real triage across the aggregate findings, not one
worked example, and that's what was attempted — with an honest stopping
point recorded rather than a rushed or inferred result.

One finding was picked deliberately, not for a favourable outcome: the
widest-reaching CVE in the whole scan, affecting 14 of 19 images, with a
specific, checkable condition (an HTTP/2 server accepting unencrypted
connections). For the one affected image whose full source is this repo's
own, the triage was real: read the code, confirmed no HTTP server exists
anywhere in it, applied a VEX statement, and verified with a live Grype
rescan that the finding actually disappeared.

The other 13 affected images — Grafana, Traefik, CoreDNS, all four Kyverno
controllers — were left explicitly untriaged. A defensible judgement for
any of them requires knowing that specific project's HTTP server
configuration, which is real security-engineering work per image, not a
pattern that generalizes from one clean case. Doing it responsibly for
thirteen more third-party projects, without source access, in the time
available, would have meant doing it badly.

That gap is itself the finding worth surfacing to anyone evaluating this
approach: triaging your own code, with source in hand, is fast — the one
real example above took minutes. Triaging someone else's upstream image
responsibly is not, and that asymmetry is exactly what determines whether
VEX triage scales for a given team, not a claim that the mechanism itself
works (it does — Grype respects a correctly formed VEX document every
time it was tested, across three separate documents in this build).

## Licence findings, read carefully

A full licence inventory across all 19 images (5,099 packages via Grant)
returned 0 packages `allowed` and 4,128 (81%) marked `unlicensed`. Neither
number means what it looks like at first glance.

The zero-allowed figure confirms a finding from early in this build at
full scale: Grant's default policy has an empty allow-list, not an empty
deny-list, so every package with any identifiable licence — including
permissive ones like MIT and BSD-3-Clause — is `denied` by default until
someone writes a real policy file naming what's actually acceptable.
That's a first-run surprise worth knowing about before assuming a bare
`grant check` run tells you anything about actual compliance risk.

The 81%-unlicensed figure is a genuine finding, but about SBOM tooling
generally, not this build specifically: licence *identification* from an
already-built container image is harder than vulnerability matching,
because a CVE match only needs a name and version, while a licence claim
needs the actual licensing text or metadata to have survived into the
shipped layer — which most Dockerfiles don't preserve. A "full licence
inventory," done thoroughly with the right tool, is not the same claim as
"we know the licence of everything we ship." Eighty-one percent unlicensed
here is close to the honest ceiling of what SBOM-based licence scanning
can currently tell you about a typical image built from upstream base
layers.

## Where a self-assembled stack stops being worth it

This is the question the private version of this plan set out to answer,
and the honest answer from one week of building it alone: not at the
scale this lab reached (19 images, single cluster), but the seams are
already visible at that scale, and every one of them is the kind of thing
a commercial platform exists to absorb.

- **Registry compatibility** across architectures is not something most
  teams want to debug themselves — it cost real hours here and the fix
  (switching registries entirely) is not something every team can do
  mid-project.
- **The insecure-registry configuration sprawl** — four separate settings
  for one plain-HTTP registry — is exactly the kind of integration tax
  that compounds as more tools join a stack. A platform that owns the
  whole pipeline doesn't have this problem because it controls every
  layer.
- **Upstream image availability is not guaranteed to be stable**, and a
  self-assembled stack inherits that risk directly, per pinned dependency,
  with no vendor relationship to fall back on.
- **VEX triage is a per-image, source-access-dependent cost**, and it
  scales with the number of third-party components in the stack, not with
  cluster size. A team running mostly upstream infrastructure images (as
  this lab does) hits this ceiling faster than a team running mostly its
  own code.

None of these are reasons the open source tooling is bad — Syft and Grype
themselves worked correctly and predictably throughout this entire build.
They're reasons the *platform* around the tooling — the registry, the
storage, the orchestration, the policy engine, the version compatibility
across all of it — is where the real cost lives, and where a customer
should expect to spend money once self-assembly stops paying for itself.

## Repository layout

- `phase1-toolchain/` — Syft/Grype/Grant install, SBOM format comparison
  across a container image, a filesystem, and a git checkout, and a VEX
  suppression exercise.
- `phase2-cluster/` — the k3d cluster: multi-node, storage class, ingress,
  namespaces, RBAC, and two deliberately broken scenarios diagnosed and
  recorded.
- `phase3-inventory/` — the core pipeline: registry, runtime inventory,
  SBOM generation and storage, continuous re-matching, admission control,
  dashboard.
- `phase4-ci/` — GitHub Actions integration, including a real recorded
  failing run and its fix.
- `phase5-agentic/` — two MCP servers and a real pre-push scan gate.
- `phase6-self-scan/` — the pipeline pointed at itself, with the full
  aggregate report, licence inventory, and VEX triage.
- `docs/build-log/` — the chronological account of the build, kept from
  the first command, errors and dead ends included.
- `docs/decisions/` — short ADRs for non-trivial process decisions.

Each phase directory has its own README with a full checklist and numbered
findings — this document is the synthesis, those are the primary sources.

## Quickstart

```sh
make toolchain       # syft, grype, grant, docker (via colima), kubectl, helm, k3d, k9s
make cluster          # bring up the k3d cluster
cd phase3-inventory && ./bootstrap.sh   # registry, storage, catalogue, jobs, admission control, dashboard
cd ../phase6-self-scan && ./aggregate-report.sh   # the numbers above, reproduced
```

`make help` lists every available target.

## A note on the lab defaults

Manifests in this repo contain plaintext default credentials for
MinIO/Postgres/Grafana. These are intentional, local-only lab defaults for
a cluster that never leaves `127.0.0.1` on the machine it was built on —
not a security posture recommendation, and not reused anywhere outside
this lab.

## Status

All seven phases of the original build plan are complete:

1. **Toolchain baseline** — [phase1-toolchain/README.md](phase1-toolchain/README.md)
2. **Kubernetes cluster** — [phase2-cluster/README.md](phase2-cluster/README.md)
3. **Continuous inventory** — [phase3-inventory/README.md](phase3-inventory/README.md)
4. **CI integration** — [phase4-ci/README.md](phase4-ci/README.md)
5. **Agentic interface** — [phase5-agentic/README.md](phase5-agentic/README.md)
6. **Self-scan** — [phase6-self-scan/README.md](phase6-self-scan/README.md)
7. **Write-up** — this document
