"""Structural classification of body links: ExpressionLink.kind.

Sprint body-links, T3. Measured on the gold set after T2, the 82 remaining
false positives are TOC 27, RECO 21, X_OTHER 9, NAV 8, META_REFTOOL 7,
NOMAJ 4, DATA_LISTING 3, EDIT 2, META_BOILER 1. This ticket targets the 35
table-of-contents and navigation links.

Two invariants matter more than the rules themselves:

* **No vocabulary.** A rule keyed on the words "Article", "Recital" or
  "References" has perfect precision on the test land and no value anywhere
  else. Enforced by an allowlist read off the module's AST, and by replaying
  the same page in Japanese.
* **The classification reads the RAW DOM.** Trafilatura's HTML output carries
  no class, no id and no nav/header/footer/aside, so a rule written against it
  would be silently inert.
"""
import ast
import asyncio
import importlib.util
import os
import re
from unittest.mock import patch

import peewee

from mwi import body_links, link_context


BASE = 'https://site.test/article'
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')


def run(coro):
    """Tiny helper since the project does not use pytest-asyncio."""
    return asyncio.new_event_loop().run_until_complete(coro)


def _load(name):
    with open(os.path.join(FIXTURES, name), encoding='utf-8') as handle:
        return handle.read()


def _kinds(html, base_url=BASE):
    """url -> kind, as the crawl path computes it."""
    dom_map = link_context.extract_link_dom_map(html, base_url)
    out = {}
    for html_url in link_context.extract_all_links(html, base_url):
        info = link_context.lookup_link_info(dom_map, html_url)
        out[html_url] = body_links.classify(info)[0]
    return out


class TestKindVocabulary:

    def test_kind_values_are_the_declared_set(self):
        assert body_links.KINDS == ('body', 'nav', 'toc', 'reco', 'ref')

    def test_body_is_the_default_and_null_means_body(self):
        assert body_links.KIND_DEFAULT == 'body'
        assert body_links.is_retained(None) is True
        assert body_links.is_retained('body') is True
        assert body_links.is_retained('nav') is False

    def test_rank_orders_by_distance_to_the_discourse(self):
        """body wins over everything; nav loses to everything."""
        rank = body_links.KIND_RANK

        assert rank['body'] == 0
        assert rank['body'] < rank['ref'] < rank['reco'] < rank['toc'] < rank['nav']
        assert set(rank) == set(body_links.KINDS)


class TestStructuralRules:

    def test_semantic_ancestor_is_nav(self):
        kinds = _kinds(_load('link_zones_page.html'))

        assert kinds['https://site.test/accueil'] == 'nav'
        assert kinds['https://site.test/mentions'] == 'nav'

    def test_short_breadcrumb_is_nav(self):
        kinds = _kinds(_load('link_zones_page.html'))

        assert kinds['https://site.test/rubrique'] == 'nav'

    def test_an_article_wrapped_in_a_header_stays_body(self):
        """The failure the gold set exposed, frozen as a test.

        Templates routinely use <header> as a page-wide hero wrapper rather
        than a masthead. An unqualified "any sectioning ancestor" rule then
        exiles the whole article: measured on the gold set it cost 4 genuine
        citations. A sectioning element that is mostly prose is not an annex.
        """
        html = _load('link_zones_page.html')
        assert 'class="page-hero"' in html

        kinds = _kinds(html)

        assert kinds['https://externe-a.test/etude'] == 'body'
        assert kinds['https://externe-b.test/rapport'] == 'body'

    def test_anchor_grid_is_toc(self):
        kinds = _kinds(_load('link_zones_page.html'))

        assert kinds['https://site.test/s1'] == 'toc'
        assert kinds['https://site.test/s10'] == 'toc'

    def test_toc_is_recognised_without_a_matching_class_name(self):
        """The fixture names that section "sommaire" on purpose.

        No token of the structural allowlist matches it, so only the anchor
        grid can classify it -- which is the whole point of a rule that does
        not depend on the language of the markup.
        """
        html = _load('link_zones_page.html')
        assert 'class="sommaire"' in html

        assert _kinds(html)['https://site.test/s5'] == 'toc'

    def test_prose_citation_stays_body(self):
        kinds = _kinds(_load('link_zones_page.html'))

        assert kinds['https://externe-a.test/etude'] == 'body'

    def test_three_close_links_in_one_paragraph_stay_body(self):
        """The failure that destroys 112 true positives if a rule is naive."""
        kinds = _kinds(_load('link_zones_page.html'))

        for url in ('https://externe-b.test/rapport',
                    'https://externe-c.test/avis',
                    'https://externe-d.test/note'):
            assert kinds[url] == 'body', url

    def test_small_aside_block_is_caught_by_the_semantic_rule(self):
        """Two links only: the grid rule cannot fire, the zone rule must."""
        kinds = _kinds(_load('link_zones_page.html'))

        assert kinds['https://externe-e.test/carte'] == 'nav'

    def test_missing_dom_info_defaults_to_body(self):
        """Never exclude for lack of evidence."""
        assert body_links.classify(None) == ('body', 'r0_default')

    def test_classify_never_raises(self):
        info = link_context.LinkDomInfo(dom='', dom_html=None, block_text=None)

        assert body_links.classify(info)[0] in body_links.KINDS


