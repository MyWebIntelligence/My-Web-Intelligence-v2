"""Body links: union of the markdown and HTML legs of Trafilatura.

Sprint body-links, T2. Measured on the gold set: on the 123 citations the
extractor misses, the markdown leg recovers 6 and Trafilatura's HTML output --
already computed for media extraction and never used for links -- recovers 26.
Widening that leg with favor_recall recovers 33 more, for 0.002 of precision.

The markdown leg must stay byte-identical to what it produced before: it is
what feeds expression.readable, hence relevance, the LLM gate, embeddings and
the corpus export.
"""
from unittest.mock import patch

import pytest

from mwi import body_links, core, link_context


BASE = 'https://source.test/article'

# The link inside <em> is the shape the markdown serialisation loses.
READABLE_HTML = """<html><body>
<p>Prose citant <a href="https://cible-a.test/page">une source</a>.</p>
<p>Encore de la prose avec <em><a href="https://cible-b.test/page">une
autre</a></em> au milieu.</p>
<ul><li><a href="/relatif/x">lien relatif</a></li></ul>
<p><a href="mailto:x@y.test">courriel</a>
<a href="javascript:void(0)">script</a>
<a href="#section">ancre</a>
<a href="https://source.test/article#bas">meme page</a></p>
</body></html>"""

MARKDOWN = """Prose citant [une source](https://cible-a.test/page).

Un paragraphe sans lien.
"""


class TestExtractBodyLinks:

    def test_markdown_leg_matches_the_historical_extractor(self):
        links = body_links.extract_body_links(MARKDOWN, None, BASE)

        assert [link.url for link in links] == \
            link_context.extract_markdown_links(MARKDOWN, BASE)

    def test_html_leg_recovers_what_markdown_loses(self):
        links = body_links.extract_body_links(MARKDOWN, READABLE_HTML, BASE)

        urls = [link.url for link in links]
        assert 'https://cible-b.test/page' in urls

    def test_document_order_markdown_first_then_html_only(self):
        links = body_links.extract_body_links(MARKDOWN, READABLE_HTML, BASE)

        urls = [link.url for link in links]
        assert urls[0] == 'https://cible-a.test/page'
        assert urls.index('https://cible-b.test/page') < \
            urls.index('https://source.test/relatif/x')
        assert [link.order for link in links] == sorted(
            link.order for link in links)

    def test_origin_is_marked(self):
        links = body_links.extract_body_links(MARKDOWN, READABLE_HTML, BASE)
        origin = {link.url: link.origin for link in links}

        # Present in both legs -> both; HTML only -> html.
        assert origin['https://cible-a.test/page'] == body_links.ORIGIN_BOTH
        assert origin['https://cible-b.test/page'] == body_links.ORIGIN_HTML

    def test_markdown_only_link_is_marked_md(self):
        links = body_links.extract_body_links(MARKDOWN, None, BASE)

        assert links[0].origin == body_links.ORIGIN_MD
        assert links[0].raw == 'https://cible-a.test/page'

    def test_deduplicated_on_normalized_url(self):
        html = ('<p><a href="https://cible-a.test/page">a</a>'
                '<a href="https://cible-a.test/page">a again</a></p>')

        links = body_links.extract_body_links(None, html, BASE)

        assert [link.url for link in links] == ['https://cible-a.test/page']

    def test_relative_href_is_resolved(self):
        links = body_links.extract_body_links(None, READABLE_HTML, BASE)

        assert 'https://source.test/relatif/x' in [link.url for link in links]

    @pytest.mark.parametrize('href', [
        'mailto:x@y.test', 'javascript:void(0)', '#section',
    ])
    def test_non_navigational_hrefs_are_dropped(self, href):
        links = body_links.extract_body_links(None, READABLE_HTML, BASE)

        assert all(href not in link.url for link in links)

    def test_same_page_anchor_is_dropped(self):
        links = body_links.extract_body_links(None, READABLE_HTML, BASE)

        assert all(not link.url.startswith(BASE) for link in links)

    def test_is_deterministic(self):
        runs = [[link.url for link in
                 body_links.extract_body_links(MARKDOWN, READABLE_HTML, BASE)]
                for _ in range(10)]

        assert all(run == runs[0] for run in runs)

    @pytest.mark.parametrize('md, html', [
        (None, None), ('', ''), (None, '<not html'), ('[x](', None),
    ])
    def test_never_raises_on_degenerate_input(self, md, html):
        assert isinstance(body_links.extract_body_links(md, html, BASE), list)

    def test_reuses_a_soup_the_caller_already_built(self):
        soup = link_context._quiet_soup(READABLE_HTML, 'html.parser')

        with patch.object(link_context, '_quiet_soup') as quiet:
            body_links.extract_body_links(MARKDOWN, READABLE_HTML, BASE,
                                          soup=soup)

        assert quiet.call_count == 0

    def test_module_is_a_leaf(self):
        """A module that can import core or model is a module that can write."""
        with open(body_links.__file__, encoding='utf-8') as handle:
            text = handle.read()
        assert 'from . import core' not in text
        assert 'from . import model' not in text
        assert 'llm_openrouter' not in text


