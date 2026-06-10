"""Unit tests for the curl_cffi fallback strategy (sprint-403, Sprint 2).

These tests mock ``curl_cffi.requests.AsyncSession`` so the suite stays
fast and offline. A live integration test (skipped by default) is
provided for manual sanity checks.
"""

import asyncio
import sys
import types
from unittest.mock import MagicMock, patch

import aiohttp
import pytest

from mwi.fetcher import (
    AiohttpStrategy,
    ArchiveOrgStrategy,
    CurlCffiStrategy,
    DEFAULT_RETRY_STATUS_CODES,
    FetchResult,
    _ArchiveOrgBreaker,
    fetch_html,
)


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Helpers — fake aiohttp session and curl_cffi session
# ---------------------------------------------------------------------------

class _MockResponse:
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
    """Async context manager mimicking curl_cffi.requests.AsyncSession."""

    def __init__(self, response: _FakeCurlResponse):
        self._response = response
        self.last_kwargs = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def get(self, url, **kwargs):
        self.last_kwargs = kwargs
        return self._response


def _install_fake_curl_module(fake_session):
    """Patch ``curl_cffi.requests.AsyncSession`` for the duration of a test.

    Returns a context manager handle. We register a fake module so that
    ``from curl_cffi.requests import AsyncSession`` inside the strategy
    picks it up.
    """
    fake_module = types.ModuleType('curl_cffi')
    fake_requests = types.ModuleType('curl_cffi.requests')
    fake_requests.AsyncSession = lambda: fake_session  # factory
    fake_module.requests = fake_requests
    return patch.dict(sys.modules, {
        'curl_cffi': fake_module,
        'curl_cffi.requests': fake_requests,
    })


# ---------------------------------------------------------------------------
# CurlCffiStrategy unit tests
# ---------------------------------------------------------------------------

class TestCurlCffiStrategy:
    def test_marked_as_only_on_retry(self):
        assert CurlCffiStrategy.only_on_retry is True
        assert CurlCffiStrategy.name == "curl_cffi"

    def test_success_returns_html(self):
        fake = _FakeCurlSession(_FakeCurlResponse(
            200, '<html><body>chrome saved us</body></html>',
        ))
        with _install_fake_curl_module(fake):
            result = run(CurlCffiStrategy().fetch('https://forb.test/page'))
        assert result.status_code == "200"
        assert result.html == '<html><body>chrome saved us</body></html>'
        assert result.method_used == "curl_cffi"

    def test_passes_impersonate_kwarg(self):
        fake = _FakeCurlSession(_FakeCurlResponse(200, '<html/>'))
        with _install_fake_curl_module(fake):
            run(CurlCffiStrategy(impersonate='safari17_2').fetch('https://x.test'))
        assert fake.last_kwargs['impersonate'] == 'safari17_2'

    def test_non_html_yields_no_html(self):
        fake = _FakeCurlSession(_FakeCurlResponse(
            200, '{"json":true}', content_type='application/json',
        ))
        with _install_fake_curl_module(fake):
            result = run(CurlCffiStrategy().fetch('https://json.test'))
        assert result.status_code == "200"
        assert result.html is None  # not HTML, declined

    def test_403_still_returned(self):
        fake = _FakeCurlSession(_FakeCurlResponse(403, ''))
        with _install_fake_curl_module(fake):
            result = run(CurlCffiStrategy().fetch('https://still-blocked.test'))
        assert result.status_code == "403"
        assert result.html is None
        assert result.method_used == "curl_cffi"

    def test_exception_yields_err(self):
        class _Boom:
            async def __aenter__(self): raise RuntimeError("tls failed")
            async def __aexit__(self, *_): return False

        fake_module = types.ModuleType('curl_cffi')
        fake_requests = types.ModuleType('curl_cffi.requests')
        fake_requests.AsyncSession = lambda: _Boom()
        fake_module.requests = fake_requests
        with patch.dict(sys.modules, {
            'curl_cffi': fake_module,
            'curl_cffi.requests': fake_requests,
        }):
            result = run(CurlCffiStrategy().fetch('https://broken.test'))
        assert result.status_code == "ERR"
        assert "tls failed" in (result.error or "")

    def test_missing_dependency_returns_none(self):
        """If curl_cffi is not installed, the strategy defers cleanly."""
        # Simulate ImportError by removing curl_cffi from sys.modules
        # and inserting a sentinel that raises on attribute access.
        with patch.dict(sys.modules, {'curl_cffi': None,
                                       'curl_cffi.requests': None}):
            result = run(CurlCffiStrategy().fetch('https://x.test'))
        assert result is None  # graceful skip, next strategy gets a turn


