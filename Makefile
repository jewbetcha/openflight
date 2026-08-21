.PHONY: test test-ui lint format dev build-ui start

## Run Python tests
test:
	uv run pytest tests/ -v

## Run UI unit tests
test-ui:
	cd ui && npm run test

## Run all linters (Python + UI)
lint:
	uv run ruff check src/openflight/ tests/
	uv run pylint src/openflight/ --fail-under=9
	cd ui && npm run lint

## Auto-format Python code
format:
	uv run ruff format src/openflight/ tests/
	uv run ruff check --fix src/openflight/ tests/

## Start server in mock mode (no hardware needed)
dev:
	scripts/start-kiosk.sh --mock

## Build the React UI
build-ui:
	cd ui && npm install && npm run build

## Start the full application (requires hardware)
start:
	scripts/start-kiosk.sh

## Install all dependencies (Python + UI)
install:
	uv sync --group dev
	cd ui && npm install

## Install pre-commit hooks
hooks:
	uv run pre-commit install
