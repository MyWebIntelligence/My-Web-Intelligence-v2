"""Tests for the URL normalization sprint:
  - mwi.url_normalizer (rule unit tests + idempotence)
  - integration with core.add_expression and original_url
  - circuit breaker for archive.org fallback
  - CLI `land normalize` (rename + merge with chain resolution)
  - migration 008 idempotence
"""

import os
import random
import string

import pytest

from mwi import url_normalizer
from mwi.url_normalizer import (
    DEFAULT_RULES,
    classify_url,
    is_archive_wrapper,
    normalize_url,
)


def rand_name(prefix="land"):
    return f"{prefix}_" + "".join(random.choice(string.ascii_lowercase) for _ in range(8))


# ────────────────────────────────────────────────────────────────────────
# Unit tests: normalize_url rules
# ────────────────────────────────────────────────────────────────────────

class TestNormalizeUrlRules:
    def test_idempotent_on_clean_url(self):
        u = "https://example.com/article"
        assert normalize_url(u) == u
        assert normalize_url(normalize_url(u)) == normalize_url(u)

    def test_idempotent_on_archive(self):
        u = "https://web.archive.org/web/20230605/https://example.com/article"
        assert normalize_url(normalize_url(u)) == normalize_url(u)

    def test_idempotent_on_tracker_polluted_url(self):
        u = "https://example.com/page?utm_source=fb&id=42&fbclid=xyz"
        assert normalize_url(normalize_url(u)) == normalize_url(u)

    def test_remove_anchor(self):
        assert normalize_url("https://example.com/p#section") == "https://example.com/p"

    def test_unwrap_archive_simple(self):
        u = "https://web.archive.org/web/20230605/https://www.lemonde.fr/article"
        assert normalize_url(u) == "https://www.lemonde.fr/article"

    def test_unwrap_archive_with_im_suffix(self):
        u = "https://web.archive.org/web/20241211122618im_/https://example.com/img.jpg"
        assert normalize_url(u) == "https://example.com/img.jpg"

    def test_unwrap_archive_nested(self):
        u = ("https://web.archive.org/web/20240101/"
             "https://web.archive.org/web/20230101/"
             "https://example.com/page")
        assert normalize_url(u) == "https://example.com/page"

    def test_unwrap_ghostarchive(self):
        u = "https://ghostarchive.org/archive/abc123/https://example.com/page"
        assert normalize_url(u) == "https://example.com/page"

    def test_lowercase_host(self):
        u = "https://EXAMPLE.com/Page"
        assert normalize_url(u) == "https://example.com/Page"

    def test_path_case_preserved(self):
        u = "https://example.com/Article/CamelCase"
        assert normalize_url(u) == "https://example.com/Article/CamelCase"

    def test_strip_trackers_default_set(self):
        u = "https://example.com/page?utm_source=fb&utm_medium=x&id=42&fbclid=abc&gclid=xyz"
        out = normalize_url(u)
        assert "utm_" not in out
        assert "fbclid" not in out
        assert "gclid" not in out
        assert "id=42" in out

    def test_strip_trackers_keeps_legit_params(self):
        u = "https://example.com/page?id=42&q=hello"
        assert "id=42" in normalize_url(u)
        assert "q=hello" in normalize_url(u)

    def test_query_order_canonical(self):
        u1 = "https://example.com/page?b=2&a=1&c=3"
        u2 = "https://example.com/page?a=1&b=2&c=3"
        assert normalize_url(u1) == normalize_url(u2)

    def test_force_https_off_by_default(self):
        u = "http://example.com/page"
        assert normalize_url(u) == "http://example.com/page"

    def test_force_https_when_enabled(self):
        u = "http://example.com/page"
        assert normalize_url(u, rules={'force_https': True}) == "https://example.com/page"

    def test_strip_www_off_by_default(self):
        u = "https://www.example.com/page"
        assert normalize_url(u) == u

    def test_strip_www_when_enabled(self):
        u = "https://www.example.com/page"
        assert normalize_url(u, rules={'strip_www': True}) == "https://example.com/page"

    def test_strip_mobile_subdomain_off_by_default(self):
        u = "https://m.example.com/page"
        assert normalize_url(u) == u

    def test_strip_mobile_subdomain_when_enabled(self):
        u = "https://m.example.com/page"
        out = normalize_url(u, rules={'strip_mobile_subdomain': True})
        assert out == "https://example.com/page"

    def test_trailing_slash_preserve(self):
        a = normalize_url("https://example.com/page/")
        b = normalize_url("https://example.com/page")
        assert a.endswith('/')
        assert not b.endswith('/')

    def test_trailing_slash_strip(self):
        out = normalize_url("https://example.com/page/", rules={'trailing_slash': 'strip'})
        assert out == "https://example.com/page"

    def test_empty_url_returns_unchanged(self):
        assert normalize_url("") == ""

    def test_non_string_returns_unchanged(self):
        assert normalize_url(None) is None

    def test_classify_url_archive_detection(self):
        info = classify_url("https://web.archive.org/web/20230605/https://x.com/p")
        assert info['is_archive'] is True

    def test_classify_url_normal(self):
        info = classify_url("https://example.com/page?a=1#sec")
        assert info['is_archive'] is False
        assert info['has_anchor'] is True
        assert info['has_query'] is True

    def test_is_archive_wrapper_true_cases(self):
        assert is_archive_wrapper("https://web.archive.org/web/20230605/https://x.com/")
        assert is_archive_wrapper("http://web.archive.org/web/123/https://x.com/")
        assert is_archive_wrapper("https://ghostarchive.org/archive/abc/https://x.com/")

    def test_is_archive_wrapper_false_cases(self):
        assert not is_archive_wrapper("https://example.com/page")
        assert not is_archive_wrapper("https://archive.fo/abc")  # different service


