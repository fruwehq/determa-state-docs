PYTHON ?= python3
SOURCE_ROOT ?= .sources

.PHONY: check extract site sources candidate-install serve

sources:
	$(PYTHON) scripts/fetch_sources.py --destination "$(SOURCE_ROOT)"

candidate-install:
	$(PYTHON) scripts/install_candidate.py

extract:
	$(PYTHON) scripts/validate.py --source-root "$(SOURCE_ROOT)" --extract-only

site:
	$(PYTHON) -m mkdocs build --strict

check:
	$(PYTHON) scripts/check_publication_hold.py
	$(PYTHON) -m pytest -q tests/test_publication_hold.py
	$(PYTHON) scripts/validate.py --source-root "$(SOURCE_ROOT)"
	$(PYTHON) -m mkdocs build --strict

serve:
	$(PYTHON) -m mkdocs serve
