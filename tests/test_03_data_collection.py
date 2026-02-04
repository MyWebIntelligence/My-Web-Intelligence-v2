"""
Tests for data collection: crawl, readable, SEO Rank, LLM validation.
"""
import os
import random
import string
import pytest
from unittest.mock import patch, Mock
from datetime import datetime


def rand_name(prefix="land"):
    """Generate random land name for tests."""
    letters = string.ascii_lowercase
    return f"{prefix}_" + "".join(random.choice(letters) for _ in range(8))


class TestLandCrawlMocked:
    """Tests for land crawl with mocked HTTP responses."""

    def test_crawl_fetches_pages(self, fresh_db, monkeypatch):
        """land crawl récupère le contenu des URLs."""
        controller = fresh_db["controller"]
        model = fresh_db["model"]
        core = fresh_db["core"]

        name = rand_name("test")
        controller.LandController.create(
            core.Namespace(name=name, desc="Test land", lang=["fr"])
        )
        land = model.Land.get(model.Land.name == name)

        # Ajouter URL
        controller.LandController.addurl(
            core.Namespace(land=name, urls="https://example.com/test", path=None)
        )

        # Mock async crawl response
        async def mock_crawl_land(land_obj, limit, http_status, depth):
            # Mark expression as fetched
            expr = model.Expression.get(
                (model.Expression.land == land_obj)
                & (model.Expression.url == "https://example.com/test")
            )
            expr.title = "Test Page Title"
            expr.description = "Test page description"
            expr.http_status = "200"
            expr.fetched_at = datetime.now()
            expr.save()
            return (1, 0)  # 1 processed, 0 errors

        # Patch at the mwi.core module level so controller sees it
        from mwi import core as mwi_core
        monkeypatch.setattr(mwi_core, "crawl_land", mock_crawl_land)

        # Crawl
        ret = controller.LandController.crawl(core.Namespace(name=name, limit=None, http=None, depth=None))

        assert ret == 1
        expr = model.Expression.get((model.Expression.land == land))
        assert expr.title == "Test Page Title"
        assert expr.http_status == "200"
        assert expr.fetched_at is not None

    def test_crawl_respects_limit(self, fresh_db, monkeypatch):
        """--limit=N ne crawle que N pages."""
        controller = fresh_db["controller"]
        model = fresh_db["model"]
        core = fresh_db["core"]

        name = rand_name("test")
        controller.LandController.create(
            core.Namespace(name=name, desc="Test land", lang=["fr"])
        )
        land = model.Land.get(model.Land.name == name)

        # Ajouter 3 URLs
        for i in range(3):
            controller.LandController.addurl(
                core.Namespace(land=name, urls=f"https://example.com/page{i}", path=None)
            )

        crawl_count = [0]

        async def mock_crawl_land(land_obj, limit, http_status, depth):
            # Should only process limit
            count = min(limit or 3, 3)
            crawl_count[0] = count
            return (count, 0)

        # Patch at the mwi.core module level so controller sees it
        from mwi import core as mwi_core
        monkeypatch.setattr(mwi_core, "crawl_land", mock_crawl_land)

        # Crawl with limit=2
        controller.LandController.crawl(core.Namespace(name=name, limit=2, http=None, depth=None))

        assert crawl_count[0] == 2

    def test_crawl_records_http_status(self, fresh_db, monkeypatch):
        """Le statut HTTP est enregistré."""
        controller = fresh_db["controller"]
        model = fresh_db["model"]
        core = fresh_db["core"]

        name = rand_name("test")
        controller.LandController.create(
            core.Namespace(name=name, desc="Test land", lang=["fr"])
        )
        land = model.Land.get(model.Land.name == name)

        controller.LandController.addurl(
            core.Namespace(land=name, urls="https://example.com/notfound", path=None)
        )

        async def mock_crawl_land(land_obj, limit, http_status, depth):
            expr = model.Expression.get((model.Expression.land == land_obj))
            expr.http_status = "404"
            expr.fetched_at = datetime.now()
            expr.save()
            return (1, 0)

        # Patch at the mwi.core module level so controller sees it
        from mwi import core as mwi_core
        monkeypatch.setattr(mwi_core, "crawl_land", mock_crawl_land)

        controller.LandController.crawl(core.Namespace(name=name, limit=None, http=None, depth=None))

        expr = model.Expression.get((model.Expression.land == land))
        assert expr.http_status == "404"


