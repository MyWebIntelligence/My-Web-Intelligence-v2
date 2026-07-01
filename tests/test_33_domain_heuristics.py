"""Tests for table-driven domain resolution (sprint-heuristique).

Covers the unified platform_heuristics table {host: {"url": regex|None,
"html": signal}}:
- domain_from_url: url rule for listed hosts, netloc for the rest.
- _is_opaque: table membership (only listed hosts).
- per-signal HTML extraction (ldjson_author / canonical / og_url / rel_author).
- domain_from_html + resolve_domain (pure, no I/O).
- update_heuristic: only-listed scope + dry-run.
- HeuristicController.update 1/0 contract + guards.
- fetch_missing_opaque_html selection (listed + html IS NULL), fetch mocked.

Tests patch mwi.core.settings.platform_heuristics with a small controlled table
so they are deterministic and independent of the shipped 163-entry default.
"""
import asyncio

import pytest

from mwi.fetcher import FetchResult

# Small controlled table for deterministic tests.
TABLE = {
    "youtube.com": {"url": r"(youtube\.com/@[A-Za-z0-9_.-]+)", "html": "ldjson_author"},
    "wordpress.com": {"url": None, "html": "canonical"},
    "mediapart.fr": {"url": None, "html": "rel_author"},
    "twitter.com": {"url": r"(twitter\.com/(?!intent(?:[/?]|$))[A-Za-z0-9_]+)",
                    "html": "canonical"},
}


def _patch_table(monkeypatch, core, table=None):
    monkeypatch.setattr(core.settings, "platform_heuristics",
                        table if table is not None else TABLE, raising=False)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# HTML fixtures --------------------------------------------------------------

YT_HTML = """<html><head>
<link rel="canonical" href="https://www.youtube.com/watch?v=ABC">
<script type="application/ld+json">
{"@type":"VideoObject","author":{"url":"https://www.youtube.com/@franceinfo"}}
</script></head><body></body></html>"""

YT_HTML_B = YT_HTML.replace("@franceinfo", "@mediapart")

CANONICAL_HTML = """<html><head>
<link rel="canonical" href="https://realblog.example/post"></head></html>"""

OG_HTML = """<html><head>
<meta property="og:url" content="https://realblog.example/from-og"></head></html>"""

REL_AUTHOR_HTML = """<html><body>
<a rel="author" href="/author/jane">Jane</a></body></html>"""

PUBLISHER_HTML = """<html><head>
<script type="application/ld+json">
{"@type":"NewsArticle","publisher":{"url":"https://pub.example/"}}
</script></head></html>"""

NO_SIGNAL_HTML = "<html><head><title>x</title></head><body>hi</body></html>"

# YouTube /watch: channel in schema.org microdata (no JSON-LD at all).
ITEMPROP_AUTHOR_HTML = """<html><body>
<link itemprop="url" href="https://www.youtube.com/watch?v=1">
<span itemprop="author" itemscope itemtype="http://schema.org/Person">
<link itemprop="url" href="https://www.youtube.com/@JLMelenchon">
<link itemprop="name" content="JLM"></span></body></html>"""

# Dailymotion /video: 200 JS shell, channel only in embedded SSR state JSON.
DM_HTML = ('<html><body><script>window.__DATA__={"video":{"channel":'
           '{"accountType":"verified-partner","xid":"xf4wt7",'
           '"name":"Europe1fr","displayName":"Europe 1"}}};'
           '</script></body></html>')


