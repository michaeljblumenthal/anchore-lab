# Phase 6: turn the system on itself — checklist

Status legend: `[x]` done and verified, `[ ]` not started, `[~]` in progress.

Per the plan's own instruction, no exemptions for "it's just infrastructure":
this phase points the exact same pipeline built in Phase 3 — runtime
inventory, SBOM generation, continuous re-matching — at every pod in the
cluster, k3s system components and Kyverno's own controllers included, and
reports the honest aggregate.

## Checklist

- [x] Scan everything, enumerated honestly first.
  Triggered a fresh `runtime-inventory` run against the live cluster: 18
  distinct images across every namespace (`kube-system`, `kyverno`,
  `anchore-lab`, `anchore-lab-system`) — see the full list below.
- [x] SBOM every discovered image.
  19 images tracked, 19 SBOMs stored (one extra row was a stale Phase 4
  demo artefact, cleaned up — see finding #2).
- [x] Aggregate report: total packages and total findings, before triage.
  `aggregate-report.sh` — numbers below.
- [x] Base image / package commonality.
  Same script, "findings by package" section — a proxy for which single
  update would clear the most findings at once.
- [x] Bootstrap ordering, exemptions, where trust has to start.
  `bootstrap-ordering.md` — traces the real dependency chain in this
  specific lab, not a general statement.
- [x] Licence inventory across every component.
  `license-inventory.sh` / `license_inventory.py`, run against all 19
  stored SBOMs. Results and interpretation below (see "Licence findings").
- [x] Self-compliance: does the stack pass its own Kyverno policy?
  Full cluster-wide audit, first pass: **64 rule evaluations pass, 8
  fail**, all 8 attributable to one root cause across two of this repo's
  own manifests (`catalogue-schema` and `whoami`) — see below. Fixed both
  root causes genuinely (not by loosening the policy into a no-op) and
  re-ran the audit: **72 pass, 0 fail, cluster-wide.**
- [x] VEX triage in earnest, honestly scoped.
  Triaged one real finding (`GO-2026-6089`, an HTTP/2 h2c timeout bypass
  affecting 14 of 19 images) against `lab/sbom-jobs`, the one affected
  image whose full source is this repo's own — confirmed by reading
  `sbom_generate.py`/`sbom_rescan.py` that neither runs an HTTP server at
  all. VEX applied, verified: 2 matches -> 0, both moved to
  `ignoredMatches`. The other 13 affected images (Grafana, Kyverno's four
  controllers, CoreDNS, Traefik, MinIO, etc.) are real upstream projects
  whose server configuration was not independently verified in this
  session and remain untriaged — recorded as such, not silently
  suppressed by inference. See "VEX triage" below for why a broader pass
  wasn't attempted and what it would actually require.
- [x] The test that matters: given a newly disclosed CVE, how long to
  answer "is it present and reachable" — timed, not estimated. **2.58
  seconds wall-clock** (including cold-starting a throwaway pod to run the
  query — a real client with a live connection to the catalogue would be
  faster still). See "The test that matters" below.

## Full component list (18 distinct images, cluster-wide, no exemptions)

- k3s platform: `rancher/mirrored-coredns-coredns`,
  `rancher/local-path-provisioner`, `rancher/mirrored-metrics-server`,
  `rancher/mirrored-library-traefik`, `rancher/klipper-lb`,
  `rancher/klipper-helm`
- This lab's own platform services: `ghcr.io/project-zot/zot`,
  `bitnamilegacy/minio`, `bitnamilegacy/minio-object-browser`,
  `bitnami/postgresql`, `grafana/grafana`
- Admission control: `reg.kyverno.io/kyverno/kyverno`,
  `reg.kyverno.io/kyverno/background-controller`,
  `reg.kyverno.io/kyverno/cleanup-controller`,
  `reg.kyverno.io/kyverno/reports-controller`
- This lab's own job images: `lab/runtime-inventory`, `lab/sbom-jobs`
- Test/demo fixtures still resident in the cluster:
  `postgres:16-alpine` (catalogue schema job), `traefik/whoami`

## Process findings (debugging this phase)

1. **Same as Phase 3, but the self-scan makes it unavoidable**: images
   pulled implicitly (`postgres:16-alpine`, resolving to
   `docker.io/library/postgres`) are exactly the ones a naive allowlist
   misses — already caught once by Kyverno in Phase 3, and would be missed
   again by anyone who assumed "we only pull from our approved registries"
   without checking bare image names specifically.
2. **A stray demo artefact from Phase 4 polluted the self-scan.**
   `push-sbom-to-catalogue.py`'s local test run (Phase 4) inserted a row
   using `github.com/michaeljblumenthal/anchore-lab/sbom-mcp-server` as the
   `repository` value — a source-repo identifier, not a pullable image
   reference. `sbom_generate.py` correctly tried to `syft scan registry:`
   it and correctly failed with a clean 404, but this meant every
   subsequent `sbom-generate` run re-attempted and re-failed on the same
   bad row, one real failure buried in what otherwise looked like a
   confusing intermittent crash-loop during debugging (see finding #3).
   Deleted the row; the underlying job code was never actually broken.
   **Lesson for the write-up**: a catalogue accepts whatever it's given,
   and a manual/demo insert with the wrong kind of key can look identical
   to a real bug days later. The fix isn't defensive code in
   `sbom_generate.py` (a malformed row genuinely should fail loudly) — it's
   discipline about not leaving demo/test rows in a catalogue meant to
   represent real state.
3. **A confusing, only-partially-explained crash-loop during this phase's
   debugging, recorded honestly rather than resolved with false
   confidence.** While chasing finding #2, several `sbom-generate` Job
   pods crash-looped with a `Back-off restarting failed container` cycle
   and produced *zero* log output — `kubectl logs`, even `--previous`,
   came back empty. Ruled out stdout buffering (added `PYTHONUNBUFFERED=1`
   to both job Dockerfiles as a real, worthwhile fix regardless — it's
   good practice and removes one class of "silent crash" for good) and
   ruled out the OOM/resource-limit hypothesis (a subsequent run under the
   same 512Mi limit completed cleanly). Running the exact same image
   manually via `kubectl exec` into a debug pod worked immediately and
   surfaced finding #2's real error clearly. The crash-loop did not
   reproduce on the next `kubectl create job` attempt. **Left unresolved
   rather than claiming a fix**: possible causes not ruled out include a
   race during the rapid delete/recreate/rebuild cycle this debugging
   session involved (a new image digest landing mid-pull, or the node's
   image cache in an inconsistent state from several pushes to the same
   tag in quick succession). Worth a line in the write-up as exactly the
   kind of finding a real on-call engineer has to write "would not
   reproduce, added observability, moving on" for — not every failure
   resolves to a clean root cause in the time available, and pretending
   otherwise would be less honest than the plan's own principle asks for.

## Metrics (real run, this cluster, this session)

**Coverage: 19 images tracked, 19 SBOMs stored, 0 coverage gaps** (every
tracked image has a stored SBOM — the "images tracked but never SBOM'd"
query returns zero rows).

**5,099 total packages catalogued** across those 19 images.

**2,406 total findings before any VEX triage**: 185 Critical, 1,012 High,
774 Medium, 78 Low, 241 Negligible. This is the headline number the plan
predicts: nineteen images — mostly small platform/utility components, none
of them exotic — and the raw finding count is already far beyond what
anyone would triage by reading a report. A queryable catalogue answering
"which images, which packages, which severities" is not a nice-to-have at
this scale, it is the only way the number is usable at all.

**Continuous re-matching still holds at cluster scale**: refreshing the
Grype DB and re-matching all 19 stored SBOMs took 35.1s (DB refresh) +
30.4s (re-match), reading 30MB from MinIO, zero images re-pulled — the
same mechanism validated at 11 images in Phase 3, now confirmed at the
full self-scan scope with no material change in per-SBOM cost.

**Base image / package commonality — the most quantifiable "one update
clears N findings" data point**: the Go standard library (`stdlib`),
statically compiled into 14 of the 19 tracked images (everything built in
Go: Traefik, CoreDNS, metrics-server, local-path-provisioner, Zot, all
four Kyverno controllers, this lab's own job images), accounts for 573
findings on its own — roughly a quarter of the entire finding total from
one shared dependency. This is exactly the kind of finding the plan asks
for: not "here is a list of CVEs," but "here is the one thing that, if
updated, moves the aggregate number the most."

**Worst individual images**: `bitnamilegacy/minio` (737 findings, 63
Critical) and `grafana/grafana` (399 findings, 41 Critical) — both
platform services this lab installed via Helm chart defaults, not custom
images, underscoring that "infrastructure" components carry real exposure
and the plan's instruction not to exempt them was the right call.

**Best individual images**: `rancher/klipper-lb` (2 findings, 0 Critical)
and `bitnami/postgresql:latest` (2 findings, 0 Critical) — both small,
narrowly-scoped, recently-built images.

## VEX triage

The plan asks for real triage across the aggregate findings, not a single
worked example — "most findings in third party infrastructure images will
not be reachable in this deployment. Working through which ones are is the
same judgement the CRA exploitability test demands, done against real
data."

Picked a genuinely representative starting point rather than an easy one:
`GO-2026-6089`, the widest-reaching Critical/High-adjacent finding in the
aggregate (14 of 19 images), a real CVE with a specific, checkable
condition — a `net/http` server accepting unencrypted HTTP/2 (h2c)
connections. Triaged it properly for `lab/sbom-jobs`
(`phase6-self-scan/vex/GO-2026-6089-h2c-triage.openvex.json`): read the
actual job source, confirmed no `http.Server` or listener exists anywhere
in the code path, applied the VEX statement, and verified with a real
Grype rescan that both matches on that image moved from `matches` to
`ignoredMatches`.

**Deliberately did not extend this to the other 13 affected images in this
session, and the reason is itself the finding.** A defensible
`not_affected` judgement for Grafana, Traefik, CoreDNS, or any of
Kyverno's four controllers requires actually knowing each one's HTTP
server configuration — whether h2c is enabled, whether it's reachable from
outside the pod, whether an upstream config flag already disables it. That
is real security engineering per image, not a pattern that generalizes
from one clean case, and doing it honestly for 13 more third-party
projects in the time available would have meant doing it badly. The
plan's own words are precise on this point — "working through which ones
are is the same judgement the CRA exploitability test demands" — and a
rushed or inferred judgement on 13 findings is worse than an honest
"untriaged" label on all of them. **This is the practical answer to why
VEX triage doesn't scale by a person doing it findings-by-finding**: one
CVE, one image, with source available, took real (if modest) effort to
triage defensibly; the same CVE across 13 more images, without source
access, would take meaningfully longer per image and produce a lower-
confidence answer. That gap — between "I can VEX my own code quickly" and
"triaging someone else's upstream image responsibly is slow" — is exactly
the kind of finding a customer evaluating this approach needs to see
before assuming VEX triage is a solved problem at scale.

## The test that matters

The plan's own framing: given a newly disclosed CVE, how long does it take
to answer whether it is present and whether it is reachable? If the answer
is not minutes, the system does not do what it was built to do.

Ran this for real against a Critical finding already in the catalogue
(`GHSA-jppx-rxg9-jmrx`, a `golang.org/x/crypto` CVE) — not chosen for a
favourable result, chosen because it was the first Critical CVE returned by
a "most-affected-images" query, i.e. the kind of thing a security team
would plausibly ask about first:

```sql
SELECT i.repository, i.tag, f.package_name, f.package_version, f.fix_state, f.severity
FROM findings f
JOIN scan_results sr ON sr.id = f.scan_result_id
JOIN images i ON i.id = f.image_id
WHERE sr.id IN (SELECT max(id) FROM scan_results GROUP BY sbom_id)
AND f.vulnerability_id = 'GHSA-jppx-rxg9-jmrx';
```

**Result: 2.58 seconds wall-clock**, timed with `time`, including the
overhead of spinning up a throwaway `postgres:16-alpine` pod inside the
cluster to run the query (a real dashboard or CLI with a live connection
to the catalogue would skip that overhead entirely). The answer named all
7 affected images, the exact package version in each, and confirmed a fix
exists for all 7 — everything the "present" half of the plan's question
asks for, in one query against data that already existed before the
question was asked.

**Honest limit: this answers "present," not "reachable."** The catalogue
schema has a `vex_status` column on every finding specifically for this
(see `phase3-inventory/catalogue-service/schema.sql`), and Phase 1
demonstrated the mechanism works (suppressing `perl-base` CVEs on
`python:3.12-slim` via an OpenVEX document). But no VEX statements have
been applied to *this* self-scan's findings yet — every `vex_status` in
the catalogue right now is `NULL`. Answering "is it reachable" for these 7
images specifically would require the actual exploitability judgement
Phase 1 and the plan's Article 14 framing both call for: does anything in
these images' actual runtime paths invoke the affected `golang.org/x/crypto`
code, which is a real security-engineering question that data alone
doesn't answer, no matter how fast the query. **The honest report for this
metric is: presence in under 3 seconds, reachability not yet triaged for
this specific finding set** — stated plainly rather than either
overclaiming a "reachable" answer the system doesn't actually have, or
skipping the distinction the plan explicitly cares about.

## Self-compliance

The plan predicts the stack likely fails its own policy on first run and
asks for a real decision — exempt, pin, rebuild, or accept — with the
reasoning recorded, not silently fixed or silently ignored.

**First cluster-wide audit: 64 pass, 8 fail.** Both failure modes traced
to the same root cause already flagged in Phase 3 with one instance
(`catalogue-schema`), now confirmed to recur (`whoami`, a second, unrelated
manifest): Kyverno's `images-from-approved-registries` pattern only
matched image references that explicitly named a registry
(`docker.io/...`, `ghcr.io/...`), missing the *implicit* Docker Hub form —
a bare `postgres:16-alpine` or `traefik/whoami:v1.10` with no prefix at
all, which Kubernetes silently resolves to `docker.io/library/postgres`
and `docker.io/traefik/whoami` respectively but which never contains the
literal string `docker.io`. `catalogue-schema` additionally had no
resource limits set, a plain oversight in that one manifest.

**Decision: fix both, genuinely, not by loosening the policy.** The easy
wrong fix would have been adding a bare `*` wildcard to the registry
pattern — it would have cleared every failure instantly, and it would
have made the entire policy a no-op, since `*` matches any image
reference including a hypothetical `evil.example.com/malware:latest`.
Instead: added `postgres:*` and `traefik/whoami:*` as explicit,
named-by-repository-name entries to the allowed pattern (documented
inline in `kyverno-policies.yaml` as a real, ongoing maintenance cost —
anyone adding a new bare-name image reference to this repo needs to add
it here too, which is a genuine trade-off worth naming rather than
hiding), and added the missing `resources.limits` to
`catalogue-schema-job.yaml` directly.

**Re-ran the full cluster-wide audit after both fixes: 72 pass, 0 fail.**
Confirmed via a second `kubectl get polr -A` sweep, not assumed from the
manifest diff alone.

## Licence findings

Ran `license-inventory.sh` against every stored SBOM (full per-image
breakdown in `license-results/summary.json`). Totals across all 19 images:
**5,099 packages, 0 allowed, 4,715 denied, 4,128 unlicensed.**

`allowed=0` across every single image confirms the Phase 1 finding at full
scale: Grant's default policy has an empty allow-list, not an empty
deny-list, so every package with *any* identifiable licence gets `denied`
by default until a real `grant.yaml` policy explicitly allows the licence
families this project accepts (MIT, BSD-3-Clause, Apache-2.0, etc.). This
is not evidence of 4,715 real licence violations — it is evidence that
nobody has yet written the policy file that would separate "fine" from
"actually a problem," which is itself the point: without a queryable
inventory and an explicit policy, "everything is denied" and "everything
is fine" produce the exact same silence.

**The `unlicensed=4128` figure (81% of all cataloged packages) is the more
substantive finding**, and it's a data-completeness gap rather than a
licence-compliance one: this many packages, across every image type in
this cluster (Go static binaries, Python/Debian userlands, from-scratch
minimal images alike), simply carry no licence metadata Syft could
extract — no `LICENSE` file at a path Syft's Debian/Go/Python catalogers
check, no SPDX headers, no package-manager-declared licence field. This
tracks with a broader, well-known limitation of SBOM tooling generally,
not something specific to Syft or this build: licence *identification*
from an already-built artefact is fundamentally harder than vulnerability
matching, because a CVE match only needs a name+version, while a licence
needs the actual licensing text or metadata to still be present in the
shipped layer, which most Dockerfiles don't preserve. **Worth stating
plainly for the write-up**: a "full licence inventory," even done
thoroughly with the right tool, is not the same claim as "we know the
licence of everything we ship" — 81% unlicensed here is the honest
ceiling of what SBOM-based licence scanning can currently tell you about a
typical container image built from upstream base layers, not a gap
specific to this lab's setup.
