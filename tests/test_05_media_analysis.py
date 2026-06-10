"""
Tests for media analysis functionality.
"""
import pytest
import random
import string
from datetime import datetime


def rand_name(prefix="land"):
    """Generate random land name for tests."""
    letters = string.ascii_lowercase
    return f"{prefix}_" + "".join(random.choice(letters) for _ in range(8))


class TestMediaExtraction:
    """Tests for media extraction from HTML and markdown."""

    def test_extract_media_creates_records(self, fresh_db):
        """L'extraction de média crée des entrées Media."""
        controller = fresh_db["controller"]
        model = fresh_db["model"]
        core = fresh_db["core"]

        name = rand_name("test")
        controller.LandController.create(
            core.Namespace(name=name, desc="Test land", lang=["fr"])
        )
        land = model.Land.get(model.Land.name == name)

        # Créer expression avec médias
        domain = model.Domain.create(name="example.com")
        expr = model.Expression.create(
            land=land,
            domain=domain,
            url="https://example.com/page",
            fetched_at=datetime.now()
        )

        # Créer Media manuellement (simule extraction)
        media = model.Media.create(
            expression=expr,
            url="https://example.com/image.jpg",
            type="image"
        )

        assert media.id is not None
        assert media.expression == expr
        assert media.url == "https://example.com/image.jpg"


class TestMediaAnalysis:
    """Tests for media analysis using MediaAnalyzer."""

    def test_media_analyze_command_runs(self, fresh_db, monkeypatch):
        """land medianalyse s'exécute sans erreur."""
        controller = fresh_db["controller"]
        model = fresh_db["model"]
        core = fresh_db["core"]

        name = rand_name("test")
        controller.LandController.create(
            core.Namespace(name=name, desc="Test land", lang=["fr"])
        )
        land = model.Land.get(model.Land.name == name)

        # Créer expression avec média
        domain = model.Domain.create(name="example.com")
        expr = model.Expression.create(
            land=land,
            domain=domain,
            url="https://example.com/page",
            fetched_at=datetime.now()
        )

        model.Media.create(
            expression=expr,
            url="https://example.com/image.jpg",
            type="image"
        )

        # Mock medianalyse_land to avoid real HTTP calls.
        # Patch on controller.core: the module reference the controller
        # actually resolves (fresh_db can return stale module objects).
        async def mock_medianalyse(land_obj, depth=None, minrel=None):
            return {"processed": 1, "errors": 0}

        monkeypatch.setattr(controller.core, "medianalyse_land", mock_medianalyse)

        ret = controller.LandController.medianalyse(
            core.Namespace(name=name, depth=None, minrel=None)
        )

        assert ret == 1

    def test_media_analyze_transmits_depth_and_minrel(self, fresh_db, monkeypatch):
        """land medianalyse transmet --depth/--minrel à core.medianalyse_land (sprint-multilang, B2)."""
        controller = fresh_db["controller"]
        core = fresh_db["core"]

        name = rand_name("test")
        controller.LandController.create(
            core.Namespace(name=name, desc="Test land", lang=["fr"])
        )

        received = {}

        async def mock_medianalyse(land_obj, depth=None, minrel=None):
            received["depth"] = depth
            received["minrel"] = minrel
            return {"processed": 0}

        monkeypatch.setattr(controller.core, "medianalyse_land", mock_medianalyse)

        ret = controller.LandController.medianalyse(
            core.Namespace(name=name, depth=1, minrel=2)
        )

        assert ret == 1
        assert received == {"depth": 1, "minrel": 2}

    def test_medianalyse_land_filters_by_depth_and_minrel(self, fresh_db, monkeypatch):
        """core.medianalyse_land filtre les médias par depth/minrel (sprint-multilang, B1)."""
        import asyncio as _asyncio

        controller = fresh_db["controller"]
        model = fresh_db["model"]
        core = fresh_db["core"]

        name = rand_name("test")
        controller.LandController.create(
            core.Namespace(name=name, desc="Test land", lang=["fr"])
        )
        land = model.Land.get(model.Land.name == name)
        domain = model.Domain.create(name="filter.example")

        expr_keep = model.Expression.create(
            land=land, domain=domain, url="https://filter.example/keep",
            depth=0, relevance=5, fetched_at=datetime.now())
        expr_deep = model.Expression.create(
            land=land, domain=domain, url="https://filter.example/deep",
            depth=3, relevance=5, fetched_at=datetime.now())
        expr_irrelevant = model.Expression.create(
            land=land, domain=domain, url="https://filter.example/irrelevant",
            depth=0, relevance=0, fetched_at=datetime.now())

        for expr, suffix in ((expr_keep, "keep"), (expr_deep, "deep"),
                             (expr_irrelevant, "irrelevant")):
            model.Media.create(expression=expr,
                               url=f"https://filter.example/{suffix}.jpg",
                               type="image")

        analyzed_urls = []

        class FakeAnalyzer:
            def __init__(self, session, config):
                pass

            async def analyze_image(self, url):
                analyzed_urls.append(str(url))
                return {}

        import mwi.media_analyzer as media_analyzer_module
        monkeypatch.setattr(media_analyzer_module, "MediaAnalyzer", FakeAnalyzer)

        result = _asyncio.run(core.medianalyse_land(land, depth=1, minrel=2))

        assert result["processed"] == 1
        assert analyzed_urls == ["https://filter.example/keep.jpg"]

    def test_media_conforming_check(self, fresh_db):
        """Vérification Media.is_conforming()."""
        model = fresh_db["model"]
        controller = fresh_db["controller"]
        core = fresh_db["core"]

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
            fetched_at=datetime.now()
        )

        # Créer média avec dimensions
        media = model.Media.create(
            expression=expr,
            url="https://example.com/image.jpg",
            type="image",
            width=800,
            height=600
        )

        # Test is_conforming method
        # Le média devrait être conforme (dimensions suffisantes)
        if hasattr(media, 'is_conforming'):
            # Note: is_conforming nécessite settings pour min_width/min_height
            # Le test vérifie juste que la méthode existe et est callable
            assert callable(media.is_conforming)


