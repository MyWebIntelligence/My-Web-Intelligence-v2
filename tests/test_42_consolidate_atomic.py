"""A03/A04/A03bis - consolidate and the Mercury path must prepare, then mutate.

`consolidate_land` opened its per-expression work with two DELETEs (links,
then medias) and no transaction, and persisted `relevance`/`validllm` before
extraction. Anything failing afterwards -- a `database is locked` from a
second writer, a Google Drive eviction, a Ctrl-C -- left the expression with
no links, no medias and a half-written state, while its `readable` was still
perfectly fine. Reproduced with a real second-connection `BEGIN IMMEDIATE`
lock: (0 processed, 2 errors) and the in-flight expression stripped bare.

The contract these tests pin: **either the whole expression is rebuilt, or
nothing about it changes**. They never look at how the transaction is opened.

A04 adds media reconciliation on top: a successful consolidate used to purge
and recreate bare `Media` rows, silently dropping the twelve enrichment
columns and changing the row id (which breaks external joins on
`mediacsv.id`).
"""

import asyncio
from datetime import datetime
from unittest.mock import patch

import pytest
from peewee import IntegrityError, OperationalError


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


READABLE_A = (
    "Un paragraphe qui cite [la cible](https://example.com/b) dans le corps "
    "du texte, assez long pour ressembler a de la prose.\n\n"
    "Et une illustration ![photo](https://example.com/i.jpg) ici.\n"
)


def _arrange(fresh_db, name, readable=READABLE_A):
    """One land, expression A (readable + link + enriched media) and target B."""
    m = fresh_db["model"]
    domain = m.Domain.create(name=f"{name}.example.com")
    land = m.Land.create(name=name, description="t", lang="fr")
    a = m.Expression.create(
        land=land, domain=domain, url="https://example.com/a", depth=0,
        relevance=7, validllm='oui', validmodel='m1',
        readable=readable, readable_at=datetime.now())
    b = m.Expression.create(
        land=land, domain=domain, url="https://example.com/b", depth=1)
    m.ExpressionLink.create(source=a, target=b, context='ancien contexte')
    m.Media.create(
        expression=a, url="https://example.com/i.jpg", type='img',
        width=1280, height=720, image_hash='abc123',
        exif_data='{"Make": "Canon"}', analyzed_at=datetime.now())
    return land, a, b


def _counts(m, expr):
    links = (m.ExpressionLink.select()
             .where(m.ExpressionLink.source == expr.id).count())
    medias = m.Media.select().where(m.Media.expression == expr.id).count()
    return links, medias


