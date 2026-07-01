"""Tests for HTML-aware domain resolution (sprint-heuristique).

Covers:
- domain_from_url refactor (regression: unchanged URL heuristic + alias).
- _is_opaque suffix membership (label boundary, settings override).
- editorial_url_from_html signal cascade (author-first, then canonical/og).
- domain_from_html + resolve_domain orchestration (pure, no I/O).
- update_heuristic --html path (opaque reassignment, distinct channels).
- HeuristicController.update 1/0 contract + --fetch-missing guards.
- fetch_missing_opaque_html selection (opaque + html IS NULL), fetch mocked.

Zero real network: fetch is monkeypatched; settings.heuristics is patched to
the binding mwi.core actually reads.
"""
import asyncio

import pytest

from mwi.fetcher import FetchResult


def _run(coro):
    """Run a coroutine in an isolated event loop (no leak between tests)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# HTML fixtures (as strings) --------------------------------------------------

# A YouTube watch page: canonical + og:url point at the *video*; the channel
# only lives in the JSON-LD author. Author-first cascade must return the channel.
YOUTUBE_WATCH_HTML = """<html><head>
<link rel="canonical" href="https://www.youtube.com/watch?v=ABC123">
<meta property="og:url" content="https://www.youtube.com/watch?v=ABC123">
<script type="application/ld+json">
{"@type":"VideoObject","name":"A video",
 "author":{"@type":"Person","name":"ChaineA","url":"https://www.youtube.com/@chaineA"}}