class TestDomainFromUrl:
    def test_alias_identity(self, fresh_db):
        core = fresh_db["core"]
        assert core.get_domain_name is core.domain_from_url

    def test_listed_url_rule_captures_entity(self, fresh_db, monkeypatch):
        core = fresh_db["core"]
        _patch_table(monkeypatch, core)
        assert core.domain_from_url(
            "https://www.youtube.com/@franceinfo/videos") == "youtube.com/@franceinfo"

    def test_listed_no_url_rule_returns_netloc(self, fresh_db, monkeypatch):
        core = fresh_db["core"]
        _patch_table(monkeypatch, core)
        assert core.domain_from_url(
            "https://user.wordpress.com/post") == "user.wordpress.com"

    def test_unlisted_host_returns_netloc(self, fresh_db, monkeypatch):
        core = fresh_db["core"]
        _patch_table(monkeypatch, core)
        assert core.domain_from_url("https://www.la-croix.com/France/x") == "www.la-croix.com"

    def test_url_rule_no_match_returns_netloc(self, fresh_db, monkeypatch):
        core = fresh_db["core"]
        _patch_table(monkeypatch, core)
        # youtube watch has no /@handle -> url rule fails -> netloc
        assert core.domain_from_url("https://www.youtube.com/watch?v=1") == "www.youtube.com"

    def test_blocklist_collapses_reserved_word(self, fresh_db, monkeypatch):
        core = fresh_db["core"]
        _patch_table(monkeypatch, core)
        assert core.domain_from_url("https://twitter.com/intent/tweet") == "twitter.com"
        assert core.domain_from_url(
            "https://twitter.com/JLMelenchon/status/1") == "twitter.com/JLMelenchon"

    def test_facebook_group_kept_as_entity(self, fresh_db, monkeypatch):
        """A Facebook group URL IS the editorial entity (groups/<id>); a bare
        /groups hub and blocked paths fall back to the netloc."""
        core = fresh_db["core"]
        fb = {"facebook.com": {
            "url": (r"([a-z0-9\-_]+\.facebook\.com/(?:groups/[a-zA-Z0-9%\.\-_]+"
                    r"|(?!(?:groups)|(?:reel))[a-zA-Z0-9%\.\-_]+))/?\??"),
            "html": "og_url", "alias": "facebook.com", "lower": True}}
        _patch_table(monkeypatch, core, fb)
        assert core.domain_from_url(
            "https://www.facebook.com/groups/253581821992797/") == \
            "facebook.com/groups/253581821992797"
        assert core.domain_from_url(
            "https://www.facebook.com/JLMelenchon/") == "facebook.com/jlmelenchon"
        assert core.domain_from_url(
            "https://www.facebook.com/groups/") == "www.facebook.com"
        assert core.domain_from_url(
            "https://www.facebook.com/reel/9") == "www.facebook.com"

    def test_facebook_technical_endpoints_and_pages(self, fresh_db, monkeypatch):
        """FB widget/redirect endpoints (.php, dialog, plugins) collapse to the
        netloc; old-format pages/<name>/<id> is captured whole; real pages that
        merely contain those substrings are preserved."""
        core = fresh_db["core"]
        fb_url = (r"([a-z0-9\-_]+\.facebook\.com/(?:groups/[a-zA-Z0-9%\.\-_]+"
                  r"|pages/[^?#]*[^?#/]"
                  r"|(?!(?:[a-zA-Z0-9_\-]+\.php)(?:[/?]|$)|(?:dialog)(?:[/?]|$)"
                  r"|(?:plugins)(?:[/?]|$)|(?:pages)(?:[/?]|$))"
                  r"[a-zA-Z0-9%\.\-_]+))/?\??")
        fb = {"facebook.com": {"url": fb_url, "html": "og_url",
                               "alias": "facebook.com", "lower": True}}
        _patch_table(monkeypatch, core, fb)
        assert core.domain_from_url(
            "https://l.facebook.com/l.php?h=x") == "l.facebook.com"
        assert core.domain_from_url(
            "https://www.facebook.com/dialog/feed?a=1") == "www.facebook.com"
        assert core.domain_from_url(
            "https://www.facebook.com/plugins/like.php") == "www.facebook.com"
        # old-format page (name/id) captured whole
        assert core.domain_from_url(
            "https://www.facebook.com/pages/RT-France/153671") == \
            "facebook.com/pages/rt-france/153671"
        # category-format page: full path captured, alias normalises the
        # subdomain so www./fr-fr. collapse to the same entity
        assert core.domain_from_url(
            "https://www.facebook.com/pages/category/Cause/Gilets-Toulouse-218") == \
            "facebook.com/pages/category/cause/gilets-toulouse-218"
        assert core.domain_from_url(
            "https://fr-fr.facebook.com/pages/category/Cause/Gilets-Toulouse-218") == \
            "facebook.com/pages/category/cause/gilets-toulouse-218"
        # bare /pages hub -> netloc
        assert core.domain_from_url(
            "https://www.facebook.com/pages") == "www.facebook.com"
        # real page containing a reserved substring is NOT blocked
        assert core.domain_from_url(
            "https://www.facebook.com/dialogue-2-sourds-112") == \
            "facebook.com/dialogue-2-sourds-112"

    def test_anchored_blocklist_blocks_word_dot_extension(self, fresh_db, monkeypatch):
        """A reserved word anchored with [/.?] blocks 'subscribe.php' but leaves
        a longer handle ('subscriber') intact."""
        core = fresh_db["core"]
        tbl = {"netvibes.com": {
            "url": r"(netvibes\.com/(?!(?:subscribe)(?:[/.?]|$))"
                   r"[a-zA-Z0-9%\.\-_]+)", "html": None}}
        _patch_table(monkeypatch, core, tbl)
        assert core.domain_from_url(
            "https://www.netvibes.com/subscribe.php?u=x") == "www.netvibes.com"
        assert core.domain_from_url(
            "https://www.netvibes.com/subscriber") == "netvibes.com/subscriber"

    def test_unwraps_archive(self, fresh_db, monkeypatch):
        core = fresh_db["core"]
        _patch_table(monkeypatch, core)
        assert core.domain_from_url(
            "https://web.archive.org/web/2020/https://example.com/x") == "example.com"


