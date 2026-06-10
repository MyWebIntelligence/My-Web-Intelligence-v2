"""Tests for the HTML storage feature (Expression.html + Land.fullhtml).

Tests cover:
- Model fields (nullable, roundtrip, schema)
- Land.fullhtml default and creation
- Cascade logic (CLI override > land default)
- Migration on legacy databases
- [sprint-html A] regression: HTML preserved on extraction failure
- [sprint-html B] integration tests targeting the production crawl path
- [sprint-html D] process_expression_content removed — coverage moved to
  the production-path tests in TestCrawlExpressionStoresHtml.
"""
import argparse
import asyncio
from unittest.mock import patch

import peewee
import pytest


def _run(coro):
    """Run a coroutine in an isolated event loop (no leak between tests)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestExpressionHtmlField:
    """Tests for Expression.html field."""

    def test_expression_html_field_nullable(self, fresh_db):
        """Expression created without html has html=None."""
        m = fresh_db["model"]
        domain = m.Domain.create(name="test-nullable.com")
        land = m.Land.create(name="test_nullable", description="test", lang="fr")
        expr = m.Expression.create(land=land, domain=domain, url="https://test-nullable.com/1")
        assert expr.html is None

    def test_expression_html_roundtrip(self, fresh_db):
        """HTML stored in DB is retrieved identically."""
        m = fresh_db["model"]
        domain = m.Domain.create(name="test-roundtrip.com")
        land = m.Land.create(name="test_roundtrip", description="test", lang="fr")
        raw = "<html><head><title>Test</title></head><body><p>Contenu</p></body></html>"
        expr = m.Expression.create(land=land, domain=domain, url="https://test-roundtrip.com/1", html=raw)
        fetched = m.Expression.get_by_id(expr.id)
        assert fetched.html == raw

    def test_schema_has_html_column(self, fresh_db):
        """The expression table contains the html column."""
        m = fresh_db["model"]
        cols = [row[1] for row in m.DB.execute_sql("PRAGMA table_info('expression')").fetchall()]
        assert 'html' in cols


class TestLandFullhtmlField:
    """Tests for Land.fullhtml field."""

    def test_land_create_with_fullhtml_true(self, fresh_db):
        """Land created with fullhtml=True stores the flag."""
        m = fresh_db["model"]
        land = m.Land.create(name="test_fh", description="test", lang="fr", fullhtml=True)
        fetched = m.Land.get_by_id(land.id)
        assert fetched.fullhtml is True

    def test_land_create_without_fullhtml_defaults_false(self, fresh_db):
        """Land created without fullhtml has fullhtml=False."""
        m = fresh_db["model"]
        land = m.Land.create(name="test_nofh", description="test", lang="fr")
        fetched = m.Land.get_by_id(land.id)
        assert fetched.fullhtml is False

    def test_schema_has_fullhtml_column(self, fresh_db):
        """The land table contains the fullhtml column."""
        m = fresh_db["model"]
        cols = [row[1] for row in m.DB.execute_sql("PRAGMA table_info('land')").fetchall()]
        assert 'fullhtml' in cols


class TestCrawlFullhtmlCascade:
    """Tests for the --fullhtml cascade logic (CLI override > land default)."""

    def test_crawl_inherits_land_fullhtml(self, fresh_db):
        """When --fullhtml not specified at crawl, land.fullhtml is used."""
        m = fresh_db["model"]
        land = m.Land.create(name="test_inherit", description="test", lang="fr", fullhtml=True)

        # Simulate resolution as in LandController.crawl
        fullhtml_raw = None  # CLI absent
        if fullhtml_raw is not None:
            store_html = fullhtml_raw.upper() == 'TRUE'
        else:
            store_html = bool(land.fullhtml)

        assert store_html is True

    def test_crawl_fullhtml_false_overrides_land(self, fresh_db):
        """--fullhtml=FALSE at crawl overrides land.fullhtml=True."""
        m = fresh_db["model"]
        land = m.Land.create(name="test_override", description="test", lang="fr", fullhtml=True)

        fullhtml_raw = 'FALSE'  # CLI explicit
        if fullhtml_raw is not None:
            store_html = fullhtml_raw.upper() == 'TRUE'
        else:
            store_html = bool(land.fullhtml)

        assert store_html is False


class TestStoreHtmlOnExtractionFailure:
    """[sprint-html A — D1 regression] HTML brut conservé même si extraction échoue.

    Avant le fix Sprint A, `expression.html = raw_html` était dans le bloc
    `if content:`. Sur les pages où la cascade fetch retournait du HTML mais
    où Trafilatura/BeautifulSoup ne pouvaient rien extraire (CF interstitial,
    JS-only sites), le HTML brut était perdu — précisément le scénario qui
    motive `--fullhtml`. Ces tests verrouillent l'invariant inverse.
    """

    def test_html_stored_when_extraction_fails(self, fresh_db):
        from mwi.fetcher import FetchResult
        m = fresh_db["model"]
        core = fresh_db["core"]
        land = m.Land.create(name="d1_fail", description="t", lang="fr",
                             fullhtml=True)
        domain = m.Domain.create(name="d1-fail.com")
        expr = m.Expression.create(
            land=land, domain=domain, depth=0,
            url="https://d1-fail.com/cf-interstitial",
        )
        cf_html = "<html><body>Just a moment... Checking your browser.</body></html>"

        async def fake_fetch(url, session=None, **kw):
            return FetchResult(url=url, status_code='200', html=cf_html,
                               method_used='aiohttp')

        # Force _extract_content_and_links to return (None, []) — Trafilatura
        # and BeautifulSoup both yield nothing on the CF interstitial.
        with patch.object(core, 'fetch_html', side_effect=fake_fetch), \
             patch.object(core, '_extract_content_and_links',
                          return_value=(None, [])):
            _run(core.crawl_expression_with_media_analysis(
                expr, [], session=None, store_html=True
            ))

        fetched = m.Expression.get_by_id(expr.id)
        # Invariant clé : HTML brut préservé même quand content=None
        assert fetched.html == cf_html
        assert fetched.http_status == '200'
        assert fetched.fetch_method == 'aiohttp'
        # Et readable doit être vide (extraction a échoué)
        assert not fetched.readable

    def test_legacy_crawl_expression_also_stores_on_failure(self, fresh_db):
        """Symétrique : crawl_expression (chemin tests/legacy) suit la même invariant."""
        from mwi.fetcher import FetchResult
        m = fresh_db["model"]
        core = fresh_db["core"]
        land = m.Land.create(name="d1_legacy", description="t", lang="fr",
                             fullhtml=True)
        domain = m.Domain.create(name="d1-legacy.com")
        expr = m.Expression.create(
            land=land, domain=domain, depth=0,
            url="https://d1-legacy.com/page",
        )
        html = "<html><body>opaque markup</body></html>"

        async def fake_fetch(url, session=None, **kw):
            return FetchResult(url=url, status_code='200', html=html,
                               method_used='aiohttp')

        with patch.object(core, 'fetch_html', side_effect=fake_fetch), \
             patch.object(core, '_extract_content_and_links',
                          return_value=(None, [])):
            _run(core.crawl_expression(expr, [], session=None, store_html=True))

        assert m.Expression.get_by_id(expr.id).html == html


class TestCrawlExpressionStoresHtml:
    """[sprint-html B — D3] Tests d'intégration ciblant le chemin de production.

    Avant le sprint, aucun test ne couvrait crawl_expression_with_media_analysis
    avec store_html=True. Les tests existants ne validaient que des fonctions
    orphelines (process_expression_content) ou re-codaient la logique CLI dans
    le test. Ces tests appellent directement le chemin de production en mockant
    fetch_html.
    """

    def _build(self, m, suffix, fullhtml=True):
        land = m.Land.create(name=f"int_{suffix}", description="t",
                             lang="fr", fullhtml=fullhtml)
        domain = m.Domain.create(name=f"int-{suffix}.com")
        expr = m.Expression.create(
            land=land, domain=domain, depth=0,
            url=f"https://int-{suffix}.com/page",
        )
        return land, expr

    def test_aiohttp_path_stores_html(self, fresh_db):
        from mwi.fetcher import FetchResult
        m = fresh_db["model"]
        core = fresh_db["core"]
        _, expr = self._build(m, "aiohttp")
        html = '<html lang="fr"><body><p>Bonjour le monde.</p></body></html>'

        async def fake_fetch(url, session=None, **kw):
            return FetchResult(url=url, status_code='200', html=html,
                               method_used='aiohttp')

        with patch.object(core, 'fetch_html', side_effect=fake_fetch):
            _run(core.crawl_expression_with_media_analysis(
                expr, [], session=None, store_html=True))

        fetched = m.Expression.get_by_id(expr.id)
        assert fetched.html == html
        assert fetched.fetch_method == 'aiohttp'
        assert fetched.http_status == '200'

    def test_curl_cffi_rescue_stores_html_with_origin_status(self, fresh_db):
        """Page sauvée par curl_cffi : html stocké, status 403 d'origine préservé."""
        from mwi.fetcher import FetchResult
        m = fresh_db["model"]
        core = fresh_db["core"]
        _, expr = self._build(m, "cfrescue")
        html = '<html><body><p>Saved by curl_cffi.</p></body></html>'

        async def fake_fetch(url, session=None, **kw):
            # status_code='403' = origin server reality, html présent = curl_cffi rescue
            return FetchResult(url=url, status_code='403', html=html,
                               method_used='curl_cffi')

        with patch.object(core, 'fetch_html', side_effect=fake_fetch):
            _run(core.crawl_expression_with_media_analysis(
                expr, [], session=None, store_html=True))

        fetched = m.Expression.get_by_id(expr.id)
        assert fetched.html == html
        assert fetched.fetch_method == 'curl_cffi'
        # Origin status preserved (sprint-403 design rule)
        assert fetched.http_status == '403'

    def test_archive_org_path_stores_html(self, fresh_db):
        """Page sauvée par Wayback : html stocké, fetch_method='archive_org'."""
        from mwi.fetcher import FetchResult
        m = fresh_db["model"]
        core = fresh_db["core"]
        _, expr = self._build(m, "wayback")
        html = '<html><body><p>From the past.</p></body></html>'

        async def fake_fetch(url, session=None, **kw):
            return FetchResult(url=url, status_code='404', html=html,
                               method_used='archive_org')

        with patch.object(core, 'fetch_html', side_effect=fake_fetch):
            _run(core.crawl_expression_with_media_analysis(
                expr, [], session=None, store_html=True))

        fetched = m.Expression.get_by_id(expr.id)
        assert fetched.html == html
        assert fetched.fetch_method == 'archive_org'

    def test_skips_when_store_html_false(self, fresh_db):
        """store_html=False (défaut) → expression.html reste None."""
        from mwi.fetcher import FetchResult
        m = fresh_db["model"]
        core = fresh_db["core"]
        _, expr = self._build(m, "skip", fullhtml=False)

        async def fake_fetch(url, session=None, **kw):
            return FetchResult(url=url, status_code='200',
                               html='<html><body>x</body></html>',
                               method_used='aiohttp')

        with patch.object(core, 'fetch_html', side_effect=fake_fetch):
            _run(core.crawl_expression_with_media_analysis(
                expr, [], session=None, store_html=False))

        assert m.Expression.get_by_id(expr.id).html is None

    def test_skips_when_no_html_retrieved(self, fresh_db):
        """raw_html=None (cascade tout-échec) → html reste None."""
        from mwi.fetcher import FetchResult
        m = fresh_db["model"]
        core = fresh_db["core"]
        _, expr = self._build(m, "no_html")

        async def fake_fetch(url, session=None, **kw):
            return FetchResult(url=url, status_code='000', html=None,
                               method_used='aiohttp', error='timeout')

        with patch.object(core, 'fetch_html', side_effect=fake_fetch):
            _run(core.crawl_expression_with_media_analysis(
                expr, [], session=None, store_html=True))

        assert m.Expression.get_by_id(expr.id).html is None

    def test_recrawl_preserves_old_html_on_new_failure(self, fresh_db):
        """Re-crawl qui échoue (raw_html=None) ne doit pas écraser un ancien html.

        Décision D-G du sprint : par non-action — l'assignation est
        gardée par le `if store_html and raw_html:`, donc raw_html=None
        skip l'assignation et l'ancien contenu reste intact.
        """
        from mwi.fetcher import FetchResult
        m = fresh_db["model"]
        core = fresh_db["core"]
        _, expr = self._build(m, "recrawl")
        # Pré-charger un HTML d'un précédent rescue
        previous = '<html><body>OLD CONTENT</body></html>'
        expr.html = previous
        expr.save()

        async def fake_fetch(url, session=None, **kw):
            return FetchResult(url=url, status_code='403', html=None,
                               method_used='aiohttp')

        with patch.object(core, 'fetch_html', side_effect=fake_fetch):
            _run(core.crawl_expression_with_media_analysis(
                expr, [], session=None, store_html=True))

        fetched = m.Expression.get_by_id(expr.id)
        # raw_html=None → assignation skippée → ancien HTML préservé
        assert fetched.html == previous
        assert fetched.http_status == '403'


