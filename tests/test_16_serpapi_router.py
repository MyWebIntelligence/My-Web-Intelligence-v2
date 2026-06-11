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


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text

    def json(self):
        return self._payload


def test_http_get_retries_transient_then_succeeds(monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(1)
        if len(calls) < 3:
            raise search.requests.exceptions.ReadTimeout("Read timed out.")
        return _FakeResponse(payload={"ok": True})

    monkeypatch.setattr(search.requests, "get", fake_get)
    monkeypatch.setattr(search.time, "sleep", lambda _s: None)

    assert search._http_get({"q": "x"}) == {"ok": True}
    assert len(calls) == 3


def test_http_get_client_error_fails_fast(monkeypatch):
    # 400 (bad param) / 401 (bad key) must not be retried: retrying cannot
    # fix them and burns quota.
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(1)
        return _FakeResponse(status_code=400, text="Unsupported `xx` country")

    monkeypatch.setattr(search.requests, "get", fake_get)
    monkeypatch.setattr(search.time, "sleep", lambda _s: None)

    with pytest.raises(search.SearchError) as exc_info:
        search._http_get({"q": "x"})
    assert not isinstance(exc_info.value, search.TransientSearchError)
    assert len(calls) == 1


def test_http_get_exhausted_retries_raises_transient(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        raise search.requests.exceptions.ConnectionError(
            "Max retries exceeded with url: /search?api_key=SECRET&q=x"
        )

    monkeypatch.setattr(search.requests, "get", fake_get)
    monkeypatch.setattr(search.time, "sleep", lambda _s: None)

    with pytest.raises(search.TransientSearchError) as exc_info:
        search._http_get({"q": "x"})
    # The api_key must never leak into error messages.
    assert "SECRET" not in str(exc_info.value)
    assert "api_key=***" in str(exc_info.value)


def test_run_search_skips_failed_window_and_keeps_results(monkeypatch):
    # A window lost after retries is skipped; results from other windows
    # survive (each SerpAPI call was billed — losing them wastes quota).
    def fake_http_get(params):
        if "cd_min:01/01/2024" in str(params.get("tbs", "")):
            raise search.TransientSearchError("Read timed out")
        return _build_payload(range(1, 4))

    monkeypatch.setattr(search, "_http_get", fake_http_get)
    monkeypatch.setattr(search, "_jitter_sleep", lambda _b: None)

    results = run_search(SearchRequest(
        api_key="fake", query="x", engine="google",
        datestart="2024-01-01", dateend="2024-02-29", timestep="month",
    ))
    assert len(results) == 3  # February survived January's failure


def test_run_search_raises_when_all_windows_fail(monkeypatch):
    def fake_http_get(params):
        raise search.TransientSearchError("Read timed out")

    monkeypatch.setattr(search, "_http_get", fake_http_get)
    monkeypatch.setattr(search, "_jitter_sleep", lambda _b: None)

    with pytest.raises(SearchError):
        run_search(SearchRequest(
            api_key="fake", query="x", engine="google",
            datestart="2024-01-01", dateend="2024-02-29", timestep="month",
        ))


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


def test_run_search_google_pagination_exhausted_is_clean(monkeypatch):
    """Google's `hasn't returned any results` mid-pagination ends the window
    cleanly and keeps the results fetched so far (observed at start=210 on a
    date-filtered query, 2026-06-11)."""
    calls = []

    def fake_http_get(params):
        calls.append(dict(params))
        if params.get("start", 0) == 0:
            return _build_payload(
                range(1, 11),
                next_offset=10,
                next_link="https://serpapi.com/search?start=10",
            )
        return {"error": "Google hasn't returned any results for this query."}

    monkeypatch.setattr(search, "_http_get", fake_http_get)
    monkeypatch.setattr(search, "_jitter_sleep", lambda _b: None)

    results = run_search(SearchRequest(api_key="fake", query="x", engine="google"))
    assert len(results) == 10
    assert len(calls) == 2


def test_run_search_fatal_midrun_keeps_collected_results(monkeypatch):
    """A non-transient error after some windows succeeded (e.g. quota
    exhausted) stops the run but returns what was already collected —
    those requests were billed."""
    def fake_http_get(params):
        if "cd_min:01/01/2024" in str(params.get("tbs", "")):
            return _build_payload(range(1, 6))
        return {"error": "Your account has run out of searches."}

    monkeypatch.setattr(search, "_http_get", fake_http_get)
    monkeypatch.setattr(search, "_jitter_sleep", lambda _b: None)

    results = run_search(SearchRequest(
        api_key="fake", query="x", engine="google",
        datestart="2024-01-01", dateend="2024-02-29", timestep="month",
    ))
    assert len(results) == 5  # January kept despite February's fatal error


def test_run_search_window_hook_delivers_per_window(monkeypatch):
    """With window_results_hook set, each window's results are delivered as
    soon as the window completes and run_search returns an empty list."""
    def fake_http_get(params):
        if "cd_min:01/01/2024" in str(params.get("tbs", "")):
            return _build_payload(range(1, 4))
        return _build_payload(range(4, 6))

    monkeypatch.setattr(search, "_http_get", fake_http_get)
    monkeypatch.setattr(search, "_jitter_sleep", lambda _b: None)

    delivered = []
    results = run_search(SearchRequest(
        api_key="fake", query="x", engine="google",
        datestart="2024-01-01", dateend="2024-02-29", timestep="month",
        window_results_hook=lambda ws, we, res: delivered.append((ws, len(res))),
    ))
    assert results == []
    assert delivered == [(date(2024, 1, 1), 3), (date(2024, 2, 1), 2)]


def test_run_search_fatal_keeps_partial_window_results(monkeypatch):
    """Mid-pagination fatal error: page 1 of the dying window was billed —
    its results are kept."""
    calls = []

    def fake_http_get(params):
        calls.append(1)
        if len(calls) == 1:
            return _build_payload(
                range(1, 4), next_offset=10,
                next_link="https://serpapi.com/search?start=10",
            )
        return {"error": "Your account has run out of searches."}

    monkeypatch.setattr(search, "_http_get", fake_http_get)
    monkeypatch.setattr(search, "_jitter_sleep", lambda _b: None)

    results = run_search(SearchRequest(api_key="fake", query="x", engine="google"))
    assert len(results) == 3


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