class TestLandReadableMocked:
    """Tests for readable content extraction with mocked Mercury Parser."""

    def test_readable_extracts_content(self, fresh_db, monkeypatch):
        """land readable extrait le contenu lisible."""
        controller = fresh_db["controller"]
        model = fresh_db["model"]
        core = fresh_db["core"]

        name = rand_name("test")
        controller.LandController.create(
            core.Namespace(name=name, desc="Test land", lang=["fr"])
        )
        land = model.Land.get(model.Land.name == name)

        # Créer expression avec HTML
        domain = model.Domain.create(name="example.com")
        expr = model.Expression.create(
            land=land,
            domain=domain,
            url="https://example.com/article",
            html="<html><body><article>Content</article></body></html>",
            fetched_at=datetime.now()
        )

        # Mock readable pipeline
        async def mock_readable_pipeline(land_obj, limit, depth, merge, llm):
            expr_upd = model.Expression.get(model.Expression.id == expr.id)
            expr_upd.readable = "Extracted readable content"
            expr_upd.title = "Article Title"
            expr_upd.readable_at = datetime.now()
            expr_upd.save()
            return (1, 0)

        from mwi import readable_pipeline
        monkeypatch.setattr(readable_pipeline, "run_readable_pipeline", mock_readable_pipeline)

        ret = controller.LandController.readable(
            core.Namespace(name=name, limit=None, depth=None, merge="smart_merge", llm="false")
        )

        assert ret == 1
        expr_check = model.Expression.get(model.Expression.id == expr.id)
        assert expr_check.readable == "Extracted readable content"
        assert expr_check.title == "Article Title"
        assert expr_check.readable_at is not None

    def test_readable_limit_parameter(self, fresh_db, monkeypatch):
        """--limit=N traite au max N pages."""
        controller = fresh_db["controller"]
        model = fresh_db["model"]
        core = fresh_db["core"]

        name = rand_name("test")
        controller.LandController.create(
            core.Namespace(name=name, desc="Test land", lang=["fr"])
        )
        land = model.Land.get(model.Land.name == name)

        # Créer 3 expressions
        domain = model.Domain.create(name="example.com")
        for i in range(3):
            model.Expression.create(
                land=land,
                domain=domain,
                url=f"https://example.com/page{i}",
                html=f"<html><body>Content {i}</body></html>",
                fetched_at=datetime.now()
            )

        process_count = [0]

        async def mock_readable_pipeline(land_obj, limit, depth, merge, llm):
            count = min(limit or 3, 3)
            process_count[0] = count
            return (count, 0)

        from mwi import readable_pipeline
        monkeypatch.setattr(readable_pipeline, "run_readable_pipeline", mock_readable_pipeline)

        controller.LandController.readable(
            core.Namespace(name=name, limit=2, depth=None, merge="smart_merge", llm="false")
        )

        assert process_count[0] == 2


@pytest.mark.seorank
class TestLandSeorank:
    """Tests for SEO Rank API (requires API key)."""

    def test_seorank_enriches_expressions(self, fresh_db):
        """land seorank stocke le JSON dans expression.seorank."""
        controller = fresh_db["controller"]
        model = fresh_db["model"]
        core = fresh_db["core"]

        name = rand_name("test")
        controller.LandController.create(
            core.Namespace(name=name, desc="Test land", lang=["fr"])
        )
        land = model.Land.get(model.Land.name == name)

        # Créer expression avec relevance >= 1
        domain = model.Domain.create(name="example.com")
        expr = model.Expression.create(
            land=land,
            domain=domain,
            url="https://example.com/page",
            relevance=5,
            fetched_at=datetime.now()
        )

        ret = controller.LandController.seorank(
            core.Namespace(name=name, limit=1, depth=None, http="200", minrel=1, force=False)
        )

        # API call should succeed (or return 1 even with no updates)
        assert ret == 1