class TestEntityNormalization:
    """alias (twitter->x) + lower (case-insensitive handles), youtube preserved."""

    NTABLE = {
        "twitter.com": {"url": r"(twitter\.com/(?!intent(?:[/?]|$))[A-Za-z0-9_]+)",
                        "html": "canonical", "alias": "x.com", "lower": True},
        "x.com": {"url": r"(x\.com/(?!intent(?:[/?]|$))[A-Za-z0-9_]+)",
                  "html": "canonical", "alias": "x.com", "lower": True},
        "youtube.com": {"url": r"(youtube\.com/channel/UC[\w-]+)",
                        "html": "ldjson_author"},
    }

    def test_alias_and_lower_unify_twitter_x(self, fresh_db, monkeypatch):
        core = fresh_db["core"]
        monkeypatch.setattr(core.settings, "platform_heuristics", self.NTABLE,
                            raising=False)
        for u in ("https://twitter.com/JLMelenchon/status/1",
                  "https://www.twitter.com/JLMelenchon",
                  "https://x.com/JLMelenchon",
                  "https://twitter.com/jlmelenchon/status/2"):
            assert core.domain_from_url(u) == "x.com/jlmelenchon"

    def test_percent_encoded_slug_captured_and_decoded(self, fresh_db, monkeypatch):
        """An accented slug (s%C3%A9bastien) is captured whole then URL-decoded,
        not truncated at the '%'."""
        core = fresh_db["core"]
        table = {"linkedin.com": {
            "url": r"([a-z0-9\-_]+\.linkedin\.com/in/[a-zA-Z0-9%\.\-_]+)",
            "html": None}}
        monkeypatch.setattr(core.settings, "platform_heuristics", table,
                            raising=False)
        assert core.domain_from_url(
            "https://fr.linkedin.com/in/s%C3%A9bastien-melenchon-7a0186a") == \
            "fr.linkedin.com/in/sébastien-melenchon-7a0186a"

    def test_lower_not_applied_to_case_sensitive_ids(self, fresh_db, monkeypatch):
        core = fresh_db["core"]
        monkeypatch.setattr(core.settings, "platform_heuristics", self.NTABLE,
                            raising=False)
        assert core.domain_from_url(
            "https://www.youtube.com/channel/UCkAbc123") == "youtube.com/channel/UCkAbc123"

    def test_prefix_unifies_two_url_forms(self, fresh_db, monkeypatch):
        """prefix rebuilds host/<author> from an author-only capture (two forms)."""
        core = fresh_db["core"]
        rx = (r"blogs\.mediapart\.fr/(?:blog/)?"
              r"(?!(?:edition|sitemap)(?:/|$))([a-zA-Z0-9._-]+)")
        table = {"blogs.mediapart.fr": {
            "url": rx, "html": "rel_author", "prefix": "blogs.mediapart.fr/"}}
        monkeypatch.setattr(core.settings, "platform_heuristics", table,
                            raising=False)
        # new form /<author>/blog/ and legacy /blog/<author>/ both -> author
        assert core.domain_from_url(
            "https://blogs.mediapart.fr/raar/blog/040624/x") == \
            "blogs.mediapart.fr/raar"
        assert core.domain_from_url(
            "http://blogs.mediapart.fr/blog/edwy-plenel/240708/x") == \
            "blogs.mediapart.fr/edwy-plenel"
        assert core.domain_from_url(
            "https://blogs.mediapart.fr/edition/les-invites/x") == "blogs.mediapart.fr"


