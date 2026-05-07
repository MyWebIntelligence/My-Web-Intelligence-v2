"""Unit tests for the Playwright HTML fallback (sprint-403, Sprint 3).

The real Chromium isn't launched — every test injects a fake
:class:`BrowserPool` whose ``page()`` context manager yields a stub
page. This keeps the suite fast and offline. A live integration test
exists at the bottom, skipped by default.
"""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import patch

import aiohttp
import pytest

from mwi.fetcher import (
    AiohttpStrategy,
    ArchiveOrgStrategy,
    CurlCffiStrategy,
    FetchResult,
    PlaywrightStrategy,
    _ArchiveOrgBreaker,
    default_chain,
    fetch_html,
)


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, status):
        self.status = status


class _FakePage:
    """Minimal stub of playwright.async_api.Page used by PlaywrightStrategy."""

    def __init__(self, response_status=200, content_html='<html>ok</html>',
                 cf_marker_then_resolved=False, raise_on_goto=None):
        self._response = _FakeResponse(response_status) if response_status is not None else None
        self._html = content_html
        self._cf_dance = cf_marker_then_resolved
        self._goto_call_count = 0
        self._raise_on_goto = raise_on_goto

    async def goto(self, url, **_):
        self._goto_call_count += 1
        if self._raise_on_goto is not None:
            raise self._raise_on_goto
        return self._response

    async def wait_for_load_state(self, *_, **__):
        return None

    async def content(self):
        if self._cf_dance and self._goto_call_count <= 1:
            # First call: serve the CF interstitial. wait_for_function will
            # then "resolve" it.
            return "<html>Just a moment…</html>"
        return self._html

    async def wait_for_function(self, *_, **__):
        # Pretend the challenge resolved.
        self._cf_dance = False
        return None


class _FakePool:
    """Stand-in for BrowserPool: yields a single _FakePage each borrow."""

    def __init__(self, page: _FakePage):
        self._page = page
        self.page_calls = 0

    @asynccontextmanager
    async def page(self):
        self.page_calls += 1
        yield self._page


# ---------------------------------------------------------------------------
# PlaywrightStrategy unit tests
# ---------------------------------------------------------------------------

class TestPlaywrightStrategy:
    def test_marked_as_only_on_retry(self):
        assert PlaywrightStrategy.only_on_retry is True
        assert PlaywrightStrategy.name == "playwright"

    def test_returns_none_when_pool_unavailable(self):
        """If Playwright isn't installed, defer cleanly to the next
        strategy (return None) instead of crashing."""
        s = PlaywrightStrategy(pool=None)
        with patch('mwi.browser_pool.PLAYWRIGHT_AVAILABLE', False):
            result = run(s.fetch('https://x.test'))
        assert result is None

    def test_success_returns_html(self):
        page = _FakePage(response_status=200,
                         content_html='<html><body>js-rendered</body></html>')
        pool = _FakePool(page)
        result = run(PlaywrightStrategy(pool=pool).fetch('https://js.test'))
        assert result.status_code == "200"
        assert result.html == '<html><body>js-rendered</body></html>'
        assert result.method_used == "playwright"
        assert pool.page_calls == 1

    def test_resolves_cloudflare_challenge(self):
        """When the first content() returns the CF interstitial, the
        strategy waits for it to disappear before returning."""
        page = _FakePage(response_status=200,
                         content_html='<html>real content</html>',
                         cf_marker_then_resolved=True)
        pool = _FakePool(page)
        result = run(PlaywrightStrategy(pool=pool).fetch('https://cf.test'))
        assert result.status_code == "200"
        assert "real content" in result.html

    def test_403_status_propagated(self):
        page = _FakePage(response_status=403, content_html='')
        pool = _FakePool(page)
        result = run(PlaywrightStrategy(pool=pool).fetch('https://blocked.test'))
        assert result.status_code == "403"
        assert result.html is None
        assert result.method_used == "playwright"

    def test_navigation_exception_yields_err(self):
        page = _FakePage(raise_on_goto=RuntimeError("net::ERR_TIMED_OUT"))
        pool = _FakePool(page)
        result = run(PlaywrightStrategy(pool=pool).fetch('https://timeout.test'))
        assert result.status_code == "ERR"
        assert result.error and "ERR_TIMED_OUT" in result.error


# ---------------------------------------------------------------------------
# default_chain configuration
# ---------------------------------------------------------------------------

