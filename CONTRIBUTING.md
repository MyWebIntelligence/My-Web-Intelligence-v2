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
- Ensure existing tests pass before submitting PR
- Target >85% code coverage for new code
- Use pytest fixtures from `tests/conftest.py`

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
├── cli.py          # Command-line interface
├── controller.py   # Business logic controllers
├── core.py         # Core algorithms
├── model.py        # Database schema (Peewee ORM)
├── export.py       # Export functionality
└── ...             # Other modules

tests/
├── conftest.py     # Shared fixtures
├── fixtures/       # Test data
└── test_*.py       # Test files
```

## Questions?

- Open an issue for questions about contributing
- Check existing issues and discussions first
- For research methodology questions, see the JOSS paper

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
