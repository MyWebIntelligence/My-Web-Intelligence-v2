"""Tests for the fetch_method audit column (sprint-403 Sprint 4).

Locks the contract introduced by migration 009:
- Expression.fetch_method exists in the schema and is nullable.
- crawl_expression* persists FetchResult.method_used into the column.
- Defensive ALTER on legacy databases adds the column idempotently.
"""

import asyncio
from unittest.mock import patch

import peewee
import pytest


def run(coro):
    """Tiny helper since the project does not use pytest-asyncio."""
    return asyncio.new_event_loop().run_until_complete(coro)


class TestSchema:
    """Schema-level guarantees for fetch_method."""

    def test_expression_has_fetch_method_column(self, fresh_db):
        m = fresh_db["model"]
        cols = [row[1] for row in
                m.DB.execute_sql("PRAGMA table_info('expression')").fetchall()]
        assert 'fetch_method' in cols

    def test_fetch_method_is_nullable_by_default(self, fresh_db):
        m = fresh_db["model"]
        domain = m.Domain.create(name="fm-null.com")
        land = m.Land.create(name="fm_null", description="t", lang="fr")
        expr = m.Expression.create(land=land, domain=domain,
                                   url="https://fm-null.com/1")
        assert expr.fetch_method is None

    def test_fetch_method_roundtrip(self, fresh_db):
        m = fresh_db["model"]
        domain = m.Domain.create(name="fm-rt.com")
        land = m.Land.create(name="fm_rt", description="t", lang="fr")
        expr = m.Expression.create(land=land, domain=domain,
                                   url="https://fm-rt.com/1",
                                   fetch_method="curl_cffi")
        assert m.Expression.get_by_id(expr.id).fetch_method == "curl_cffi"


class TestMigration009:
    """Migration 009 adds the column on legacy databases."""

    def test_migration_009_adds_column_idempotent(self, tmp_path):
        db = peewee.SqliteDatabase(str(tmp_path / "legacy.db"))
        db.execute_sql("""CREATE TABLE expression (
            id INTEGER PRIMARY KEY, url TEXT NOT NULL
        )""")
        db.execute_sql("INSERT INTO expression (url) VALUES ('https://x.test')")

        cols = [r[1] for r in
                db.execute_sql("PRAGMA table_info('expression')").fetchall()]
        assert 'fetch_method' not in cols

        # Apply migration (mirrors what 009 upgrade() does)
        db.execute_sql(
            "ALTER TABLE expression ADD COLUMN fetch_method TEXT DEFAULT NULL")

        cols = [r[1] for r in
                db.execute_sql("PRAGMA table_info('expression')").fetchall()]
        assert 'fetch_method' in cols

        row = db.execute_sql(
            "SELECT fetch_method FROM expression WHERE url='https://x.test'"
        ).fetchone()
        assert row[0] is None

        # Idempotent: second ALTER must raise duplicate-column error,
        # which the migration helper swallows. We just verify SQLite
        # raises so the helper's catch path is meaningful.
        with pytest.raises(Exception) as exc:
            db.execute_sql(
                "ALTER TABLE expression ADD COLUMN fetch_method TEXT DEFAULT NULL")
        assert 'duplicate column' in str(exc.value).lower()
        db.close()


class TestCrawlPersistsFetchMethod:
    """crawl_expression* writes FetchResult.method_used to the DB."""

    def _build_expression(self, m, suffix):
        land = m.Land.create(name=f"fm_crawl_{suffix}", description="t", lang="fr")
        domain = m.Domain.create(name=f"fm-crawl-{suffix}.com")
        return m.Expression.create(
            land=land, domain=domain,
            url=f"https://fm-crawl-{suffix}.com/page",
            depth=0,
        )

    def test_crawl_records_aiohttp_method(self, fresh_db):
        m = fresh_db["model"]
        core = fresh_db["core"]
        from mwi.fetcher import FetchResult
        expr = self._build_expression(m, "aiohttp")

        async def fake_fetch(url, session=None, **kw):
            return FetchResult(url=url, status_code='200', html='<html/>',
                               method_used='aiohttp')

        with patch.object(core, 'fetch_html', side_effect=fake_fetch):
            run(core.crawl_expression(expr, [], session=None))

        assert m.Expression.get_by_id(expr.id).fetch_method == 'aiohttp'

    def test_crawl_records_curl_cffi_method(self, fresh_db):
        m = fresh_db["model"]
        core = fresh_db["core"]
        from mwi.fetcher import FetchResult
        expr = self._build_expression(m, "curlcffi")

        async def fake_fetch(url, session=None, **kw):
            # status_code preserved from initial 403, but curl_cffi rescued HTML
            return FetchResult(url=url, status_code='403', html='<html/>',
                               method_used='curl_cffi')

        with patch.object(core, 'fetch_html', side_effect=fake_fetch):
            run(core.crawl_expression(expr, [], session=None))

        fetched = m.Expression.get_by_id(expr.id)
        assert fetched.fetch_method == 'curl_cffi'
        # status_code preserved (regression guard for sprint-403 design rule)
        assert fetched.http_status == '403'

    def test_crawl_records_archive_org_method(self, fresh_db):
        m = fresh_db["model"]
        core = fresh_db["core"]
        from mwi.fetcher import FetchResult
        expr = self._build_expression(m, "archive")

        async def fake_fetch(url, session=None, **kw):
            return FetchResult(url=url, status_code='404', html='<html/>',
                               method_used='archive_org')

        with patch.object(core, 'fetch_html', side_effect=fake_fetch):
            run(core.crawl_expression(expr, [], session=None))

        assert m.Expression.get_by_id(expr.id).fetch_method == 'archive_org'

    def test_crawl_records_method_even_when_extraction_fails(self, fresh_db):
        """fetch_method is persisted even when html is None (no rescue)."""
        m = fresh_db["model"]
        core = fresh_db["core"]
        from mwi.fetcher import FetchResult
        expr = self._build_expression(m, "fail")

        async def fake_fetch(url, session=None, **kw):
            return FetchResult(url=url, status_code='000', html=None,
                               method_used='aiohttp', error='boom')

        with patch.object(core, 'fetch_html', side_effect=fake_fetch):
            run(core.crawl_expression(expr, [], session=None))

        assert m.Expression.get_by_id(expr.id).fetch_method == 'aiohttp'
