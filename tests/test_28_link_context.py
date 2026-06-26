"""Tests for the link-context feature (sprint link-context, migration 012).

Locks the contract:
- mwi.link_context pure helpers (dom path, block ancestor, dom map, markdown
  paragraph extraction).
- Migration 012 adds expressionlink.context/dom/dom_html idempotently.
- crawl_expression* populates the new columns from the raw HTML.
- consolidate_land backfills from expression.html (NULL dom without it).
- MercuryReadablePipeline._update_expression_links populates them too.
"""

import asyncio
from unittest.mock import patch

import peewee
import pytest
from bs4 import BeautifulSoup

from mwi import link_context


def run(coro):
    """Tiny helper since the project does not use pytest-asyncio."""
    return asyncio.new_event_loop().run_until_complete(coro)


NESTED_HTML = """
<html><head><title>Page de test</title></head>
<body>
<div id="main" class="layout wide">
  <article class="post">
    <p>Un paragraphe introductif qui parle du sujet et cite
       <a href="https://exemple-cible.com/article">cet article</a> en détail.</p>
    <p>Un second paragraphe avec un autre lien vers
       <a href="https://autre-cible.org/page/">une autre page</a> de référence.</p>
  </article>
</div>
<footer><a href="https://exemple-cible.com/article">lien dupliqué en footer</a></footer>
</body></html>
"""


class TestBuildDomPath:
    """CSS path construction from a <a> tag up to the root."""

    def test_build_dom_path_ids_and_classes(self):
        soup = BeautifulSoup(NESTED_HTML, 'html.parser')
        a_tag = soup.find('a', href="https://exemple-cible.com/article")
        path = link_context.build_dom_path(a_tag)
        assert path == 'html > body > div#main.layout.wide > article.post > p'

    def test_build_dom_path_caps_classes_at_three(self):
        html = '<html><body><div class="a b c d e"><p><a href="https://x.test/">x</a></p></div></body></html>'
        soup = BeautifulSoup(html, 'html.parser')
        path = link_context.build_dom_path(soup.find('a'))
        assert 'div.a.b.c' in path
        assert '.d' not in path and '.e' not in path


class TestFindBlockAncestor:
    """Closest block-level ancestor resolution."""

    def test_find_block_ancestor_prefers_strict_block(self):
        soup = BeautifulSoup(NESTED_HTML, 'html.parser')
        a_tag = soup.find('a', href="https://exemple-cible.com/article")
        block = link_context.find_block_ancestor(a_tag)
        assert block.name == 'p'

    def test_find_block_ancestor_falls_back_to_div(self):
        html = '<html><body><div class="box"><a href="https://x.test/">x</a></div></body></html>'
        soup = BeautifulSoup(html, 'html.parser')
        block = link_context.find_block_ancestor(soup.find('a'))
        assert block.name == 'div'

    def test_find_block_ancestor_none_under_body(self):
        html = '<html><body><a href="https://x.test/">x</a></body></html>'
        soup = BeautifulSoup(html, 'html.parser')
        assert link_context.find_block_ancestor(soup.find('a')) is None


class TestExtractLinkDomMap:
    """href -> LinkDomInfo map construction."""

    def test_extract_link_dom_map_nominal(self):
        mapping = link_context.extract_link_dom_map(
            NESTED_HTML, "https://source.test/page")
        info = link_context.lookup_link_info(
            mapping, "https://exemple-cible.com/article")
        assert info is not None
        assert info.dom.endswith('> p')
        assert info.dom_html.startswith('<p>')
        assert 'cet article' in info.block_text

    def test_extract_link_dom_map_resolves_relative_href(self):
        html = '<html><body><p><a href="/sous/page">rel</a></p></body></html>'
        mapping = link_context.extract_link_dom_map(html, "https://source.test/dir/")
        info = link_context.lookup_link_info(mapping, "https://source.test/sous/page")
        assert info is not None
        assert info.dom.endswith('> p')

    def test_extract_link_dom_map_skips_mailto_javascript_anchor(self):
        html = ('<html><body><p>'
                '<a href="mailto:x@y.z">m</a>'
                '<a href="javascript:void(0)">j</a>'
                '<a href="#section">a</a>'
                '<a href="tel:+33102030405">t</a>'
                '</p></body></html>')
        mapping = link_context.extract_link_dom_map(html, "https://source.test/")
        assert mapping == {}

    def test_extract_link_dom_map_first_occurrence_wins(self):
        mapping = link_context.extract_link_dom_map(
            NESTED_HTML, "https://source.test/page")
        # The same URL appears in <p> (first) and in <footer> (second)
        info = link_context.lookup_link_info(
            mapping, "https://exemple-cible.com/article")
        assert 'footer' not in info.dom
        assert info.dom.endswith('> p')

    def test_extract_link_dom_map_never_raises(self):
        assert link_context.extract_link_dom_map(None, "https://x.test/") == {}
        assert link_context.extract_link_dom_map("", "https://x.test/") == {}