class TestIsOpaque:
    @pytest.mark.parametrize("url,expected", [
        ("https://www.youtube.com/watch?v=1", True),
        ("https://youtube.com/watch?v=1", True),
        ("https://m.youtube.com/watch?v=1", True),
        ("https://mediapart.fr/journal/x", True),
        ("https://example.com/x", False),
        ("https://notyoutube.com/x", False),
        ("https://youtube.com.evil.test/x", False),
    ])
    def test_membership(self, fresh_db, monkeypatch, url, expected):
        core = fresh_db["core"]
        _patch_table(monkeypatch, core)
        assert core._is_opaque(url) is expected


class TestSignalExtraction:
    def test_ldjson_author(self, fresh_db):
        core = fresh_db["core"]
        assert core.editorial_url_from_html(YT_HTML, "https://www.youtube.com/watch?v=1",
                                            "ldjson_author") == \
            "https://www.youtube.com/@franceinfo"

    def test_canonical(self, fresh_db):
        core = fresh_db["core"]
        assert core.editorial_url_from_html(CANONICAL_HTML, "https://x.test/", "canonical") == \
            "https://realblog.example/post"

    def test_og_url(self, fresh_db):
        core = fresh_db["core"]
        assert core.editorial_url_from_html(OG_HTML, "https://x.test/", "og_url") == \
            "https://realblog.example/from-og"

    def test_rel_author(self, fresh_db):
        core = fresh_db["core"]
        got = core.editorial_url_from_html(REL_AUTHOR_HTML, "https://blog.test/p",
                                           "rel_author")
        assert got == "https://blog.test/author/jane"

    def test_ldjson_publisher(self, fresh_db):
        core = fresh_db["core"]
        got = core.editorial_url_from_html(PUBLISHER_HTML, "https://x.test/",
                                           "ldjson_publisher")
        assert got == "https://pub.example/"

    def test_itemprop_author(self, fresh_db):
        core = fresh_db["core"]
        got = core.editorial_url_from_html(
            ITEMPROP_AUTHOR_HTML, "https://www.youtube.com/watch?v=1",
            "itemprop_author")
        assert got == "https://www.youtube.com/@JLMelenchon"

    def test_dailymotion_channel(self, fresh_db):
        core = fresh_db["core"]
        got = core.editorial_url_from_html(
            DM_HTML, "https://www.dailymotion.com/video/x1",
            "dailymotion_channel")
        assert got == "https://www.dailymotion.com/Europe1fr"

    def test_dailymotion_channel_absent_returns_none(self, fresh_db):
        core = fresh_db["core"]
        got = core.editorial_url_from_html(
            NO_SIGNAL_HTML, "https://www.dailymotion.com/video/x1",
            "dailymotion_channel")
        assert got is None

    def test_unknown_signal_falls_back_canonical(self, fresh_db):
        core = fresh_db["core"]
        got = core.editorial_url_from_html(CANONICAL_HTML, "https://x.test/",
                                           "citation_author")
        assert got == "https://realblog.example/post"

    def test_signal_no_match_returns_none(self, fresh_db):
        core = fresh_db["core"]
        got = core.editorial_url_from_html(NO_SIGNAL_HTML, "https://x.test/",
                                           "ldjson_author")
        assert got is None

    def test_empty_html_none(self, fresh_db):
        core = fresh_db["core"]
        assert core.editorial_url_from_html("", "https://x.test/", "canonical") is None


