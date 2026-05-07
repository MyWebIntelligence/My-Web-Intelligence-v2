"""Unit tests for the SearXNG provider adapter (J3 of sprint-searchrouter).

Mocks all HTTP via ``aioresponses`` — no real network access.
"""

from __future__ import annotations

import asyncio
import re

import aiohttp
import pytest
from aioresponses import aioresponses

from mwi.search.models import ProviderStatus
from mwi.search.providers.searxng import SearxngProvider
from mwi.search.utils import canonicalize_url, merge_results
from mwi.search.models import SearchResult


# ---------------------------------------------------------------------------
# canonicalize_url
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("HTTPS://Example.COM/Path/", "https://example.com/Path"),
    ("https://example.com/", "https://example.com/"),
    ("https://example.com",  "https://example.com"),
    ("https://example.com/page#frag", "https://example.com/page"),
    ("https://example.com/?a=1&b=2", "https://example.com/?a=1&b=2"),
    ("https://EXAMPLE.com/x?utm_source=foo", "https://example.com/x?utm_source=foo"),
])
def test_canonicalize_url_rules(raw, expected):
    assert canonicalize_url(raw) == expected


def test_canonicalize_url_handles_empty():
    assert canonicalize_url("") == ""
    assert canonicalize_url(None) == ""  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# merge_results
# ---------------------------------------------------------------------------

def test_merge_results_dedups_and_concats_providers():
    a = [SearchResult(url="https://a.com/x", rank=1, providers="searxng")]
    b = [SearchResult(url="https://A.com/x", rank=3, providers="brave")]
    c = [SearchResult(url="https://other.com", rank=2, providers="serper")]
    merged = merge_results([a, b, c])
    by_url = {r.url: r for r in merged}
    # Canonical form is lowercase
    assert "https://a.com/x" in by_url
    assert by_url["https://a.com/x"].providers == "searxng+brave"
    assert by_url["https://a.com/x"].rank == 1  # min of (1, 3)
    # Order: rank 1 then rank 2
    assert merged[0].url == "https://a.com/x"
    assert merged[1].url == "https://other.com"


def test_merge_results_drops_empty_urls():
    batch = [SearchResult(url="", providers="x"), SearchResult(url="https://a", providers="x")]
    merged = merge_results([batch])
    assert len(merged) == 1
    assert merged[0].url == "https://a"


# ---------------------------------------------------------------------------
# SearxngProvider — adapter behaviour
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_searxng_search_success():
    payload = {"results": [
        {"url": "https://a.com/1", "title": "T1", "content": "S1"},
        {"url": "https://b.com/2", "title": "T2", "content": "S2"},
    ]}
    provider = SearxngProvider(base_url="http://test-searxng:8888")
    with aioresponses() as m:
        m.get(re.compile(r"http://test-searxng:8888/search.*"),
              status=200, payload=payload)
        async with aiohttp.ClientSession() as session:
            results = await provider.search(session, "ma requête", num=10, language="fr")

    assert len(results) == 2
    assert results[0].url == "https://a.com/1"
    assert results[0].title == "T1"
    assert results[0].snippet == "S1"
    assert results[0].rank == 1
    assert results[0].providers == "searxng"
    assert provider.last_status == ProviderStatus.OK
    assert provider.calls_made == 1


@pytest.mark.asyncio
async def test_searxng_search_respects_num():
    payload = {"results": [{"url": f"https://x/{i}"} for i in range(50)]}
    provider = SearxngProvider(base_url="http://t:8888")
    with aioresponses() as m:
        m.get(re.compile(r"http://t:8888/search.*"), status=200, payload=payload)
        async with aiohttp.ClientSession() as session:
            results = await provider.search(session, "q", num=5)
    assert len(results) == 5
    assert [r.rank for r in results] == [1, 2, 3, 4, 5]


