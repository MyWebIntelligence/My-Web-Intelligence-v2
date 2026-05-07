"""Serper.dev provider unit tests."""

from __future__ import annotations

import re

import aiohttp
import pytest
from aioresponses import aioresponses

from mwi.search.models import ProviderStatus
from mwi.search.providers.serper import SerperProvider


_PATTERN = re.compile(r"https://google\.serper\.dev/.*")


@pytest.mark.asyncio
async def test_search_success():
    payload = {"organic": [
        {"link": "https://a.com/1", "title": "T1", "snippet": "S1", "position": 1},
        {"link": "https://b.com/2", "title": "T2", "snippet": "S2", "position": 2},
    ]}
    p = SerperProvider(api_key="abc")
    with aioresponses() as m:
        m.post(_PATTERN, status=200, payload=payload)
        async with aiohttp.ClientSession() as s:
            results = await p.search(s, "q", num=10)
    assert [r.url for r in results] == ["https://a.com/1", "https://b.com/2"]
    assert results[0].providers == "serper"
    assert p.last_status == ProviderStatus.OK


@pytest.mark.asyncio
async def test_missing_key():
    p = SerperProvider(api_key=None)
    assert p.is_configured() is False
    async with aiohttp.ClientSession() as s:
        assert await p.search(s, "q") == []


@pytest.mark.asyncio
async def test_quota_exceeded():
    p = SerperProvider(api_key="abc")
    with aioresponses() as m:
        m.post(_PATTERN, status=429)
        async with aiohttp.ClientSession() as s:
            assert await p.search(s, "q") == []
    assert p.last_status == ProviderStatus.QUOTA_EXCEEDED


@pytest.mark.asyncio
async def test_network_error():
    p = SerperProvider(api_key="abc")
    with aioresponses() as m:
        m.post(_PATTERN, exception=aiohttp.ClientConnectionError("boom"))
        async with aiohttp.ClientSession() as s:
            assert await p.search(s, "q") == []
    assert p.last_status == ProviderStatus.ERROR


@pytest.mark.asyncio
async def test_empty_response():
    p = SerperProvider(api_key="abc")
    with aioresponses() as m:
        m.post(_PATTERN, status=200, payload={"organic": []})
        async with aiohttp.ClientSession() as s:
            assert await p.search(s, "q") == []
    assert p.last_status == ProviderStatus.OK
    assert p.calls_made == 1


@pytest.mark.asyncio
async def test_invalid_key_returns_not_configured():
    p = SerperProvider(api_key="bad")
    with aioresponses() as m:
        m.post(_PATTERN, status=403)
        async with aiohttp.ClientSession() as s:
            assert await p.search(s, "q") == []
    assert p.last_status == ProviderStatus.NOT_CONFIGURED
