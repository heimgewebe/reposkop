PYTHON ?= python3

.PHONY: validate test lint smoke deploy-check

validate:
	$(PYTHON) scripts/validate_examples.py

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check reposkop tests scripts

smoke:
	@set -eu; \
	tmp="$$(mktemp -d)"; \
	trap 'rm -rf "$$tmp"' EXIT INT TERM; \
	git -C "$$tmp" init -q; \
	git -C "$$tmp" config user.email reposkop@example.invalid; \
	git -C "$$tmp" config user.name Reposkop; \
	printf 'ok\n' > "$$tmp/file.txt"; \
	git -C "$$tmp" add file.txt; \
	git -C "$$tmp" commit -qm init; \
	$(PYTHON) -m reposkop inspect "$$tmp" --purpose smoke --json > "$$tmp/before.json"; \
	$(PYTHON) -m reposkop report "$$tmp" --purpose smoke --json | $(PYTHON) -m json.tool >/dev/null; \
	$(PYTHON) -m reposkop transition "$$tmp" --before "$$tmp/before.json" --purpose smoke --json | $(PYTHON) -m json.tool >/dev/null; \
	$(PYTHON) -m reposkop continuity "$$tmp" --expected "$$tmp/before.json" --purpose smoke --json | $(PYTHON) -m json.tool >/dev/null; \
	$(PYTHON) -m reposkop validate "$$tmp/before.json" --json | $(PYTHON) -m json.tool >/dev/null; \
	echo "smoke: passed"

deploy-check: validate lint test smoke
	@echo "deploy-check: passed"