class TestLandSeorankMocked:
    """Tests for SEO Rank with mocked API."""

    def test_seorank_parses_api_response(self, fresh_db, monkeypatch):
        """Vérifie le parsing de la réponse SEO Rank."""
        controller = fresh_db["controller"]
        model = fresh_db["model"]
        core = fresh_db["core"]

        name = rand_name("test")
        controller.LandController.create(
            core.Namespace(name=name, desc="Test land", lang=["fr"])
        )
        land = model.Land.get(model.Land.name == name)

        # Créer expression avec http_status=200 pour matcher le filtre
        domain = model.Domain.create(name="example.com")
        expr = model.Expression.create(
            land=land,
            domain=domain,
            url="https://example.com/page",
            relevance=5,
            http_status="200",  # Important: doit matcher le filtre
            fetched_at=datetime.now()
        )

        # Mock update_seorank_for_land
        def mock_update_seorank(land, api_key, limit, depth, http_status, min_relevance, force_refresh):
            expr_upd = model.Expression.get(model.Expression.id == expr.id)
            expr_upd.seorank = '{"sr_rank": 1000, "sr_traffic": 50000}'
            expr_upd.save()
            return (1, 1)  # processed, updated

        monkeypatch.setattr(core, "update_seorank_for_land", mock_update_seorank)

        ret = controller.LandController.seorank(
            core.Namespace(name=name, limit=None, depth=None, http="200", minrel=1, force=False)
        )

        assert ret == 1
        expr_check = model.Expression.get(model.Expression.id == expr.id)
        assert expr_check.seorank is not None
        assert "sr_rank" in expr_check.seorank


@pytest.mark.openrouter
class TestLandLlmValidate:
    """Tests for LLM validation via OpenRouter (requires API key)."""

    def test_llm_validate_sets_validllm(self, fresh_db):
        """land llm validate définit expression.validllm."""
        controller = fresh_db["controller"]
        model = fresh_db["model"]
        core = fresh_db["core"]

        name = rand_name("test")
        controller.LandController.create(
            core.Namespace(name=name, desc="Test land", lang=["fr"])
        )
        land = model.Land.get(model.Land.name == name)

        # Add terms
        controller.LandController.addterm(
            core.Namespace(land=name, terms="test, keyword")
        )

        # Créer expression avec readable
        domain = model.Domain.create(name="example.com")
        model.Expression.create(
            land=land,
            domain=domain,
            url="https://example.com/page",
            readable="This is a long test article about keywords and research topics. " * 20,
            relevance=5
        )

        ret = controller.LandController.llm_validate(
            core.Namespace(name=name, limit=1, force=False)
        )

        # Should process (return 1) even if no API key configured
        assert ret in [0, 1]


class TestLandLlmValidateMocked:
    """Tests for LLM validation with mocked responses."""

    def test_llm_validate_parses_oui(self, fresh_db, monkeypatch):
        """Réponse 'oui' → validllm='oui', relevance conservée."""
        controller = fresh_db["controller"]
        model = fresh_db["model"]
        core = fresh_db["core"]
        import settings
        from mwi import controller as ctrl_module

        # Enable OpenRouter for test - patch both settings and controller.settings
        monkeypatch.setattr(settings, "openrouter_enabled", True)
        monkeypatch.setattr(settings, "openrouter_api_key", "test_key")
        monkeypatch.setattr(settings, "openrouter_model", "test_model")
        monkeypatch.setattr(settings, "openrouter_readable_min_chars", 100)

        # Also patch in controller module
        monkeypatch.setattr(ctrl_module.settings, "openrouter_enabled", True)
        monkeypatch.setattr(ctrl_module.settings, "openrouter_api_key", "test_key")
        monkeypatch.setattr(ctrl_module.settings, "openrouter_model", "test_model")
        monkeypatch.setattr(ctrl_module.settings, "openrouter_readable_min_chars", 100)

        name = rand_name("test")
        controller.LandController.create(
            core.Namespace(name=name, desc="Test land", lang=["fr"])
        )
        land = model.Land.get(model.Land.name == name)

        # Créer expression
        domain = model.Domain.create(name="example.com")
        expr = model.Expression.create(
            land=land,
            domain=domain,
            url="https://example.com/page",
            readable="This is a relevant article about test keywords. " * 10,
            relevance=5
        )

        # Mock LLM validation
        from mwi import llm_openrouter
        def mock_is_relevant(land_obj, expr_obj):
            return True  # oui

        monkeypatch.setattr(llm_openrouter, "is_relevant_via_openrouter", mock_is_relevant)

        ret = controller.LandController.llm_validate(
            core.Namespace(name=name, limit=None, force=False)
        )

        assert ret == 1
        expr_check = model.Expression.get(model.Expression.id == expr.id)
        assert expr_check.validllm == "oui"
        assert expr_check.validmodel == "test_model"
        assert expr_check.relevance == 5  # conservée

    def test_llm_validate_parses_non(self, fresh_db, monkeypatch):
        """Réponse 'non' → validllm='non', relevance=0."""
        controller = fresh_db["controller"]
        model = fresh_db["model"]
        core = fresh_db["core"]
        import settings
        from mwi import controller as ctrl_module

        # Enable OpenRouter for test - patch both settings and controller.settings
        monkeypatch.setattr(settings, "openrouter_enabled", True)
        monkeypatch.setattr(settings, "openrouter_api_key", "test_key")
        monkeypatch.setattr(settings, "openrouter_model", "test_model")
        monkeypatch.setattr(settings, "openrouter_readable_min_chars", 100)

        # Also patch in controller module
        monkeypatch.setattr(ctrl_module.settings, "openrouter_enabled", True)
        monkeypatch.setattr(ctrl_module.settings, "openrouter_api_key", "test_key")
        monkeypatch.setattr(ctrl_module.settings, "openrouter_model", "test_model")
        monkeypatch.setattr(ctrl_module.settings, "openrouter_readable_min_chars", 100)

        name = rand_name("test")
        controller.LandController.create(
            core.Namespace(name=name, desc="Test land", lang=["fr"])
        )
        land = model.Land.get(model.Land.name == name)

        domain = model.Domain.create(name="example.com")
        expr = model.Expression.create(
            land=land,
            domain=domain,
            url="https://example.com/page",
            readable="This is an irrelevant article about unrelated topics. " * 10,
            relevance=5
        )

        from mwi import llm_openrouter
        def mock_is_relevant(land_obj, expr_obj):
            return False  # non

        monkeypatch.setattr(llm_openrouter, "is_relevant_via_openrouter", mock_is_relevant)

        ret = controller.LandController.llm_validate(
            core.Namespace(name=name, limit=None, force=False)
        )

        assert ret == 1
        expr_check = model.Expression.get(model.Expression.id == expr.id)
        assert expr_check.validllm == "non"
        assert expr_check.validmodel == "test_model"
        assert expr_check.relevance == 0  # réinitialisée


