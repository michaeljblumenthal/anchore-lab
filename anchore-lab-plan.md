# SBOM First Supply Chain Security: A Kubernetes Lab Build

A hands on lab reconstructing continuous, SBOM based vulnerability management on Kubernetes using open source tooling, to understand what the approach costs and where it breaks.

Started September 2026.

## What this is

Most container vulnerability scanning happens at the registry, once, at build time. That leaves two gaps. Images already running in a cluster drift out of scope, and a vulnerability disclosed after the scan is invisible until something triggers a rescan.

The SBOM first alternative inverts it: catalogue what is in each artefact once, store that inventory centrally, and re-match the stored inventories against a refreshed vulnerability database on a schedule. When a new CVE is published you already know which images contain the affected package, without pulling or re-analysing anything.

Commercial platforms sell this. This lab builds a crude version out of open source parts to find out what is genuinely hard about it.

There is a regulatory driver as well. Under the EU Cyber Resilience Act, Article 14 reporting obligations began on 11 September 2026, requiring manufacturers to notify their national CSIRT and ENISA of an actively exploited vulnerability within 24 hours of becoming aware of it. The full requirements, including SBOMs under Annex I Part II, follow on 11 December 2027. A 24 hour clock is only survivable if the question "is this component in anything we ship, and is it reachable" can be answered in minutes. That is an inventory problem before it is a scanning problem.

## Tooling

Anchore publishes three open source command line tools under Apache 2.0, documented at `https://oss.anchore.com/docs/projects/`:

- **Syft**, SBOM generation from images, filesystems, directories and archives
- **Grype**, vulnerability scanning against images or against an existing SBOM
- **Grant**, open source licence compliance scanning

Plus **grype-mcp**, an MCP server bridging an AI assistant to the Grype CLI, and the **syft-action** and **scan-action** GitHub Actions.

Note that Anchore Engine, the former open source server side product, is EOL and its Helm chart deprecated. The server side is now the commercial Anchore Enterprise.

**This lab is deliberately open source only.** The storage, cataloguing and continuous re-matching layers are built rather than bought, which is the interesting part of the exercise: it establishes where a self assembled open source stack genuinely stops being viable, rather than assuming it either does or does not.

## Principles

- Verify command syntax and configuration against current upstream documentation before running anything. Chart and tool versions move.
- Keep a build log from the first command. Errors, dead ends and fixes included. The log is the point of the exercise, not a by-product.
- Do the harder version where there is a choice. A single node local cluster with default settings does not exercise the things that break in real deployments.

## Phase 1: Toolchain baseline

- Install Syft, Grype and Grant.
- Generate SBOMs across a spread of target types: a container image, a filesystem directory, a source repository.
- Scan the generated SBOMs with Grype rather than scanning images directly, so the SBOM is the unit of work throughout.
- Include at least one real application with a messy dependency tree. A Python agent project built on LangGraph is a good target: transitive dependency depth is where SBOM generation gets interesting.
- Compare SPDX, CycloneDX and Syft's native JSON output for the same artefact. Record where they disagree and what each format drops.
- Run Grant and assess the licence picture separately from the vulnerability picture.
- Produce a VEX document suppressing a finding that is present in the SBOM but not reachable in the running application, and confirm it is respected.

The last point matters more than it looks. The distinction between a component being present and being exploitable is what separates a real finding from noise, and under a 24 hour reporting clock it is the difference between a notification and a non event.

**Record:** what Syft missed, what Grype flagged that was noise, scan duration against image size.

## Phase 2: Kubernetes cluster

Local via k3s or k3d, or a managed cluster on EKS or GKE. Budget at least 4 vCPU and 8 to 16 GB RAM once the supporting services are running.

Build the platform properly rather than accepting defaults:

- Multiple nodes, so scheduling and affinity are real rather than theoretical.
- A configured storage class, with persistent volume claims confirmed bound.
- An ingress controller with a real hostname resolving.
- Namespaces, RBAC and dedicated service accounts. Nothing running as cluster admin.
- Tooling: `kubectl`, `helm`, and a cluster inspection tool such as k9s.

Break things deliberately and record the diagnosis. A pod stuck in `Pending` on a storage class misconfiguration, or `CrashLoopBackOff` from a malformed secret, is worth more than a clean first run.

## Phase 3: Building the continuous inventory

The substance of the lab. Assemble the capability that commercial platforms provide and document where it strains.

**Registry.** Harbor, self hosted in cluster, as a real OCI registry with images pushed to it.

**Runtime inventory.** A CronJob enumerating the images actually running in the cluster via the Kubernetes API. This closes the gap between what the registry knows about and what is genuinely deployed.

**SBOM generation and storage.** Syft against each discovered image, SBOMs persisted to object storage such as MinIO, with a Postgres catalogue mapping image digest to stored SBOM.

**Continuous re-matching.** A scheduled job that refreshes the Grype vulnerability database and re-scans the stored SBOMs rather than re-pulling images.