class TestExtractMdParagraph:
    """Markdown paragraph (blank-line delimited) lookup."""

    MD = ("# Titre\n\n"
          "Premier paragraphe sans lien, juste du texte.\n\n"
          "Deuxième paragraphe citant [cet article](https://exemple-cible.com/article) "
          "au milieu d'une phrase plus longue.\n\n"
          "Troisième paragraphe final.")

    def test_extract_md_paragraph_finds_paragraph(self):
        para = link_context.extract_md_paragraph(
            self.MD, "https://exemple-cible.com/article")
        assert para is not None
        assert para.startswith("Deuxième paragraphe")
        assert "Premier paragraphe" not in para

    def test_extract_md_paragraph_truncates(self, monkeypatch):
        # Patch the settings object captured by link_context (conftest may
        # have replaced sys.modules['settings'] with a re-imported copy).
        monkeypatch.setattr(link_context.settings, 'link_context_max_chars',
                            30, raising=False)
        para = link_context.extract_md_paragraph(
            self.MD, "https://exemple-cible.com/article")
        assert para is not None
        assert len(para) <= 30

    def test_extract_md_paragraph_matches_without_trailing_slash(self):
        md = "Un paragraphe avec [lien](https://exemple-cible.com/article/) final."
        para = link_context.extract_md_paragraph(
            md, "https://exemple-cible.com/article")
        assert para is not None

    def test_extract_md_paragraph_none_when_absent(self):
        assert link_context.extract_md_paragraph(
            self.MD, "https://introuvable.test/x") is None
        assert link_context.extract_md_paragraph(None, "https://x.test/") is None
        assert link_context.extract_md_paragraph(self.MD, None) is None


class TestSchemaAndMigration012:
    """Schema guarantees + defensive migration on legacy databases."""

    def test_expressionlink_has_new_columns(self, fresh_db):
        m = fresh_db["model"]
        cols = [row[1] for row in
                m.DB.execute_sql("PRAGMA table_info('expressionlink')").fetchall()]
        for col in ('context', 'dom', 'dom_html'):
            assert col in cols

    def test_new_columns_nullable_by_default(self, fresh_db):
        m = fresh_db["model"]
        domain = m.Domain.create(name="lc-null.com")
        land = m.Land.create(name="lc_null", description="t", lang="fr")
        src = m.Expression.create(land=land, domain=domain,
                                  url="https://lc-null.com/src")
        tgt = m.Expression.create(land=land, domain=domain,
                                  url="https://lc-null.com/tgt")
        m.ExpressionLink.create(source=src, target=tgt)
        link = m.ExpressionLink.get(m.ExpressionLink.source == src)
        assert link.context is None
        assert link.dom is None
        assert link.dom_html is None

    def test_migration_012_adds_columns_idempotent(self, tmp_path):
        db = peewee.SqliteDatabase(str(tmp_path / "legacy.db"))
        db.execute_sql("""CREATE TABLE expressionlink (
            source_id INTEGER NOT NULL, target_id INTEGER NOT NULL,
            PRIMARY KEY (source_id, target_id)
        )""")
        db.execute_sql("INSERT INTO expressionlink VALUES (1, 2)")

        cols = [r[1] for r in
                db.execute_sql("PRAGMA table_info('expressionlink')").fetchall()]
        assert 'context' not in cols

        # Apply migration (mirrors what 012 upgrade() does)
        for col in ('context', 'dom', 'dom_html'):
            db.execute_sql(
                f"ALTER TABLE expressionlink ADD COLUMN {col} TEXT DEFAULT NULL")

        cols = [r[1] for r in
                db.execute_sql("PRAGMA table_info('expressionlink')").fetchall()]
        for col in ('context', 'dom', 'dom_html'):
            assert col in cols

        row = db.execute_sql(
            "SELECT context, dom, dom_html FROM expressionlink").fetchone()
        assert row == (None, None, None)

        # Idempotent: second ALTER raises duplicate-column, swallowed by helper
        with pytest.raises(Exception) as exc:
            db.execute_sql(
                "ALTER TABLE expressionlink ADD COLUMN context TEXT DEFAULT NULL")
        assert 'duplicate column' in str(exc.value).lower()
        db.close()


