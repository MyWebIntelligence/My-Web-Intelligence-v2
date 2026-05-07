"""Brave provider unit tests (mocked HTTP via aioresponses)."""

from __future__ import annotations

import re

import aiohttp
import pytest
from aioresponses import aioresponses

from mwi.search.models import ProviderStatus
from mwi.search.providers.brave import BraveProvider


_PATTERN = re.compile(r"https://api\.search\.brave\.com/.*")


@pytest.mark.asyncio
async def test_search_success():
    payload = {"web": {"results": [
        {"url": "https://a.com/1", "title": "T1", "description": "S1"},
        {"url": "https://b.com/2", "title": "T2", "description": "S2"},
    ]}}
    p = BraveProvider(api_key="abc")
    p.min_delay_between_calls = 0  # speed up tests
    with aioresponses() as m:
        m.get(_PATTERN, status=200, payload=payload)
        async with aiohttp.ClientSession() as s:
            results = await p.search(s, "q", num=10, language="fr")
    assert len(results) == 2
    assert results[0].providers == "brave"
    assert results[0].rank == 1
    assert p.last_status == ProviderStatus.OK


@pytest.mark.asyncio
async def test_missing_key():
    p = BraveProvider(api_key=None)
    assert p.is_configured() is False
    assert p.last_status == ProviderStatus.NOT_CONFIGURED
    async with aiohttp.ClientSession() as s:
        results = await p.search(s, "q")
    assert results == []


@pytest.mark.asyncio
async def test_quota_exceeded_402():
    p = BraveProvider(api_key="abc")
    p.min_delay_between_calls = 0
    with aioresponses() as m:
        m.get(_PATTERN, status=402)
        async with aiohttp.ClientSession() as s:
            results = await p.search(s, "q")
    assert results == []
    assert p.last_status == ProviderStatus.QUOTA_EXCEEDED
    assert p.errors == 1


@pytest.mark.asyncio
async def test_quota_exceeded_429():
    p = BraveProvider(api_key="abc")
    p.min_delay_between_calls = 0
    with aioresponses() as m:
        m.get(_PATTERN, status=429)
        async with aiohttp.ClientSession() as s:
            results = await p.search(s, "q")
    assert results == []
    assert p.last_status == ProviderStatus.QUOTA_EXCEEDED


@pytest.mark.asyncio
async def test_invalid_key_401():
    p = BraveProvider(api_key="bad")
    p.min_delay_between_calls = 0
    with aioresponses() as m:
        m.get(_PATTERN, status=401)
        async with aiohttp.ClientSession() as s:
            results = await p.search(s, "q")
    assert results == []
    assert p.last_status == ProviderStatus.NOT_CONFIGURED


@pytest.mark.asyncio
async def test_network_error():
    p = BraveProvider(api_key="abc")
    p.min_delay_between_calls = 0
    with aioresponses() as m:
        m.get(_PATTERN, exception=aiohttp.ClientConnectionError("nope"))
        async with aiohttp.ClientSession() as s:
            results = await p.search(s, "q")
    assert results == []
    assert p.last_status == ProviderStatus.ERROR


@pytest.mark.asyncio
async def test_empty_response():
    p = BraveProvider(api_key="abc")
    p.min_delay_between_calls = 0
    with aioresponses() as m:
        m.get(_PATTERN, status=200, payload={"web": {"results": []}})
        async with aiohttp.ClientSession() as s:
            results = await p.search(s, "q")
    assert results == []
    assert p.last_status == ProviderStatus.OK
    assert p.calls_made == 1


def test_resolves_key_from_env(monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "from-env")
    p = BraveProvider()
    assert p.api_key == "from-env"
    assert p.is_configured() is True