# The allowlist lives HERE, not in the module under test. If it lived in the
# module, adding a content word to a rule would be a one-line edit inside the
# same file; here it forces a visible change to the test, which is the review
# signal we actually want. Each group carries the reason it is allowed.
ALLOWED_TOKENS = frozenset(
    # kind values -- the structural zones themselves
    ('body', 'nav', 'toc', 'reco', 'ref')
    # origin values -- which extraction leg saw the link
    + ('md', 'html', 'both', 'raw')
    # words appearing in rule identifiers (audit trail, never matched against
    # page content)
    + ('default', 'semantic', 'ancestor', 'container', 'token', 'anchor',
       'grid', 'terminal', 'density')
    # UI structure tokens matched against class/id: they name a REGION OF THE
    # INTERFACE, never a subject. This is the exception the sprint allows.
    + ('navbar', 'navigation', 'menu', 'submenu', 'breadcrumb', 'crumb',
       'sidebar')
    # HTML attribute and bs4 parser names
    + ('href', 'parser')
    # fragments of settings key names
    + ('link', 'kind', 'cout', 'min', 'anchors', 'favor', 'recall')
)


def _string_tokens(tree):
    """Alphabetic tokens of every non-docstring string constant, with lines."""
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef,
                             ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                docstrings.add(doc)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if node.value in docstrings:
            continue
        # A regex would otherwise smuggle a whole vocabulary past the check,
        # so every literal is split into words, not compared as a whole.
        for token in re.findall(r'[A-Za-z]{2,}', node.value):
            yield node.lineno, token.lower()


class TestNoLexicalRule:

    def test_rules_use_no_content_vocabulary(self):
        """Allowlist, not denylist: a new word must be argued for in review."""
        with open(body_links.__file__, encoding='utf-8') as handle:
            tree = ast.parse(handle.read())

        offenders = sorted({(line, token)
                            for line, token in _string_tokens(tree)
                            if token not in ALLOWED_TOKENS})

        assert not offenders, (
            'Content words in body_links.py: {}. Add them to ALLOWED_TOKENS '
            'in this test with a justification, or remove them.'
            .format(offenders))

    def test_verdicts_are_identical_in_japanese(self):
        """Same structure, same classes, other language -> same verdicts."""
        french = _kinds(_load('link_zones_page.html'))
        japanese = _kinds(_load('link_zones_page_ja.html'))

        assert sorted(french.items()) == sorted(japanese.items())

    def test_module_stays_a_leaf(self):
        with open(body_links.__file__, encoding='utf-8') as handle:
            tree = ast.parse(handle.read())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported.add('{}.{}'.format(node.module or '',
                                            (node.names[0].name if node.names
                                             else '')))
            elif isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)

        assert not any('core' in name or 'model' in name
                       or 'llm_openrouter' in name for name in imported), imported


