"""Unit tests for the fetch pipeline (mwi.fetcher).

Sprint-cloudflare Sprint 1 — locks the refactored fetch behavior so
upcoming strategies (curl_cffi, Playwright HTML) can plug in without
regressing the baseline.
"""

import asyncio
from unittest.mock import patch

import aiohttp
import pytest

from mwi.fetcher import (
    AiohttpStrategy,
    ArchiveOrgStrategy,
    FetchResult,
    _ArchiveOrgBreaker,
    fetch_html,
)


def run(coro):
    """Tiny helper since the project does not use pytest-asyncio."""
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Mock helpers
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


class _MockSession:
    """Minimal aiohttp.ClientSession stand-in."""

    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc

    def get(self, url, **kwargs):
        if self._exc is not None:
            raise self._exc
        return self._response


# ---------------------------------------------------------------------------
# FetchResult dataclass
# ---------------------------------------------------------------------------

class TestFetchResult:
    def test_minimal_construction(self):
        r = FetchResult(url='https://x.test', status_code='200',
                        html='<html/>', method_used='aiohttp')
        assert r.error is None
        assert r.html == '<html/>'

    def test_error_field_optional(self):
        r = FetchResult(url='u', status_code='000', html=None,
                        method_used='aiohttp', error='boom')
        assert r.error == 'boom'


# ---------------------------------------------------------------------------
# AiohttpStrategy
# ---------------------------------------------------------------------------

class TestAiohttpStrategy:
    def test_success_returns_html(self):
        session = _MockSession(_MockResponse(200, 'text/html; charset=utf-8',
                                             '<html><body>ok</body></html>'))
        result = run(AiohttpStrategy(session).fetch('https://ok.test'))
        assert result.status_code == '200'
        assert result.html == '<html><body>ok</body></html>'
        assert result.method_used == 'aiohttp'
        assert result.error is None

    def test_non_html_content_type_yields_no_html(self):
        session = _MockSession(_MockResponse(200, 'application/pdf', ''))
        result = run(AiohttpStrategy(session).fetch('https://pdf.test'))
        assert result.status_code == '200'
        assert result.html is None

    def test_403_preserves_status(self):
        session = _MockSession(_MockResponse(403, 'text/html', ''))
        result = run(AiohttpStrategy(session).fetch('https://forbidden.test'))
        assert result.status_code == '403'
        assert result.html is None
        assert result.method_used == 'aiohttp'

    def test_client_error_yields_000(self):
        session = _MockSession(exc=aiohttp.ClientError('connection refused'))
        result = run(AiohttpStrategy(session).fetch('https://dead.test'))
        assert result.status_code == '000'
        assert result.html is None
        assert result.error and 'connection refused' in result.error

    def test_unknown_exception_yields_err(self):
        session = _MockSession(exc=RuntimeError('weird'))
        result = run(AiohttpStrategy(session).fetch('https://broken.test'))
        assert result.status_code == 'ERR'
        assert result.html is None
        assert result.error == 'weird'


# ---------------------------------------------------------------------------
# ArchiveOrgStrategy (no real network)
# ---------------------------------------------------------------------------

class TestArchiveOrgStrategy:
    def setup_method(self):
        _ArchiveOrgBreaker.reset()

    def test_skips_archive_wrapper_input(self):
        url = 'https://web.archive.org/web/2020/https://example.com/'
        result = run(ArchiveOrgStrategy().fetch(url))
        assert result is None

    def test_skips_when_breaker_open(self):
        for _ in range(_ArchiveOrgBreaker.OPEN_THRESHOLD):
            _ArchiveOrgBreaker.record_failure()
        result = run(ArchiveOrgStrategy().fetch('https://x.test'))
        assert result is None

    def test_returns_html_when_snapshot_available(self):
        # Mock both: requests.get for /wayback/available, trafilatura.fetch_url for snapshot
        snapshot_url = 'https://web.archive.org/web/20210101000000/https://x.test/'
        snapshot_html = '<html><body>archived</body></html>'

        class _MockArchiveResp:
            def raise_for_status(self):
                return None

            def json(self):
                return {'archived_snapshots': {'closest': {'url': snapshot_url}}}

        with patch('mwi.fetcher.requests.get', return_value=_MockArchiveResp()):
            with patch('trafilatura.fetch_url', return_value=snapshot_html):
                result = run(ArchiveOrgStrategy().fetch('https://x.test'))
        assert result is not None
        assert result.html == snapshot_html
        assert result.method_used == 'archive_org'
        assert _ArchiveOrgBreaker.failures == 0  # success closes


# ---------------------------------------------------------------------------
# fetch_html orchestrator
# ---------------------------------------------------------------------------

class TestFetchHtmlOrchestrator:
    def setup_method(self):
        _ArchiveOrgBreaker.reset()

    def test_aiohttp_success_short_circuits(self):
        session = _MockSession(_MockResponse(200, 'text/html',
                                             '<html>live</html>'))
        result = run(fetch_html('https://live.test', session=session))
        assert result.status_code == '200'
        assert result.html == '<html>live</html>'
        assert result.method_used == 'aiohttp'

    def test_403_then_archive_preserves_status_code(self):
        """When the live URL is forbidden but archive.org rescues us, the
        recorded status_code must still be '403' so the corpus reflects
        reality. The HTML comes from the archive, method_used reports it.
        """
        session = _MockSession(_MockResponse(403, 'text/html', ''))

        snapshot_url = 'https://web.archive.org/web/2020/https://forb.test/'
        snapshot_html = '<html>archived</html>'

        class _MockArchiveResp:
            def raise_for_status(self):
                return None

            def json(self):
                return {'archived_snapshots': {'closest': {'url': snapshot_url}}}

        with patch('mwi.fetcher.requests.get', return_value=_MockArchiveResp()):
            with patch('trafilatura.fetch_url', return_value=snapshot_html):
                result = run(fetch_html('https://forb.test', session=session))
        assert result.status_code == '403'           # original status preserved
        assert result.html == snapshot_html          # archive's HTML
        assert result.method_used == 'archive_org'   # who provided the body

    def test_all_fail_returns_first_result(self):
        """When no strategy yields HTML, the orchestrator returns the
        first attempt's result (its status_code is the most truthful)."""
        session = _MockSession(_MockResponse(404, 'text/html', ''))
        # archive returns no snapshot
        with patch('mwi.fetcher.requests.get') as mocked_get:
            mocked_get.return_value.raise_for_status = lambda: None
            mocked_get.return_value.json = lambda: {'archived_snapshots': {}}
            result = run(fetch_html('https://gone.test', session=session))
        assert result.status_code == '404'
        assert result.html is None
        assert result.method_used == 'aiohttp'
