.PHONY: toolchain mcp-server mcp-server-scan image-scan repo-scan cluster clean-cluster help

help:
	@echo "Targets:"
	@echo "  toolchain         install/verify syft, grype, grant, docker(colima), kubectl, helm, k3d, k9s"
	@echo "  mcp-server        create venv and install sbom-mcp-server"
	@echo "  mcp-server-scan   run a full syft->grype->grant scan against a TARGET (default: this repo)"
	@echo "  image-scan        SBOM (3 formats) + grype + VEX for an IMAGE (default: python:3.12-slim)"
	@echo "  repo-scan         shallow-clone a REPO and SBOM it as a source-repo target"
	@echo "  cluster           bring up the Phase 2 k3d cluster (not yet implemented)"
	@echo "  clean-cluster     tear down the Phase 2 k3d cluster (not yet implemented)"

toolchain:
	./phase1-toolchain/install.sh

mcp-server:
	cd phase5-agentic/sbom-mcp-server && \
	python3 -m venv .venv && \
	. .venv/bin/activate && \
	pip install -q --upgrade pip && \
	pip install -q -e ".[dev]"

TARGET ?= dir:.
mcp-server-scan:
	cd phase5-agentic/sbom-mcp-server && \
	. .venv/bin/activate && \
	python3 -c "import json,sys; from sbom_mcp_server import tools; print(json.dumps(tools.full_scan('$(TARGET)', workdir='/tmp/sbom-mcp-scan'), indent=2))"

IMAGE ?= python:3.12-slim
VEX ?= vex/python-3.12-slim.openvex.json
image-scan:
	cd phase1-toolchain && ./scan-image.sh "$(IMAGE)" "$(VEX)"

REPO ?= https://github.com/anchore/grype-mcp
repo-scan:
	mkdir -p phase1-toolchain/repos
	name=$$(basename "$(REPO)" .git); \
	[ -d "phase1-toolchain/repos/$$name" ] || git clone --depth 1 "$(REPO)" "phase1-toolchain/repos/$$name"; \
	syft scan "dir:phase1-toolchain/repos/$$name" -o syft-json > "phase1-toolchain/sboms/$$name-repo.syft-json.json"; \
	echo "SBOM written to phase1-toolchain/sboms/$$name-repo.syft-json.json"

cluster:
	cd phase2-cluster && ./bootstrap.sh

clean-cluster:
	k3d cluster delete anchore-lab
