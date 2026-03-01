SHELL := /usr/bin/env bash

REPO_ROOT := $(abspath $(CURDIR)/../..)
TEXT_DIR := $(CURDIR)/text
ART_DIR := $(CURDIR)/artifacts
SCRIPT_DIR := $(ART_DIR)/scripts

PAPER_TEX := $(TEXT_DIR)/paper.tex
PAPER_PDF := $(TEXT_DIR)/paper.pdf

.PHONY: paper clean artifacts check

paper:
	@if command -v latexmk >/dev/null 2>&1; then \
		latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=$(TEXT_DIR) $(PAPER_TEX); \
		echo "PDF generated: $(PAPER_PDF)"; \
	else \
		echo "latexmk not found in PATH."; \
		echo "Install TeX tooling, then run:"; \
		echo "  latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=$(TEXT_DIR) $(PAPER_TEX)"; \
	fi

clean:
	@if command -v latexmk >/dev/null 2>&1; then \
		latexmk -C -outdir=$(TEXT_DIR) $(PAPER_TEX) || true; \
	fi
	@rm -f $(TEXT_DIR)/*.aux $(TEXT_DIR)/*.bbl $(TEXT_DIR)/*.bcf $(TEXT_DIR)/*.blg \
		$(TEXT_DIR)/*.fdb_latexmk $(TEXT_DIR)/*.fls $(TEXT_DIR)/*.log $(TEXT_DIR)/*.out \
		$(TEXT_DIR)/*.run.xml $(TEXT_DIR)/*.toc

artifacts:
	@bash $(SCRIPT_DIR)/regenerate_artifacts.sh

check:
	@cd $(REPO_ROOT) && python -m pytest -q
	@cd $(REPO_ROOT) && python tools/audit_min.py --mode software > $(ART_DIR)/evidence/audit_software.json
	@cd $(REPO_ROOT) && python tools/audit_min.py --mode hardware > $(ART_DIR)/evidence/audit_hardware.json
	@$(MAKE) artifacts
	@bash $(SCRIPT_DIR)/validate_artifacts.sh
	@echo "check: OK"
