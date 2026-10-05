.PHONY: run build publish lint format test

PYTHON = uv run --env-file .env python

run:
	$(PYTHON) server.py

build:
	uv build

publish:
	uv publish

lint:
	$(PYTHON) -m ruff check . --fix

format:
	$(PYTHON) -m ruff format .

test:
	$(PYTHON) -m pytest test/ -v