@pytest.mark.asyncio
async def test_searxng_empty_query_marks_error():
    provider = SearxngProvider(base_url="http://t:8888")
    async with aiohttp.ClientSession() as session:
        results = await provider.search(session, "   ")
    assert results == []
    assert provider.last_status == ProviderStatus.ERROR
    assert provider.errors == 1
    assert provider.calls_made == 0


@pytest.mark.asyncio
async def test_searxng_429_retries_then_succeeds():
    payload = {"results": [{"url": "https://ok"}]}
    provider = SearxngProvider(base_url="http://t:8888")
    with aioresponses() as m:
        m.get(re.compile(r"http://t:8888/search.*"), status=429)
        m.get(re.compile(r"http://t:8888/search.*"), status=200, payload=payload)
        async with aiohttp.ClientSession() as session:
            results = await provider.search(session, "q")
    assert len(results) == 1
    assert provider.last_status == ProviderStatus.OK
    assert provider.calls_made == 1


@pytest.mark.asyncio
async def test_searxng_429_quota_after_retry():
    provider = SearxngProvider(base_url="http://t:8888")
    with aioresponses() as m:
        m.get(re.compile(r"http://t:8888/search.*"), status=429)
        m.get(re.compile(r"http://t:8888/search.*"), status=429)
        async with aiohttp.ClientSession() as session:
            results = await provider.search(session, "q")
    assert results == []
    assert provider.last_status == ProviderStatus.QUOTA_EXCEEDED
    assert provider.errors == 1


@pytest.mark.asyncio
async def test_searxng_5xx_marks_error():
    provider = SearxngProvider(base_url="http://t:8888")
    with aioresponses() as m:
        m.get(re.compile(r"http://t:8888/search.*"), status=503)
        async with aiohttp.ClientSession() as session:
            results = await provider.search(session, "q")
    assert results == []
    assert provider.last_status == ProviderStatus.ERROR


@pytest.mark.asyncio
async def test_searxng_network_error_marks_error():
    provider = SearxngProvider(base_url="http://t:8888")
    with aioresponses() as m:
        m.get(re.compile(r"http://t:8888/search.*"),
              exception=aiohttp.ClientConnectionError("boom"))
        async with aiohttp.ClientSession() as session:
            results = await provider.search(session, "q")
    assert results == []
    assert provider.last_status == ProviderStatus.ERROR
    assert provider.errors == 1


@pytest.mark.asyncio
async def test_searxng_skips_results_without_url():
    payload = {"results": [
        {"title": "no url"},
        {"url": "https://ok", "title": "ok"},
    ]}
    provider = SearxngProvider(base_url="http://t:8888")
    with aioresponses() as m:
        m.get(re.compile(r"http://t:8888/search.*"), status=200, payload=payload)
        async with aiohttp.ClientSession() as session:
            results = await provider.search(session, "q")
    assert [r.url for r in results] == ["https://ok"]


@pytest.mark.asyncio
async def test_searxng_empty_response_returns_empty_list():
    provider = SearxngProvider(base_url="http://t:8888")
    with aioresponses() as m:
        m.get(re.compile(r"http://t:8888/search.*"), status=200, payload={"results": []})
        async with aiohttp.ClientSession() as session:
            results = await provider.search(session, "q")
    assert results == []
    assert provider.last_status == ProviderStatus.OK
    assert provider.calls_made == 1


def test_searxng_resolves_base_url_from_env(monkeypatch):
    monkeypatch.setenv("SEARXNG_BASE_URL", "http://from-env:9000/")
    p = SearxngProvider()
    assert p.base_url == "http://from-env:9000"


def test_searxng_is_configured():
    assert SearxngProvider(base_url="http://x").is_configured() is True


def test_searxng_usage_snapshot():
    p = SearxngProvider(base_url="http://x")
    p.calls_made = 4
    p.errors = 1
    p.last_status = ProviderStatus.ERROR
    snap = p.usage()
    assert snap.name == "searxng"
    assert snap.calls == 4
    assert snap.errors == 1
    assert snap.status == ProviderStatus.ERROR
    assert snap.monthly_quota is None
