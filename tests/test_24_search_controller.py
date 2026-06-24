"""End-to-end (mocked) tests for SearchController (J7).

The router is monkeypatched at ``SearchController._build_router`` to return
an in-memory router with a fake provider — no HTTP. We exercise:
- ``search run``   creates SearchQuery + SearchResultLog + Expression rows.
- ``search list``  prints rows for a Land (smoke check).
- ``search usage`` aggregates JSON ``usage_report`` columns.
- ``search check`` produces a status line per provider.
"""

from __future__ import annotations

import json
from typing import List

import pytest

from mwi.search import SearchResult, SearchRouter
from mwi.search.models import ProviderStatus
from mwi.search.providers.base import BaseProvider


class _FakeProvider(BaseProvider):
    """Returns canned results without ever hitting the network."""
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


def _build_fake_router(name: str, urls: List[str]) -> SearchRouter:
    router = SearchRouter()
    router.register(_FakeProvider(name, [
        SearchResult(url=u, title=f"T-{i}", snippet=f"S-{i}",
                     rank=i + 1, providers=name)
        for i, u in enumerate(urls)
    ]))
    return router


@pytest.fixture()
def land_fixture(fresh_db):
    """Build a single Land that the search commands will populate."""
    m = fresh_db["model"]
    land = m.Land.create(name="LSearch", description="d", lang="fr")
    return {**fresh_db, "land": land}


def test_search_run_persists_query_logs_and_expressions(land_fixture, monkeypatch):
    """`search run` stores SearchQuery + per-result SearchResultLog + Expression."""
    controller = land_fixture["controller"]
    core = land_fixture["core"]
    m = land_fixture["model"]
    SearchController = controller.SearchController

    fake_router = _build_fake_router("searxng", [
        "https://example.com/a",
        "https://example.com/b",
        "https://other.org/c",
    ])
    monkeypatch.setattr(SearchController, "_build_router", lambda: fake_router)

    args = core.Namespace(
        land="LSearch", query="humanités numériques",
        limit=10, strategy="fallback", language="fr", providers=None,
    )
    rc = SearchController.run(args)
    assert rc == 1

    queries = list(m.SearchQuery.select())
    assert len(queries) == 1
    sq = queries[0]
    assert sq.query == "humanités numériques"
    assert sq.strategy == "fallback"
    assert sq.num_collected == 3
    assert sq.completed_at is not None

    logs = list(m.SearchResultLog.select().where(m.SearchResultLog.search_query == sq))
    assert len(logs) == 3
    log_urls = {l.url for l in logs}
    assert "https://example.com/a" in log_urls

    # Expression rows were created in the Land for each URL.
    exprs = list(m.Expression.select().where(m.Expression.land == land_fixture["land"]))
    assert len(exprs) == 3
    # FK back-ref from log → expression is set.
    assert all(l.expression is not None for l in logs)

    # The usage_report JSON round-trips.
    report = json.loads(sq.usage_report)
    assert "searxng" in report
    assert report["searxng"]["calls"] == 1


def test_search_run_skips_duplicates(land_fixture, monkeypatch):
    """A second `search run` over the same URLs creates new logs but not duplicate Expressions."""
    controller = land_fixture["controller"]
    core = land_fixture["core"]
    m = land_fixture["model"]
    SC = controller.SearchController

    fake_router = _build_fake_router("searxng", ["https://a.com/x", "https://b.com/y"])
    monkeypatch.setattr(SC, "_build_router", lambda: fake_router)

    args = core.Namespace(
        land="LSearch", query="q1", limit=5,
        strategy="fallback", language="fr", providers=None,
    )
    SC.run(args)
    SC.run(core.Namespace(
        land="LSearch", query="q2", limit=5,
        strategy="fallback", language="fr", providers=None,
    ))

    # Two SearchQuery rows — one per call.
    assert m.SearchQuery.select().count() == 2
    # Two Expression rows total — same URLs, no duplicates in the Land.
    assert m.Expression.select().count() == 2
    # Four log rows (2 URLs × 2 queries).
    assert m.SearchResultLog.select().count() == 4


def test_search_run_requires_land_and_query(land_fixture, monkeypatch):
    controller = land_fixture["controller"]
    core = land_fixture["core"]
    SC = controller.SearchController
    monkeypatch.setattr(SC, "_build_router", lambda: SearchRouter())

    assert SC.run(core.Namespace(land=None, query="q", limit=5)) == 0
    assert SC.run(core.Namespace(land="LSearch", query=None, limit=5)) == 0