class TestConsolidateAtomicity:
    """A failure anywhere leaves the expression exactly as it was."""

    @pytest.mark.parametrize('where', ['extraction', 'link_create', 'medias'])
    def test_failure_keeps_links_media_and_metadata(self, fresh_db, where):
        m, core = fresh_db["model"], fresh_db["core"]
        land, a, _b = _arrange(fresh_db, "atomic_fail")

        failures = {
            'extraction': lambda: patch.object(
                core.body_links, 'extract_body_links',
                side_effect=RuntimeError("extraction blew up")),
            'link_create': lambda: patch.object(
                m.ExpressionLink, 'create',
                side_effect=OperationalError("database is locked")),
            'medias': lambda: patch.object(
                core, 'extract_medias',
                side_effect=RuntimeError("media pass blew up")),
        }

        with failures[where]():
            processed, errors = run(core.consolidate_land(land))

        assert (processed, errors) == (0, 1)
        assert _counts(m, a) == (1, 1)
        link = m.ExpressionLink.get(m.ExpressionLink.source == a.id)
        assert link.context == 'ancien contexte'
        media = m.Media.get(m.Media.expression == a.id)
        assert media.width == 1280
        assert media.image_hash == 'abc123'
        fresh_a = m.Expression.get_by_id(a.id)
        assert fresh_a.relevance == 7
        assert fresh_a.validllm == 'oui'

    def test_failure_on_one_expression_does_not_block_next(self, fresh_db):
        m, core = fresh_db["model"], fresh_db["core"]
        land, a, b = _arrange(fresh_db, "atomic_next")
        # B becomes consolidatable too, and cites A back.
        b.readable = "B cite [la source](https://example.com/a) ici."
        b.readable_at = datetime.now()
        b.save()

        real_extract = core.body_links.extract_body_links

        def fail_on_a(md, html, base_url, *args, **kwargs):
            if str(base_url).endswith('/a'):
                raise RuntimeError("only A fails")
            return real_extract(md, html, base_url, *args, **kwargs)

        with patch.object(core.body_links, 'extract_body_links', fail_on_a):
            processed, errors = run(core.consolidate_land(land))

        assert (processed, errors) == (1, 1)
        assert _counts(m, a) == (1, 1)
        assert m.ExpressionLink.select().where(
            m.ExpressionLink.source == b.id,
            m.ExpressionLink.target == a.id).count() == 1

    def test_network_and_extraction_run_before_any_mutation(self, fresh_db,
                                                            monkeypatch):
        """The LLM gate and the extraction see the pre-DELETE state, unwrapped.

        Recording `(in_transaction, link_count)` is the whole point: today the
        DELETE runs first, so the extraction sees 0 links; and holding a
        transaction open across a network call is what turns one slow gate
        into a land-wide lock.
        """
        m, core = fresh_db["model"], fresh_db["core"]
        land, a, _b = _arrange(fresh_db, "atomic_order")
        monkeypatch.setattr(core.settings, 'openrouter_readable_min_chars', 0,
                            raising=False)
        seen = []

        def probe():
            count = (m.ExpressionLink.select()
                     .where(m.ExpressionLink.source == a.id).count())
            seen.append((m.DB.in_transaction(), count))

        def fake_gate(land_arg, expr, *args, **kwargs):
            probe()
            return True

        real_extract = core.body_links.extract_body_links

        def probing_extract(md, html, base_url, *args, **kwargs):
            probe()
            return real_extract(md, html, base_url, *args, **kwargs)

        with patch('mwi.llm_openrouter.is_relevant_via_openrouter', fake_gate):
            with patch.object(core.body_links, 'extract_body_links',
                              probing_extract):
                processed, errors = run(
                    core.consolidate_land(land, llm_revalidate=True))

        assert (processed, errors) == (1, 0)
        assert seen == [(False, 1), (False, 1)]
        assert m.Expression.get_by_id(a.id).validllm == 'oui'

    def test_duplicate_target_in_readable_keeps_single_edge_without_error(
            self, fresh_db, monkeypatch):
        """Contract: two URL variants of one target make one edge, no error.

        The IntegrityError raised by the second create is caught inside the
        transaction; peewee/SQLite do not poison the enclosing atomic block,
        so the rest of the expression still commits.
        """
        m, core = fresh_db["model"], fresh_db["core"]
        from mwi import url_normalizer
        rules = dict(getattr(url_normalizer.settings, 'url_normalization', {}))
        rules.update({'force_https': False, 'trailing_slash': 'preserve',
                      'strip_www': False})
        monkeypatch.setattr(url_normalizer.settings, 'url_normalization',
                            rules, raising=False)

        readable = (
            "Une premiere mention de [la cible](https://example.com/b) puis "
            "une seconde sous une autre forme [idem](http://example.com/b).\n")
        land, a, b = _arrange(fresh_db, "atomic_dup", readable=readable)

        processed, errors = run(core.consolidate_land(land))

        assert (processed, errors) == (1, 0)
        assert m.ExpressionLink.select().where(
            m.ExpressionLink.source == a.id,
            m.ExpressionLink.target == b.id).count() == 1

    def test_integrity_error_inside_atomic_does_not_poison_it(self, fresh_db):
        """Probe: peewee 4.1 lets an atomic() survive a caught IntegrityError.

        The A03 design depends on it (duplicate edges are swallowed inside the
        transaction). If a peewee upgrade ever changes this, this test fails
        first and explains why.
        """
        m = fresh_db["model"]
        land, a, b = _arrange(fresh_db, "atomic_probe")

        with m.DB.atomic():
            try:
                m.ExpressionLink.create(source=a, target=b)
            except IntegrityError:
                pass
            a.relevance = 42
            a.save()

        assert m.Expression.get_by_id(a.id).relevance == 42


