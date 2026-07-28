PYTHON ?= python3
SOURCE_ROOT ?= .sources

.PHONY: check extract site sources serve

sources:
	$(PYTHON) scripts/fetch_sources.py --destination "$(SOURCE_ROOT)"

extract:
	$(PYTHON) scripts/validate.py --source-root "$(SOURCE_ROOT)" --extract-only

site:
	$(PYTHON) -m mkdocs build --strict

check:
	$(PYTHON) scripts/validate.py --source-root "$(SOURCE_ROOT)"
	$(PYTHON) -m mkdocs build --strict

serve:
	$(PYTHON) -m mkdocs serve