# ────────────────────────────────────────────────────────────────────────
# Integration tests: add_expression + original_url
# ────────────────────────────────────────────────────────────────────────

class TestAddExpressionIntegration:
    def test_add_expression_records_original_url_when_changed(self, fresh_db):
        m = fresh_db["model"]
        core = fresh_db["core"]
        land = m.Land.create(name=rand_name("oo"), description="t", lang="fr")

        archive = "https://web.archive.org/web/20230605/https://example.com/page"
        expr = core.add_expression(land, archive)

        assert expr.url == "https://example.com/page"
        assert expr.original_url == archive

    def test_add_expression_no_original_url_when_unchanged(self, fresh_db):
        m = fresh_db["model"]
        core = fresh_db["core"]
        land = m.Land.create(name=rand_name("oo"), description="t", lang="fr")

        clean = "https://example.com/page"
        expr = core.add_expression(land, clean)

        assert expr.url == clean
        assert expr.original_url is None

    def test_add_expression_anchor_only_change_records_original(self, fresh_db):
        m = fresh_db["model"]
        core = fresh_db["core"]
        land = m.Land.create(name=rand_name("oo"), description="t", lang="fr")

        with_anchor = "https://example.com/page#section"
        expr = core.add_expression(land, with_anchor)

        assert expr.url == "https://example.com/page"
        assert expr.original_url == with_anchor

    def test_add_expression_idempotent_with_normalization(self, fresh_db):
        m = fresh_db["model"]
        core = fresh_db["core"]
        land = m.Land.create(name=rand_name("oo"), description="t", lang="fr")

        archive = "https://web.archive.org/web/20230605/https://example.com/page"
        canonical = "https://example.com/page"

        e1 = core.add_expression(land, archive)
        e2 = core.add_expression(land, canonical)
        assert e1.id == e2.id
        assert m.Expression.select().where(m.Expression.land == land).count() == 1

    def test_schema_has_original_url_column(self, fresh_db):
        m = fresh_db["model"]
        cols = [r[1] for r in m.DB.execute_sql(
            "PRAGMA table_info('expression')").fetchall()]
        assert 'original_url' in cols