def _arrange_media(fresh_db, name, readable, medias=()):
    """One expression carrying `readable`, plus the given pre-existing medias.

    A second expression always owns a media row too: without it, SQLite would
    happily hand the freed rowid back to a recreated row and an id change
    would be invisible.
    """
    m = fresh_db["model"]
    domain = m.Domain.create(name=f"{name}.example.com")
    land = m.Land.create(name=name, description="t", lang="fr")
    a = m.Expression.create(
        land=land, domain=domain, url="https://example.com/a", depth=0,
        readable=readable, readable_at=datetime.now())
    other = m.Expression.create(
        land=land, domain=domain, url="https://example.com/other", depth=0)
    m.Media.create(expression=other, url="https://example.com/keepme.jpg",
                   type='img')
    for spec in medias:
        m.Media.create(expression=a, **spec)
    return land, a


def _media_urls(m, expr):
    return sorted(str(x.url) for x in
                  m.Media.select().where(m.Media.expression == expr.id))


class TestConsolidateMediaReconcile:
    """A04 - consolidate reconciles medias by URL instead of purge-and-recreate."""

    def test_consolidate_keeps_enriched_media_row(self, fresh_db):
        m, core = fresh_db["model"], fresh_db["core"]
        land, a = _arrange_media(
            fresh_db, "md_keep",
            "Voir ![photo](https://example.com/i.jpg) ici.",
            medias=[dict(url="https://example.com/i.jpg", type='img',
                         width=1280, height=720, image_hash='abc123',
                         exif_data='{"Make": "Canon"}',
                         analyzed_at=datetime.now())])
        before = m.Media.get(m.Media.expression == a.id)

        processed, errors = run(core.consolidate_land(land))

        assert (processed, errors) == (1, 0)
        after = m.Media.get(m.Media.expression == a.id)
        assert after.id == before.id
        assert after.width == 1280
        assert after.image_hash == 'abc123'
        assert after.exif_data == '{"Make": "Canon"}'
        assert after.analyzed_at is not None

    def test_consolidate_removes_vanished_and_adds_new(self, fresh_db):
        m, core = fresh_db["model"], fresh_db["core"]
        land, a = _arrange_media(
            fresh_db, "md_swap",
            "Nouvelle ![photo](https://example.com/new.jpg) seulement.",
            medias=[dict(url="https://example.com/gone.jpg", type='img',
                         width=800)])

        run(core.consolidate_land(land))

        assert _media_urls(m, a) == ["https://example.com/new.jpg"]

    def test_consolidate_readable_null_removes_all_media(self, fresh_db):
        m, core = fresh_db["model"], fresh_db["core"]
        land, a = _arrange_media(
            fresh_db, "md_null", "placeholder",
            medias=[dict(url="https://example.com/x.jpg", type='img')])
        a.readable = None
        a.save()

        run(core.consolidate_land(land))

        assert _media_urls(m, a) == []

    @pytest.mark.parametrize('readable,expected', [
        pytest.param("![p](<https://example.com/photo.jpg>)",
                     "https://example.com/photo.jpg", id="chevrons"),
        pytest.param('![p](https://example.com/photo.jpg "Titre")',
                     "https://example.com/photo.jpg", id="titre"),
        pytest.param("![p](https://example.com/paris_(1).jpg)",
                     "https://example.com/paris_(1).jpg", id="parentheses"),
        pytest.param(
            "[![p](https://example.com/photo.jpg)](https://example.com/f.jpg)",
            "https://example.com/photo.jpg", id="image_liee"),
    ])
    def test_consolidate_markdown_image_syntaxes(self, fresh_db, readable,
                                                 expected):
        m, core = fresh_db["model"], fresh_db["core"]
        land, a = _arrange_media(fresh_db, "md_syntax", readable)

        run(core.consolidate_land(land))

        assert _media_urls(m, a) == [expected]

    def test_consolidate_legacy_html_img_and_marker_still_extracted(
            self, fresh_db):
        m, core = fresh_db["model"], fresh_db["core"]
        land, a = _arrange_media(
            fresh_db, "md_legacy",
            '<img src="/a.png"> et [IMAGE: https://example.com/b.png]')

        run(core.consolidate_land(land))

        assert _media_urls(m, a) == ["https://example.com/a.png",
                                     "https://example.com/b.png"]

    def test_query_string_ampersand_preserved(self, fresh_db):
        """The '&' must stay raw: str(soup) used to turn it into '&amp;'."""
        m, core = fresh_db["model"], fresh_db["core"]
        land, a = _arrange_media(
            fresh_db, "md_amp",
            "![p](https://example.com/i.jpg?a=1&b=2)")

        run(core.consolidate_land(land))

        assert _media_urls(m, a) == ["https://example.com/i.jpg?a=1&b=2"]

    def test_case_insensitive_reconciliation(self, fresh_db):
        """Mercury stores urljoin (case kept), core stores resolve_url (lower)."""
        m, core = fresh_db["model"], fresh_db["core"]
        land, a = _arrange_media(
            fresh_db, "md_case",
            "![p](https://example.com/wp-content/IMG.jpg)",
            medias=[dict(url="https://example.com/wp-content/IMG.jpg",
                         type='img', width=640)])
        before = m.Media.get(m.Media.expression == a.id)

        run(core.consolidate_land(land))

        rows = list(m.Media.select().where(m.Media.expression == a.id))
        assert len(rows) == 1
        assert rows[0].id == before.id
        assert rows[0].width == 640

    def test_extension_less_existing_media_kept(self, fresh_db):
        """A referenced media with no image extension is not recreated, nor dropped."""
        m, core = fresh_db["model"], fresh_db["core"]
        land, a = _arrange_media(
            fresh_db, "md_noext",
            "![p](https://example.com/img.php)",
            medias=[dict(url="https://example.com/img.php", type='img',
                         width=640)])

        run(core.consolidate_land(land))

        rows = list(m.Media.select().where(m.Media.expression == a.id))
        assert len(rows) == 1
        assert rows[0].width == 640