class TestLinkDomInfoFields:

    def test_structural_fields_are_filled(self):
        html = _load('link_zones_page.html')
        dom_map = link_context.extract_link_dom_map(html, BASE)

        info = link_context.lookup_link_info(dom_map, 'https://site.test/s1')
        assert info.block_anchor_count >= 8
        assert info.same_domain is True
        assert info.in_semantic_aside is False

        prose = link_context.lookup_link_info(dom_map,
                                              'https://externe-a.test/etude')
        assert prose.same_domain is False
        assert prose.block_anchor_count == 1
        assert prose.block_text_len > 100

    def test_anchor_text_is_not_stored(self):
        """Only its length. Storing the text is what enables a lexical rule."""
        info = link_context.LinkDomInfo(dom='', dom_html=None, block_text=None)

        assert not hasattr(info, 'anchor_text')
        assert hasattr(info, 'anchor_chars')

    def test_no_extra_parse_when_the_caller_supplies_the_soup(self):
        html = _load('link_zones_page.html')
        soup = link_context._quiet_soup(html, 'html.parser')

        with patch.object(link_context, '_quiet_soup') as quiet:
            link_context.extract_link_dom_map(html, BASE, soup=soup)

        assert quiet.call_count == 0

    def test_a_huge_anchor_grid_does_not_blow_up(self):
        """Ascending single pass: a descending find_all would be quadratic."""
        anchors = ''.join(
            '<a href="https://site.test/p{}">{}</a>'.format(i, i)
            for i in range(2000))
        html = '<html><body><section>{}</section></body></html>'.format(anchors)

        dom_map = link_context.extract_link_dom_map(html, BASE)

        info = link_context.lookup_link_info(dom_map, 'https://site.test/p1500')
        assert info.block_anchor_count == 2000


class TestBestOccurrenceWins:

    HTML = """<html><body>
    <nav><a href="https://cible.test/page">Menu</a></nav>
    <article><p>Une phrase de prose citant
    <a href="https://cible.test/page">la meme cible</a> au fil du texte,
    assez longue pour que la densite reste celle d un corps de texte.</p>
    </article></body></html>"""

    def test_the_body_occurrence_wins_over_the_menu_one(self):
        """Menus come first in the document; first-wins would bias to nav."""
        links = [body_links.BodyLink(url='https://cible.test/page',
                                     key='https://cible.test/page',
                                     origin='md', order=0)]
        dom_map = link_context.extract_link_dom_map(self.HTML, BASE,
                                                    rank=body_links.dom_rank)

        resolved = body_links.resolve(links, dom_map)

        assert resolved[0].kind == 'body'

    def test_without_rank_the_first_occurrence_still_wins(self):
        """Retro-compatibility: rank=None keeps the historical behaviour."""
        dom_map = link_context.extract_link_dom_map(self.HTML, BASE)
        info = link_context.lookup_link_info(dom_map, 'https://cible.test/page')

        assert info.in_semantic_aside is True


