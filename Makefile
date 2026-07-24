PYTHON ?= python3

.PHONY: validate test lint smoke deploy-check

validate:
	$(PYTHON) scripts/validate_examples.py

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check reposkop steuerboard tests scripts

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
	$(PYTHON) -m reposkop inspect "$$tmp" --json | $(PYTHON) -m json.tool >/dev/null; \
	$(PYTHON) -m reposkop report "$$tmp" --json | $(PYTHON) -m json.tool >/dev/null; \
	$(PYTHON) -m steuerboard observe repo "$$tmp" --json | $(PYTHON) -m json.tool >/dev/null; \
	echo "smoke: passed"

deploy-check: validate lint test smoke
	@echo "deploy-check: passed"
