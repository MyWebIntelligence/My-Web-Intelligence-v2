.PHONY: help test test-basic test-all test-cov test-quick test-apis test-integration lint lint-all typecheck clean install install-ml lock bench-cache bench-links bench-determinism

# Default target
.DEFAULT_GOAL := help

help: ## Show this help message
	@echo "MyWebIntelligence - Test Commands"
	@echo "=================================="
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Environment variables for API tests:"
	@echo "  MWI_SERPAPI_API_KEY     - SerpAPI key for search tests"
	@echo "  MWI_SEORANK_API_KEY     - SEO Rank API key"
	@echo "  MWI_OPENROUTER_API_KEY  - OpenRouter API key for LLM tests"

install: ## Install dependencies (base + dev group) into .venv via uv
	uv sync

install-ml: ## Install with optional ML extras (FAISS + transformers/torch)
	uv sync --extra ml

lock: ## Re-resolve and refresh uv.lock, then regenerate requirements.txt
	uv lock
	uv export --no-hashes --no-default-groups --no-emit-project --no-annotate -o requirements.txt

lint: ## BLOCKING in CI: the bug-class subset of flake8 (syntax, undefined names)
	@echo "Linting (bug class only: E9,F63,F7,F82)..."
	uv run --locked flake8 mwi tests --count --select=E9,F63,F7,F82 --show-source --statistics

# BLOCKING in CI since 2026-09-19 (both targets below). Caveat worth knowing:
# flake8's verdict DEPENDS ON THE INTERPRETER RUNNING IT. Since Python 3.12
# (PEP 701) the tokenizer emits tokens inside f-string replacement fields, so
# pycodestyle finally inspects them -- `f"{getattr(x,'y','')}"` is 2 x E231 on
# 3.12 and silent on 3.11. The CI `quality` job runs 3.12 and is therefore the
# authority; a local `.venv` on 3.11 UNDER-reports. To reproduce the CI verdict:
#   uv run --locked --python 3.12 flake8 mwi/ --count
# Be aware it REBUILDS .venv under 3.12; the next `make test` rebuilds it back.
# That churn is why the version is not pinned in the recipes themselves.
lint-all: ## BLOCKING in CI: the full flake8 report
	@echo "Full flake8 report..."
	uv run --locked flake8 mwi/ --count --statistics

# mypy must run ON the floor it is configured to CHECK. `[tool.mypy]
# python_version = "3.10"` asks it to reason as 3.10; in a 3.12 venv the INSTALLED
# numpy stubs use PEP 695 (`type X = ...`) and mypy then refuses to read them --
# "Type statement is only supported in Python 3.12 and greater", an error coming
# from a dependency, not from our code. The CI `types` job pins 3.10 for exactly
# this reason. Locally the default .venv (3.11) also passes; 3.12 does not.
typecheck: ## BLOCKING in CI: mypy on the mwi package (CI pins Python 3.10)
	@echo "Type checking..."
	uv run --locked mypy mwi

test: test-basic ## Run basic tests (no API keys required) - alias for test-basic

test-basic: ## Run basic tests without API keys
	@echo "Running basic tests (no API keys required)..."
	PYTHONPATH=. uv run pytest tests/ -v -m "not (serpapi or seorank or openrouter or mercury or playwright or integration)"

test-all: ## Run all tests including those requiring API keys
	@echo "Running all tests..."
	PYTHONPATH=. uv run pytest tests/ -v

test-quick: ## Quick smoke test (installation only)
	@echo "Running quick smoke test..."
	PYTHONPATH=. uv run pytest tests/test_01_installation.py -v

test-cov: ## Run tests with coverage report
	@echo "Running tests with coverage..."
	PYTHONPATH=. uv run pytest tests/ --cov=mwi --cov-report=html --cov-report=term -m "not (serpapi or seorank or openrouter or mercury or playwright or integration)"
	@echo ""
	@echo "Coverage report generated: htmlcov/index.html"

test-cov-open: test-cov ## Run tests with coverage and open report
	@echo "Opening coverage report..."
	@command -v open >/dev/null 2>&1 && open htmlcov/index.html || \
	command -v xdg-open >/dev/null 2>&1 && xdg-open htmlcov/index.html || \
	command -v start >/dev/null 2>&1 && start htmlcov/index.html || \
	echo "Please open htmlcov/index.html manually"

test-apis: ## Run API tests (requires API keys)
	@echo "Running API tests..."
	@if [ -z "$$MWI_SERPAPI_API_KEY" ] && [ -z "$$MWI_SEORANK_API_KEY" ] && [ -z "$$MWI_OPENROUTER_API_KEY" ]; then \
		echo "Warning: No API keys set. Tests will be skipped."; \
		echo "Set MWI_SERPAPI_API_KEY, MWI_SEORANK_API_KEY, or MWI_OPENROUTER_API_KEY"; \
	fi
	PYTHONPATH=. uv run pytest tests/ -v -m "serpapi or seorank or openrouter"