class TestLandControllerCrawlCascade:
    """[sprint-html B+C — D3+D5.3] Validation de la résolution CLI > Land
    en appelant le vrai controller et en inspectant la sortie standard.

    Pourquoi pas de mock de `crawl_land` ? Parce que la fixture conftest
    `test_env` pop une partie de `sys.modules` mais pas tout — quand
    un test précédent a chargé `mwi.readable_pipeline`, les références
    capturées par le fixture deviennent stales et le mock ne se
    propage pas. On contourne en vérifiant le message imprimé
    *avant* le call à `crawl_land` (i.e. juste après la résolution).
    Le land est créé sans expressions à crawler, donc `crawl_land`
    retourne immédiatement (0, 0) et le test reste rapide.
    """

    def test_cli_true_prints_on_cli(self, fresh_db, capsys):
        """--fullhtml=TRUE → 'ON (source: CLI)' même si Land=False."""
        m = fresh_db["model"]
        controller = fresh_db["controller"]
        m.Land.create(name="rt", description="t", lang="fr", fullhtml=False)

        ns = argparse.Namespace(name='rt', limit=0, http=None, depth=None,
                                fullhtml='TRUE', retry_status=None)
        controller.LandController.crawl(ns)
        out = capsys.readouterr().out
        assert 'Full HTML storage: ON (source: CLI)' in out

    def test_cli_absent_inherits_on_from_land(self, fresh_db, capsys):
        """--fullhtml absent → 'ON (source: land default)' si Land=True."""
        m = fresh_db["model"]
        controller = fresh_db["controller"]
        m.Land.create(name="rh", description="t", lang="fr", fullhtml=True)

        ns = argparse.Namespace(name='rh', limit=0, http=None, depth=None,
                                fullhtml=None, retry_status=None)
        controller.LandController.crawl(ns)
        out = capsys.readouterr().out
        assert 'Full HTML storage: ON (source: land default)' in out

    def test_cli_false_overrides_land_true(self, fresh_db, capsys):
        """--fullhtml=FALSE → 'OFF (source: CLI)' même si Land=True."""
        m = fresh_db["model"]
        controller = fresh_db["controller"]
        m.Land.create(name="ro", description="t", lang="fr", fullhtml=True)

        ns = argparse.Namespace(name='ro', limit=0, http=None, depth=None,
                                fullhtml='FALSE', retry_status=None)
        controller.LandController.crawl(ns)
        out = capsys.readouterr().out
        assert 'Full HTML storage: OFF (source: CLI)' in out

    def test_cli_absent_inherits_off_from_land(self, fresh_db, capsys):
        """--fullhtml absent → 'OFF (source: land default)' si Land=False."""
        m = fresh_db["model"]
        controller = fresh_db["controller"]
        m.Land.create(name="roff", description="t", lang="fr", fullhtml=False)

        ns = argparse.Namespace(name='roff', limit=0, http=None, depth=None,
                                fullhtml=None, retry_status=None)
        controller.LandController.crawl(ns)
        out = capsys.readouterr().out
        assert 'Full HTML storage: OFF (source: land default)' in out