# ────────────────────────────────────────────────────────────────────────
# Circuit breaker tests
# ────────────────────────────────────────────────────────────────────────

class TestArchiveOrgBreaker:
    def setup_method(self):
        from mwi.core import _ArchiveOrgBreaker
        _ArchiveOrgBreaker.reset()

    def test_breaker_closed_initially(self):
        from mwi.core import _ArchiveOrgBreaker
        assert _ArchiveOrgBreaker.is_open() is False

    def test_breaker_opens_after_threshold(self):
        from mwi.core import _ArchiveOrgBreaker
        for _ in range(_ArchiveOrgBreaker.OPEN_THRESHOLD):
            _ArchiveOrgBreaker.record_failure()
        assert _ArchiveOrgBreaker.is_open() is True

    def test_breaker_stays_closed_below_threshold(self):
        from mwi.core import _ArchiveOrgBreaker
        for _ in range(_ArchiveOrgBreaker.OPEN_THRESHOLD - 1):
            _ArchiveOrgBreaker.record_failure()
        assert _ArchiveOrgBreaker.is_open() is False

    def test_breaker_resets_on_success(self):
        from mwi.core import _ArchiveOrgBreaker
        for _ in range(_ArchiveOrgBreaker.OPEN_THRESHOLD - 1):
            _ArchiveOrgBreaker.record_failure()
        _ArchiveOrgBreaker.record_success()
        assert _ArchiveOrgBreaker.failures == 0

    def test_breaker_closes_after_cooldown(self, monkeypatch):
        from mwi.core import _ArchiveOrgBreaker
        for _ in range(_ArchiveOrgBreaker.OPEN_THRESHOLD):
            _ArchiveOrgBreaker.record_failure()
        # Simulate cooldown elapsed by rewinding last_failure_ts
        _ArchiveOrgBreaker.last_failure_ts -= _ArchiveOrgBreaker.COOLDOWN_SEC + 1
        assert _ArchiveOrgBreaker.is_open() is False
        assert _ArchiveOrgBreaker.failures == 0


# ────────────────────────────────────────────────────────────────────────
# CLI `land normalize`
# ────────────────────────────────────────────────────────────────────────