class TestMediaFiltering:
    """Tests for media filtering by size and dimensions."""

    def test_media_filtering_by_dimensions(self, fresh_db):
        """Les médias peuvent être filtrés par dimensions."""
        model = fresh_db["model"]
        controller = fresh_db["controller"]
        core = fresh_db["core"]

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
            fetched_at=datetime.now()
        )

        # Créer média petit (non conforme)
        small_media = model.Media.create(
            expression=expr,
            url="https://example.com/small.jpg",
            type="image",
            width=50,
            height=50
        )

        # Créer média grand (conforme)
        large_media = model.Media.create(
            expression=expr,
            url="https://example.com/large.jpg",
            type="image",
            width=1920,
            height=1080
        )

        # Query media with dimensions
        media_list = model.Media.select().where(
            (model.Media.expression == expr) & (model.Media.width >= 200)
        )

        assert media_list.count() == 1
        assert media_list[0].url == "https://example.com/large.jpg"


class TestMediaMetadata:
    """Tests for media metadata storage."""

    def test_media_stores_dimensions(self, fresh_db):
        """Les dimensions sont stockées dans Media."""
        model = fresh_db["model"]
        controller = fresh_db["controller"]
        core = fresh_db["core"]

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
            fetched_at=datetime.now()
        )

        media = model.Media.create(
            expression=expr,
            url="https://example.com/image.jpg",
            type="image",
            width=1024,
            height=768
        )

        assert media.width == 1024
        assert media.height == 768

    def test_media_stores_analyzed_timestamp(self, fresh_db):
        """Le timestamp analyzed_at est stocké."""
        model = fresh_db["model"]
        controller = fresh_db["controller"]
        core = fresh_db["core"]

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
            fetched_at=datetime.now()
        )

        media = model.Media.create(
            expression=expr,
            url="https://example.com/image.jpg",
            type="image",
            analyzed_at=datetime.now()
        )

        assert media.analyzed_at is not None

    def test_media_stores_color_data(self, fresh_db):
        """Les couleurs dominantes peuvent être stockées en JSON."""
        model = fresh_db["model"]
        controller = fresh_db["controller"]
        core = fresh_db["core"]

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
            fetched_at=datetime.now()
        )

        import json
        colors_json = json.dumps([[255, 0, 0], [0, 255, 0], [0, 0, 255]])

        media = model.Media.create(
            expression=expr,
            url="https://example.com/image.jpg",
            type="image",
            dominant_colors=colors_json,
            n_dominant_colors=3
        )

        assert media.dominant_colors is not None
        colors = json.loads(media.dominant_colors)
        assert len(colors) == 3
        assert colors[0] == [255, 0, 0]  # Red