</script>
</head><body><p>video</p></body></html>"""

YOUTUBE_WATCH_HTML_B = YOUTUBE_WATCH_HTML.replace("@chaineA", "@chaineB").replace(
    "ChaineA", "ChaineB")

# No author signal: canonical points off-host (custom-domain blog).
CANONICAL_ONLY_HTML = """<html><head>
<link rel="canonical" href="https://realblog.example/post-1">
<meta property="og:url" content="https://www.wordpress.com/somepost">
</head><body></body></html>"""

OG_ONLY_HTML = """<html><head>
<meta property="og:url" content="https://realblog.example/from-og">
</head><body></body></html>"""

REL_AUTHOR_HTML = """<html><head></head>
<body><a rel="author" href="/author/jane">Jane</a></body></html>"""

NO_SIGNAL_HTML = "<html><head><title>x</title></head><body><p>hi</p></body></html>"

MALFORMED_LDJSON_HTML = """<html><head>
<script type="application/ld+json">{ this is not json </script>
<link rel="canonical" href="https://realblog.example/post-1">
</head><body></body></html>"""


class TestDomainFromUrl:
    """Regression: the URL heuristic is unchanged, get_domain_name is an alias."""

    def test_alias_identity(self, fresh_db):
        core = fresh_db["core"]
        assert core.get_domain_name is core.domain_from_url

    def test_heuristic_capture(self, fresh_db, monkeypatch):
        core = fresh_db["core"]
        monkeypatch.setattr(core.settings, "heuristics",
                            {"twitter.com": r"(twitter\.com/[A-Za-z0-9_]+)"})
        assert core.domain_from_url(
            "https://twitter.com/jack/status/1") == "twitter.com/jack"

    def test_no_heuristic_returns_netloc(self, fresh_db, monkeypatch):
        core = fresh_db["core"]
        monkeypatch.setattr(core.settings, "heuristics", {})
        assert core.domain_from_url("https://www.lemonde.fr/article") == "www.lemonde.fr"

    def test_unwraps_archive(self, fresh_db, monkeypatch):
        core = fresh_db["core"]
        monkeypatch.setattr(core.settings, "heuristics", {})
        wrapped = "https://web.archive.org/web/2020/https://example.com/x"
        assert core.domain_from_url(wrapped) == "example.com"


class TestIsOpaque:
    """Suffix membership on a label boundary + settings override."""

    @pytest.mark.parametrize("url,expected", [
        ("https://www.youtube.com/watch?v=1", True),
        ("https://youtube.com/watch?v=1", True),
        ("https://m.youtube.com/watch?v=1", True),
        ("https://blogs.mediapart.fr/user/blog", True),
        ("https://mediapart.fr/journal/x", True),
        ("https://notyoutube.com/x", False),
        ("https://example.com/x", False),
        ("https://youtube.com.evil.test/x", False),
    ])
    def test_membership(self, fresh_db, url, expected):
        core = fresh_db["core"]
        assert core._is_opaque(url) is expected

    def test_settings_override(self, fresh_db, monkeypatch):
        core = fresh_db["core"]
        monkeypatch.setattr(core.settings, "opaque_platforms", {"example.com"},
                            raising=False)
        assert core._is_opaque("https://example.com/x") is True
        assert core._is_opaque("https://youtube.com/watch?v=1") is False


class TestEditorialUrlFromHtml:
    """Signal cascade: author-first, then rel=author, canonical, og."""

    def test_ldjson_author_wins_over_canonical(self, fresh_db):
        core = fresh_db["core"]
        page = "https://www.youtube.com/watch?v=ABC123"
        assert core.editorial_url_from_html(YOUTUBE_WATCH_HTML, page) == \
            "https://www.youtube.com/@chaineA"

    def test_canonical_when_no_author(self, fresh_db):
        core = fresh_db["core"]
        page = "https://www.wordpress.com/somepost"
        assert core.editorial_url_from_html(CANONICAL_ONLY_HTML, page) == \
            "https://realblog.example/post-1"

    def test_og_url_fallback(self, fresh_db):
        core = fresh_db["core"]
        page = "https://www.wordpress.com/somepost"
        assert core.editorial_url_from_html(OG_ONLY_HTML, page) == \
            "https://realblog.example/from-og"

    def test_rel_author_resolved_against_base(self, fresh_db):
        core = fresh_db["core"]
        page = "https://blogs.mediapart.fr/post/1"
        assert core.editorial_url_from_html(REL_AUTHOR_HTML, page) == \
            "https://blogs.mediapart.fr/author/jane"

    def test_no_signal_returns_none(self, fresh_db):
        core = fresh_db["core"]
        assert core.editorial_url_from_html(NO_SIGNAL_HTML,
                                            "https://x.test/") is None

    def test_malformed_ldjson_skipped(self, fresh_db):
        core = fresh_db["core"]
        assert core.editorial_url_from_html(
            MALFORMED_LDJSON_HTML, "https://x.test/") == \
            "https://realblog.example/post-1"

    def test_empty_html_returns_none(self, fresh_db):
        core = fresh_db["core"]
        assert core.editorial_url_from_html("", "https://x.test/") is None


class TestDomainFromHtml:
    """editorial_url_from_html re-fed through the URL heuristic."""

    def test_youtube_watch_returns_channel(self, fresh_db, monkeypatch):
        core = fresh_db["core"]
        monkeypatch.setattr(core.settings, "heuristics",
                            {"youtube.com": r"(youtube\.com/@[A-Za-z0-9_\-]+)"})
        page = "https://www.youtube.com/watch?v=ABC123"
        got = core.domain_from_html(page, YOUTUBE_WATCH_HTML)
        assert got == "youtube.com/@chaineA"
        assert got != core.domain_from_url(page)

    def test_no_signal_returns_none(self, fresh_db):
        core = fresh_db["core"]
        assert core.domain_from_html("https://x.test/", NO_SIGNAL_HTML) is None


class TestResolveDomain:
    """Pure orchestration: no network, no DB writes."""

    def _make_expr(self, m, url, html=None, domain_name="seed.test"):
        domain = m.Domain.create(name=domain_name)
        land = m.Land.get_or_none(m.Land.name == "rd_land") or \
            m.Land.create(name="rd_land", description="d", lang="fr")
        return m.Expression.create(land=land, domain=domain, url=url, html=html)

    def test_non_opaque_host_ignores_html(self, fresh_db):
        core, m = fresh_db["core"], fresh_db["model"]
        expr = self._make_expr(m, "https://example.com/article",
                               html=YOUTUBE_WATCH_HTML)
        # HTML present but host is not opaque → URL heuristic wins, html ignored.
        assert core.resolve_domain(expr) == "example.com"

    def test_opaque_uses_db_html(self, fresh_db, monkeypatch):
        core, m = fresh_db["core"], fresh_db["model"]
        monkeypatch.setattr(core.settings, "heuristics",
                            {"youtube.com": r"(youtube\.com/@[A-Za-z0-9_\-]+)"})
        expr = self._make_expr(m, "https://www.youtube.com/watch?v=ABC123",
                               html=YOUTUBE_WATCH_HTML)
        assert core.resolve_domain(expr) == "youtube.com/@chaineA"

    def test_opaque_no_html_falls_back_to_url(self, fresh_db, monkeypatch):
        core, m = fresh_db["core"], fresh_db["model"]
        monkeypatch.setattr(core.settings, "heuristics",
                            {"youtube.com": r"(youtube\.com/@[A-Za-z0-9_\-]+)"})
        expr = self._make_expr(m, "https://www.youtube.com/watch?v=ABC123",
                               html=None)
        # No HTML signal at all → URL heuristic (no /@ match) → bare netloc.
        assert core.resolve_domain(expr) == "www.youtube.com"

    def test_html_param_overrides_missing_db_html(self, fresh_db, monkeypatch):
        core, m = fresh_db["core"], fresh_db["model"]
        monkeypatch.setattr(core.settings, "heuristics",
                            {"youtube.com": r"(youtube\.com/@[A-Za-z0-9_\-]+)"})
        expr = self._make_expr(m, "https://www.youtube.com/watch?v=ABC123",
                               html=None)
        assert core.resolve_domain(expr, html=YOUTUBE_WATCH_HTML) == \
            "youtube.com/@chaineA"


class TestUpdateHeuristicHtml:
    """core.update_heuristic integration (no network)."""

    def _land(self, m):
        return m.Land.create(name="uh_land", description="d", lang="fr")

    def test_reassigns_two_videos_to_two_channels(self, fresh_db, monkeypatch):
        core, m = fresh_db["core"], fresh_db["model"]
        monkeypatch.setattr(core.settings, "heuristics",
                            {"youtube.com": r"(youtube\.com/@[A-Za-z0-9_\-]+)"})
        land = self._land(m)
        d = m.Domain.create(name="youtube.com")
        e1 = m.Expression.create(land=land, domain=d,
                                 url="https://www.youtube.com/watch?v=1",
                                 html=YOUTUBE_WATCH_HTML)
        e2 = m.Expression.create(land=land, domain=d,
                                 url="https://www.youtube.com/watch?v=2",
                                 html=YOUTUBE_WATCH_HTML_B)

        updated = core.update_heuristic(land, use_html=True)

        assert updated == 2
        n1 = m.Expression.get_by_id(e1.id).domain.name
        n2 = m.Expression.get_by_id(e2.id).domain.name
        assert n1 == "youtube.com/@chaineA"
        assert n2 == "youtube.com/@chaineB"
        assert n1 != n2  # flagship: distinct channels, not one collapsed node

    def test_default_url_only_still_works(self, fresh_db, monkeypatch):
        core, m = fresh_db["core"], fresh_db["model"]
        monkeypatch.setattr(core.settings, "heuristics",
                            {"twitter.com": r"(twitter\.com/[A-Za-z0-9_]+)"})
        land = self._land(m)
        d = m.Domain.create(name="twitter.com")
        e = m.Expression.create(land=land, domain=d,
                                url="https://twitter.com/jack/status/1")

        updated = core.update_heuristic()  # legacy zero-arg call

        assert updated == 1
        assert m.Expression.get_by_id(e.id).domain.name == "twitter.com/jack"

    def test_non_opaque_untouched_under_html(self, fresh_db, monkeypatch):
        core, m = fresh_db["core"], fresh_db["model"]
        monkeypatch.setattr(core.settings, "heuristics", {})
        land = self._land(m)
        d = m.Domain.create(name="example.com")
        e = m.Expression.create(land=land, domain=d,
                                url="https://example.com/a", html=YOUTUBE_WATCH_HTML)

        updated = core.update_heuristic(land, use_html=True)

        assert updated == 0
        assert m.Expression.get_by_id(e.id).domain.name == "example.com"


class TestFetchMissingOpaqueHtml:
    """Async selection: only opaque hosts with html IS NULL, fetch mocked."""

    def test_selects_opaque_null_only(self, fresh_db, monkeypatch):
        core, m = fresh_db["core"], fresh_db["model"]
        land = m.Land.create(name="fm_land", description="d", lang="fr")
        dy = m.Domain.create(name="youtube.com")
        de = m.Domain.create(name="example.com")
        yt = m.Expression.create(land=land, domain=dy,
                                 url="https://www.youtube.com/watch?v=1", html=None)
        m.Expression.create(land=land, domain=de,
                            url="https://example.com/a", html=None)  # not opaque
        m.Expression.create(land=land, domain=dy,
                            url="https://www.youtube.com/watch?v=2",
                            html="<html>stored</html>")  # already has html

        async def fake_fetch(url, session=None, **kw):
            return FetchResult(url=url, status_code="200",
                               html="<html>fetched</html>", method_used="aiohttp")

        monkeypatch.setattr(core, "fetch_html", fake_fetch)

        result = _run(core.fetch_missing_opaque_html(land, limit=10))

        assert list(result.keys()) == [str(yt.url)]
        assert result[str(yt.url)] == "<html>fetched</html>"

    def test_limit_caps_fetches(self, fresh_db, monkeypatch):
        core, m = fresh_db["core"], fresh_db["model"]
        land = m.Land.create(name="fm_land2", description="d", lang="fr")
        dy = m.Domain.create(name="youtube.com")
        for i in range(5):
            m.Expression.create(land=land, domain=dy,
                                url=f"https://www.youtube.com/watch?v={i}", html=None)

        async def fake_fetch(url, session=None, **kw):
            return FetchResult(url=url, status_code="200",
                               html="<x/>", method_used="aiohttp")

        monkeypatch.setattr(core, "fetch_html", fake_fetch)

        result = _run(core.fetch_missing_opaque_html(land, limit=2))

        assert len(result) == 2


class TestHeuristicUpdateController:
    """Controller 1/0 contract + --fetch-missing guards."""

    def test_default_returns_1(self, fresh_db):
        controller, core = fresh_db["controller"], fresh_db["core"]
        assert controller.HeuristicController.update(core.Namespace()) == 1

    def test_unknown_land_returns_0(self, fresh_db):
        controller, core = fresh_db["controller"], fresh_db["core"]
        ret = controller.HeuristicController.update(
            core.Namespace(land="does_not_exist_xyz"))
        assert ret == 0

    def test_fetch_missing_without_html_returns_0(self, fresh_db):
        controller, core = fresh_db["controller"], fresh_db["core"]
        ret = controller.HeuristicController.update(
            core.Namespace(fetch_missing=True, limit=5))
        assert ret == 0

    def test_fetch_missing_without_limit_returns_0(self, fresh_db):
        controller, core = fresh_db["controller"], fresh_db["core"]
        ret = controller.HeuristicController.update(
            core.Namespace(html=True, fetch_missing=True))
        assert ret == 0

    def test_html_flag_does_not_fetch(self, fresh_db, monkeypatch):
        controller, core = fresh_db["controller"], fresh_db["core"]
        calls = {"n": 0}

        async def spy(land, limit):
            calls["n"] += 1
            return {}

        monkeypatch.setattr(controller.core, "fetch_missing_opaque_html", spy)
        ret = controller.HeuristicController.update(core.Namespace(html=True))
        assert ret == 1 and calls["n"] == 0

    def test_fetch_missing_calls_fetch_and_returns_1(self, fresh_db, monkeypatch):
        controller, core = fresh_db["controller"], fresh_db["core"]
        calls = {"n": 0}

        async def spy(land, limit):
            calls["n"] += 1
            return {}

        monkeypatch.setattr(controller.core, "fetch_missing_opaque_html", spy)
        ret = controller.HeuristicController.update(
            core.Namespace(html=True, fetch_missing=True, limit=5))
        assert ret == 1 and calls["n"] == 1
