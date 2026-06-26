"""Integration tests for consolidate link rehydration (sprint EXTRACTLINKS-2026-06).

Proves, end-to-end through ``core.consolidate_land`` on a real test DB:

- Family B: a *relative* markdown link in ``readable`` now creates an
  ``ExpressionLink`` (reproduces audit bug id=7173 in local — test-first).
- Family A non-regression: readable carrying A1/A2/A3 patterns yields clean,
  non-truncated targets — no ``)(`` / ``](`` / ``)[`` / ``javascript:``
  signature on any edge, and the balanced ``_(story)`` URL is kept whole.

The optional real-corpus check (``TestRealCorpusSample``) is skipped unless
``MWI_AUDIT_DB`` points at a consolidated land DB — run it manually on the
airegulation clone after DATA-1.
"""

import asyncio
import os

import pytest


def run(coro):
    """Tiny helper since the project does not use pytest-asyncio here."""
    return asyncio.new_event_loop().run_until_complete(coro)


CORRUPTION_SIGNATURES = (')(', '](', ')[', 'javascript:')


def _make_expr(m, land, domain, url, readable):
    import datetime
    return m.Expression.create(
        land=land, domain=domain, url=url, depth=0,
        readable=readable, readable_at=datetime.datetime.now())


def _targets_of(m, source_id):
    rows = m.ExpressionLink.select().where(
        m.ExpressionLink.source == source_id)
    return [m.Expression.get_by_id(r.target_id).url for r in rows]


class TestConsolidateRelativeLinks:
    """Family B: relative markdown links create edges after consolidate."""

    def test_relative_link_creates_edge(self, fresh_db):
        m = fresh_db["model"]
        core = fresh_db["core"]

        land = m.Land.create(name="el_rel", description="t", lang="en")
        domain = m.Domain.create(name="ai-act-service-desk.ec.europa.eu")
        readable = ("Voir l'analyse de [Article 57](/en/ai-act/article-57) "
                    "dans le texte ci-dessous.\n\nAutre paragraphe.")
        src = _make_expr(
            m, land, domain,
            "https://ai-act-service-desk.ec.europa.eu/en/ai-act-explorer",
            readable)

        processed, errors = run(core.consolidate_land(land))

        assert errors == 0 and processed >= 1
        targets = _targets_of(m, src.id)
        assert any(t.endswith("/en/ai-act/article-57") for t in targets), targets

    def test_relative_dotdot_link_resolved(self, fresh_db):
        m = fresh_db["model"]
        core = fresh_db["core"]

        land = m.Land.create(name="el_dotdot", description="t", lang="en")
        domain = m.Domain.create(name="artificialintelligenceact.eu")
        readable = "Référence croisée [Article 5](../article/5) ici.\n\nFin."
        src = _make_expr(
            m, land, domain,
            "https://artificialintelligenceact.eu/article/1", readable)

        run(core.consolidate_land(land))

        targets = _targets_of(m, src.id)
        assert any(t.endswith("/article/5") for t in targets), targets


class TestConsolidateNoCorruption:
    """Family A non-regression: clean, non-truncated targets after consolidate."""

    def test_no_corruption_signature_on_edges(self, fresh_db):
        m = fresh_db["model"]
        core = fresh_db["core"]

        land = m.Land.create(name="el_corrupt", description="t", lang="en")
        domain = m.Domain.create(name="src-corrupt.test")
        readable = (
            "ArXiv [paper](http://arxiv.org/abs/2011.02395)(2020) shows...\n\n"
            "See [Runaround](https://en.wikipedia.org/wiki/Runaround_(story)) "
            "and the permalink <https://perma.cc/54M5-V8YB>.\n\n"
            "Logo ![logo](https://site.org/img/logo.png) end."
        )
        src = _make_expr(
            m, land, domain, "https://src-corrupt.test/page", readable)

        processed, errors = run(core.consolidate_land(land))
        assert errors == 0 and processed >= 1

        targets = _targets_of(m, src.id)
        # No corruption signature on any edge.
        for t in targets:
            for sig in CORRUPTION_SIGNATURES:
                assert sig not in t, f"corruption {sig!r} in {t!r}"
        # A1: the arxiv "(2020)" overflow is gone — clean abs URL present.
        assert any(t == "http://arxiv.org/abs/2011.02395" for t in targets), targets
        # A2: the wikipedia URL is NOT truncated (balanced parens kept).
        assert any(t.endswith("/wiki/Runaround_(story)") for t in targets), targets
        # A3: the autolink permalink became an edge.
        assert any("perma.cc/54M5-V8YB" in t for t in targets), targets
        # A4: the image is not a link target.
        assert not any("logo.png" in t for t in targets), targets


@pytest.mark.integration
class TestRealCorpusSample:
    """Opt-in: scan a consolidated land DB for residual corruption.

    Skipped unless ``MWI_AUDIT_DB`` points at a SQLite file (run manually on
    the airegulation clone after ``land consolidate``).
    """

    def test_no_corrupted_node_with_inbound_edge(self):
        db_path = os.getenv("MWI_AUDIT_DB")
        if not db_path or not os.path.isfile(db_path):
            pytest.skip("set MWI_AUDIT_DB to a consolidated land DB to run")

        import sqlite3
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.execute(
                "SELECT COUNT(*) FROM expression e "
                "WHERE (e.url LIKE '%)(%' OR e.url LIKE '%](%' "
                "       OR e.url LIKE '%)[%' OR e.url LIKE '%javascript:%') "
                "  AND e.id IN (SELECT DISTINCT target_id FROM expressionlink)")
            corrupted_with_inbound = cur.fetchone()[0]
        finally:
            conn.close()

        assert corrupted_with_inbound == 0, (
            f"{corrupted_with_inbound} corrupted nodes still have inbound edges")
