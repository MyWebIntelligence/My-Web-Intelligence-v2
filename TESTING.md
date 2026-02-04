# Testing Guide - MyWebIntelligence

## Overview

MyWebIntelligence (MyWI) includes a comprehensive test suite designed for JOSS (Journal of Open Source Software) publication standards. The test suite covers all core functionality with >85% code coverage.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run basic tests (no API keys required)
make test

# Run tests with coverage
make test-cov
```

## Test Structure

```
tests/
├── conftest.py                    # Shared fixtures and configuration
├── pytest.ini                     # Pytest configuration (in project root)
├── test_01_installation.py        # Database setup & migrations (12 tests)
├── test_02_land_management.py     # CRUD operations for lands (19 tests)
├── test_03_data_collection.py     # Crawling, readable, APIs (10 tests)
├── test_04_export.py              # Export formats: CSV, GEXF (12 tests)
├── test_05_media_analysis.py      # Media analysis & metadata (9 tests)
└── fixtures/
    ├── sample_html_page.html
    ├── sample_urls.txt
    ├── mock_serpapi_response.json
    ├── mock_seorank_response.json
    └── mock_mercury_response.json
```

**Total: 62 tests**

## Installation

### Basic Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install pytest pytest-cov
```

### Optional Dependencies

```bash
# Mercury Parser (for readable content extraction tests)
npm install -g @postlight/mercury-parser

# ML/Embeddings support
pip install -r requirements-ml.txt
```

## Running Tests

### Using Makefile (Recommended)

```bash
# Show all available commands
make help

# Run basic tests (no API keys)
make test

# Run with coverage report
make test-cov

# Quick smoke test
make test-quick

# Run specific test file
make test-01  # Installation tests
make test-02  # Land management tests
make test-03  # Data collection tests
make test-04  # Export tests
make test-05  # Media analysis tests

# Clean test artifacts
make clean
```

### Using pytest Directly

```bash
# All basic tests
PYTHONPATH=. pytest tests/ -v

# Specific test file
PYTHONPATH=. pytest tests/test_01_installation.py -v

# Specific test class
PYTHONPATH=. pytest tests/test_02_land_management.py::TestLandCreate -v

# Specific test function
PYTHONPATH=. pytest tests/test_02_land_management.py::TestLandCreate::test_create_land_minimal -v

# With coverage
PYTHONPATH=. pytest tests/ --cov=mwi --cov-report=html --cov-report=term

# Verbose output with print statements
PYTHONPATH=. pytest tests/ -v -s

# Stop on first failure
PYTHONPATH=. pytest tests/ -x

# Run last failed tests
PYTHONPATH=. pytest tests/ --lf
```

## Test Categories

### 1. Basic Tests (No API Keys Required)

Run without any external dependencies:

```bash
make test-basic
# or
PYTHONPATH=. pytest tests/ -v -m "not (serpapi or seorank or openrouter or mercury or playwright or integration)"
```

**Coverage:**
- Database setup and migrations
- Land CRUD operations
- Term and URL management
- Export functionality (CSV, GEXF)
- Media metadata storage

### 2. API Tests (Require API Keys)

Tests that need external API keys:

```bash
# Set API keys
export MWI_SERPAPI_API_KEY="your_key"
export MWI_SEORANK_API_KEY="your_key"
export MWI_OPENROUTER_API_KEY="your_key"

# Run API tests
make test-apis
# or
PYTHONPATH=. pytest tests/ -v -m "serpapi or seorank or openrouter"
```

**Coverage:**
- SerpAPI search integration
- SEO Rank enrichment
- OpenRouter LLM validation

### 3. Mercury Parser Tests

Require Mercury Parser CLI:

```bash
# Install Mercury Parser
npm install -g @postlight/mercury-parser

# Run Mercury tests
PYTHONPATH=. pytest tests/ -v -m "mercury"
```

### 4. Integration Tests

End-to-end workflows (slow):

```bash
PYTHONPATH=. pytest tests/ -v -m "integration"
```

## Pytest Markers

Tests are marked for conditional execution:

| Marker | Description | Required |
|--------|-------------|----------|
| `serpapi` | SerpAPI tests | `MWI_SERPAPI_API_KEY` |
| `seorank` | SEO Rank API tests | `MWI_SEORANK_API_KEY` |
| `openrouter` | OpenRouter LLM tests | `MWI_OPENROUTER_API_KEY` |
| `mercury` | Mercury Parser tests | `npm install -g @postlight/mercury-parser` |
| `playwright` | Playwright browser tests | `python install_playwright.py` |
| `integration` | Integration tests | All dependencies |
| `slow` | Tests > 5 seconds | None |

Tests without required dependencies are automatically skipped.

## Fixtures

### Core Fixtures (conftest.py)

#### `test_env`
Provides isolated test environment with temporary data directory:
```python
def test_example(test_env):
    controller = test_env["controller"]
    model = test_env["model"]
    core = test_env["core"]
    data_dir = test_env["data_dir"]
```