class TestDomainFromHtml:
    def test_youtube_ldjson_author_to_channel(self, fresh_db, monkeypatch):
        core = fresh_db["core"]
        _patch_table(monkeypatch, core)
        got = core.domain_from_html("https://www.youtube.com/watch?v=1", YT_HTML)
        assert got == "youtube.com/@franceinfo"

    def test_youtube_itemprop_author_to_channel(self, fresh_db, monkeypatch):
        core = fresh_db["core"]
        table = {"youtube.com": {
            "url": r"([a-z0-9\-_]*\.?youtube\.com/@[a-zA-Z0-9%\.\-_]+)",
            "html": "itemprop_author"}}
        _patch_table(monkeypatch, core, table)
        got = core.domain_from_html("https://www.youtube.com/watch?v=1",
                                    ITEMPROP_AUTHOR_HTML)
        assert got == "www.youtube.com/@JLMelenchon"

    def test_dailymotion_channel_from_state_json(self, fresh_db, monkeypatch):
        core = fresh_db["core"]
        table = {"dailymotion.com": {
            "url": r"([a-z0-9\-_]+\.dailymotion\.com/(?!(?:video))"
                   r"[a-zA-Z0-9%\.\-_]+)",
            "html": "dailymotion_channel"}}
        _patch_table(monkeypatch, core, table)
        got = core.domain_from_html(
            "https://www.dailymotion.com/video/x9h0wvk", DM_HTML)
        assert got == "www.dailymotion.com/Europe1fr"

    def test_unlisted_host_returns_none(self, fresh_db, monkeypatch):
        core = fresh_db["core"]
        _patch_table(monkeypatch, core)
        assert core.domain_from_html("https://example.com/x", CANONICAL_HTML) is None

    def test_signal_absent_returns_none(self, fresh_db, monkeypatch):
        core = fresh_db["core"]
        _patch_table(monkeypatch, core)
        assert core.domain_from_html("https://www.youtube.com/watch?v=1", NO_SIGNAL_HTML) is None


class TestResolveDomain:
    def _expr(self, m, url, html=None, domain_name="seed.test"):
        d = m.Domain.create(name=domain_name)
        land = m.Land.get_or_none(m.Land.name == "rd") or \
            m.Land.create(name="rd", description="d", lang="fr")
        return m.Expression.create(land=land, domain=d, url=url, html=html)

    def test_unlisted_ignores_html(self, fresh_db, monkeypatch):
        core, m = fresh_db["core"], fresh_db["model"]
        _patch_table(monkeypatch, core)
        expr = self._expr(m, "https://example.com/a", html=YT_HTML)
        assert core.resolve_domain(expr) == "example.com"

    def test_listed_uses_db_html(self, fresh_db, monkeypatch):
        core, m = fresh_db["core"], fresh_db["model"]
        _patch_table(monkeypatch, core)
        expr = self._expr(m, "https://www.youtube.com/watch?v=1", html=YT_HTML)
        assert core.resolve_domain(expr) == "youtube.com/@franceinfo"

    def test_listed_no_html_falls_back_url(self, fresh_db, monkeypatch):
        core, m = fresh_db["core"], fresh_db["model"]
        _patch_table(monkeypatch, core)
        expr = self._expr(m, "https://www.youtube.com/watch?v=1", html=None)
        assert core.resolve_domain(expr) == "www.youtube.com"

    def test_html_param_override(self, fresh_db, monkeypatch):
        core, m = fresh_db["core"], fresh_db["model"]
        _patch_table(monkeypatch, core)
        expr = self._expr(m, "https://www.youtube.com/watch?v=1", html=None)
        assert core.resolve_domain(expr, html=YT_HTML) == "youtube.com/@franceinfo"