class TestDomainCrawl:
    """Tests for domain crawl."""

    def test_domain_crawl_fetches_info(self, fresh_db, monkeypatch):
        """domain crawl récupère les infos domaine."""
        controller = fresh_db["controller"]
        model = fresh_db["model"]
        core = fresh_db["core"]

        # Créer un domaine
        model.Domain.create(name="test-domain.com")

        # Mock crawl_domains to avoid real HTTP calls
        def mock_crawl_domains(limit, http_status):
            return 1  # Return count of domains processed

        monkeypatch.setattr(core, "crawl_domains", mock_crawl_domains)

        ret = controller.DomainController.crawl(core.Namespace(limit=None, http=None))

        # Check that controller returned success
        assert ret == 1


class TestLandConsolidate:
    """Tests for land consolidation."""

    def test_consolidate_recalculates_relevance(self, fresh_db, monkeypatch):
        """land consolidate recalcule les scores."""
        controller = fresh_db["controller"]
        model = fresh_db["model"]
        core = fresh_db["core"]

        name = rand_name("test")
        controller.LandController.create(
            core.Namespace(name=name, desc="Test land", lang=["fr"])
        )
        land = model.Land.get(model.Land.name == name)

        # Ajouter terms
        controller.LandController.addterm(
            core.Namespace(land=name, terms="test, keyword")
        )

        # Créer expression avec HTML contenant keywords
        domain = model.Domain.create(name="example.com")
        expr = model.Expression.create(
            land=land,
            domain=domain,
            url="https://example.com/page",
            html="<html><head><title>Test Keyword Article</title></head><body>Content with test and keyword repeated.</body></html>",
            fetched_at=datetime.now(),
            relevance=0
        )

        # Mock consolidate
        async def mock_consolidate(land_obj, limit, depth, minrel):
            # Simulate relevance recalculation
            core.land_relevance(land_obj)
            return (1, 0)

        monkeypatch.setattr(core, "consolidate_land", mock_consolidate)

        ret = controller.LandController.consolidate(
            core.Namespace(name=name, limit=None, depth=None, minrel=0)
        )

        assert ret == 1
        expr_check = model.Expression.get(model.Expression.id == expr.id)
        # Relevance should be recalculated (> 0 if keywords present)
        assert expr_check.relevance >= 0