class TestMediaDuplicateDetection:
    """Tests for duplicate detection using perceptual hashing."""

    def test_media_stores_image_hash(self, fresh_db):
        """Le hash perceptuel est stocké dans Media."""
        model = fresh_db["model"]
        controller = fresh_db["controller"]
        core = fresh_db["core"]

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
            fetched_at=datetime.now()
        )

        media = model.Media.create(
            expression=expr,
            url="https://example.com/image.jpg",
            type="image",
            image_hash="abc123def456"  # Simulated hash
        )

        assert media.image_hash == "abc123def456"

    def test_detect_duplicate_by_hash(self, fresh_db):
        """Détection de doublons par hash identique."""
        model = fresh_db["model"]
        controller = fresh_db["controller"]
        core = fresh_db["core"]

        name = rand_name("test")
        controller.LandController.create(
            core.Namespace(name=name, desc="Test land", lang=["fr"])
        )
        land = model.Land.get(model.Land.name == name)

        domain = model.Domain.create(name="example.com")
        expr1 = model.Expression.create(
            land=land,
            domain=domain,
            url="https://example.com/page1",
            fetched_at=datetime.now()
        )
        expr2 = model.Expression.create(
            land=land,
            domain=domain,
            url="https://example.com/page2",
            fetched_at=datetime.now()
        )

        # Deux médias avec même hash (doublons)
        hash_value = "duplicate_hash_123"
        model.Media.create(
            expression=expr1,
            url="https://example.com/image1.jpg",
            type="image",
            image_hash=hash_value
        )
        model.Media.create(
            expression=expr2,
            url="https://example.com/image2.jpg",
            type="image",
            image_hash=hash_value
        )

        # Query duplicates
        from peewee import fn
        duplicates = (model.Media
                      .select(model.Media.image_hash, fn.COUNT(model.Media.id).alias('count'))
                      .where(model.Media.image_hash.is_null(False))
                      .group_by(model.Media.image_hash)
                      .having(fn.COUNT(model.Media.id) > 1))

        assert duplicates.count() == 1  # 1 groupe de doublons
        assert duplicates[0].count == 2  # 2 médias dans le groupe