class TestUpdateHeuristic:
    def _land(self, m):
        return m.Land.create(name="uh", description="d", lang="fr")

    def test_only_listed_skips_unlisted(self, fresh_db, monkeypatch):
        core, m = fresh_db["core"], fresh_db["model"]
        _patch_table(monkeypatch, core)
        land = self._land(m)
        d = m.Domain.create(name="la-croix.com/France")  # garbage on unlisted host
        e = m.Expression.create(land=land, domain=d,
                                url="https://www.la-croix.com/France/x")
        updated = core.update_heuristic(land)  # only_listed=True default
        assert updated == 0
        assert m.Expression.get_by_id(e.id).domain.name == "la-croix.com/France"

    def test_full_recompute_fixes_unlisted_garbage(self, fresh_db, monkeypatch):
        core, m = fresh_db["core"], fresh_db["model"]
        _patch_table(monkeypatch, core)
        land = self._land(m)
        d = m.Domain.create(name="la-croix.com/France")
        e = m.Expression.create(land=land, domain=d,
                                url="https://www.la-croix.com/France/x")
        updated = core.update_heuristic(land, only_listed=False)
        assert updated == 1
        assert m.Expression.get_by_id(e.id).domain.name == "www.la-croix.com"

    def test_listed_reassigned_via_url(self, fresh_db, monkeypatch):
        core, m = fresh_db["core"], fresh_db["model"]
        _patch_table(monkeypatch, core)
        land = self._land(m)
        d = m.Domain.create(name="www.youtube.com")
        e = m.Expression.create(land=land, domain=d,
                                url="https://www.youtube.com/@franceinfo/videos")
        updated = core.update_heuristic(land)
        assert updated == 1
        assert m.Expression.get_by_id(e.id).domain.name == "youtube.com/@franceinfo"

    def test_reassigns_two_channels_via_html(self, fresh_db, monkeypatch):
        core, m = fresh_db["core"], fresh_db["model"]
        _patch_table(monkeypatch, core)
        land = self._land(m)
        d = m.Domain.create(name="www.youtube.com")
        e1 = m.Expression.create(land=land, domain=d,
                                 url="https://www.youtube.com/watch?v=1", html=YT_HTML)
        e2 = m.Expression.create(land=land, domain=d,
                                 url="https://www.youtube.com/watch?v=2", html=YT_HTML_B)
        updated = core.update_heuristic(land, use_html=True)
        assert updated == 2
        n1 = m.Expression.get_by_id(e1.id).domain.name
        n2 = m.Expression.get_by_id(e2.id).domain.name
        assert {n1, n2} == {"youtube.com/@franceinfo", "youtube.com/@mediapart"}

    def test_dry_run_writes_nothing(self, fresh_db, monkeypatch):
        core, m = fresh_db["core"], fresh_db["model"]
        _patch_table(monkeypatch, core)
        land = self._land(m)
        d = m.Domain.create(name="www.youtube.com")
        e = m.Expression.create(land=land, domain=d,
                                url="https://www.youtube.com/@franceinfo/x")
        would = core.update_heuristic(land, dry_run=True)
        assert would == 1
        assert m.Expression.get_by_id(e.id).domain.name == "www.youtube.com"  # unchanged


class TestFetchMissingOpaqueHtml:
    def test_selects_listed_null_only(self, fresh_db, monkeypatch):
        core, m = fresh_db["core"], fresh_db["model"]
        _patch_table(monkeypatch, core)
        land = m.Land.create(name="fm", description="d", lang="fr")
        dy = m.Domain.create(name="www.youtube.com")
        de = m.Domain.create(name="example.com")
        yt = m.Expression.create(land=land, domain=dy,
                                 url="https://www.youtube.com/watch?v=1", html=None)
        m.Expression.create(land=land, domain=de,
                            url="https://example.com/a", html=None)  # unlisted
        m.Expression.create(land=land, domain=dy,
                            url="https://www.youtube.com/watch?v=2", html="<x/>")  # has html

        async def fake_fetch(url, session=None, **kw):
            return FetchResult(url=url, status_code="200", html="<html/>",
                               method_used="aiohttp")

        monkeypatch.setattr(core, "fetch_html", fake_fetch)
        result = _run(core.fetch_missing_opaque_html(land, limit=10))
        assert list(result.keys()) == [str(yt.url)]

    def test_limit_caps(self, fresh_db, monkeypatch):
        core, m = fresh_db["core"], fresh_db["model"]
        _patch_table(monkeypatch, core)
        land = m.Land.create(name="fm2", description="d", lang="fr")
        dy = m.Domain.create(name="www.youtube.com")
        for i in range(5):
            m.Expression.create(land=land, domain=dy,
                                url=f"https://www.youtube.com/watch?v={i}", html=None)

        async def fake_fetch(url, session=None, **kw):
            return FetchResult(url=url, status_code="200", html="<x/>",
                               method_used="aiohttp")

        monkeypatch.setattr(core, "fetch_html", fake_fetch)
        assert len(_run(core.fetch_missing_opaque_html(land, limit=2))) == 2

    def test_skips_subdomain_html_none_hosts(self, fresh_db, monkeypatch):
        """Subdomain hosts (html=None) are never fetched — netloc resolves them."""
        core, m = fresh_db["core"], fresh_db["model"]
        table = {"blogspot.com": {"url": None, "html": None},
                 "youtube.com": {"url": None, "html": "ldjson_author"}}
        monkeypatch.setattr(core.settings, "platform_heuristics", table,
                            raising=False)
        land = m.Land.create(name="fm3", description="d", lang="fr")
        db = m.Domain.create(name="x.blogspot.com")
        dy = m.Domain.create(name="www.youtube.com")
        m.Expression.create(land=land, domain=db,
                            url="https://x.blogspot.com/2024/a", html=None)
        yt = m.Expression.create(land=land, domain=dy,
                                 url="https://www.youtube.com/watch?v=1", html=None)

        async def fake_fetch(url, session=None, **kw):
            return FetchResult(url=url, status_code="200", html="<html/>",
                               method_used="aiohttp")

        monkeypatch.setattr(core, "fetch_html", fake_fetch)
        result = _run(core.fetch_missing_opaque_html(land))
        assert list(result.keys()) == [str(yt.url)]  # blogspot skipped

    def test_url_resolved_host_not_fetched(self, fresh_db, monkeypatch):
        """A host with BOTH a url rule and an html signal is fetched ONLY for
        URLs the url rule did not resolve (entity not already in the URL)."""
        core, m = fresh_db["core"], fresh_db["model"]
        _patch_table(monkeypatch, core)  # youtube: url=@regex, html=ldjson_author
        land = m.Land.create(name="fm4", description="d", lang="fr")
        d = m.Domain.create(name="www.youtube.com")
        m.Expression.create(land=land, domain=d,  # @handle captured -> skip fetch
                            url="https://www.youtube.com/@franceinfo/videos", html=None)
        watch = m.Expression.create(land=land, domain=d,  # watch unresolved -> fetch
                                    url="https://www.youtube.com/watch?v=1", html=None)

        async def fake_fetch(url, session=None, **kw):
            return FetchResult(url=url, status_code="200", html="<x/>",
                               method_used="aiohttp")

        monkeypatch.setattr(core, "fetch_html", fake_fetch)
        result = _run(core.fetch_missing_opaque_html(land))
        assert list(result.keys()) == [str(watch.url)]

    def test_html_none_host_never_uses_html(self, fresh_db, monkeypatch):
        core, m = fresh_db["core"], fresh_db["model"]
        table = {"blogspot.com": {"url": None, "html": None}}
        monkeypatch.setattr(core.settings, "platform_heuristics", table,
                            raising=False)
        land = m.Land.create(name="hn", description="d", lang="fr")
        d = m.Domain.create(name="s.test")
        # html present, but html=None host -> netloc, HTML ignored
        expr = m.Expression.create(
            land=land, domain=d, url="https://user.blogspot.com/2024/a",
            html='<html><link rel="canonical" href="https://other.test/"></html>')
        assert core.resolve_domain(expr) == "user.blogspot.com"


