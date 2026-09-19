"""Tests for the multi-API SearchRouter (J6 of sprint-searchrouter).

Uses a small in-process FakeProvider so the strategies can be exercised
without HTTP. The router itself opens an ``aiohttp.ClientSession`` even
when the providers don't use it; that's fine for tests since aiohttp is
already installed.
"""

from __future__ import annotations

import asyncio
from typing import List, Optional

import aiohttp
import pytest

from mwi.search import SearchResult, SearchRouter
from mwi.search.models import ProviderStatus
from mwi.search.providers.base import BaseProvider


class FakeProvider(BaseProvider):
    """In-memory provider that returns canned results."""

    def __init__(
        self,
        name: str,
        results: Optional[List[SearchResult]] = None,
        *,
        configured: bool = True,
        raise_exc: Optional[Exception] = None,
        status: ProviderStatus = ProviderStatus.OK,
    ) -> None:
        super().__init__()
        self.name = name
        self._results = results or []
        self._configured = configured
        self._raise = raise_exc
        self._init_status = status

    def is_configured(self) -> bool:
        if not self._configured:
            self.last_status = ProviderStatus.NOT_CONFIGURED
        return self._configured

    async def search(
        self,
        session: aiohttp.ClientSession,
        query: str,
        num: int = 20,
        language: str = "fr",
    ) -> List[SearchResult]:
        if self._raise is not None:
            raise self._raise
        self._mark_call()
        self.last_status = self._init_status
        return list(self._results)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def test_register_skips_unconfigured():
    router = SearchRouter()
    assert router.register(FakeProvider("x", configured=False)) is False
    assert router.providers == []


def test_register_dedups_by_name():
    router = SearchRouter()
    assert router.register(FakeProvider("dup")) is True
    assert router.register(FakeProvider("dup")) is False
    assert len(router.providers) == 1


def test_register_propagates_router_timeout_to_provider():
    """Registering stamps the router timeout onto the provider so
    ``settings.SEARCH_PROVIDER_TIMEOUT`` governs each adapter's per-request
    ``ClientTimeout(total=self.timeout)`` (regression: ``_timeout`` was dead)."""
    router = SearchRouter(timeout=7)
    provider = FakeProvider("slow")
    assert router.register(provider) is True
    assert provider.timeout == 7


def test_register_default_timeout_is_router_default():
    router = SearchRouter()
    provider = FakeProvider("def")
    router.register(provider)
    assert provider.timeout == SearchRouter.DEFAULT_TIMEOUT


def test_unsupported_strategy_raises():
    router = SearchRouter()
    router.register(FakeProvider("a"))
    with pytest.raises(ValueError):
        import asyncio
        asyncio.run(router.search("q", strategy="round-robin"))


# ---------------------------------------------------------------------------
# Fallback strategy
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fallback_first_success():
    """When the first provider yields results, the second is never called."""
    p1 = FakeProvider("p1", results=[
        SearchResult(url="https://a", rank=1, providers="p1"),
    ])
    p2 = FakeProvider("p2", results=[
        SearchResult(url="https://b", rank=1, providers="p2"),
    ])
    router = SearchRouter()
    router.register(p1)
    router.register(p2)
    out = await router.search("q", strategy="fallback")
    assert [r.url for r in out] == ["https://a"]
    assert p1.calls_made == 1
    assert p2.calls_made == 0


@pytest.mark.asyncio
async def test_fallback_first_empty_then_second():
    """Empty results from the first provider trigger a fallback to the next."""
    p1 = FakeProvider("p1", results=[])
    p2 = FakeProvider("p2", results=[
        SearchResult(url="https://b", rank=1, providers="p2"),
    ])
    router = SearchRouter()
    router.register(p1)
    router.register(p2)
    out = await router.search("q", strategy="fallback")
    assert [r.url for r in out] == ["https://b"]
    assert p1.calls_made == 1
    assert p2.calls_made == 1


@pytest.mark.asyncio
async def test_fallback_all_fail_returns_empty():
    p1 = FakeProvider("p1", results=[])
    p2 = FakeProvider("p2", raise_exc=RuntimeError("boom"))
    router = SearchRouter()
    router.register(p1)
    router.register(p2)
    out = await router.search("q", strategy="fallback")
    assert out == []
    # Provider that raised must have its error counter incremented.
    assert p2.errors >= 1
    assert p2.last_status == ProviderStatus.ERROR


# ---------------------------------------------------------------------------
# Parallel strategy
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parallel_merge_dedup_and_provider_concat():
    """Canonical URLs match across providers → providers concatenated, best rank kept."""
    p1 = FakeProvider("searxng", results=[
        SearchResult(url="https://A.com/path", rank=1, providers="searxng"),
        SearchResult(url="https://B.com/x", rank=2, providers="searxng"),
    ])
    p2 = FakeProvider("brave", results=[
        SearchResult(url="https://a.com/path", rank=4, providers="brave"),
        SearchResult(url="https://c.com/y", rank=1, providers="brave"),
    ])
    router = SearchRouter()
    router.register(p1)
    router.register(p2)
    out = await router.search("q", strategy="parallel")
    by_url = {r.url: r for r in out}
    # Canonicalised lowercase host.
    assert "https://a.com/path" in by_url
    # Provider concatenation preserves first-seen order.
    assert by_url["https://a.com/path"].providers == "searxng+brave"
    # Best rank kept.
    assert by_url["https://a.com/path"].rank == 1
    # Three URLs total.
    assert len(out) == 3