CRAWL_HTML = """
<html lang="fr"><head><title>Article sur la transition</title></head>
<body>
<div id="content" class="layout">
  <article class="post">
    <p>La transition écologique mobilise de nombreux acteurs publics et privés,
       comme l'explique <a href="https://cible-un.test/analyse">cette analyse</a>
       publiée récemment par un laboratoire de recherche.</p>
    <p>D'autres travaux complémentaires sont disponibles sur
       <a href="https://cible-deux.test/rapport">ce rapport</a> institutionnel
       qui détaille les politiques territoriales engagées depuis dix ans.</p>
  </article>
</div>
</body></html>
"""


class TestCrawlPopulatesLinkContext:
    """crawl_expression persists context/dom/dom_html on created links."""

    def test_crawl_populates_link_context(self, fresh_db, monkeypatch):
        m = fresh_db["model"]
        core = fresh_db["core"]
        from mwi.fetcher import FetchResult

        land = m.Land.create(name="lc_crawl", description="t", lang="fr")
        domain = m.Domain.create(name="lc-crawl.com")
        expr = m.Expression.create(land=land, domain=domain,
                                   url="https://lc-crawl.com/page", depth=0)

        async def fake_fetch(url, session=None, **kw):
            return FetchResult(url=url, status_code='200', html=CRAWL_HTML,
                               method_used='aiohttp')

        # Force a positive relevance and a compatible language; disable
        # dynamic media extraction (would spawn a browser).
        monkeypatch.setattr(core, 'expression_relevance', lambda d, e: 1)
        monkeypatch.setattr(core, 'detect_content_language', lambda *a, **k: 'fr')
        monkeypatch.setattr(core.settings, 'dynamic_media_extraction', False,
                            raising=False)

        with patch.object(core, 'fetch_html', side_effect=fake_fetch):
            run(core.crawl_expression(expr, [], session=None))

        links = list(m.ExpressionLink.select().where(
            m.ExpressionLink.source == expr.id))
        assert len(links) >= 2
        for link in links:
            assert link.context, "context must be populated"
            assert link.dom, "dom must be populated"
            assert link.dom.endswith('> p')
            assert 'div#content.layout' in link.dom
            assert link.dom_html.startswith('<p>')

    def test_crawl_without_html_leaves_columns_null(self, fresh_db, monkeypatch):
        """Links created from content without raw HTML keep NULL dom columns."""
        m = fresh_db["model"]
        core = fresh_db["core"]

        land = m.Land.create(name="lc_nohtml", description="t", lang="fr")
        domain = m.Domain.create(name="lc-nohtml.com")
        src = m.Expression.create(land=land, domain=domain,
                                  url="https://lc-nohtml.com/src", depth=0)
        # Direct call: no raw HTML in the loop -> empty dom_map path
        ok = core.link_expression(land, src, "https://cible-trois.test/page")
        assert ok is True
        link = m.ExpressionLink.get(m.ExpressionLink.source == src)
        assert link.context is None
        assert link.dom is None
        assert link.dom_html is None


class TestConsolidateBackfill:
    """land consolidate backfills context/dom/dom_html on existing lands."""

    def _make_expression(self, m, land, domain, url, readable, html=None):
        import datetime
        return m.Expression.create(
            land=land, domain=domain, url=url, depth=0,
            readable=readable, html=html,
            readable_at=datetime.datetime.now())

    def test_consolidate_backfills_and_nulls_without_html(self, fresh_db):
        m = fresh_db["model"]
        core = fresh_db["core"]

        land = m.Land.create(name="lc_consol", description="t", lang="fr")
        domain = m.Domain.create(name="lc-consol.com")
        readable = ("Un paragraphe citant [cette analyse]"
                    "(https://cible-un.test/analyse) au fil du texte.\n\n"
                    "Autre paragraphe sans lien.")

        with_html = self._make_expression(
            m, land, domain, "https://lc-consol.com/avec-html",
            readable, html=CRAWL_HTML)
        without_html = self._make_expression(
            m, land, domain, "https://lc-consol.com/sans-html",
            readable, html=None)

        processed, errors = run(core.consolidate_land(land))
        assert errors == 0
        assert processed >= 2

        link_with = m.ExpressionLink.get(
            m.ExpressionLink.source == with_html.id)
        assert link_with.context and 'cette analyse' in link_with.context
        assert link_with.dom and link_with.dom.endswith('> p')
        assert link_with.dom_html and link_with.dom_html.startswith('<p>')

        link_without = m.ExpressionLink.get(
            m.ExpressionLink.source == without_html.id)
        assert link_without.context and 'cette analyse' in link_without.context
        assert link_without.dom is None
        assert link_without.dom_html is None