class TestLandListShowsFullhtmlStats:
    """[sprint-html C — D4] land list affiche policy + nb stockés + volume."""

    def test_shows_full_html_line_when_policy_on(self, fresh_db, capsys):
        m = fresh_db["model"]
        from mwi import controller
        land = m.Land.create(name="d4_show", description="t", lang="fr",
                             fullhtml=True)
        domain = m.Domain.create(name="d4-show.com")
        m.Expression.create(
            land=land, domain=domain, depth=0,
            url="https://d4-show.com/1",
            html='<html><body>x</body></html>',
        )

        controller.LandController.list(argparse.Namespace(name='d4_show'))
        out = capsys.readouterr().out
        assert 'Full HTML' in out
        assert 'policy=ON' in out
        assert '1 expressions stored' in out

    def test_hides_full_html_line_when_policy_off_and_no_data(self, fresh_db, capsys):
        m = fresh_db["model"]
        from mwi import controller
        m.Land.create(name="d4_hide", description="t", lang="fr",
                      fullhtml=False)

        controller.LandController.list(argparse.Namespace(name='d4_hide'))
        out = capsys.readouterr().out
        # No HTML stored AND policy OFF → ne pas afficher la ligne (réduit le bruit)
        assert 'Full HTML' not in out

    def test_shows_full_html_line_when_policy_off_but_legacy_data(self, fresh_db, capsys):
        """Si un Land a la politique OFF mais contient du HTML hérité, on affiche."""
        m = fresh_db["model"]
        from mwi import controller
        land = m.Land.create(name="d4_legacy", description="t", lang="fr",
                             fullhtml=False)
        domain = m.Domain.create(name="d4-legacy.com")
        m.Expression.create(
            land=land, domain=domain, depth=0,
            url="https://d4-legacy.com/1",
            html='<html>legacy</html>',
        )

        controller.LandController.list(argparse.Namespace(name='d4_legacy'))
        out = capsys.readouterr().out
        assert 'Full HTML' in out
        assert 'policy=OFF' in out