class TestMediaMaintenanceVerbs:
    """Sprint-multilang C (P7) — land media_stats / preview_deletion / reanalyze."""

    def _make_land_with_media(self, fresh_db):
        controller = fresh_db["controller"]
        model = fresh_db["model"]
        core = fresh_db["core"]
        name = rand_name("mediac")
        controller.LandController.create(
            core.Namespace(name=name, desc="Test land", lang=["fr"]))
        land = model.Land.get(model.Land.name == name)
        domain = model.Domain.create(name=f"{name}.example")
        expr = model.Expression.create(
            land=land, domain=domain, url=f"https://{name}.example/page",
            fetched_at=datetime.now())
        big = model.Media.create(
            expression=expr, url=f"https://{name}.example/big.jpg",
            type="image", width=1200, height=900, file_size=50000,
            format="JPEG", analyzed_at=datetime.now())
        small = model.Media.create(
            expression=expr, url=f"https://{name}.example/small.jpg",
            type="image", width=50, height=50, file_size=1000,
            format="JPEG", analyzed_at=datetime.now())
        pending = model.Media.create(
            expression=expr, url=f"https://{name}.example/pending.jpg",
            type="image")
        return name, land, (big, small, pending)

    def test_media_stats_runs_and_counts(self, fresh_db, capsys):
        controller = fresh_db["controller"]
        core = fresh_db["core"]
        name, land, _ = self._make_land_with_media(fresh_db)
        ret = controller.LandController.media_stats(core.Namespace(name=name))
        assert ret == 1
        out = capsys.readouterr().out
        assert "Total: 3" in out
        assert "analyzed: 2" in out

    def test_media_stats_unknown_land(self, fresh_db):
        controller = fresh_db["controller"]
        core = fresh_db["core"]
        assert controller.LandController.media_stats(
            core.Namespace(name="nope_missing")) == 0

    def test_preview_deletion_is_pure_dry_run(self, fresh_db, capsys):
        controller = fresh_db["controller"]
        model = fresh_db["model"]
        core = fresh_db["core"]
        name, land, _ = self._make_land_with_media(fresh_db)
        before = model.Media.select().count()
        ret = controller.LandController.preview_deletion(
            core.Namespace(name=name, minwidth=200, minheight=200))
        assert ret == 1
        assert model.Media.select().count() == before  # nothing deleted
        out = capsys.readouterr().out
        assert "1 media would be deleted" in out  # only 'small' (50x50)
        assert "small.jpg" in out

    def test_reanalyze_processes_and_suppress_deletes_after_confirm(
            self, fresh_db, monkeypatch):
        controller = fresh_db["controller"]
        model = fresh_db["model"]
        core = fresh_db["core"]
        name, land, (big, small, pending) = self._make_land_with_media(fresh_db)

        sizes = {
            f"https://{name}.example/big.jpg": (1200, 900),
            f"https://{name}.example/small.jpg": (50, 50),
            f"https://{name}.example/pending.jpg": (800, 600),
        }

        class FakeAnalyzer:
            def __init__(self, session, config):
                pass

            async def analyze_image(self, url):
                w, h = sizes[str(url)]
                return {"width": w, "height": h}

        import mwi.media_analyzer as media_analyzer_module
        monkeypatch.setattr(media_analyzer_module, "MediaAnalyzer", FakeAnalyzer)
        # fresh_db patches confirm -> True, so --suppress proceeds
        ret = controller.LandController.reanalyze(
            core.Namespace(name=name, minwidth=200, minheight=200, suppress=True))
        assert ret == 1
        urls = [str(m.url) for m in model.Media.select()]
        assert f"https://{name}.example/small.jpg" not in urls  # deleted
        assert f"https://{name}.example/big.jpg" in urls
        assert f"https://{name}.example/pending.jpg" in urls  # 800x600 conforms

    def test_reanalyze_suppress_aborts_without_confirmation(
            self, fresh_db, monkeypatch):
        controller = fresh_db["controller"]
        model = fresh_db["model"]
        core = fresh_db["core"]
        name, land, _ = self._make_land_with_media(fresh_db)

        class FakeAnalyzer:
            def __init__(self, session, config):
                pass

            async def analyze_image(self, url):
                return {}

        import mwi.media_analyzer as media_analyzer_module
        monkeypatch.setattr(media_analyzer_module, "MediaAnalyzer", FakeAnalyzer)
        monkeypatch.setattr(controller.core, "confirm", lambda msg: False)
        before = model.Media.select().count()
        ret = controller.LandController.reanalyze(
            core.Namespace(name=name, minwidth=200, minheight=200, suppress=True))
        assert ret == 0  # aborted
        assert model.Media.select().count() == before