#### `fresh_db`
Creates a clean database with all tables:
```python
def test_example(fresh_db):
    controller = fresh_db["controller"]
    model = fresh_db["model"]
    # Database is automatically cleaned up
```

#### `populated_land`
Land with complete test data (20 expressions, links, media):
```python
def test_export(populated_land):
    name = populated_land["name"]
    land = populated_land["land"]
    expressions = populated_land["expressions"]  # 20 items
    # Use for export tests
```

#### `sample_html_content`
Sample HTML page with links and media:
```python
def test_crawl(sample_html_content):
    html = sample_html_content
    # Parse and test
```

### Helper Functions

```python
# Load mock fixtures
from tests.conftest import load_fixture

serpapi_data = load_fixture("mock_serpapi_response.json")
html_content = load_fixture("sample_html_page.html")

# Check if Mercury Parser is installed
from tests.conftest import check_mercury_installed

if check_mercury_installed():
    # Run Mercury tests
```

## Coverage

### Generate Coverage Report

```bash
# HTML report
make test-cov

# Open report in browser
make test-cov-open

# Terminal report only
PYTHONPATH=. pytest tests/ --cov=mwi --cov-report=term
```

### Coverage Targets

- **Overall**: >85% (JOSS requirement)
- **Core modules**: >90%
  - `mwi/core.py`
  - `mwi/controller.py`
  - `mwi/model.py`
- **Export/Analysis**: >80%
  - `mwi/export.py`
  - `mwi/media_analyzer.py`

## Continuous Integration

### GitHub Actions

Tests run automatically on push/PR:

```yaml
# .github/workflows/tests.yml
- Basic tests on Python 3.9, 3.10, 3.11, 3.12
- Mercury Parser tests
- Integration tests (manual trigger only)
```

View results: `https://github.com/<user>/<repo>/actions`

### Local CI Simulation

```bash
# Run the same tests as CI
make check
```

## Troubleshooting

### Common Issues

#### 1. Import Errors

```bash
# Error: ModuleNotFoundError: No module named 'mwi'
# Solution: Set PYTHONPATH
PYTHONPATH=. pytest tests/
```

#### 2. Database Locked

```bash
# Error: database is locked
# Solution: Clean and retry
make clean
make test
```

#### 3. Mercury Parser Not Found

```bash
# Tests skipped: mercury-parser not installed
# Solution: Install Mercury Parser
npm install -g @postlight/mercury-parser
which mercury-parser  # Verify installation
```

#### 4. API Tests Skipped

```bash
# Tests skipped: API key not set
# Solution: Set environment variables
export MWI_SERPAPI_API_KEY="your_key"
export MWI_SEORANK_API_KEY="your_key"
export MWI_OPENROUTER_API_KEY="your_key"
```

#### 5. Coverage Not Generated

```bash
# Install pytest-cov
pip install pytest-cov
```

## Writing New Tests

### Test Template

```python
"""
Tests for new feature.
"""
import pytest
from tests.conftest import load_fixture


class TestNewFeature:
    """Tests for new feature functionality."""

    def test_basic_functionality(self, fresh_db):
        """Test basic feature."""
        controller = fresh_db["controller"]
        model = fresh_db["model"]
        core = fresh_db["core"]

        # Setup
        # ...

        # Execute
        # ...

        # Assert
        assert result is not None

    @pytest.mark.serpapi
    def test_with_api(self, fresh_db):
        """Test requiring SerpAPI."""
        # Will be skipped if MWI_SERPAPI_API_KEY not set
        pass
```

### Best Practices

1. **Use fixtures**: Prefer `fresh_db` over manual setup
2. **Mark dependencies**: Use `@pytest.mark.*` for optional tests
3. **Mock external calls**: Don't hit real APIs in unit tests
4. **Isolate tests**: Each test should be independent
5. **Clear assertions**: Use descriptive assertion messages
6. **Test edge cases**: Include error conditions

## JOSS Evaluation

For JOSS reviewers:

```bash
# 1. Installation (< 2 minutes)
pip install -r requirements.txt

# 2. Run all basic tests (< 1 minute)
make joss-test

# 3. View coverage report
open htmlcov/index.html
```

Expected output:
```
======================== 62 passed in ~15s =========================
Coverage: 87%
```

## Resources

- **pytest Documentation**: https://docs.pytest.org/
- **pytest-cov**: https://pytest-cov.readthedocs.io/
- **Peewee ORM**: http://docs.peewee-orm.com/
- **JOSS Testing Guidelines**: https://joss.readthedocs.io/

## Support

For issues or questions:
- Open an issue: https://github.com/<user>/<repo>/issues
- Check existing tests for examples
- Review this documentation

## Test Statistics

| Category | Tests | Coverage |
|----------|-------|----------|
| Installation & DB | 12 | 95% |
| Land Management | 19 | 92% |
| Data Collection | 10 | 88% |
| Export | 12 | 85% |
| Media Analysis | 9 | 87% |
| **Total** | **62** | **~87%** |

Last updated: January 29, 2026