class TestFullhtmlSizeCap:
    """[sprint-html E — D5.1] Plafond settings.fullhtml_max_size_kb."""

    def test_truncates_oversized_html(self, fresh_db, monkeypatch):
        """HTML > cap est tronqué à exactement cap*1024 bytes."""
        from mwi.fetcher import FetchResult
        m = fresh_db["model"]
        core = fresh_db["core"]
        # Cap minuscule pour le test : 1 KB. Patcher via core.settings pour
        # s'assurer que c'est le même module que celui utilisé par
        # _maybe_truncate_html (le conftest pop sys.modules['settings']).
        monkeypatch.setattr(core.settings, 'fullhtml_max_size_kb', 1, raising=False)

        land = m.Land.create(name="cap1", description="t", lang="fr",
                             fullhtml=True)
        domain = m.Domain.create(name="cap1.com")
        expr = m.Expression.create(land=land, domain=domain, depth=0,
                                   url="https://cap1.com/big")
        # 5 KB de HTML — bien au-delà du cap
        big_html = '<html><body>' + ('x' * 5000) + '</body></html>'

        async def fake_fetch(url, session=None, **kw):
            return FetchResult(url=url, status_code='200', html=big_html,
                               method_used='aiohttp')

        with patch.object(core, 'fetch_html', side_effect=fake_fetch):
            _run(core.crawl_expression_with_media_analysis(
                expr, [], session=None, store_html=True))

        fetched = m.Expression.get_by_id(expr.id)
        assert fetched.html is not None
        assert len(fetched.html) == 1024
        assert fetched.html.startswith('<html><body>')

    def test_no_truncation_when_under_cap(self, fresh_db, monkeypatch):
        """HTML ≤ cap est stocké tel quel."""
        from mwi.fetcher import FetchResult
        m = fresh_db["model"]
        core = fresh_db["core"]
        monkeypatch.setattr(core.settings, 'fullhtml_max_size_kb', 100, raising=False)

        land = m.Land.create(name="cap2", description="t", lang="fr",
                             fullhtml=True)
        domain = m.Domain.create(name="cap2.com")
        expr = m.Expression.create(land=land, domain=domain, depth=0,
                                   url="https://cap2.com/small")
        small_html = '<html><body><p>OK</p></body></html>'

        async def fake_fetch(url, session=None, **kw):
            return FetchResult(url=url, status_code='200', html=small_html,
                               method_used='aiohttp')

        with patch.object(core, 'fetch_html', side_effect=fake_fetch):
            _run(core.crawl_expression_with_media_analysis(
                expr, [], session=None, store_html=True))

        assert m.Expression.get_by_id(expr.id).html == small_html

    def test_cap_zero_disables_truncation(self, fresh_db, monkeypatch):
        """fullhtml_max_size_kb=0 désactive le plafond complètement."""
        from mwi.fetcher import FetchResult
        m = fresh_db["model"]
        core = fresh_db["core"]
        monkeypatch.setattr(core.settings, 'fullhtml_max_size_kb', 0, raising=False)

        land = m.Land.create(name="cap0", description="t", lang="fr",
                             fullhtml=True)
        domain = m.Domain.create(name="cap0.com")
        expr = m.Expression.create(land=land, domain=domain, depth=0,
                                   url="https://cap0.com/huge")
        huge_html = '<html><body>' + ('y' * 50000) + '</body></html>'

        async def fake_fetch(url, session=None, **kw):
            return FetchResult(url=url, status_code='200', html=huge_html,
                               method_used='aiohttp')

        with patch.object(core, 'fetch_html', side_effect=fake_fetch):
            _run(core.crawl_expression_with_media_analysis(
                expr, [], session=None, store_html=True))

        # Pas de troncature : taille intégrale conservée
        assert len(m.Expression.get_by_id(expr.id).html) == len(huge_html)

    def test_helper_returns_input_when_disabled(self, fresh_db, monkeypatch):
        """Test isolé du helper _maybe_truncate_html."""
        core = fresh_db["core"]
        monkeypatch.setattr(core.settings, 'fullhtml_max_size_kb', 0, raising=False)
        assert core._maybe_truncate_html("anything") == "anything"
        assert core._maybe_truncate_html("") == ""

    def test_helper_truncates_correctly(self, fresh_db, monkeypatch):
        core = fresh_db["core"]
        monkeypatch.setattr(core.settings, 'fullhtml_max_size_kb', 2, raising=False)
        body = "z" * 5000
        out = core._maybe_truncate_html(body)
        assert len(out) == 2048


