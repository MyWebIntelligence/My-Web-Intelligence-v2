.PHONY: help test test-basic test-all test-cov test-quick test-apis test-integration clean install

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

install: ## Install dependencies
	pip install -r requirements.txt

test: test-basic ## Run basic tests (no API keys required) - alias for test-basic

test-basic: ## Run basic tests without API keys
	@echo "Running basic tests (no API keys required)..."
	PYTHONPATH=. pytest tests/ -v -m "not (serpapi or seorank or openrouter or mercury or playwright or integration)"

test-all: ## Run all tests including those requiring API keys
	@echo "Running all tests..."
	PYTHONPATH=. pytest tests/ -v

test-quick: ## Quick smoke test (installation only)
	@echo "Running quick smoke test..."
	PYTHONPATH=. pytest tests/test_01_installation.py -v

test-cov: ## Run tests with coverage report
	@echo "Running tests with coverage..."
	PYTHONPATH=. pytest tests/ --cov=mwi --cov-report=html --cov-report=term -m "not (serpapi or seorank or openrouter or mercury or playwright or integration)"
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
	PYTHONPATH=. pytest tests/ -v -m "serpapi or seorank or openrouter"

test-integration: ## Run integration tests (slow, requires APIs)
	@echo "Running integration tests..."
	PYTHONPATH=. pytest tests/ -v -m "integration"

test-01: ## Run test_01_installation.py
	PYTHONPATH=. pytest tests/test_01_installation.py -v

test-02: ## Run test_02_land_management.py
	PYTHONPATH=. pytest tests/test_02_land_management.py -v

test-03: ## Run test_03_data_collection.py
	PYTHONPATH=. pytest tests/test_03_data_collection.py -v -m "not (serpapi or seorank or openrouter)"

test-04: ## Run test_04_export.py
	PYTHONPATH=. pytest tests/test_04_export.py -v

test-05: ## Run test_05_media_analysis.py
	PYTHONPATH=. pytest tests/test_05_media_analysis.py -v

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
	PYTHONPATH=. pytest tests/ --collect-only -q

list-markers: ## Show available pytest markers
	@echo "Available pytest markers:"
	PYTHONPATH=. pytest --markers | grep -A 1 "@pytest.mark"

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
