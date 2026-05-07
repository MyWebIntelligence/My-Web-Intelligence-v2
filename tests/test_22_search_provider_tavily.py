"""Tavily provider unit tests."""

from __future__ import annotations

import re

import aiohttp
import pytest
from aioresponses import aioresponses

from mwi.search.models import ProviderStatus
from mwi.search.providers.tavily import TavilyProvider


_PATTERN = re.compile(r"https://api\.tavily\.com/.*")


@pytest.mark.asyncio
async def test_search_success():
    payload = {"results": [
        {"url": "https://a.com/1", "title": "T1", "content": "S1"},
        {"url": "https://b.com/2", "title": "T2", "content": "S2"},
    ]}
    p = TavilyProvider(api_key="abc")
    with aioresponses() as m:
        m.post(_PATTERN, status=200, payload=payload)
        async with aiohttp.ClientSession() as s:
            results = await p.search(s, "q", num=10)
    assert [r.url for r in results] == ["https://a.com/1", "https://b.com/2"]
    assert results[0].providers == "tavily"


@pytest.mark.asyncio
async def test_missing_key():
    p = TavilyProvider(api_key=None)
    assert p.is_configured() is False
    async with aiohttp.ClientSession() as s:
        assert await p.search(s, "q") == []


@pytest.mark.asyncio
async def test_quota_exceeded():
    p = TavilyProvider(api_key="abc")
    with aioresponses() as m:
        m.post(_PATTERN, status=429)
        async with aiohttp.ClientSession() as s:
            assert await p.search(s, "q") == []
    assert p.last_status == ProviderStatus.QUOTA_EXCEEDED


@pytest.mark.asyncio
async def test_network_error():
    p = TavilyProvider(api_key="abc")
    with aioresponses() as m:
        m.post(_PATTERN, exception=aiohttp.ClientConnectionError("boom"))
        async with aiohttp.ClientSession() as s:
            assert await p.search(s, "q") == []
    assert p.last_status == ProviderStatus.ERROR


@pytest.mark.asyncio
async def test_empty_response():
    p = TavilyProvider(api_key="abc")
    with aioresponses() as m:
        m.post(_PATTERN, status=200, payload={"results": []})
        async with aiohttp.ClientSession() as s:
            assert await p.search(s, "q") == []
    assert p.last_status == ProviderStatus.OK
    assert p.calls_made == 1
