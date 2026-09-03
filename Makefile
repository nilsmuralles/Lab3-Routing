.PHONY: venv run run-all test

venv:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt

run: ## make run NODE=A
	.venv/bin/python -m src.node --config config/$(NODE).json

run-all:
	.venv/bin/python -m src.harness.run_all

test:
	.venv/bin/python -m pytest tests/
