import pytest

from mwi import core


class DummyResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or ""

    def json(self):
        return self._payload


def test_fetch_serpapi_url_list_requires_query():
    with pytest.raises(core.SerpApiError):
        core.fetch_serpapi_url_list(api_key="key", query="")


def test_fetch_serpapi_url_list_handles_http_error(monkeypatch):
    def fake_get(*args, **kwargs):
        return DummyResponse(status_code=500, text="boom")

    monkeypatch.setattr(core.requests, "get", fake_get)
    # 500 is retryable; cap attempts at 1 so the test does not sit through the
    # exponential backoff sleeps (2s, 4s, ...).
    monkeypatch.setattr(core.settings, "serpapi_max_retries", 1, raising=False)

    with pytest.raises(core.SerpApiError) as exc:
        core.fetch_serpapi_url_list(api_key="key", query="smart", sleep_seconds=0.0)
    # Collection runs window by window: when every request fails and nothing is
    # collected, the orchestrator raises an aggregate error rather than the raw
    # per-request status (the status detail is logged, not surfaced).
    assert "All SerpAPI requests failed" in str(exc.value)


def test_fetch_serpapi_url_list_builds_params(monkeypatch):
    captured = []

    def fake_get(url, params=None, timeout=None):
        captured.append({"url": url, "params": params, "timeout": timeout})
        payload = {
            "organic_results": [
                {"position": 1, "title": "Result", "link": "https://example.com", "date": "2024-01-01"}
            ],
            "serpapi_pagination": {},
        }
        return DummyResponse(status_code=200, payload=payload, text="{}")

    monkeypatch.setattr(core.requests, "get", fake_get)

    results = core.fetch_serpapi_url_list(
        api_key="key",
        query="Test Query",
        lang="fr",
        datestart="2024-01-01",
        dateend="2024-01-07",
        timestep="week",
        sleep_seconds=0.0,
    )

    assert len(results) == 1
    assert results[0]["link"] == "https://example.com"

    assert len(captured) == 1
    params = captured[0]["params"]
    assert params["tbs"] == "cdr:1,cd_min:01/01/2024,cd_max:01/07/2024"
    # Language-only targeting by default: hl + lr, no country bias. `gl` is an
    # ISO 3166 COUNTRY code and is opt-in via --gl — it is no longer copied
    # from the language (SerpAPI rejects gl=fr / gl=en, which are not countries).
    assert params["hl"] == "fr"
    assert params["lr"] == "lang_fr"
    assert "gl" not in params
    # Legacy parity (serpapi_router.GoogleProvider): when a date filter is
    # active, Google ignores `num`, so the router deliberately omits it.
    assert "num" not in params
    assert params["start"] == 0
    assert captured[0]["timeout"] == getattr(core.settings, "serpapi_timeout", 15)


def test_fetch_serpapi_url_list_gl_country_is_opt_in(monkeypatch):
    captured = []

    def fake_get(url, params=None, timeout=None):
        captured.append(params)
        return DummyResponse(
            status_code=200,
            payload={"organic_results": [], "serpapi_pagination": {}},
            text="{}",
        )

    monkeypatch.setattr(core.requests, "get", fake_get)

    core.fetch_serpapi_url_list(
        api_key="key",
        query="Test Query",
        lang="en",
        gl="US",
        sleep_seconds=0.0,
    )

    assert len(captured) == 1
    params = captured[0]
    # An explicit --gl adds the country restriction (lowercased), alongside the
    # language scoping that is always present.
    assert params["gl"] == "us"
    assert params["hl"] == "en"
    assert params["lr"] == "lang_en"