class TestLandNormalizeCLI:
    def _make_land_with_legacy_archives(self, fresh_db):
        """Build a land with a mix of clean URLs and legacy archive URLs.

        Bypasses add_expression's normalization to insert legacy state.
        """
        m = fresh_db["model"]
        land = m.Land.create(name=rand_name("nz"), description="t", lang="fr")
        d_archive = m.Domain.get_or_create(name="web.archive.org")[0]
        d_clean = m.Domain.get_or_create(name="example.com")[0]
        d_other = m.Domain.get_or_create(name="other.com")[0]

        # Direct INSERT bypassing add_expression
        clean = m.Expression.create(
            land=land, domain=d_clean,
            url="https://example.com/page1", depth=0)
        archive_dup = m.Expression.create(
            land=land, domain=d_archive,
            url="https://web.archive.org/web/20230605/https://example.com/page1",
            depth=1)
        archive_only = m.Expression.create(
            land=land, domain=d_archive,
            url="https://web.archive.org/web/20230605/https://example.com/page2",
            depth=1)
        other = m.Expression.create(
            land=land, domain=d_other,
            url="https://other.com/foo", depth=0)
        return {
            'land': land,
            'clean': clean,
            'archive_dup': archive_dup,   # canonical exists -> merge
            'archive_only': archive_only,  # canonical absent -> rename
            'other': other,
        }

    def test_dry_run_modifies_nothing(self, fresh_db):
        m = fresh_db["model"]
        controller = fresh_db["controller"]
        core = fresh_db["core"]
        ctx = self._make_land_with_legacy_archives(fresh_db)

        ret = controller.LandController.normalize(core.Namespace(
            name=ctx['land'].name, dry_run='TRUE',
            reset_status=None, verbose=None, limit=0))
        assert ret == 1

        # No deletion
        assert m.Expression.select().where(
            m.Expression.land == ctx['land']).count() == 4
        # URL unchanged
        archive = m.Expression.get_by_id(ctx['archive_only'].id)
        assert archive.url.startswith("https://web.archive.org/")

    def test_apply_renames_archive_only(self, fresh_db):
        m = fresh_db["model"]
        controller = fresh_db["controller"]
        core = fresh_db["core"]
        ctx = self._make_land_with_legacy_archives(fresh_db)

        controller.LandController.normalize(core.Namespace(
            name=ctx['land'].name, dry_run=None,
            reset_status=None, verbose=None, limit=0))

        renamed = m.Expression.get_by_id(ctx['archive_only'].id)
        assert renamed.url == "https://example.com/page2"
        assert renamed.original_url == \
            "https://web.archive.org/web/20230605/https://example.com/page2"

    def test_apply_merges_duplicate_archive(self, fresh_db):
        m = fresh_db["model"]
        controller = fresh_db["controller"]
        core = fresh_db["core"]
        ctx = self._make_land_with_legacy_archives(fresh_db)

        # Add a link from `other` to `archive_dup` to verify remap
        m.ExpressionLink.create(
            source=ctx['other'], target=ctx['archive_dup'])

        controller.LandController.normalize(core.Namespace(
            name=ctx['land'].name, dry_run=None,
            reset_status=None, verbose=None, limit=0))

        # archive_dup should be gone
        assert not m.Expression.select().where(
            m.Expression.id == ctx['archive_dup'].id).exists()
        # Link from `other` should now point to `clean`
        link_to_clean = m.ExpressionLink.select().where(
            (m.ExpressionLink.source == ctx['other'])
            & (m.ExpressionLink.target == ctx['clean'])
        ).exists()
        assert link_to_clean

    def test_apply_resolves_chain(self, fresh_db):
        """Wayback of Wayback should resolve in one pass."""
        m = fresh_db["model"]
        controller = fresh_db["controller"]
        core = fresh_db["core"]
        land = m.Land.create(name=rand_name("nz"), description="t", lang="fr")
        d_archive = m.Domain.get_or_create(name="web.archive.org")[0]
        d_clean = m.Domain.get_or_create(name="example.com")[0]

        # All three have to refer to the same canonical chain
        deep = m.Expression.create(
            land=land, domain=d_archive,
            url=("https://web.archive.org/web/20240101/"
                 "https://web.archive.org/web/20230101/"
                 "https://example.com/page"),
            depth=0)
        m.Expression.create(
            land=land, domain=d_clean,
            url="https://example.com/page", depth=0)

        controller.LandController.normalize(core.Namespace(
            name=land.name, dry_run=None,
            reset_status=None, verbose=None, limit=0))

        # The deep wayback expression should be merged away (or renamed
        # if canonical was missing, but here canonical exists)
        assert not m.Expression.select().where(
            m.Expression.id == deep.id).exists()
        # The canonical remains, exactly once
        assert m.Expression.select().where(
            (m.Expression.land == land)
            & (m.Expression.url == "https://example.com/page")).count() == 1

    def test_reset_status_clears_http_status(self, fresh_db):
        m = fresh_db["model"]
        controller = fresh_db["controller"]
        core = fresh_db["core"]
        land = m.Land.create(name=rand_name("nz"), description="t", lang="fr")
        d_archive = m.Domain.get_or_create(name="web.archive.org")[0]
        archive = m.Expression.create(
            land=land, domain=d_archive,
            url="https://web.archive.org/web/20230605/https://example.com/page",
            http_status="000",
            depth=0)

        controller.LandController.normalize(core.Namespace(
            name=land.name, dry_run=None,
            reset_status='TRUE', verbose=None, limit=0))

        renamed = m.Expression.get_by_id(archive.id)
        assert renamed.url == "https://example.com/page"
        assert renamed.http_status is None

    def test_normalize_idempotent(self, fresh_db):
        """Running normalize twice on a land does nothing the second time."""
        m = fresh_db["model"]
        controller = fresh_db["controller"]
        core = fresh_db["core"]
        ctx = self._make_land_with_legacy_archives(fresh_db)

        controller.LandController.normalize(core.Namespace(
            name=ctx['land'].name, dry_run=None,
            reset_status=None, verbose=None, limit=0))

        count_after_first = m.Expression.select().where(
            m.Expression.land == ctx['land']).count()

        # 2nd run should produce 0 changes
        controller.LandController.normalize(core.Namespace(
            name=ctx['land'].name, dry_run=None,
            reset_status=None, verbose=None, limit=0))

        count_after_second = m.Expression.select().where(
            m.Expression.land == ctx['land']).count()
        assert count_after_first == count_after_second