class TestReadablePipelineLinkContext:
    """Mercury pipeline populates the new columns too."""

    def _build(self, m, suffix, html=None):
        import datetime
        land = m.Land.create(name=f"lc_merc_{suffix}", description="t", lang="fr")
        domain = m.Domain.create(name=f"lc-merc-{suffix}.com")
        readable = ("Paragraphe d'ouverture.\n\n"
                    "Paragraphe citant [cette analyse]"
                    "(https://cible-un.test/analyse) avec précision.\n\n"
                    "Paragraphe de clôture.")
        expr = m.Expression.create(
            land=land, domain=domain,
            url=f"https://lc-merc-{suffix}.com/page", depth=0,
            readable=readable, html=html,
            readable_at=datetime.datetime.now())
        return expr

    def test_readable_pipeline_links_get_context(self, fresh_db):
        m = fresh_db["model"]
        from mwi.readable_pipeline import MercuryReadablePipeline

        pipeline = MercuryReadablePipeline()
        expr = self._build(m, "ctx", html=CRAWL_HTML)
        new_links = pipeline._extract_links_from_markdown(
            str(expr.readable), str(expr.url))
        assert new_links and new_links[0]['raw_url']

        pipeline._update_expression_links(expr, new_links)

        link = m.ExpressionLink.get(m.ExpressionLink.source == expr.id)
        assert link.context and 'cette analyse' in link.context
        assert link.dom and link.dom.endswith('> p')
        assert link.dom_html and link.dom_html.startswith('<p>')

    def test_dom_html_truncation(self, fresh_db, monkeypatch):
        m = fresh_db["model"]
        from mwi.readable_pipeline import MercuryReadablePipeline

        # Patch the settings object captured by link_context (conftest
        # re-imports the settings module, link_context keeps its own ref).
        monkeypatch.setattr(link_context.settings, 'link_dom_html_max_chars',
                            50, raising=False)
        pipeline = MercuryReadablePipeline()
        expr = self._build(m, "trunc", html=CRAWL_HTML)
        new_links = pipeline._extract_links_from_markdown(
            str(expr.readable), str(expr.url))

        pipeline._update_expression_links(expr, new_links)

        link = m.ExpressionLink.get(m.ExpressionLink.source == expr.id)
        assert link.dom_html is not None
        assert len(link.dom_html) <= 50

    def test_readable_pipeline_balanced_parens_not_truncated(self, fresh_db):
        # sprint EXTRACTLINKS-2026-06 (A2): the unified iterator keeps balanced
        # parentheses; the legacy [^)\s]+ regex truncated at the first ')'.
        from mwi.readable_pipeline import MercuryReadablePipeline

        pipeline = MercuryReadablePipeline()
        markdown = ("Voir [Runaround]"
                    "(https://en.wikipedia.org/wiki/Runaround_(story)) ici.")
        new_links = pipeline._extract_links_from_markdown(
            markdown, "https://src.test/page")

        urls = [link['url'] for link in new_links]
        assert "https://en.wikipedia.org/wiki/Runaround_(story)" in urls

    def test_readable_pipeline_relative_link_resolved(self, fresh_db):
        # sprint EXTRACTLINKS-2026-06 (Family B): relative links resolved.
        from mwi.readable_pipeline import MercuryReadablePipeline

        pipeline = MercuryReadablePipeline()
        new_links = pipeline._extract_links_from_markdown(
            "Voir [Article 57](/en/ai-act/article-57) ci-dessous.",
            "https://ai-act-service-desk.ec.europa.eu/en/ai-act-explorer")

        urls = [link['url'] for link in new_links]
        assert ("https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-57"
                in urls)
