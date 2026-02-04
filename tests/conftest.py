import os
import shutil
import importlib
import sys
import json
from datetime import datetime
import pytest


# =============================================================================
# Helper Functions
# =============================================================================

def check_mercury_installed():
    """Vérifie si mercury-parser CLI est disponible."""
    return shutil.which("mercury-parser") is not None


def load_fixture(filename):
    """Charge un fichier fixture JSON/text depuis tests/fixtures/."""
    fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures")
    path = os.path.join(fixtures_dir, filename)
    with open(path, "r", encoding="utf-8") as f:
        if filename.endswith(".json"):
            return json.load(f)
        else:
            return f.read()


# =============================================================================
# Pytest Markers Configuration
# =============================================================================

def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line(
        "markers", "serpapi: requires MWI_SERPAPI_API_KEY environment variable"
    )
    config.addinivalue_line(
        "markers", "seorank: requires MWI_SEORANK_API_KEY environment variable"
    )
    config.addinivalue_line(
        "markers", "openrouter: requires MWI_OPENROUTER_API_KEY environment variable"
    )
    config.addinivalue_line(
        "markers", "mercury: requires mercury-parser CLI installed"
    )
    config.addinivalue_line(
        "markers", "playwright: requires playwright browsers installed"
    )
    config.addinivalue_line(
        "markers", "integration: slow integration tests hitting real services"
    )
    config.addinivalue_line(
        "markers", "slow: tests taking more than 5 seconds"
    )


def pytest_runtest_setup(item):
    """Skip tests based on markers if requirements are not met."""
    # Check SerpAPI key
    if "serpapi" in item.keywords:
        if not os.environ.get("MWI_SERPAPI_API_KEY"):
            pytest.skip("MWI_SERPAPI_API_KEY not set")

    # Check SEO Rank key
    if "seorank" in item.keywords:
        if not os.environ.get("MWI_SEORANK_API_KEY"):
            pytest.skip("MWI_SEORANK_API_KEY not set")

    # Check OpenRouter key
    if "openrouter" in item.keywords:
        if not os.environ.get("MWI_OPENROUTER_API_KEY"):
            pytest.skip("MWI_OPENROUTER_API_KEY not set")

    # Check Mercury Parser
    if "mercury" in item.keywords:
        if not check_mercury_installed():
            pytest.skip("mercury-parser not installed")

    # Check Playwright
    if "playwright" in item.keywords:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            pytest.skip("playwright not installed")


# =============================================================================
# Base Fixtures
# =============================================================================

@pytest.fixture()
def test_env(tmp_path, monkeypatch):
    """Isolate data location and return imported modules (cli, controller, core, model).
    Sets MWI_DATA_LOCATION to a temporary directory before importing project modules.
    """
    # Point app to an isolated temp data directory
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MWI_DATA_LOCATION", str(data_dir))

    # Ensure a clean import state for modules that depend on settings
    for name in list(sys.modules.keys()):
        if name in ("settings", "mwi.model", "mwi.core", "mwi.controller", "mwi.cli"):
            sys.modules.pop(name, None)

    # Import modules after env var is set so settings picks it up
    from mwi import cli as _cli
    from mwi import controller as _controller
    from mwi import model as _model
    from mwi import core as _core
    # Force settings.data_location to the temp dir for any path-based logic
    import settings as _settings
    _settings.data_location = str(data_dir)
    # Also ensure controller module references the updated settings value
    _controller.settings.data_location = str(data_dir)

    # Return modules and the data dir for convenience
    return {
        "cli": _cli,
        "controller": _controller,
        "model": _model,
        "core": _core,
        "data_dir": data_dir,
    }


@pytest.fixture()
def fresh_db(test_env, monkeypatch):
    """Create/drop tables for a clean DB using DbController.setup with auto-confirm.
    Returns the same dict as test_env.
    """
    core = test_env["core"]
    controller = test_env["controller"]
    data_dir = test_env["data_dir"]
    # Ensure DB file exists and (re)init peewee DB to this path
    db_path = os.path.join(str(data_dir), "mwi.db")
    if not os.path.exists(db_path):
        open(db_path, "a").close()
    model = test_env["model"]
    # Rebind DB in case it captured an older path
    model.DB.init(db_path, pragmas={
        'journal_mode': 'wal',
        'cache_size': -1 * 512000,
        'foreign_keys': 1,
        'ignore_check_constrains': 0,
        'synchronous': 0
    })
    try:
        model.DB.connect(reuse_if_open=True)
    except Exception:
        # Connection may be opened lazily later
        pass
    # Auto-confirm destructive actions (patch both module refs)
    monkeypatch.setattr(core, "confirm", lambda msg: True, raising=True)
    monkeypatch.setattr(controller.core, "confirm", lambda msg: True, raising=True)
    # Setup database (drop + create tables)
    ret = controller.DbController.setup(core.Namespace())
    assert ret == 1
    return test_env


# =============================================================================
# Advanced Fixtures
# =============================================================================

@pytest.fixture()
def sample_html_content():
    """Retourne le contenu HTML de test pour les tests de crawl."""
    return load_fixture("sample_html_page.html")


@pytest.fixture()
def populated_land(fresh_db):
    """Crée un land avec données complètes pour tests d'export.

    Crée:
    - 1 land avec terms
    - 2 domains
    - 20 expressions avec relevance variée
    - 10 expression links
    - 5 media
    """
    controller = fresh_db["controller"]
    model = fresh_db["model"]
    core = fresh_db["core"]

    # Créer land
    name = "test_export_land"
    controller.LandController.create(
        core.Namespace(name=name, desc="Test export land", lang=["fr"])
    )
    land = model.Land.get(model.Land.name == name)

    # Ajouter terms
    controller.LandController.addterm(
        core.Namespace(land=name, terms="test, keyword, research")
    )

    # Créer domains
    domain1 = model.Domain.create(name="example.com")
    domain2 = model.Domain.create(name="test.org")

    # Créer expressions avec relevance variée
    expressions = []
    for i in range(20):
        expr = model.Expression.create(
            land=land,
            domain=domain1 if i % 2 == 0 else domain2,
            url=f"https://example.com/page{i}",
            title=f"Page {i} test keyword",
            description=f"Description with research keyword {i}",
            readable=f"Content test keyword research " * 50,
            relevance=i,
            depth=i % 3,
            http_status="200",
            fetched_at=datetime.now(),
            readable_at=datetime.now()
        )
        expressions.append(expr)

    # Créer ExpressionLinks
    for i in range(10):
        model.ExpressionLink.create(
            source=expressions[i],
            target=expressions[(i + 1) % 20]
        )

    # Créer Media
    for i in range(5):
        model.Media.create(
            expression=expressions[i],
            url=f"https://example.com/image{i}.jpg",
            type="image",
            width=800,
            height=600,
            analyzed_at=datetime.now()
        )

    return {
        "land": land,
        "expressions": expressions,
        "domains": [domain1, domain2],
        "name": name,
        "controller": controller,
        "model": model,
        "core": core,
        "data_dir": fresh_db["data_dir"]
    }