class TestHeuristicUpdateController:
    def test_default_returns_1(self, fresh_db):
        controller, core = fresh_db["controller"], fresh_db["core"]
        assert controller.HeuristicController.update(core.Namespace()) == 1

    def test_unknown_land_returns_0(self, fresh_db):
        controller, core = fresh_db["controller"], fresh_db["core"]
        assert controller.HeuristicController.update(
            core.Namespace(land="nope_xyz")) == 0

    def test_fetch_missing_without_html_returns_0(self, fresh_db):
        controller, core = fresh_db["controller"], fresh_db["core"]
        assert controller.HeuristicController.update(
            core.Namespace(fetch_missing=True, limit=5)) == 0

    def test_fetch_missing_without_limit_returns_0(self, fresh_db):
        controller, core = fresh_db["controller"], fresh_db["core"]
        assert controller.HeuristicController.update(
            core.Namespace(html=True, fetch_missing=True)) == 0

    def test_dry_run_does_not_fetch(self, fresh_db, monkeypatch):
        controller, core = fresh_db["controller"], fresh_db["core"]
        calls = {"n": 0}

        async def spy(land, limit, minrel=None):
            calls["n"] += 1
            return {}

        monkeypatch.setattr(controller.core, "fetch_missing_opaque_html", spy)
        ret = controller.HeuristicController.update(
            core.Namespace(html=True, fetch_missing=True, limit=5, dry_run=True))
        assert ret == 1 and calls["n"] == 0

    def test_fetch_missing_calls_fetch(self, fresh_db, monkeypatch):
        controller, core = fresh_db["controller"], fresh_db["core"]
        calls = {"n": 0}

        async def spy(land, limit, minrel=None):
            calls["n"] += 1
            return {}

        monkeypatch.setattr(controller.core, "fetch_missing_opaque_html", spy)
        ret = controller.HeuristicController.update(
            core.Namespace(html=True, fetch_missing=True, limit=5))
        assert ret == 1 and calls["n"] == 1
