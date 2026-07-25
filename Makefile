# netdust-flow — the commands CI runs, runnable locally by the same names.
.PHONY: help deps test lint compile check

help:
	@echo "make deps     install authoring-side dependencies"
	@echo "make test     run the suite"
	@echo "make lint     lint every flow (built-in + examples)"
	@echo "make compile  recompile .json twins from their .yaml sources"
	@echo "make check    lint + test — the gate command for this repo"

deps:
	pip install -r requirements-dev.txt

test:
	python3 -m pytest tests/ -q

lint:
	python3 bin/flow-lint.py flows/*.yaml examples/*/flow.yaml

compile:
	python3 bin/flow-lint.py flows/*.yaml --compile

# `make check` is this repo's own gate command (see CLAUDE.md): the
# thing that has to be green before work advances.
check: lint test