def test_search_run_no_provider_returns_zero(land_fixture, monkeypatch, capsys):
    controller = land_fixture["controller"]
    core = land_fixture["core"]
    SC = controller.SearchController
    # Router with zero registered providers.
    monkeypatch.setattr(SC, "_build_router", lambda: SearchRouter())
    rc = SC.run(core.Namespace(
        land="LSearch", query="q", limit=5,
        strategy="fallback", language="fr", providers=None,
    ))
    assert rc == 0
    out = capsys.readouterr().out
    assert "no provider configured" in out


def test_search_list_prints_queries(land_fixture, monkeypatch, capsys):
    controller = land_fixture["controller"]
    core = land_fixture["core"]
    m = land_fixture["model"]
    SC = controller.SearchController

    fake = _build_fake_router("searxng", ["https://x.com/y"])
    monkeypatch.setattr(SC, "_build_router", lambda: fake)
    SC.run(core.Namespace(
        land="LSearch", query="ma reqête", limit=5,
        strategy="fallback", language="fr", providers=None,
    ))

    rc = SC.list(core.Namespace(land="LSearch"))
    assert rc == 1
    out = capsys.readouterr().out
    assert "ma reqête" in out
    assert "fallback" in out


def test_search_usage_aggregates_calls(land_fixture, monkeypatch, capsys):
    controller = land_fixture["controller"]
    core = land_fixture["core"]
    SC = controller.SearchController

    fake = _build_fake_router("searxng", ["https://x.com/y"])
    monkeypatch.setattr(SC, "_build_router", lambda: fake)
    # Two runs → 2 calls aggregated.
    SC.run(core.Namespace(land="LSearch", query="q1", limit=5,
                          strategy="fallback", language="fr", providers=None))
    SC.run(core.Namespace(land="LSearch", query="q2", limit=5,
                          strategy="fallback", language="fr", providers=None))

    rc = SC.usage(core.Namespace(land="LSearch"))
    assert rc == 1
    out = capsys.readouterr().out
    assert "searxng" in out


def test_search_check_lists_all_providers(land_fixture, capsys, monkeypatch):
    controller = land_fixture["controller"]
    core = land_fixture["core"]
    SC = controller.SearchController

    # Make sure no API keys are set in the env.
    for var in ("BRAVE_API_KEY", "SERPER_API_KEY",
                "SERPAPI_API_KEY", "TAVILY_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    import settings as _settings
    for attr in ("BRAVE_API_KEY", "SERPER_API_KEY", "SERPAPI_API_KEY",
                 "TAVILY_API_KEY", "serpapi_api_key"):
        monkeypatch.setattr(_settings, attr, None, raising=False)

    rc = SC.check(core.Namespace())
    assert rc == 1
    out = capsys.readouterr().out
    for name in ("searxng", "brave", "serper", "serpapi", "tavily"):
        assert name in out
    # SearXNG always reports configured (no key).
    assert "searxng" in out


def test_search_run_filters_providers(land_fixture, monkeypatch):
    controller = land_fixture["controller"]
    core = land_fixture["core"]
    m = land_fixture["model"]
    SC = controller.SearchController

    router = SearchRouter()
    router.register(_FakeProvider("searxng", [
        SearchResult(url="https://A/1", rank=1, providers="searxng"),
    ]))
    router.register(_FakeProvider("brave", [
        SearchResult(url="https://B/1", rank=1, providers="brave"),
    ]))
    monkeypatch.setattr(SC, "_build_router", lambda: router)

    SC.run(core.Namespace(
        land="LSearch", query="q", limit=5,
        strategy="parallel", language="fr", providers="searxng",
    ))
    logs = list(m.SearchResultLog.select())
    assert all("searxng" in l.providers for l in logs)
    assert all("brave" not in l.providers for l in logs)


def test_build_router_reads_search_provider_timeout(fresh_db, monkeypatch):
    """`_build_router` reads settings.SEARCH_PROVIDER_TIMEOUT and propagates it
    to the always-configured SearXNG provider (regression: the value used to be
    dead config — never read by the router nor reaching any provider)."""
    controller = fresh_db["controller"]
    import settings as _settings
    monkeypatch.setattr(_settings, "SEARCH_PROVIDER_TIMEOUT", 11, raising=False)

    router = controller.SearchController._build_router()
    assert router._timeout == 11
    searxng = next((p for p in router.providers if p.name == "searxng"), None)
    assert searxng is not None
    assert searxng.timeout == 11
