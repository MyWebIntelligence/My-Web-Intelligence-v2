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

from mwi.url_normalizer import (
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

    # Malformed hosts scraped from page sources (e.g. template placeholders
    # left in HTML) must never raise: Python 3.14's hardened urlparse throws
    # "Invalid IPv6 URL" on a bracketed host, which used to crash whole crawl
    # runs (regression 2026-06-12). normalize_url returns them unchanged and
    # is_crawlable() filters them downstream.
    @pytest.mark.parametrize("bad", [
        "https://[domain]/x",      # template placeholder host
        "https://[",               # truncated bracket
        "https://[tmpl]/path",     # non-IPv6 bracketed host
    ])
    def test_malformed_host_returns_unchanged_no_raise(self, bad):
        assert normalize_url(bad) == bad

    @pytest.mark.parametrize("bad", [
        "https://[domain]/x",
        "https://[",
        "https://[tmpl]/path",
    ])
    def test_malformed_host_idempotent(self, bad):
        assert normalize_url(normalize_url(bad)) == normalize_url(bad)

    def test_malformed_host_not_crawlable(self):
        # Defense-in-depth: even returned unchanged, the bad URL is rejected.
        from mwi.core import is_crawlable
        assert is_crawlable("https://[domain]/x") is False

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

    def test_unwrap_linkedin_off_by_default(self):
        u = ("https://www.linkedin.com/redir/redirect"
             "?url=https%3A%2F%2Fa.org%2Fb")
        # Off by default: only host lowercasing / query handling, no unwrap.
        assert "linkedin.com" in normalize_url(u)

    def test_unwrap_linkedin_redirect_when_enabled(self):
        u = ("https://www.linkedin.com/redir/redirect"
             "?url=https%3A%2F%2Fa.org%2Fb")
        out = normalize_url(u, rules={'unwrap_linkedin_redirect': True})
        assert out == "https://a.org/b"

    def test_unwrap_linkedin_session_redirect_when_enabled(self):
        u = ("https://www.linkedin.com/signup/cold-join"
             "?session_redirect=https%3A%2F%2Fc.org%2Fd")
        out = normalize_url(u, rules={'unwrap_linkedin_redirect': True})
        assert out == "https://c.org/d"

    def test_unwrap_linkedin_idempotent(self):
        u = ("https://www.linkedin.com/redir/redirect"
             "?url=https%3A%2F%2Fa.org%2Fb")
        rules = {'unwrap_linkedin_redirect': True}
        once = normalize_url(u, rules=rules)
        assert normalize_url(once, rules=rules) == once

    def test_unwrap_linkedin_leaves_real_content_untouched(self):
        u = "https://www.linkedin.com/in/some-profile"
        out = normalize_url(u, rules={'unwrap_linkedin_redirect': True})
        assert "linkedin.com/in/some-profile" in out

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
# Groupes de collision : variantes convergeant vers une canonique absente
# ────────────────────────────────────────────────────────────────────────

class TestNormalizeCollisionPromotion:
    """Quand plusieurs variantes normalisent vers la même URL canonique
    absente de la base, une variante est promue (rename) et les autres
    fusionnées dedans — jamais deux lignes avec la même URL."""

    def _enable_dedup_rules(self, monkeypatch):
        import settings
        monkeypatch.setattr(settings, 'url_normalization',
                            {'force_https': True, 'strip_www': True,
                             'trailing_slash': 'strip'}, raising=False)

    def _make_variants(self, fresh_db, canonical_row=False,
                       a_fields=None, b_fields=None):
        """Deux variantes http/www de la même page (URL canonique absente
        sauf canonical_row=True)."""
        m = fresh_db["model"]
        land = m.Land.create(name=rand_name("col"), description="t", lang="fr")
        d_www = m.Domain.get_or_create(name="www.collision.test")[0]
        a = m.Expression.create(
            land=land, domain=d_www, url="http://www.collision.test/p",
            **{'depth': 0, **(a_fields or {})})
        b = m.Expression.create(
            land=land, domain=d_www, url="https://www.collision.test/p",
            **{'depth': 0, **(b_fields or {})})
        canonical = None
        if canonical_row:
            d_bare = m.Domain.get_or_create(name="collision.test")[0]
            canonical = m.Expression.create(
                land=land, domain=d_bare, url="https://collision.test/p",
                depth=0)
        return land, a, b, canonical

    def _normalize(self, fresh_db, land):
        controller = fresh_db["controller"]
        core = fresh_db["core"]
        ret = controller.LandController.normalize(core.Namespace(
            name=land.name, dry_run=None,
            reset_status=None, verbose=None, limit=0))
        assert ret == 1

    def test_collision_two_variants_no_canonical_single_row_remains(
            self, fresh_db, monkeypatch):
        self._enable_dedup_rules(monkeypatch)
        m = fresh_db["model"]
        land, a, b, _ = self._make_variants(fresh_db)
        d_other = m.Domain.get_or_create(name="other.test")[0]
        other = m.Expression.create(
            land=land, domain=d_other, url="https://other.test/x", depth=0)
        m.ExpressionLink.create(source=other, target=a)
        m.ExpressionLink.create(source=other, target=b)

        self._normalize(fresh_db, land)

        survivors = list(m.Expression.select().where(
            (m.Expression.land == land)
            & (m.Expression.url == "https://collision.test/p")))
        assert len(survivors) == 1
        assert m.Expression.select().where(
            m.Expression.land == land).count() == 2  # survivant + other
        # les deux liens entrants convergent en UNE arête other -> survivant
        assert m.ExpressionLink.select().where(
            (m.ExpressionLink.source == other)
            & (m.ExpressionLink.target == survivors[0])).count() == 1
        assert m.ExpressionLink.select().where(
            m.ExpressionLink.source == other).count() == 1

    def test_collision_outgoing_links_remapped(self, fresh_db, monkeypatch):
        self._enable_dedup_rules(monkeypatch)
        m = fresh_db["model"]
        land, a, b, _ = self._make_variants(
            fresh_db, b_fields={'html': '<html>x</html>'})  # b sera promue
        d_other = m.Domain.get_or_create(name="other.test")[0]
        other = m.Expression.create(
            land=land, domain=d_other, url="https://other.test/x", depth=0)
        m.ExpressionLink.create(source=a, target=other)

        self._normalize(fresh_db, land)

        survivor = m.Expression.get(
            (m.Expression.land == land)
            & (m.Expression.url == "https://collision.test/p"))
        assert survivor.id == b.id
        assert m.ExpressionLink.select().where(
            (m.ExpressionLink.source == survivor)
            & (m.ExpressionLink.target == other)).exists()

    def test_collision_with_existing_canonical_merges_all(
            self, fresh_db, monkeypatch):
        self._enable_dedup_rules(monkeypatch)
        m = fresh_db["model"]
        land, a, b, canonical = self._make_variants(fresh_db, canonical_row=True)

        self._normalize(fresh_db, land)

        assert not m.Expression.select().where(
            m.Expression.id.in_([a.id, b.id])).exists()
        assert m.Expression.select().where(
            m.Expression.land == land).count() == 1
        assert m.Expression.get_by_id(canonical.id).url == \
            "https://collision.test/p"

    def test_promotion_prefers_rich_expression(self, fresh_db, monkeypatch):
        self._enable_dedup_rules(monkeypatch)
        m = fresh_db["model"]
        land, a, b, _ = self._make_variants(
            fresh_db,
            b_fields={'html': '<html>x</html>', 'readable': 'Contenu'})

        self._normalize(fresh_db, land)

        survivor = m.Expression.get(
            (m.Expression.land == land)
            & (m.Expression.url == "https://collision.test/p"))
        assert survivor.id == b.id
        assert survivor.original_url == "https://www.collision.test/p"
        assert not m.Expression.select().where(
            m.Expression.id == a.id).exists()

    def test_promotion_tie_breaks_on_smallest_id(self, fresh_db, monkeypatch):
        self._enable_dedup_rules(monkeypatch)
        m = fresh_db["model"]
        land, a, b, _ = self._make_variants(fresh_db)  # deux stubs identiques

        self._normalize(fresh_db, land)

        survivor = m.Expression.get(
            (m.Expression.land == land)
            & (m.Expression.url == "https://collision.test/p"))
        assert survivor.id == a.id
        assert not m.Expression.select().where(
            m.Expression.id == b.id).exists()

    def test_promotion_then_backfill_from_loser(self, fresh_db, monkeypatch):
        """Synergie B1×B2 : la promue récupère les champs vides du perdant."""
        self._enable_dedup_rules(monkeypatch)
        m = fresh_db["model"]
        land, a, b, _ = self._make_variants(
            fresh_db,
            a_fields={'title': 'Titre'},
            b_fields={'html': '<html>x</html>'})  # b promue (html)

        self._normalize(fresh_db, land)

        survivor = m.Expression.get_by_id(b.id)
        assert survivor.html == '<html>x</html>'
        assert survivor.title == 'Titre'

    def test_collision_run_idempotent(self, fresh_db, monkeypatch):
        self._enable_dedup_rules(monkeypatch)
        from mwi import normalize_pipeline
        m = fresh_db["model"]
        land, a, b, _ = self._make_variants(fresh_db)

        self._normalize(fresh_db, land)
        count_first = m.Expression.select().where(
            m.Expression.land == land).count()

        totals = normalize_pipeline.normalize_land(land)

        assert totals['renamed'] == 0
        assert totals['merged'] == 0
        assert m.Expression.select().where(
            m.Expression.land == land).count() == count_first == 1

    def test_exact_duplicate_canonical_rows_merged(self, fresh_db, monkeypatch):
        """Deux lignes partageant la MÊME URL déjà canonique sont fusionnées
        (la plus riche survit) — l'ancienne limitation est levée."""
        self._enable_dedup_rules(monkeypatch)
        m = fresh_db["model"]
        land = m.Land.create(name=rand_name("dup"), description="t", lang="fr")
        d = m.Domain.get_or_create(name="collision.test")[0]
        stub = m.Expression.create(land=land, domain=d,
                                   url="https://collision.test/p", depth=0)
        rich = m.Expression.create(land=land, domain=d,
                                   url="https://collision.test/p", depth=0,
                                   html='<html>x</html>')
        d_other = m.Domain.get_or_create(name="other.test")[0]
        other = m.Expression.create(land=land, domain=d_other,
                                    url="https://other.test/x", depth=0)
        m.ExpressionLink.create(source=other, target=stub)

        self._normalize(fresh_db, land)

        survivors = list(m.Expression.select().where(
            (m.Expression.land == land)
            & (m.Expression.url == "https://collision.test/p")))
        assert len(survivors) == 1
        assert survivors[0].id == rich.id
        assert not m.Expression.select().where(
            m.Expression.id == stub.id).exists()
        assert m.ExpressionLink.select().where(
            (m.ExpressionLink.source == other)
            & (m.ExpressionLink.target == rich.id)).exists()

    def test_dry_run_counts_collision_groups_without_writes(
            self, fresh_db, monkeypatch):
        self._enable_dedup_rules(monkeypatch)
        from mwi import normalize_pipeline
        m = fresh_db["model"]
        land, a, b, _ = self._make_variants(fresh_db)

        totals = normalize_pipeline.normalize_land(land, dry_run=True)

        assert totals['collision_groups'] >= 1
        assert totals['promoted'] >= 1
        assert totals['renamed'] + totals['merged'] == 2
        # aucune écriture
        assert m.Expression.select().where(
            m.Expression.land == land).count() == 2
        assert m.Expression.get_by_id(a.id).url == "http://www.collision.test/p"
        assert m.Expression.get_by_id(b.id).url == "https://www.collision.test/p"


# ────────────────────────────────────────────────────────────────────────
# Merge backfill: le canonique récupère le contenu du doublon si vide
# ────────────────────────────────────────────────────────────────────────

class TestNormalizeMergeBackfill:
    """Au merge, les champs de contenu du doublon comblent les champs vides
    du canonique (jamais d'écrasement d'un champ rempli)."""

    def _make_pair(self, fresh_db, canonical_fields=None, duplicate_fields=None):
        """Canonique propre + doublon archive de la même page (merge attendu)."""
        m = fresh_db["model"]
        land = m.Land.create(name=rand_name("bf"), description="t", lang="fr")
        d_archive = m.Domain.get_or_create(name="web.archive.org")[0]
        d_clean = m.Domain.get_or_create(name="example.com")[0]
        canonical = m.Expression.create(
            land=land, domain=d_clean, url="https://example.com/page1",
            **{'depth': 0, **(canonical_fields or {})})
        duplicate = m.Expression.create(
            land=land, domain=d_archive,
            url="https://web.archive.org/web/20230605/https://example.com/page1",
            **{'depth': 1, **(duplicate_fields or {})})
        return land, canonical, duplicate

    def _normalize(self, fresh_db, land, reset_status=None):
        controller = fresh_db["controller"]
        core = fresh_db["core"]
        ret = controller.LandController.normalize(core.Namespace(
            name=land.name, dry_run=None,
            reset_status=reset_status, verbose=None, limit=0))
        assert ret == 1

    def test_backfill_content_to_empty_canonical(self, fresh_db):
        m = fresh_db["model"]
        land, canonical, duplicate = self._make_pair(
            fresh_db,
            duplicate_fields={'html': '<html>H</html>', 'readable': 'Readable',
                              'title': 'Titre'})

        self._normalize(fresh_db, land)

        assert not m.Expression.select().where(
            m.Expression.id == duplicate.id).exists()
        merged = m.Expression.get_by_id(canonical.id)
        assert merged.html == '<html>H</html>'
        assert merged.readable == 'Readable'
        assert merged.title == 'Titre'

    def test_backfill_does_not_overwrite_filled_canonical(self, fresh_db):
        m = fresh_db["model"]
        land, canonical, _ = self._make_pair(
            fresh_db,
            canonical_fields={'title': 'T1', 'readable': 'R1'},
            duplicate_fields={'title': 'T2', 'readable': 'R2',
                              'html': '<html>H</html>'})

        self._normalize(fresh_db, land)

        merged = m.Expression.get_by_id(canonical.id)
        assert merged.title == 'T1'
        assert merged.readable == 'R1'
        assert merged.html == '<html>H</html>'

    def test_backfill_validllm_pair_moves_together(self, fresh_db):
        m = fresh_db["model"]
        land, canonical, _ = self._make_pair(
            fresh_db,
            duplicate_fields={'validllm': 'oui', 'validmodel': 'org/model'})

        self._normalize(fresh_db, land)

        merged = m.Expression.get_by_id(canonical.id)
        assert merged.validllm == 'oui'
        assert merged.validmodel == 'org/model'

    def test_merge_depth_takes_min(self, fresh_db):
        m = fresh_db["model"]
        land, canonical, _ = self._make_pair(
            fresh_db,
            canonical_fields={'depth': 3},
            duplicate_fields={'depth': 1})

        self._normalize(fresh_db, land)

        assert m.Expression.get_by_id(canonical.id).depth == 1

    def test_merge_relevance_untouched(self, fresh_db):
        """relevance n'est jamais backfillée : land consolidate la recale."""
        m = fresh_db["model"]
        land, canonical, _ = self._make_pair(
            fresh_db,
            canonical_fields={'relevance': 0},
            duplicate_fields={'relevance': 7})

        self._normalize(fresh_db, land)

        assert m.Expression.get_by_id(canonical.id).relevance == 0

    def test_backfill_skips_status_fields_when_reset_status(self, fresh_db):
        """--reset-status : ne pas réintroduire http_status/fetched_at par
        backfill (le reset des renames serait annulé par le merge)."""
        import datetime
        m = fresh_db["model"]
        land, canonical, _ = self._make_pair(
            fresh_db,
            duplicate_fields={'http_status': '200',
                              'fetched_at': datetime.datetime.now(),
                              'title': 'Titre'})

        self._normalize(fresh_db, land, reset_status='TRUE')

        merged = m.Expression.get_by_id(canonical.id)
        assert merged.http_status is None
        assert merged.fetched_at is None
        assert merged.title == 'Titre'  # le backfill de contenu reste actif


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


class TestRootPathAndPercentEncoding:
    """Root-path convergence, RFC 3986 escapes, opt-in path case, host trackers.

    Sprint body-links, T1'. These are node-identity rules: they decide whether
    two URLs designate one resource or two. They are deliberately conservative
    -- only the `strip` policy changes, because `preserve` is the default on
    every existing land and touching it would rename nodes everywhere at the
    next `land normalize`.
    """

    # ---- root path ------------------------------------------------------ #

    def test_root_unified_under_strip(self):
        """The defect: '/' kept its slash while '' stayed empty."""
        strip = {'trailing_slash': 'strip'}

        assert normalize_url('https://a.eu/', strip) == \
            normalize_url('https://a.eu', strip)

    def test_root_converges_to_the_slashless_form(self):
        """Aligns the exact key on the two relaxed rungs, which both rstrip."""
        assert normalize_url('https://a.eu/', {'trailing_slash': 'strip'}) == \
            'https://a.eu'

    def test_root_unified_under_add(self):
        add = {'trailing_slash': 'add'}

        assert normalize_url('https://a.eu/', add) == \
            normalize_url('https://a.eu', add) == 'https://a.eu/'

    def test_root_preserved_under_preserve(self):
        """The test that protects every existing land: the default must not move."""
        preserve = {'trailing_slash': 'preserve'}

        assert normalize_url('https://a.eu/', preserve) != \
            normalize_url('https://a.eu', preserve)

    def test_root_with_query_under_strip(self):
        strip = {'trailing_slash': 'strip'}
        out = normalize_url('https://a.eu/?a=1', strip)

        assert out == 'https://a.eu?a=1'
        assert normalize_url(out, strip) == out

    def test_double_slash_root_under_strip(self):
        assert normalize_url('https://a.eu//', {'trailing_slash': 'strip'}) == \
            'https://a.eu'

    @pytest.mark.parametrize('policy', ['preserve', 'strip', 'add'])
    @pytest.mark.parametrize('url', [
        'https://a.eu', 'https://a.eu/', 'https://a.eu//',
        'https://a.eu/p', 'https://a.eu/p/', 'https://a.eu/p.html',
        'https://a.eu/?x=1', 'https://a.eu/p/?x=1',
    ])
    def test_trailing_slash_idempotent(self, policy, url):
        rules = {'trailing_slash': policy}
        once = normalize_url(url, rules)

        assert normalize_url(once, rules) == once

    # ---- percent-encoding ----------------------------------------------- #

    def test_percent_escapes_uppercased_in_path(self):
        out = normalize_url('https://a.eu/%c3%a9t%c3%a9')

        assert out == 'https://a.eu/%C3%A9t%C3%A9'
        assert 'é' not in out          # uppercased, never decoded

    def test_percent_escapes_uppercased_in_query_when_untouched_otherwise(self):
        """The only path where a lowercase escape survives today."""
        rules = {'normalize_query_order': False, 'strip_trackers': []}

        assert normalize_url('https://a.eu/p?x=%2f', rules) == \
            'https://a.eu/p?x=%2F'

    def test_percent_escapes_are_never_decoded(self):
        assert normalize_url('https://a.eu/%2Fnot-a-separator') == \
            'https://a.eu/%2Fnot-a-separator'

    @pytest.mark.parametrize('url', [
        'https://a.eu/100%-sure', 'https://a.eu/x%', 'https://a.eu/x%zz',
    ])
    def test_a_lone_percent_is_left_alone(self, url):
        assert normalize_url(url) == url

    def test_percent_uppercase_is_idempotent(self):
        once = normalize_url('https://a.eu/%c3%a9')

        assert normalize_url(once) == once

    # ---- path_casefold (opt-in) ----------------------------------------- #

    def test_path_case_is_preserved_by_default(self):
        assert normalize_url('https://a.eu/IP_23') != normalize_url('https://a.eu/ip_23')

    def test_path_casefold_opt_in(self):
        rules = {'path_casefold': True}

        assert normalize_url('https://a.eu/IP_23_6473', rules) == \
            normalize_url('https://a.eu/ip_23_6473', rules)

    def test_path_casefold_leaves_the_query_case_alone(self):
        """?S=Foo and ?s=foo are different searches on most engines."""
        rules = {'path_casefold': True, 'normalize_query_order': False,
                 'strip_trackers': []}

        assert normalize_url('https://a.eu/P?S=Foo', rules) == \
            'https://a.eu/p?S=Foo'

    def test_path_casefold_does_not_lowercase_percent_escapes(self):
        """Order matters: casefold first, escapes uppercased after."""
        rules = {'path_casefold': True}

        assert normalize_url('https://a.eu/%C3%A9', rules) == 'https://a.eu/%C3%A9'

    def test_path_casefold_is_idempotent(self):
        rules = {'path_casefold': True}
        once = normalize_url('https://a.eu/MiXeD/Case', rules)

        assert normalize_url(once, rules) == once

    # ---- host-scoped trackers ------------------------------------------- #

    HOST_RULES = {'strip_trackers_by_host': {
        'linkedin.com': ['trk', 'originalSubdomain', 'trackingId'],
    }}

    def test_host_scoped_trackers_are_stripped_on_the_listed_host(self):
        out = normalize_url(
            'https://linkedin.com/in/someone?trk=abc&keep=1', self.HOST_RULES)

        assert 'trk=' not in out and 'keep=1' in out

    def test_host_scoped_trackers_apply_to_subdomains(self):
        out = normalize_url(
            'https://fr.linkedin.com/in/x?originalSubdomain=fr', self.HOST_RULES)

        assert 'originalSubdomain' not in out

    def test_host_scoped_trackers_do_not_leak_to_other_hosts(self):
        """?s= is the WordPress search query: stripping it collapses pages."""
        out = normalize_url('https://blog.example.com/?s=climat&ref=home',
                            self.HOST_RULES)

        assert 's=climat' in out and 'ref=home' in out

    def test_host_suffix_match_is_boundary_safe(self):
        """notlinkedin.com ends with linkedin.com; it is a different site."""
        out = normalize_url('https://notlinkedin.com/p?trk=abc', self.HOST_RULES)

        assert 'trk=abc' in out

    def test_host_scoped_trackers_are_case_sensitive(self):
        """LinkedIn emits originalSubdomain in exactly that case."""
        out = normalize_url('https://linkedin.com/p?originalsubdomain=fr',
                            self.HOST_RULES)

        assert 'originalsubdomain=fr' in out

    def test_host_scoped_trackers_ignore_port_and_userinfo(self):
        out = normalize_url('https://user@linkedin.com:443/p?trk=abc',
                            self.HOST_RULES)

        assert 'trk=abc' not in out

    def test_absent_key_keeps_the_previous_behaviour(self):
        # Explicit rules, like every other test in this class. `{}` merges onto
        # DEFAULT_RULES, where `strip_trackers_by_host` is empty -- so the key
        # really is absent, which is what the name claims. Reading the ambient
        # configuration instead made the verdict depend on the machine: green
        # here, red on a fresh clone, whose example config DEFINES the key.
        assert normalize_url('https://linkedin.com/p?trk=abc', {}) == \
            'https://linkedin.com/p?trk=abc'


class TestDbOverrideDoesNotMoveExports:
    """R03 (c) - CONTRACT: `--db PATH` rebinds the database, NOT the data dir.

    `cli._switch_database` re-inits `model.DB` and nothing else. Exports and
    `lands/<id>/` still land in `settings.data_location`, because that is what
    `core.export_land` reads. So pointing `--db` at a database sitting in
    another project writes that project's exports into the CURRENT data
    directory — surprising enough that the README example was actively
    misleading.

    Restoring `model.DB` in a `finally` is mandatory: a leaked rebind
    contaminates every later test in the session.
    """

    def test_exports_stay_in_settings_data_location(self, fresh_db, tmp_path):
        import glob as _glob
        import shutil

        from mwi import cli, model

        controller = fresh_db["controller"]
        core = fresh_db["core"]
        data_dir = str(fresh_db["data_dir"])
        original_path = model.DB.database

        controller.LandController.create(
            core.Namespace(name="dbo_land", desc="d", lang=["fr"]))
        m = fresh_db["model"]
        land = m.Land.get(m.Land.name == "dbo_land")
        domain, _ = m.Domain.get_or_create(name="dbo.example")
        m.Expression.create(land=land, domain=domain,
                            url="https://dbo.example/a", depth=0, relevance=5,
                            title="t", http_status="200")

        # Checkpoint before copying: WAL keeps committed rows out of the main
        # file until then, so the copy would otherwise be empty.
        model.DB.execute_sql("PRAGMA wal_checkpoint(TRUNCATE)")
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        other = elsewhere / "other.db"
        shutil.copy(original_path, str(other))

        try:
            cli._switch_database(str(other))
            assert controller.LandController.export(
                core.Namespace(name="dbo_land", type="pagecsv", minrel=0)) == 1
        finally:
            if not model.DB.is_closed():
                model.DB.close()
            model.DB.init(original_path, pragmas={
                'journal_mode': 'wal', 'cache_size': -1 * 512000,
                'foreign_keys': 1, 'ignore_check_constrains': 0,
                'synchronous': 0})

        assert len(_glob.glob(os.path.join(
            data_dir, "export_land_*_pagecsv_*"))) == 1
        assert _glob.glob(str(elsewhere / "export_land_*")) == []