class TestSchemaAndMigration014:

    @staticmethod
    def _load_migration():
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(here, 'migrations', '014_add_expressionlink_kind.py')
        spec = importlib.util.spec_from_file_location('m014', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_columns_exist_on_a_fresh_database(self, fresh_db):
        model = fresh_db['model']

        cols = [row[1] for row in model.DB.execute_sql(
            "PRAGMA table_info('expressionlink')").fetchall()]

        assert 'kind' in cols and 'kind_rule' in cols and 'origin' in cols

    def test_migration_is_idempotent_on_an_old_database(self, fresh_db,
                                                        tmp_path, monkeypatch):
        model = fresh_db['model']
        old = peewee.SqliteDatabase(str(tmp_path / 'old.db'))
        old.execute_sql('CREATE TABLE expressionlink ('
                        'source_id INTEGER, target_id INTEGER, context TEXT)')
        migration = self._load_migration()
        monkeypatch.setattr(model, 'DB', old)

        migration.upgrade()
        migration.upgrade()          # second pass must not raise

        cols = [row[1] for row in old.execute_sql(
            "PRAGMA table_info('expressionlink')").fetchall()]
        assert 'kind' in cols and 'kind_rule' in cols and 'origin' in cols


class TestPropagation:

    HTML = """<html><head><title>T</title></head><body>
    <nav><a href="https://cible-nav.test/menu">Menu</a></nav>
    <article><p>Un paragraphe de prose veritablement long qui cite
    <a href="https://cible-body.test/source">une source</a> au fil de la phrase
    et se poursuit bien au-dela du seuil de cent caracteres exige.</p>
    <p>Un second paragraphe, present pour que l extraction retienne la page
    comme un corps de texte et non comme une page vide de contenu.</p>
    </article></body></html>"""

    @staticmethod
    def _expression(fresh_db, url=BASE):
        model = fresh_db['model']
        core = fresh_db['core']
        controller = fresh_db['controller']
        controller.LandController.create(
            core.Namespace(name='L', desc='d', lang=['fr']))
        land = model.Land.get(model.Land.name == 'L')
        domain, _ = model.Domain.get_or_create(name='site.test')
        return model.Expression.create(land=land, domain=domain, url=url,
                                       depth=0, relevance=5)

    def test_link_expression_persists_kind(self, fresh_db):
        model = fresh_db['model']
        core = fresh_db['core']
        expression = self._expression(fresh_db)

        core.link_expression(expression.land, expression,
                             'https://cible-nav.test/menu',
                             kind='nav', kind_rule='r1_semantic_ancestor',
                             origin='html')

        link = model.ExpressionLink.select().first()
        assert (link.kind, link.kind_rule, link.origin) == (
            'nav', 'r1_semantic_ancestor', 'html')

    def test_link_expression_refuses_a_self_loop(self, fresh_db):
        model = fresh_db['model']
        core = fresh_db['core']
        expression = self._expression(fresh_db)

        created = core.link_expression(expression.land, expression, BASE)

        assert created is False
        assert model.ExpressionLink.select().count() == 0

    def test_consolidate_persists_kind(self, fresh_db):
        model = fresh_db['model']
        core = fresh_db['core']
        expression = self._expression(fresh_db)
        expression.readable = (
            'Un paragraphe de prose citant '
            '[une source](https://cible-body.test/source) au fil du texte.')
        expression.html = self.HTML
        expression.approved_at = model.datetime.datetime.now()
        expression.save()

        run(core.consolidate_land(expression.land))

        link = (model.ExpressionLink
                .select()
                .where(model.ExpressionLink.source == expression.id)
                .first())
        assert link is not None
        assert link.kind in body_links.KINDS


class TestAdjacentFixes:
    """Two write paths that could destroy a body edge without noticing."""

    def test_readable_pipeline_refuses_a_self_loop(self, fresh_db):
        from mwi.readable_pipeline import MercuryReadablePipeline
        model = fresh_db['model']
        expression = TestPropagation._expression(fresh_db)

        MercuryReadablePipeline()._update_expression_links(
            expression, [{'url': BASE, 'raw_url': BASE}])

        assert model.ExpressionLink.select().count() == 0

    def test_merge_keeps_the_better_kind(self, fresh_db):
        """A URL canonicalisation must not turn a citation into navigation."""
        from mwi import normalize_pipeline
        model = fresh_db['model']
        core = fresh_db['core']
        controller = fresh_db['controller']
        controller.LandController.create(
            core.Namespace(name='L', desc='d', lang=['fr']))
        land = model.Land.get(model.Land.name == 'L')
        domain, _ = model.Domain.get_or_create(name='site.test')
        source_a = model.Expression.create(land=land, domain=domain,
                                           url='https://site.test/a', depth=0)
        source_b = model.Expression.create(land=land, domain=domain,
                                           url='https://site.test/b', depth=0)
        target = model.Expression.create(land=land, domain=domain,
                                         url='https://site.test/t', depth=1)
        survivor = model.ExpressionLink.create(
            source=source_a, target=target, kind='nav',
            kind_rule='r1_semantic_ancestor', origin='html')
        doomed = model.ExpressionLink.create(
            source=source_b, target=target, kind='body',
            kind_rule='r0_default', origin='md', context='une citation')

        normalize_pipeline._absorb_link(survivor, doomed)

        refreshed = (model.ExpressionLink
                     .get((model.ExpressionLink.source == source_a)
                          & (model.ExpressionLink.target == target)))
        assert refreshed.kind == 'body'
        assert refreshed.kind_rule == 'r0_default'
        assert refreshed.context == 'une citation'

    def test_merge_does_not_downgrade_a_body_edge(self, fresh_db):
        from mwi import normalize_pipeline
        model = fresh_db['model']
        core = fresh_db['core']
        controller = fresh_db['controller']
        controller.LandController.create(
            core.Namespace(name='L', desc='d', lang=['fr']))
        land = model.Land.get(model.Land.name == 'L')
        domain, _ = model.Domain.get_or_create(name='site.test')
        source_a = model.Expression.create(land=land, domain=domain,
                                           url='https://site.test/a', depth=0)
        source_b = model.Expression.create(land=land, domain=domain,
                                           url='https://site.test/b', depth=0)
        target = model.Expression.create(land=land, domain=domain,
                                         url='https://site.test/t', depth=1)
        survivor = model.ExpressionLink.create(source=source_a, target=target,
                                               kind='body')
        doomed = model.ExpressionLink.create(source=source_b, target=target,
                                             kind='nav')

        normalize_pipeline._absorb_link(survivor, doomed)

        refreshed = (model.ExpressionLink
                     .get((model.ExpressionLink.source == source_a)
                          & (model.ExpressionLink.target == target)))
        assert refreshed.kind == 'body'