# ---------------------------------------------------------------------------
# Cascade integration — fetch_html + curl_cffi
# ---------------------------------------------------------------------------

class TestCascadeWithCurlCffi:
    def setup_method(self):
        _ArchiveOrgBreaker.reset()

    def _live_chain(self, aio_response, curl_response):
        """Build a chain identical to default_chain but with mocked deps."""
        aio_session = _MockAioSession(aio_response)
        # Inject the fake curl session into the strategy at construction
        return aio_session, [
            AiohttpStrategy(aio_session),
            CurlCffiStrategy(),
            ArchiveOrgStrategy(),
        ]

    def test_aiohttp_200_short_circuits_no_curl_call(self):
        aio_session, strategies = self._live_chain(
            _MockResponse(200, 'text/html', '<html>fast</html>'),
            None,
        )
        result = run(fetch_html('https://fast.test',
                                session=aio_session,
                                strategies=strategies))
        assert result.method_used == "aiohttp"
        assert result.html == '<html>fast</html>'

    def test_aiohttp_403_triggers_curl_cffi(self):
        """403 from aiohttp + 200 from curl_cffi → report 200, return curl HTML.
        The signal "primary aiohttp failed" survives via method_used='curl_cffi'.
        """
        aio_session = _MockAioSession(_MockResponse(403, 'text/html', ''))
        fake_curl = _FakeCurlSession(_FakeCurlResponse(
            200, '<html>chrome rescued</html>',
        ))
        strategies = [
            AiohttpStrategy(aio_session),
            CurlCffiStrategy(),
            ArchiveOrgStrategy(),
        ]
        with _install_fake_curl_module(fake_curl):
            result = run(fetch_html('https://forb.test',
                                    session=aio_session,
                                    strategies=strategies))
        assert result.status_code == "200"               # rescue status reported
        assert result.html == '<html>chrome rescued</html>'
        assert result.method_used == "curl_cffi"

    def test_aiohttp_404_skips_curl_cffi(self):
        """404 is not in retry codes → curl_cffi is skipped, archive tried."""
        aio_session = _MockAioSession(_MockResponse(404, 'text/html', ''))
        fake_curl = _FakeCurlSession(_FakeCurlResponse(
            200, '<html>should not see me</html>',
        ))
        # Archive returns no snapshot
        class _NoSnap:
            def raise_for_status(self): return None
            def json(self): return {'archived_snapshots': {}}
        strategies = [
            AiohttpStrategy(aio_session),
            CurlCffiStrategy(),
            ArchiveOrgStrategy(),
        ]
        with _install_fake_curl_module(fake_curl):
            with patch('mwi.fetcher.requests.get', return_value=_NoSnap()):
                result = run(fetch_html('https://gone.test',
                                        session=aio_session,
                                        strategies=strategies))
        assert result.status_code == "404"
        assert result.html is None
        assert result.method_used == "aiohttp"

    def test_default_retry_codes_cover_403_429_err(self):
        for code in ("403", "429", "503", "ERR"):
            assert code in DEFAULT_RETRY_STATUS_CODES
        # 404 is intentionally NOT a retry trigger (real "gone")
        assert "404" not in DEFAULT_RETRY_STATUS_CODES
        # 200/302 are obviously not in there
        assert "200" not in DEFAULT_RETRY_STATUS_CODES


# ---------------------------------------------------------------------------
# Live integration (manual sanity check, skipped by default)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(True, reason="live network test, run manually")
class TestCurlCffiLive:
    def test_passes_real_cloudflare_lesechos(self):
        url = ('https://www.lesechos.fr/politique-societe/politique/'
               'jean-luc-melenchon-ouvre-la-porte-a-sa-succession-1786087')
        result = run(CurlCffiStrategy().fetch(url))
        assert result is not None
        assert result.status_code == "200"
        assert result.html and len(result.html) > 1000