class TestReadablePipelineMediaReconcile:
    """A04 - the Mercury path reconciles too, instead of purging every run."""

    @pytest.mark.parametrize('md,expected', [
        pytest.param("![a](<https://x.org/i.jpg>)", ["https://x.org/i.jpg"],
                     id="chevrons"),
        pytest.param('![a](https://x.org/i.jpg "T")', ["https://x.org/i.jpg"],
                     id="titre"),
        pytest.param("![a](https://x.org/p_(1).jpg)",
                     ["https://x.org/p_(1).jpg"], id="parentheses"),
        pytest.param("![a](/rel/i.png)", ["https://base.test/rel/i.png"],
                     id="relative_resolved"),
    ])
    def test_extract_media_from_markdown_variants(self, test_env, md, expected):
        from mwi.readable_pipeline import MercuryReadablePipeline

        got = MercuryReadablePipeline()._extract_media_from_markdown(
            md, "https://base.test/page")

        assert [item['url'] for item in got] == expected

    def test_apply_updates_keeps_enriched_and_drops_vanished(self, fresh_db):
        from mwi.readable_pipeline import ExpressionUpdate, MercuryReadablePipeline

        m, core = fresh_db["model"], fresh_db["core"]
        land, a = _arrange_media(
            fresh_db, "rp_reconcile", "peu importe",
            medias=[dict(url="https://example.com/i.jpg", type='img',
                         width=1280, image_hash='abc123'),
                    dict(url="https://example.com/gone.jpg", type='img')])
        before = m.Media.get(m.Media.expression == a.id,
                             m.Media.url == "https://example.com/i.jpg")

        update = ExpressionUpdate(
            expression_id=a.id,
            field_updates={},
            media_additions=[
                {'type': 'img', 'url': "https://example.com/i.jpg"},
                {'type': 'img', 'url': "https://example.com/new.jpg"},
            ],
            link_additions=[],
            update_reason="test")
        dictionary = core.get_land_dictionary(land)
        # _apply_updates became a coroutine with O01 (the LLM gate is
        # awaited off the loop); the writes still happen synchronously
        # inside it, after that await.
        run(MercuryReadablePipeline()._apply_updates(a, update, dictionary))

        assert _media_urls(m, a) == ["https://example.com/i.jpg",
                                     "https://example.com/new.jpg"]
        kept = m.Media.get(m.Media.expression == a.id,
                           m.Media.url == "https://example.com/i.jpg")
        assert kept.id == before.id
        assert kept.width == 1280
        assert kept.image_hash == 'abc123'