@pytest.mark.asyncio
async def test_parallel_isolates_failures():
    p1 = FakeProvider("p1", results=[
        SearchResult(url="https://a", rank=1, providers="p1"),
    ])
    p2 = FakeProvider("p2", raise_exc=RuntimeError("boom"))
    router = SearchRouter()
    router.register(p1)
    router.register(p2)
    out = await router.search("q", strategy="parallel")
    assert [r.url for r in out] == ["https://a"]
    assert p2.last_status == ProviderStatus.ERROR


@pytest.mark.asyncio
async def test_parallel_filter_by_provider_whitelist():
    p1 = FakeProvider("a", results=[SearchResult(url="https://a", providers="a")])
    p2 = FakeProvider("b", results=[SearchResult(url="https://b", providers="b")])
    router = SearchRouter()
    router.register(p1)
    router.register(p2)
    out = await router.search("q", strategy="parallel", providers=["b"])
    assert [r.url for r in out] == ["https://b"]
    assert p1.calls_made == 0


# ---------------------------------------------------------------------------
# No provider configured
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_provider_configured_returns_empty():
    router = SearchRouter()
    # Try to register an unconfigured provider — it gets dropped.
    router.register(FakeProvider("x", configured=False))
    assert router.providers == []
    out = await router.search("q", strategy="fallback")
    assert out == []


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_usage_report_round_trip_through_json():
    import json
    p1 = FakeProvider("p1", results=[SearchResult(url="https://a", providers="p1")])
    p2 = FakeProvider("p2", results=[])
    router = SearchRouter()
    router.register(p1)
    router.register(p2)
    await router.search("q", strategy="parallel")
    report = router.usage_report()
    encoded = json.dumps(report)
    decoded = json.loads(encoded)
    assert decoded == report
    assert "p1" in decoded
    assert decoded["p1"]["calls"] == 1
    assert decoded["p1"]["status"] == "ok"


class _NumProvider(BaseProvider):
    """Provider that honours `num`, so per-provider capping is observable."""

    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name

    def is_configured(self) -> bool:
        return True

    async def search(self, session, query, num=20, language="fr"):
        self._mark_call()
        self.last_status = ProviderStatus.OK
        return [
            SearchResult(url="https://%s.test/%d" % (self.name, i),
                         title="t", snippet="s", rank=i + 1,
                         providers=self.name)
            for i in range(num)
        ]


class TestLimitIsPerProvider:
    """R03 (a) - CONTRACT: `--limit` caps results PER PROVIDER, not in total.

    `SearchRouter.search` passes `num=limit` to each adapter and does not
    truncate after `merge_results`, so `--limit=5 --strategy=parallel` over two
    providers can return up to 10 URLs. That is deliberate — truncating a
    merged, deduplicated list would silently drop the triangulation the
    parallel strategy exists to produce — but the user documentation said
    nothing, and `SearchQuery.num_requested` archives a "20" that means
    "20 each", not "20 total".

    This test exists so the behaviour cannot be "fixed" by accident. If a
    future sprint decides to cap the total, it must delete this test on
    purpose and say so in the changelog: it changes what a published corpus
    contains.
    """

    @pytest.mark.parametrize('strategy,expected', [
        pytest.param('parallel', 10, id="parallel_sums_providers"),
        pytest.param('fallback', 5, id="fallback_stops_at_the_first"),
    ])
    @pytest.mark.asyncio
    async def test_limit_semantics(self, strategy, expected):
        router = SearchRouter()
        p1, p2 = _NumProvider("p1"), _NumProvider("p2")
        router.register(p1)
        router.register(p2)

        results = await router.search("q", num=5, strategy=strategy)

        assert len(results) == expected
        if strategy == 'fallback':
            # The second provider is never called: that is what preserves the
            # monthly quotas of the paid APIs.
            assert p2.calls_made == 0


class TestCancelledErrorIsIsolated:
    """D01a-1 - `gather(return_exceptions=True)` can hand back a BaseException.

    `asyncio.CancelledError` inherits from BaseException, not Exception, since
    Python 3.8. The parallel strategy filtered outcomes with
    `isinstance(outcome, Exception)`, so a cancelled provider task fell through
    the filter and reached `merge_results` as if it were a list of results —
    `search run --strategy=parallel` then died on a TypeError, losing the
    providers that HAD answered (and their spent quota).
    """

    @pytest.mark.asyncio
    async def test_a_cancelled_provider_does_not_sink_the_others(self):
        router = SearchRouter()
        ok = FakeProvider("ok", [SearchResult(url="https://ok.test/1",
                                              title="t", snippet="s", rank=1,
                                              providers="ok")])
        cancelled = FakeProvider("cancelled",
                                 raise_exc=asyncio.CancelledError())
        router.register(ok)
        router.register(cancelled)

        results = await router.search("q", num=5, strategy="parallel")

        assert [r.url for r in results] == ["https://ok.test/1"]
        assert cancelled.errors == 1
        assert cancelled.last_status == ProviderStatus.ERROR