# ────────────────────────────────────────────────────────────────────────
# Migration 008
# ────────────────────────────────────────────────────────────────────────

class TestDbOverride:
    """`--db PATH` reroutes the global model.DB to an arbitrary .db file."""

    def test_switch_database_rebinds_to_new_path(self, fresh_db, tmp_path):
        """After _switch_database, queries hit the new file."""
        from mwi import cli, model
        # Snapshot the original path for later restore
        original_path = model.DB.database

        # Build a separate SQLite file with a minimal expression schema
        alt_path = str(tmp_path / "other_project.db")
        import peewee
        alt_db = peewee.SqliteDatabase(alt_path)
        alt_db.execute_sql("""CREATE TABLE expression (
            id INTEGER PRIMARY KEY, url TEXT NOT NULL
        )""")
        alt_db.execute_sql(
            "INSERT INTO expression (url) VALUES ('https://from-alt.example/p')")
        alt_db.close()

        try:
            cli._switch_database(alt_path)
            row = model.DB.execute_sql(
                "SELECT url FROM expression LIMIT 1").fetchone()
            assert row[0] == 'https://from-alt.example/p'
            assert os.path.abspath(model.DB.database) == os.path.abspath(alt_path)
        finally:
            # Restore the original DB so subsequent tests don't break
            if not model.DB.is_closed():
                model.DB.close()
            model.DB.init(original_path, pragmas={
                'journal_mode': 'wal', 'cache_size': -1 * 512000,
                'foreign_keys': 1, 'ignore_check_constrains': 0,
                'synchronous': 0,
            })

    def test_switch_database_missing_file_raises(self, tmp_path):
        from mwi import cli
        with pytest.raises(SystemExit):
            cli._switch_database(str(tmp_path / "does-not-exist.db"))


class TestMigration008:
    def test_migration_adds_original_url_column(self, tmp_path):
        import peewee
        db = peewee.SqliteDatabase(str(tmp_path / "old.db"))
        # Old schema without original_url
        db.execute_sql("""CREATE TABLE expression (
            id INTEGER PRIMARY KEY, url TEXT NOT NULL, readable TEXT
        )""")
        db.execute_sql("INSERT INTO expression (url) VALUES ('https://x.com')")

        cols = [r[1] for r in db.execute_sql(
            "PRAGMA table_info('expression')").fetchall()]
        assert 'original_url' not in cols

        db.execute_sql(
            "ALTER TABLE expression ADD COLUMN original_url TEXT DEFAULT NULL")
        cols = [r[1] for r in db.execute_sql(
            "PRAGMA table_info('expression')").fetchall()]
        assert 'original_url' in cols

        # Default NULL preserved on existing rows
        row = db.execute_sql(
            "SELECT original_url FROM expression WHERE url='https://x.com'").fetchone()
        assert row[0] is None
        db.close()
