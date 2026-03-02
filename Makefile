.PHONY: \
	hw-preflight \
	ruff-lint \
	ruff-format \
	mypy-check \
	bandit-check \
	deps-audit \
	pytest-nohw \
	ci \
	arxiv-bundle \
	arxiv-pdflatex-2pass

PYTHON ?= python3
PIP_AUDIT ?= $(PYTHON) -m pip_audit
RUFF_FORMAT_SCOPE := tools/update_sha256sums.py tools/verify_paper_inputs.py tools/sync_status_docs.py tests/test_status_sync.py tests/test_verify_paper_inputs.py

hw-preflight:
	bash tools/hw/preflight_ubuntu24.sh

ruff-lint:
	ruff check . --config ruff.toml

ruff-format:
	ruff format --check $(RUFF_FORMAT_SCOPE)

mypy-check:
	mypy --config-file mypy.ini

bandit-check:
	bandit -q -r nema tools/verify_paper_inputs.py tools/update_sha256sums.py -lll

deps-audit:
	$(PIP_AUDIT) -r requirements-dev.txt --skip-editable --progress-spinner off

pytest-nohw:
	pytest -q -m "not hw and not integration"

ci: ruff-lint ruff-format mypy-check bandit-check deps-audit pytest-nohw

arxiv-bundle:
	bash tools/build_arxiv_bundle.sh

arxiv-pdflatex-2pass: arxiv-bundle
	rm -rf build/arxiv_bundle_ci
	mkdir -p build/arxiv_bundle_ci
	tar -xzf build/arxiv_bundle.tar.gz -C build/arxiv_bundle_ci
	cd build/arxiv_bundle_ci/paper && pdflatex -interaction=nonstopmode -halt-on-error -file-line-error paper.tex
	cd build/arxiv_bundle_ci/paper && pdflatex -interaction=nonstopmode -halt-on-error -file-line-error paper.tex