class TestDefaultChainOptIn:
    def test_playwright_off_by_default(self):
        # No setting → off
        async def _build():
            async with aiohttp.ClientSession() as s:
                return default_chain(s)
        chain = run(_build())
        names = [s.name for s in chain]
        assert "playwright" not in names

    def test_playwright_inserted_before_archive_when_enabled(self):
        with patch('mwi.fetcher.settings.crawl_fallback_playwright', True, create=True):
            async def _build():
                async with aiohttp.ClientSession() as s:
                    return default_chain(s)
            chain = run(_build())
        names = [s.name for s in chain]
        # Order matters: aiohttp → curl_cffi → playwright → archive_org
        assert names.index("playwright") < names.index("archive_org")
        assert names.index("playwright") > names.index("curl_cffi")


# ---------------------------------------------------------------------------
# Cascade integration: aiohttp 403 + curl_cffi 403 + playwright 200
# ---------------------------------------------------------------------------

class _MockAiohttpResponse:
    def __init__(self, status, content_type='text/html', text=''):
        self.status = status
        self.headers = {'content-type': content_type}
        self._text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def text(self):
        return self._text


class _MockAioSession:
    def __init__(self, response):
        self._response = response

    def get(self, url, **kwargs):
        return self._response


class _FakeCurlResponse:
    def __init__(self, status_code, text='', content_type='text/html'):
        self.status_code = status_code
        self.text = text
        self.headers = {'content-type': content_type}


class _FakeCurlSession:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def get(self, url, **kwargs):
        return self._response


def _install_fake_curl(fake_session):
    import sys
    import types
    fake_module = types.ModuleType('curl_cffi')
    fake_requests = types.ModuleType('curl_cffi.requests')
    fake_requests.AsyncSession = lambda: fake_session
    fake_module.requests = fake_requests
    return patch.dict(sys.modules, {
        'curl_cffi': fake_module,
        'curl_cffi.requests': fake_requests,
    })


class TestThreeTierCascade:
    def setup_method(self):
        _ArchiveOrgBreaker.reset()

    def test_403_403_then_playwright_rescues(self):
        """aiohttp 403 → curl_cffi still 403 → Playwright 200.

        Final FetchResult must:
          * status_code == "403" (truth from the live URL)
          * html from Playwright
          * method_used == "playwright"
        """
        aio_session = _MockAioSession(_MockAiohttpResponse(403, 'text/html', ''))
        curl_session = _FakeCurlSession(_FakeCurlResponse(403, ''))
        play_page = _FakePage(response_status=200,
                              content_html='<html>browser saved us</html>')
        play_pool = _FakePool(play_page)

        strategies = [
            AiohttpStrategy(aio_session),
            CurlCffiStrategy(),
            PlaywrightStrategy(pool=play_pool),
            ArchiveOrgStrategy(),
        ]
        with _install_fake_curl(curl_session):
            result = run(fetch_html('https://hard-cf.test',
                                    session=aio_session,
                                    strategies=strategies))
        assert result.status_code == "403"
        assert result.html == '<html>browser saved us</html>'
        assert result.method_used == "playwright"

    def test_curl_cffi_succeeds_skips_playwright(self):
        """When curl_cffi already succeeds, Playwright must NOT be
        invoked (cost saving). We assert via the page borrow counter."""
        aio_session = _MockAioSession(_MockAiohttpResponse(403, 'text/html', ''))
        curl_session = _FakeCurlSession(_FakeCurlResponse(
            200, '<html>chrome rescued</html>',
        ))
        play_page = _FakePage(response_status=200,
                              content_html='<html>should not be used</html>')
        play_pool = _FakePool(play_page)

        strategies = [
            AiohttpStrategy(aio_session),
            CurlCffiStrategy(),
            PlaywrightStrategy(pool=play_pool),
            ArchiveOrgStrategy(),
        ]
        with _install_fake_curl(curl_session):
            result = run(fetch_html('https://cf-light.test',
                                    session=aio_session,
                                    strategies=strategies))
        assert result.method_used == "curl_cffi"
        assert play_pool.page_calls == 0  # never borrowed!


# ---------------------------------------------------------------------------
# Live integration (manual sanity check, skipped by default)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(True, reason="live network test, run manually")
class TestPlaywrightLive:
    def test_passes_cultura_dot_com(self):
        """The site that resisted curl_cffi during the Sprint 2 test
        run. Manual check that Playwright unblocks it."""
        from mwi.browser_pool import BrowserPool
        url = 'https://www.cultura.com/p-titre-a-venir-politique-9782221271377.html'
        result = run(PlaywrightStrategy().fetch(url))
        try:
            assert result is not None
            assert result.status_code == "200"
            assert result.html and len(result.html) > 1000
        finally:
            run(BrowserPool.get().shutdown())
