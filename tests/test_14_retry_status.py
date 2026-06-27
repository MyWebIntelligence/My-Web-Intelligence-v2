"""Tests for the --retry-status CLI flag (sprint-403 Sprint 5).

Locks the contract that crawl_land selects expressions by http_status when
retry_status is provided, ignoring fetched_at. This is the backfill mode
used to retry the cascade (e.g. all 403s) on previously crawled URLs.
"""

import asyncio
from datetime import datetime
from unittest.mock import patch


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _seed_land(m, name, status_map):
    """Create a land with expressions whose http_status follows status_map.

    status_map: list of (url_suffix, http_status, depth) tuples.
    All expressions have fetched_at set (to prove we ignore it).
    """
    domain = m.Domain.create(name=f"{name}.com")
    land = m.Land.create(name=name, description="t", lang="fr")
    exprs = []
    for suffix, status, depth in status_map:
        e = m.Expression.create(
            land=land, domain=domain,
            url=f"https://{name}.com/{suffix}",
            http_status=status,
            depth=depth,
            fetched_at=datetime.now(),
        )
        exprs.append(e)
    return land, exprs


class TestRetryStatusSelection:
    """crawl_land selects the right rows when retry_status is set."""

    def test_single_code_selects_only_matching_status(self, fresh_db):
        m = fresh_db["model"]
        core = fresh_db["core"]
        land, _ = _seed_land(m, "rs_single", [
            ("a", "200", 0),
            ("b", "403", 0),
            ("c", "403", 0),
            ("d", "404", 0),
        ])

        seen = []

        async def fake_with_media(expr, dictionary, session, store_html=False, issue_mode=None):
            seen.append(expr.url)
            return 1

        with patch.object(core, 'crawl_expression_with_media_analysis',
                          side_effect=fake_with_media):
            run(core.crawl_land(land, retry_status=['403']))

        assert sorted(seen) == [
            "https://rs_single.com/b",
            "https://rs_single.com/c",
        ]

    def test_multiple_codes_union(self, fresh_db):
        m = fresh_db["model"]
        core = fresh_db["core"]
        land, _ = _seed_land(m, "rs_multi", [
            ("a", "200", 0),
            ("b", "403", 0),
            ("c", "429", 0),
            ("d", "404", 0),
            ("e", "503", 0),
        ])

        seen = []

        async def fake_with_media(expr, dictionary, session, store_html=False, issue_mode=None):
            seen.append(expr.url)
            return 1

        with patch.object(core, 'crawl_expression_with_media_analysis',
                          side_effect=fake_with_media):
            run(core.crawl_land(land, retry_status=['403', '429', '503']))

        assert sorted(seen) == [
            "https://rs_multi.com/b",
            "https://rs_multi.com/c",
            "https://rs_multi.com/e",
        ]

    def test_retry_status_ignores_fetched_at(self, fresh_db):
        """All seeded expressions have fetched_at set; retry_status must still pick them."""
        m = fresh_db["model"]
        core = fresh_db["core"]
        land, _ = _seed_land(m, "rs_fetched", [
            ("a", "403", 0),
            ("b", "403", 0),
        ])
        # Sanity: fetched_at IS set
        assert m.Expression.select().where(
            m.Expression.land == land,
            m.Expression.fetched_at.is_null(False),
        ).count() == 2

        seen = []

        async def fake_with_media(expr, dictionary, session, store_html=False, issue_mode=None):
            seen.append(expr.url)
            return 1

        with patch.object(core, 'crawl_expression_with_media_analysis',
                          side_effect=fake_with_media):
            run(core.crawl_land(land, retry_status=['403']))

        assert len(seen) == 2

    def test_retry_status_respects_limit(self, fresh_db):
        m = fresh_db["model"]
        core = fresh_db["core"]
        land, _ = _seed_land(m, "rs_limit", [
            ("a", "403", 0),
            ("b", "403", 0),
            ("c", "403", 0),
            ("d", "403", 0),
        ])

        seen = []

        async def fake_with_media(expr, dictionary, session, store_html=False, issue_mode=None):
            seen.append(expr.url)
            return 1

        with patch.object(core, 'crawl_expression_with_media_analysis',
                          side_effect=fake_with_media):
            run(core.crawl_land(land, limit=2, retry_status=['403']))

        assert len(seen) == 2

    def test_retry_status_takes_precedence_over_http(self, fresh_db):
        """When both http and retry_status are provided, retry_status wins."""
        m = fresh_db["model"]
        core = fresh_db["core"]
        land, _ = _seed_land(m, "rs_prec", [
            ("a", "200", 0),
            ("b", "403", 0),
            ("c", "429", 0),
        ])

        seen = []

        async def fake_with_media(expr, dictionary, session, store_html=False, issue_mode=None):
            seen.append(expr.url)
            return 1

        with patch.object(core, 'crawl_expression_with_media_analysis',
                          side_effect=fake_with_media):
            run(core.crawl_land(land, http='200', retry_status=['403', '429']))

        # http=200 ignored; retry_status drives selection
        assert sorted(seen) == [
            "https://rs_prec.com/b",
            "https://rs_prec.com/c",
        ]

    def test_no_retry_status_falls_back_to_fetched_at_null(self, fresh_db):
        """Default behaviour preserved: expressions never fetched."""
        m = fresh_db["model"]
        core = fresh_db["core"]
        domain = m.Domain.create(name="rs_default.com")
        land = m.Land.create(name="rs_default", description="t", lang="fr")
        # one fetched, one pending
        m.Expression.create(land=land, domain=domain,
                            url="https://rs_default.com/done",
                            http_status="200", depth=0,
                            fetched_at=datetime.now())
        m.Expression.create(land=land, domain=domain,
                            url="https://rs_default.com/pending",
                            depth=0)

        seen = []

        async def fake_with_media(expr, dictionary, session, store_html=False, issue_mode=None):
            seen.append(expr.url)
            return 1

        with patch.object(core, 'crawl_expression_with_media_analysis',
                          side_effect=fake_with_media):
            run(core.crawl_land(land))

        assert seen == ["https://rs_default.com/pending"]


class TestControllerParsing:
    """The CSV-to-list transformation used by LandController.crawl."""

    @staticmethod
    def _parse(raw):
        """Mirror of the parsing block in LandController.crawl."""
        if not raw:
            return None
        out = [s.strip() for s in raw.split(',') if s.strip()]
        return out or None

    def test_csv_with_spaces(self):
        assert self._parse("403, 429 ,406") == ['403', '429', '406']

    def test_single_code(self):
        assert self._parse("403") == ['403']

    def test_empty_string_is_none(self):
        assert self._parse("") is None

    def test_only_separators_is_none(self):
        assert self._parse(" , , ") is None

    def test_none_input_is_none(self):
        assert self._parse(None) is None