class TestCoreIntegration:
    """The crawl path keeps its contract and its HTML-parse budget."""

    HTML = """<html><head><title>T</title></head><body><article>
    <p>Un paragraphe de prose assez long pour que Trafilatura retienne la page
    comme un corps de texte veritable, citant
    <a href="https://cible-a.test/page">une source</a> au fil de la phrase.</p>
    <p>Un second paragraphe tout aussi bavard, present pour que l extraction
    ne rejette pas la page comme trop courte, avec
    <em><a href="https://cible-b.test/page">un lien enchasse</a></em>.</p>
    </article></body></html>"""

    @staticmethod
    def _expression(fresh_db):
        model = fresh_db['model']
        core_mod = fresh_db['core']
        controller = fresh_db['controller']
        controller.LandController.create(
            core_mod.Namespace(name='L', desc='d', lang=['fr']))
        land = model.Land.get(model.Land.name == 'L')
        domain, _ = model.Domain.get_or_create(name='source.test')
        return model.Expression.create(land=land, domain=domain, url=BASE,
                                       depth=0)

    def test_returns_a_two_tuple(self, fresh_db):
        expression = self._expression(fresh_db)

        result = core._extract_content_and_links(self.HTML, expression)

        assert isinstance(result, tuple) and len(result) == 2

    def test_links_are_body_links(self, fresh_db):
        expression = self._expression(fresh_db)

        _, links = core._extract_content_and_links(self.HTML, expression)

        assert links and all(isinstance(link, body_links.BodyLink)
                             for link in links)

    def test_html_leg_is_used(self, fresh_db):
        expression = self._expression(fresh_db)

        _, links = core._extract_content_and_links(self.HTML, expression)

        assert 'https://cible-b.test/page' in [link.url for link in links]

    def test_parses_the_readable_html_once(self, fresh_db):
        """The duplicate parse of readable_html funded the HTML leg."""
        expression = self._expression(fresh_db)

        with patch.object(core, 'BeautifulSoup',
                          wraps=core.BeautifulSoup) as soup:
            core._extract_content_and_links(self.HTML, expression)

        assert soup.call_count == 1

    def test_favor_recall_is_applied_to_the_html_leg_only(self, fresh_db):
        """favor_recall on markdown would corrupt expression.readable."""
        expression = self._expression(fresh_db)

        with patch.object(core.trafilatura, 'extract',
                          wraps=core.trafilatura.extract) as extract:
            core._extract_content_and_links(self.HTML, expression)

        by_format = {call.kwargs.get('output_format'): call.kwargs
                     for call in extract.call_args_list}
        assert 'favor_recall' not in by_format['markdown']
        assert by_format['html'].get('favor_recall') is True

    def test_url_is_passed_to_trafilatura(self, fresh_db):
        expression = self._expression(fresh_db)

        with patch.object(core.trafilatura, 'extract',
                          wraps=core.trafilatura.extract) as extract:
            core._extract_content_and_links(self.HTML, expression)

        assert all(call.kwargs.get('url') == BASE
                   for call in extract.call_args_list)