This is the measurable claim of the whole approach, so measure it. Time and bandwidth for a full rescan of every running image, against time and bandwidth for re-matching stored SBOMs. Publish both numbers.

**Admission control.** Kyverno or OPA Gatekeeper enforcing policy on images before they schedule: vulnerability thresholds, approved base images, licence constraints. Anchore's own `kubernetes-admission-controller` exists but is built to talk to an Anchore backend, so verify whether it operates standalone before committing to it.

**Visibility.** A Grafana dashboard over the catalogue. Rough is acceptable; the question is what a security team would actually need to see.

**Open questions this phase should answer:**

- How does storage scale as image count and SBOM revision history grow?
- What happens on a base image update, when many SBOMs change at once?
- How is drift handled when a mutable tag points at a new digest?
- What is the false positive rate on re-matching, and how much does VEX reduce it?
- At what point does maintaining this stop being worth it? Image count, team size, or operational burden: the answer to that is the most useful output of the whole lab.

## Phase 4: CI integration

- `syft-action` and `scan-action` in the pipeline of a real repository. Verify current input names against the actions themselves.
- Fail the build on a policy violation, then fix the violation and confirm it passes. Both states documented.
- Publish the SBOM as a build artefact so there is a per commit record. This is the audit trail that a CRA reporting timeline actually requires.
- Push build time SBOMs into the Phase 3 catalogue so build time and runtime inventories converge in one place.

## Phase 5: Agentic interface

- Install `anchore/grype-mcp` and connect it to an MCP capable client.
- Add a pre push gate so SBOM generation and scanning run before anything reaches the remote, driven from the project's agent configuration.
- Stretch: expose the Phase 3 catalogue over MCP so questions like "which running images contain this package" can be asked conversationally against real cluster data.

## Phase 6: Turn the system on itself

The lab is a software supply chain in its own right. Every open source component it runs, and every artefact it produces, is in scope. Point the inventory at its own namespace and scan all of it.

**Scan everything, and enumerate it honestly first.** The component list is longer than it looks from the architecture diagram:

- Cluster runtime: k3s or the managed equivalent, containerd, CoreDNS
- Platform services: the ingress controller, cert-manager, the storage provisioner
- Harbor, which is not one image but a set of them, including its own bundled scanner. Scanning a scanner with a scanner is a fair test of whether the inventory is actually complete.
- MinIO, Postgres, Redis where present
- Grafana and anything it pulls in
- Kyverno or Gatekeeper, plus the policy bundles
- The Syft and Grype images used by the jobs
- The custom jobs and catalogue service written in Phase 3, scanned both as source and as built images

Nothing gets an exemption on the grounds that it is infrastructure. Infrastructure is where the unexamined dependencies live.

**Report the aggregate.** Total packages catalogued and total findings across the whole lab, before triage. For a setup this size the number will be large, and that number is the finding: it is the practical demonstration of why manual triage does not scale and why an inventory has to be queryable rather than readable.

**Base image commonality.** Count how many components share a base image, and how many findings a single base image update would clear. This is one of the few pieces of analysis that turns a vulnerability list into a work plan.

**Licences too.** Run Grant across every component, not just the interesting ones. A full licence inventory of the stack is something almost nobody produces for their own infrastructure, and copyleft obligations arriving through a transitive dependency are a real enterprise concern.

**Bootstrap ordering.** Admission control cannot gate the admission controller into existence, and the inventory job cannot scan the storage layer it depends on before that layer is running. Document the ordering, the exemptions required, and where the trust has to start.

**Self compliance.** Harbor, Postgres and Grafana images carry real vulnerabilities. It is likely the stack fails its own policy on first run. Decide what to do about it, exempt, pin, rebuild or accept, and record the reasoning. A system that cannot pass its own gate is a genuine finding, not an embarrassment to hide.

**Triage with VEX in earnest.** Most findings in third party infrastructure images will not be reachable in this deployment. Working through which ones are is the same judgement the CRA exploitability test demands, done against real data rather than a worked example. Record how far the finding count drops once VEX is applied.

**The test that matters.** Treat the lab as a product I am responsible for. Given a newly disclosed CVE in any component, how long does it take to answer whether it is present and whether it is reachable? If the answer is not minutes, the system does not do what it was built to do, and that is the honest result to publish.

Ship the lab's own SBOM, and the full component inventory, in the repository.

## Phase 7: Write up

The repository holds manifests, Helm values, CI workflows, MCP configuration and the lab's own SBOM. The README records what was built, what broke, what the measurements showed, what happened when the system was pointed at itself, and what the limits of a lab build are. Honest about scope: this is a lab, not a production system, and the differences are worth stating explicitly.

## Status

All seven phases complete. See the top-level `README.md` for the
write-up, `docs/build-log/` for the day-by-day account, and each
`phaseN-*/README.md` for the primary-source detail and numbered findings
behind it.