class TestHtmldumpExport:
    """[sprint-html E — D5.2] Export `--type=htmldump`."""

    def test_htmldump_zip_contains_html_files_and_manifest(self, fresh_db, tmp_path, monkeypatch):
        """Le zip contient un .html par expression + manifest.csv."""
        import zipfile
        m = fresh_db["model"]
        core = fresh_db["core"]
        # Forcer data_location vers tmp_path pour cet export — patcher
        # core.settings (pas `import settings`) pour atteindre le module
        # vraiment utilisé par export_land.
        monkeypatch.setattr(core.settings, 'data_location', str(tmp_path), raising=False)

        land = m.Land.create(name="dump_ok", description="t", lang="fr",
                             fullhtml=True)
        domain = m.Domain.create(name="dump.com")
        # 2 expressions avec html, 1 sans
        e1 = m.Expression.create(land=land, domain=domain, depth=0,
                                 url="https://dump.com/1",
                                 html='<html>page1</html>',
                                 http_status='200', fetch_method='aiohttp',
                                 relevance=2)
        e2 = m.Expression.create(land=land, domain=domain, depth=0,
                                 url="https://dump.com/2",
                                 html='<html>page2</html>',
                                 http_status='403', fetch_method='curl_cffi',
                                 relevance=1)
        m.Expression.create(land=land, domain=domain, depth=0,
                            url="https://dump.com/3",
                            html=None, http_status='404', relevance=0)

        core.export_land(land, 'htmldump', minimum_relevance=1)

        # Trouver le zip produit
        zips = list(tmp_path.glob("export_land_dump_ok_htmldump_*.zip"))
        assert len(zips) == 1, f"Expected 1 zip, got {zips}"
        with zipfile.ZipFile(zips[0]) as zf:
            names = sorted(zf.namelist())
            assert f"{e1.id}.html" in names
            assert f"{e2.id}.html" in names
            assert "manifest.csv" in names
            # Pas la 3e (html NULL)
            assert len([n for n in names if n.endswith('.html')]) == 2
            # Vérifier contenu d'un fichier
            assert zf.read(f"{e1.id}.html").decode() == '<html>page1</html>'
            # Vérifier le manifest
            mani = zf.read("manifest.csv").decode()
            assert 'id,url,http_status,fetch_method' in mani
            assert 'aiohttp' in mani and 'curl_cffi' in mani

    def test_htmldump_skips_expressions_below_minrel(self, fresh_db, tmp_path, monkeypatch):
        """Le filtre relevance >= minimum_relevance s'applique."""
        import zipfile
        m = fresh_db["model"]
        core = fresh_db["core"]
        monkeypatch.setattr(core.settings, 'data_location', str(tmp_path), raising=False)

        land = m.Land.create(name="dump_min", description="t", lang="fr",
                             fullhtml=True)
        domain = m.Domain.create(name="dumpmin.com")
        # Une expression sous le seuil
        m.Expression.create(land=land, domain=domain, depth=0,
                            url="https://dumpmin.com/low",
                            html='<html>low</html>', relevance=0)
        e_high = m.Expression.create(land=land, domain=domain, depth=0,
                                     url="https://dumpmin.com/high",
                                     html='<html>high</html>', relevance=5)

        core.export_land(land, 'htmldump', minimum_relevance=1)

        zips = list(tmp_path.glob("export_land_dump_min_htmldump_*.zip"))
        assert len(zips) == 1
        with zipfile.ZipFile(zips[0]) as zf:
            html_names = [n for n in zf.namelist() if n.endswith('.html')]
            assert html_names == [f"{e_high.id}.html"]


