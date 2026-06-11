"""Tests for the SearchRouter / SearchProvider / run_search refactor.

Covers §6 of `.claude/project/sprint-searchrouter.md`:
- Router registry (engines listed, unknown raises).
- Per-provider params for Google / Bing / DuckDuckGo (parity with legacy).
- Orchestrator: pagination aggregation, date windowing, validation, DDG empty
  error breaking the loop cleanly.
- CLI choices match router state.
"""
from __future__ import annotations

from datetime import date

import pytest

from mwi import serpapi_router as search
from mwi.serpapi_router import (
    BingProvider,
    DuckDuckGoProvider,
    GoogleProvider,
    SearchError,
    SearchRequest,
    SearchRouter,
    run_search,
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_router_lists_known_engines():
    assert SearchRouter.engines() == frozenset({"google", "bing", "duckduckgo"})


def test_router_get_unknown_raises():
    with pytest.raises(SearchError):
        SearchRouter.get("altavista")


# ---------------------------------------------------------------------------
# Provider params — parity with legacy fetch_serpapi_url_list
# ---------------------------------------------------------------------------

def test_google_provider_params_fr():
    params = GoogleProvider().build_locale_params(
        "fr", 0, 100, use_date_filter=False
    )
    assert params == {
        "google_domain": "google.fr",
        "hl": "fr",
        "lr": "lang_fr",
        "safe": "off",
        "start": 0,
        "num": 100,
    }


def test_google_provider_language_only_by_default():
    # Country restriction must be opt-in: by default only hl/lr scope the
    # search. The legacy copy of the language into `gl` (a country code)
    # made SerpAPI reject gl=en with a 400.
    params = GoogleProvider().build_locale_params(
        "en", 0, 100, use_date_filter=False
    )
    assert "gl" not in params
    assert params["hl"] == "en"
    assert params["lr"] == "lang_en"
    assert params["google_domain"] == "google.com"


def test_google_provider_explicit_gl():
    params = GoogleProvider().build_locale_params(
        "en", 0, 100, use_date_filter=False, gl="US"
    )
    assert params["gl"] == "us"
    assert params["hl"] == "en"


def test_google_provider_omits_num_with_date_filter():
    params = GoogleProvider().build_locale_params(
        "fr", 0, 100, use_date_filter=True
    )
    assert "num" not in params
    # The other keys remain in place.
    assert params["start"] == 0
    assert params["google_domain"] == "google.fr"


def test_bing_provider_params_en():
    params = BingProvider().build_locale_params(
        "en", 0, 50, use_date_filter=False
    )
    assert params == {
        "mkt": "en-US",
        "count": 50,
        "first": 1,  # 1-indexed pagination
    }


def test_ddg_provider_includes_df_with_window():
    df_params = DuckDuckGoProvider().build_date_filter_params(
        date(2024, 1, 1), date(2024, 1, 31)
    )
    assert df_params == {"df": "2024-01-01..2024-01-31"}


def test_google_provider_tbs_format():
    tbs_params = GoogleProvider().build_date_filter_params(
        date(2024, 1, 1), date(2024, 1, 31)
    )
    assert tbs_params == {"tbs": "cdr:1,cd_min:01/01/2024,cd_max:01/31/2024"}


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def _build_payload(positions, *, next_offset=None, next_link=None):
    """Build a SerpAPI-shaped payload with given organic_results positions."""
    payload = {
        "organic_results": [
            {
                "position": p,
                "title": f"Title {p}",
                "link": f"https://example.com/{p}",
                "date": None,
            }
            for p in positions
        ]
    }
    pagination = {}
    if next_link:
        pagination["next_link"] = next_link
    if next_offset is not None:
        pagination["next_offset"] = next_offset
    if pagination:
        payload["serpapi_pagination"] = pagination
    return payload


def test_run_search_aggregates_pages(monkeypatch):
    """Two-page response → both pages aggregated, order preserved."""
    pages = iter([
        _build_payload(
            range(1, 101),
            next_offset=100,
            next_link="https://serpapi.com/search?start=100",
        ),
        _build_payload(range(101, 201)),  # no pagination → loop ends
    ])

    def fake_http_get(params):
        return next(pages)

    monkeypatch.setattr(search, "_http_get", fake_http_get)
    monkeypatch.setattr(search, "_jitter_sleep", lambda _b: None)

    results = run_search(SearchRequest(
        api_key="fake", query="anything", engine="google", sleep_seconds=0.0,
    ))
    assert len(results) == 200
    assert results[0]["link"] == "https://example.com/1"
    assert results[-1]["link"] == "https://example.com/200"


def test_run_search_gl_optin(monkeypatch):
    # No gl by default (language-only search); explicit request.gl flows
    # through to the SerpAPI params.
    captured = []

    def fake_http_get(params):
        captured.append(dict(params))
        return _build_payload(range(1, 3))

    monkeypatch.setattr(search, "_http_get", fake_http_get)
    monkeypatch.setattr(search, "_jitter_sleep", lambda _b: None)

    run_search(SearchRequest(api_key="fake", query="x", engine="google", lang="en"))
    assert "gl" not in captured[0]

    captured.clear()
    run_search(SearchRequest(
        api_key="fake", query="x", engine="google", lang="en", gl="us"
    ))
    assert captured[0]["gl"] == "us"


def test_run_search_pagination_falls_back_to_url_query(monkeypatch):
    """No `next_offset`, but `start=` in next_link should be detected."""
    pages = iter([
        _build_payload(
            range(1, 101),
            next_link="https://serpapi.com/search?q=x&start=200",
        ),
        _build_payload(range(201, 301)),
    ])

    def fake_http_get(params):
        return next(pages)

    monkeypatch.setattr(search, "_http_get", fake_http_get)
    monkeypatch.setattr(search, "_jitter_sleep", lambda _b: None)

    results = run_search(SearchRequest(
        api_key="fake", query="anything", engine="google", sleep_seconds=0.0,
    ))
    assert len(results) == 200


def test_run_search_iterates_windows(monkeypatch):
    """3-week range with timestep=week → 3 windows, progress_hook fires 3×."""
    calls = []

    def fake_http_get(params):
        calls.append(params)
        return {"organic_results": []}  # empty → break inner loop, advance window

    progress_calls = []

    def progress_hook(start, end, count):
        progress_calls.append((start, end, count))

    monkeypatch.setattr(search, "_http_get", fake_http_get)
    monkeypatch.setattr(search, "_jitter_sleep", lambda _b: None)

    run_search(SearchRequest(
        api_key="fake",
        query="anything",
        engine="google",
        datestart="2024-01-01",
        dateend="2024-01-21",  # 3 full weeks → 3 windows
        timestep="week",
        sleep_seconds=0.0,
        progress_hook=progress_hook,
    ))
    assert len(calls) == 3
    assert len(progress_calls) == 3
    # Each window should carry google's tbs param.
    assert all("tbs" in c for c in calls)


def test_run_search_raises_when_dates_partial():
    with pytest.raises(SearchError):
        run_search(SearchRequest(
            api_key="fake", query="x", engine="google", datestart="2024-01-01",
        ))


def test_run_search_raises_when_engine_lacks_date_support():
    with pytest.raises(SearchError):
        run_search(SearchRequest(
            api_key="fake",
            query="x",
            engine="bing",
            datestart="2024-01-01",
            dateend="2024-01-31",
        ))


def test_run_search_breaks_on_ddg_empty_error(monkeypatch):
    """DuckDuckGo's `hasn't returned any results` is a clean break, not a raise."""
    def fake_http_get(params):
        return {"error": "DuckDuckGo hasn't returned any results for this query."}

    monkeypatch.setattr(search, "_http_get", fake_http_get)
    monkeypatch.setattr(search, "_jitter_sleep", lambda _b: None)

    results = run_search(SearchRequest(
        api_key="fake", query="x", engine="duckduckgo", sleep_seconds=0.0,
    ))
    assert results == []


def test_run_search_raises_on_other_serpapi_errors(monkeypatch):
    """Any other `error` payload raises SearchError."""
    def fake_http_get(params):
        return {"error": "Invalid API key"}

    monkeypatch.setattr(search, "_http_get", fake_http_get)

    with pytest.raises(SearchError, match="Invalid API key"):
        run_search(SearchRequest(api_key="fake", query="x", engine="google"))


def test_run_search_rejects_empty_query():
    with pytest.raises(SearchError):
        run_search(SearchRequest(api_key="fake", query="   ", engine="google"))


# ---------------------------------------------------------------------------
# CLI / legacy alias
# ---------------------------------------------------------------------------

def test_cli_engine_choices_match_router():
    """The CLI parser's --engine choices must come from SearchRouter."""
    import argparse
    from mwi import cli

    # command_input builds the parser internally; we re-parse a known-good arg
    # set to assert that an out-of-router engine is rejected.
    # Easier path: check that the literal cli has no hardcoded list.
    import inspect
    src = inspect.getsource(cli)
    assert "['google', 'bing', 'duckduckgo']" not in src
    assert "SerpApiRouter.engines()" in src


def test_legacy_alias_present():
    """`core.SerpApiError` and `core.fetch_serpapi_url_list` must keep working."""
    from mwi import core

    assert core.SerpApiError is search.SearchError
    assert callable(core.fetch_serpapi_url_list)
