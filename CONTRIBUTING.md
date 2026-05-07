# Contributing to My Web Intelligence

Thank you for your interest in contributing to My Web Intelligence (MWI)! This document provides guidelines and instructions for contributing.

## How to Contribute

### Reporting Bugs

If you find a bug, please open an issue on GitHub with:

1. A clear, descriptive title
2. Steps to reproduce the bug
3. Expected behavior vs. actual behavior
4. Your environment (Python version, OS, Docker version if applicable)
5. Relevant log output or error messages

### Suggesting Features

Feature requests are welcome! Please open an issue with:

1. A clear description of the feature
2. The use case / research scenario it addresses
3. Any implementation ideas you have

### Submitting Pull Requests

1. **Fork the repository** and create your branch from `master`
2. **Set up your development environment**:
   ```bash
   git clone https://github.com/YOUR_USERNAME/mwi.git
   cd mwi
   python -m venv venv
   source venv/bin/activate  # or venv\Scripts\activate on Windows
   pip install -r requirements.txt
   pip install -r requirements-dev.txt  # if available
   ```

3. **Make your changes** following the code style guidelines below

4. **Write or update tests** for your changes:
   ```bash
   make test
   # or
   PYTHONPATH=. pytest tests/ -v
   ```

5. **Run code quality checks**:
   ```bash
   flake8 mwi/
   mypy mwi/
   ```

6. **Commit your changes** with a clear commit message:
   ```
   Add feature X for research scenario Y

   - Detailed description of changes
   - Any breaking changes noted
   ```

7. **Push and open a Pull Request** against the `master` branch

## Code Style Guidelines

### Python Style

- Follow [PEP 8](https://pep8.org/) conventions
- Use meaningful variable and function names
- Maximum line length: 120 characters
- Use type hints where practical

### Documentation

- Document public functions and classes with docstrings
- Update README.md if adding new features or changing CLI commands

### Testing

- Write tests for new functionality
- Ensure existing tests pass before submitting PR (303 tests passing on main)
- Target >85% code coverage for new code
- Use pytest fixtures from `tests/conftest.py`
- For HTTP-based tests, prefer `aioresponses` (async) or `responses` (sync)
  over patching internal helpers — see existing tests `17–25` as examples.
- New tests must follow the `tests/test_NN_topic.py` flat layout and
  numerical ordering (next free slot: `test_26_*.py`)

## Development Setup

### Basic Setup

```bash
# Clone and install
git clone https://github.com/MyWebIntelligence/mwi.git
cd mwi
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Initialize database
python mywi.py db setup

# Run tests
make test
```

### Optional Dependencies

```bash
# For Mercury Parser (content extraction)
npm install -g @postlight/mercury-parser

# For Playwright (dynamic media extraction)
python install_playwright.py

# For ML features (embeddings, NLI)
pip install -r requirements-ml.txt
```

### Docker Development

```bash
# Build and run
docker compose up -d --build

# Execute commands
docker compose exec mwi python mywi.py land list

# View logs
docker compose logs -f mwi
```

## Project Structure

```
mwi/
├── cli.py              # Command-line interface
├── controller.py       # Business logic controllers
├── core.py             # Core algorithms
├── model.py            # Database schema (Peewee ORM)
├── export.py           # Export functionality
├── fetcher.py          # Cascade fetch strategies (sprint-403)
├── browser_pool.py     # Shared Playwright pool (sprint-403)
├── url_normalizer.py   # URL canonicalization (sprint-normalise)
└── ...                 # Other modules

tests/
├── conftest.py             # Shared fixtures
├── fixtures/               # Test data
├── test_01..08*.py         # Core JOSS test suite
├── test_09_url_normalize.py   # sprint-normalise
├── test_10_fetcher.py        # sprint-403 cascade core
├── test_11_curl_cffi_*.py    # sprint-403 curl_cffi
├── test_12_playwright_*.py   # sprint-403 Playwright
├── test_13_fetch_method.py   # sprint-403 audit column
├── test_14_retry_status.py   # sprint-403 backfill CLI
├── test_15_dynamic_media_pool.py  # sprint-403 BrowserPool sharing
├── test_16_serpapi_router.py # legacy SerpAPI single-engine router (`land urlist`)
├── test_17_search_models.py  # sprint-searchrouter — Peewee + dataclasses
├── test_18_search_provider_searxng.py  # sprint-searchrouter — SearXNG adapter
├── test_19_search_provider_brave.py    # sprint-searchrouter — Brave adapter
├── test_20_search_provider_serper.py   # sprint-searchrouter — Serper adapter
├── test_21_search_provider_serpapi.py  # sprint-searchrouter — SerpAPI adapter
├── test_22_search_provider_tavily.py   # sprint-searchrouter — Tavily adapter
├── test_23_search_router.py            # sprint-searchrouter — orchestration
├── test_24_search_controller.py        # sprint-searchrouter — CLI integration
└── test_25_search_integration.py       # sprint-searchrouter — end-to-end
```

**Mock HTTP for new tests**: prefer `aioresponses` (already used by tests
17–25) over patching internals. Pattern:

```python
from aioresponses import aioresponses
with aioresponses() as m:
    m.get("https://api.example/search", payload={"results": [...]})
    # … run async code that uses aiohttp.ClientSession
```

## Questions?

- Open an issue for questions about contributing
- Check existing issues and discussions first
- For research methodology questions, see the JOSS paper

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