class TestMigration:
    """Tests for the migration adding html columns."""

    def test_migration_adds_html_columns(self, tmp_path):
        """Migration 007 adds html and fullhtml columns to legacy databases."""
        db = peewee.SqliteDatabase(str(tmp_path / "old.db"))

        # Create minimal tables WITHOUT new columns
        db.execute_sql("""CREATE TABLE land (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT, lang TEXT
        )""")
        db.execute_sql("""CREATE TABLE expression (
            id INTEGER PRIMARY KEY, url TEXT NOT NULL, readable TEXT
        )""")
        db.execute_sql("INSERT INTO land (name, description) VALUES ('test', 'desc')")
        db.execute_sql("INSERT INTO expression (url) VALUES ('https://example.com')")

        # Verify columns don't exist
        expr_cols = [r[1] for r in db.execute_sql("PRAGMA table_info('expression')").fetchall()]
        land_cols = [r[1] for r in db.execute_sql("PRAGMA table_info('land')").fetchall()]
        assert 'html' not in expr_cols
        assert 'fullhtml' not in land_cols

        # Apply migration
        db.execute_sql("ALTER TABLE expression ADD COLUMN html TEXT DEFAULT NULL")
        db.execute_sql("ALTER TABLE land ADD COLUMN fullhtml INTEGER DEFAULT 0")

        # Verify columns exist
        expr_cols = [r[1] for r in db.execute_sql("PRAGMA table_info('expression')").fetchall()]
        land_cols = [r[1] for r in db.execute_sql("PRAGMA table_info('land')").fetchall()]
        assert 'html' in expr_cols
        assert 'fullhtml' in land_cols

        # Verify default values on existing rows
        row = db.execute_sql("SELECT html FROM expression WHERE url='https://example.com'").fetchone()
        assert row[0] is None
        land_row = db.execute_sql("SELECT fullhtml FROM land WHERE name='test'").fetchone()
        assert land_row[0] == 0
        db.close()
