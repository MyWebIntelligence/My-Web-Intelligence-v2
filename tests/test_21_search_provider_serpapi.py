"""SerpAPI provider unit tests."""

from __future__ import annotations

import re

import aiohttp
import pytest
from aioresponses import aioresponses

from mwi.search.models import ProviderStatus
from mwi.search.providers.serpapi import SerpApiProvider


_PATTERN = re.compile(r"https://serpapi\.com/.*")


@pytest.mark.asyncio
async def test_search_success():
    payload = {"organic_results": [
        {"link": "https://a.com/1", "title": "T1", "snippet": "S1", "position": 1},
        {"link": "https://b.com/2", "title": "T2", "snippet": "S2", "position": 2},
    ]}
    p = SerpApiProvider(api_key="abc")
    with aioresponses() as m:
        m.get(_PATTERN, status=200, payload=payload)
        async with aiohttp.ClientSession() as s:
            results = await p.search(s, "q", num=10)
    assert len(results) == 2
    assert results[0].providers == "serpapi"
    assert p.last_status == ProviderStatus.OK


@pytest.mark.asyncio
async def test_missing_key(monkeypatch):
    """When no env var, no UPPER attr, no legacy attr — provider is unconfigured."""
    import settings as _settings
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    monkeypatch.delattr(_settings, "SERPAPI_API_KEY", raising=False)
    monkeypatch.setattr(_settings, "serpapi_api_key", None, raising=False)
    # Pass empty string explicitly so the constructor short-circuits resolve.
    p = SerpApiProvider(api_key="")
    assert p.is_configured() is False


@pytest.mark.asyncio
async def test_quota_exceeded_429():
    p = SerpApiProvider(api_key="abc")
    with aioresponses() as m:
        m.get(_PATTERN, status=429)
        async with aiohttp.ClientSession() as s:
            assert await p.search(s, "q") == []
    assert p.last_status == ProviderStatus.QUOTA_EXCEEDED


@pytest.mark.asyncio
async def test_quota_message_in_payload():
    """SerpAPI sometimes returns 200 with an error string when monthly limit hit."""
    p = SerpApiProvider(api_key="abc")
    with aioresponses() as m:
        m.get(_PATTERN, status=200, payload={
            "error": "You have run out of monthly searches",
        })
        async with aiohttp.ClientSession() as s:
            assert await p.search(s, "q") == []
    assert p.last_status == ProviderStatus.QUOTA_EXCEEDED


@pytest.mark.asyncio
async def test_network_error():
    p = SerpApiProvider(api_key="abc")
    with aioresponses() as m:
        m.get(_PATTERN, exception=aiohttp.ClientConnectionError("boom"))
        async with aiohttp.ClientSession() as s:
            assert await p.search(s, "q") == []
    assert p.last_status == ProviderStatus.ERROR


@pytest.mark.asyncio
async def test_empty_response():
    p = SerpApiProvider(api_key="abc")
    with aioresponses() as m:
        m.get(_PATTERN, status=200, payload={"organic_results": []})
        async with aiohttp.ClientSession() as s:
            assert await p.search(s, "q") == []
    assert p.last_status == ProviderStatus.OK


def test_falls_back_to_legacy_snake_case_key(monkeypatch):
    """When neither env nor SERPAPI_API_KEY are set, settings.serpapi_api_key wins."""
    import settings as _settings
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    # Ensure UPPER attr is missing so the legacy fallback fires.
    if hasattr(_settings, "SERPAPI_API_KEY"):
        monkeypatch.delattr(_settings, "SERPAPI_API_KEY", raising=False)
    monkeypatch.setattr(_settings, "serpapi_api_key", "legacy-key", raising=False)
    p = SerpApiProvider()
    assert p.api_key == "legacy-key"