test-integration: ## Run integration tests (slow, requires APIs)
	@echo "Running integration tests..."
	PYTHONPATH=. uv run pytest tests/ -v -m "integration"

# Body-links benchmark (sprint body-links, T0)
MWI_BENCH_DB   ?= benchmarks/body_links/cache/bench_corpus_v1.sqlite
MWI_BENCH_GOLD ?= benchmarks/body_links/gold_v1.csv
MWI_BENCH_OUT  ?= benchmarks/body_links/out

bench-cache: ## Build the offline bench corpus once (needs MWI_BENCH_SOURCE_DB)
	@if [ -z "$$MWI_BENCH_SOURCE_DB" ]; then \
		echo "Set MWI_BENCH_SOURCE_DB=/path/to/the/land/mwi.db"; exit 1; fi
	PYTHONPATH=. uv run python scripts/build_bench_cache.py \
		--source-db="$$MWI_BENCH_SOURCE_DB" --gold="$(MWI_BENCH_GOLD)" \
		--out="$(MWI_BENCH_DB)"

bench-links: ## Run the body-links benchmark (offline, deterministic)
	@test -f "$(MWI_BENCH_DB)" || { \
		echo "Missing bench corpus: $(MWI_BENCH_DB)"; \
		echo "Build it once: make bench-cache MWI_BENCH_SOURCE_DB=/path/to/mwi.db"; \
		exit 1; }
	PYTHONPATH=. uv run python -m mwi.benchmark_body_links \
		--corpus="$(MWI_BENCH_DB)" --gold="$(MWI_BENCH_GOLD)" \
		--out-dir="$(MWI_BENCH_OUT)"

bench-determinism: ## Two runs, different hash seeds, byte-identical outputs
	PYTHONHASHSEED=0 PYTHONPATH=. uv run python -m mwi.benchmark_body_links \
		--corpus="$(MWI_BENCH_DB)" --gold="$(MWI_BENCH_GOLD)" \
		--out-dir="$(MWI_BENCH_OUT)/a"
	PYTHONHASHSEED=1 PYTHONPATH=. uv run python -m mwi.benchmark_body_links \
		--corpus="$(MWI_BENCH_DB)" --gold="$(MWI_BENCH_GOLD)" \
		--out-dir="$(MWI_BENCH_OUT)/b"
	cmp "$(MWI_BENCH_OUT)/a/bench_edges.csv"   "$(MWI_BENCH_OUT)/b/bench_edges.csv"
	cmp "$(MWI_BENCH_OUT)/a/bench_summary.txt" "$(MWI_BENCH_OUT)/b/bench_summary.txt"
	@echo "Deterministic: OK"

test-01: ## Run test_01_installation.py
	PYTHONPATH=. uv run pytest tests/test_01_installation.py -v

test-02: ## Run test_02_land_management.py
	PYTHONPATH=. uv run pytest tests/test_02_land_management.py -v

test-03: ## Run test_03_data_collection.py
	PYTHONPATH=. uv run pytest tests/test_03_data_collection.py -v -m "not (serpapi or seorank or openrouter)"

test-04: ## Run test_04_export.py
	PYTHONPATH=. uv run pytest tests/test_04_export.py -v

test-05: ## Run test_05_media_analysis.py
	PYTHONPATH=. uv run pytest tests/test_05_media_analysis.py -v

clean: ## Clean test artifacts and cache
	@echo "Cleaning test artifacts..."
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf .coverage
	rm -rf __pycache__
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	@echo "Clean complete"

list-tests: ## List all available tests
	@echo "Listing all tests..."
	PYTHONPATH=. uv run pytest tests/ --collect-only -q

list-markers: ## Show available pytest markers
	@echo "Available pytest markers:"
	PYTHONPATH=. uv run pytest --markers | grep -A 1 "@pytest.mark"

check: test-quick test-cov ## Run quick test + coverage (recommended for CI)

# JOSS evaluation commands
joss-install: install ## Install for JOSS evaluation
	@echo "Installation complete for JOSS evaluation"
	@echo "Run 'make joss-test' to run all tests"

joss-test: ## Run tests for JOSS evaluation
	@echo "======================================"
	@echo "JOSS Evaluation Test Suite"
	@echo "======================================"
	@echo ""
	@echo "1. Running basic tests..."
	@$(MAKE) test-basic
	@echo ""
	@echo "2. Generating coverage report..."
	@$(MAKE) test-cov
	@echo ""
	@echo "======================================"
	@echo "JOSS Evaluation Complete"
	@echo "======================================"
	@echo ""
	@echo "Results:"
	@echo "  - All basic tests passed ✓"
	@echo "  - Coverage report: htmlcov/index.html"
	@echo ""
	@echo "Optional: Run 'make test-apis' if you have API keys configured"