class TestReadableAtomicity:
    """A03bis - the Mercury write path is all-or-nothing too.

    `_apply_updates` saved the expression (including `readable_at`), then
    deleted medias, then deleted and recreated links -- three unprotected
    steps. A failure after the DELETEs left a page dated as successfully
    read, with neither links nor medias.
    """

    def _pipeline_update(self, a, media_urls, link_urls, readable):
        from mwi.readable_pipeline import ExpressionUpdate
        return ExpressionUpdate(
            expression_id=a.id,
            field_updates={'readable': (a.readable, readable)},
            media_additions=[{'type': 'img', 'url': u} for u in media_urls],
            link_additions=[{'url': u, 'raw_url': u} for u in link_urls],
            update_reason="test")

    def test_failed_link_create_rolls_back_readable_media_and_timestamp(
            self, fresh_db):
        from mwi.readable_pipeline import MercuryReadablePipeline

        m, core = fresh_db["model"], fresh_db["core"]
        land, a, b = _arrange(fresh_db, "rp_atomic")
        before_readable = str(a.readable)
        before_stamp = m.Expression.get_by_id(a.id).readable_at

        update = self._pipeline_update(
            a, ["https://example.com/i.jpg"], ["https://example.com/b"],
            "un tout nouveau readable")
        dictionary = core.get_land_dictionary(land)

        with patch.object(m.ExpressionLink, 'create',
                          side_effect=OperationalError("database is locked")):
            with pytest.raises(OperationalError):
                run(MercuryReadablePipeline()._apply_updates(
                    a, update, dictionary))

        fresh = m.Expression.get_by_id(a.id)
        assert fresh.readable == before_readable
        assert fresh.readable_at == before_stamp
        assert _counts(m, a) == (1, 1)
        assert m.Media.get(m.Media.expression == a.id).width == 1280

    def test_duplicate_target_cited_twice_makes_one_edge(self, fresh_db):
        """Contract: the same target cited twice is one edge, not an error."""
        from mwi.readable_pipeline import MercuryReadablePipeline

        m, core = fresh_db["model"], fresh_db["core"]
        land, a, b = _arrange(fresh_db, "rp_dup")
        update = self._pipeline_update(
            a, [], ["https://example.com/b", "https://example.com/b"],
            "readable avec deux fois la meme cible")
        dictionary = core.get_land_dictionary(land)

        run(MercuryReadablePipeline()._apply_updates(a, update, dictionary))

        assert m.ExpressionLink.select().where(
            m.ExpressionLink.source == a.id,
            m.ExpressionLink.target == b.id).count() == 1
