"""Integration tests for the multi-API search router (J9 of sprint-searchrouter).

Five scenarios from the sprint spec:
1. SearXNG real (skipped if SEARXNG_BASE_URL is unreachable).
2. Mock parallel — three providers with overlapping URLs.
3. Mock fallback — first provider fails, second succeeds.
4. Expression creation — `search run` adds Expression rows to the Land.
5. usage_report JSON round-trip via Peewee.
"""

from __future__ import annotations

import json
import os
import re
import socket
from typing import List
from urllib.parse import urlparse

import aiohttp
import pytest
from aioresponses import aioresponses

from mwi.search import SearchResult, SearchRouter
from mwi.search.models import ProviderStatus
from mwi.search.providers.base import BaseProvider
from mwi.search.providers.searxng import SearxngProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _searxng_reachable() -> bool:
    """Return True when SEARXNG_BASE_URL accepts a TCP connection."""
    url = os.getenv("SEARXNG_BASE_URL", "http://localhost:8888")
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except (OSError, socket.timeout):
        return False


class _CannedProvider(BaseProvider):
    """Provider returning canned results without HTTP."""
    def __init__(self, name: str, results: List[SearchResult]) -> None:
        super().__init__()
        self.name = name
        self._results = results

    def is_configured(self) -> bool:
        return True

    async def search(self, session, query, num=20, language="fr"):
        self._mark_call()
        self.last_status = ProviderStatus.OK
        return list(self._results)


class _FailingProvider(BaseProvider):
    """Provider that always reports an empty result with an error."""
    def __init__(self, name: str = "failing") -> None:
        super().__init__()
        self.name = name

    def is_configured(self) -> bool:
        return True

    async def search(self, session, query, num=20, language="fr"):
        self._mark_error(ProviderStatus.ERROR, "always fails")
        return []


# ---------------------------------------------------------------------------
# Scenario 1 — SearXNG real (skipped offline)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not _searxng_reachable(),
    reason="SEARXNG_BASE_URL not reachable — start docker/searxng/",
)
@pytest.mark.asyncio
async def test_searxng_real_round_trip():
    p = SearxngProvider()
    async with aiohttp.ClientSession() as session:
        results = await p.search(session, "humanités numériques", num=5)
    assert isinstance(results, list)
    # We only assert the round-trip succeeded — content depends on the live
    # upstream engines, so we don't compare URLs.
    assert p.last_status in (ProviderStatus.OK, ProviderStatus.QUOTA_EXCEEDED)


# ---------------------------------------------------------------------------
# Scenario 2 — Mock parallel with overlapping providers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mock_parallel_merges_overlap():
    """Three providers, two share a URL — provider names concatenated."""
    p1 = _CannedProvider("searxng", [
        SearchResult(url="https://shared.com/x", rank=1, providers="searxng"),
        SearchResult(url="https://only-1.com",   rank=2, providers="searxng"),
    ])
    p2 = _CannedProvider("brave", [
        SearchResult(url="https://shared.com/x", rank=3, providers="brave"),
        SearchResult(url="https://only-2.com",   rank=2, providers="brave"),
    ])
    p3 = _CannedProvider("serper", [
        SearchResult(url="https://shared.com/x", rank=5, providers="serper"),
        SearchResult(url="https://only-3.com",   rank=2, providers="serper"),
    ])
    router = SearchRouter()
    for p in (p1, p2, p3):
        router.register(p)

    results = await router.search("q", strategy="parallel")
    by_url = {r.url: r for r in results}

    # Four unique URLs total, the shared one merges all three providers.
    assert len(results) == 4
    shared = by_url["https://shared.com/x"]
    assert "searxng" in shared.providers
    assert "brave" in shared.providers
    assert "serper" in shared.providers
    assert shared.rank == 1  # min of (1, 3, 5)


# ---------------------------------------------------------------------------
# Scenario 3 — Mock fallback (first fails)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mock_fallback_first_fails():
    fail = _FailingProvider("p_fail")
    ok = _CannedProvider("p_ok", [
        SearchResult(url="https://ok.com/y", rank=1, providers="p_ok"),
    ])
    router = SearchRouter()
    router.register(fail)
    router.register(ok)

    results = await router.search("q", strategy="fallback")
    assert [r.url for r in results] == ["https://ok.com/y"]
    assert fail.errors >= 1


# ---------------------------------------------------------------------------
# Scenario 4 — Expression creation via `search run`
# ---------------------------------------------------------------------------

def test_search_run_creates_expressions(fresh_db, monkeypatch):
    controller = fresh_db["controller"]
    core = fresh_db["core"]
    m = fresh_db["model"]

    land = m.Land.create(name="Lint", description="d", lang="fr")

    fake_router = SearchRouter()
    fake_router.register(_CannedProvider("searxng", [
        SearchResult(url="https://int1.com/a", rank=1, providers="searxng"),
        SearchResult(url="https://int2.com/b", rank=2, providers="searxng"),
    ]))
    monkeypatch.setattr(
        controller.SearchController, "_build_router", lambda: fake_router
    )

    rc = controller.SearchController.run(core.Namespace(
        land="Lint", query="q", limit=10,
        strategy="fallback", language="fr", providers=None,
    ))
    assert rc == 1
    # Two new Expression rows in the Land.
    exprs = list(m.Expression.select().where(m.Expression.land == land))
    assert {e.url for e in exprs} == {
        "https://int1.com/a",
        "https://int2.com/b",
    }
    # Logs back-ref Expressions.
    logs = list(m.SearchResultLog.select())
    assert all(l.expression is not None for l in logs)


# ---------------------------------------------------------------------------
# Scenario 5 — usage_report JSON round-trip
# ---------------------------------------------------------------------------

def test_usage_report_persists_and_decodes(fresh_db, monkeypatch):
    controller = fresh_db["controller"]
    core = fresh_db["core"]
    m = fresh_db["model"]

    m.Land.create(name="Lreport", description="d", lang="fr")

    fake = SearchRouter()
    fake.register(_CannedProvider("searxng", [
        SearchResult(url="https://r.com/x", rank=1, providers="searxng"),
    ]))
    monkeypatch.setattr(
        controller.SearchController, "_build_router", lambda: fake
    )
    controller.SearchController.run(core.Namespace(
        land="Lreport", query="q", limit=5,
        strategy="parallel", language="fr", providers=None,
    ))

    sq = m.SearchQuery.get()
    assert sq.usage_report is not None
    decoded = json.loads(sq.usage_report)
    assert "searxng" in decoded
    assert decoded["searxng"]["status"] == "ok"
    assert decoded["searxng"]["calls"] == 1
