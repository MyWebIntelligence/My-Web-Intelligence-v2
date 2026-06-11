"""Search Router — engine-agnostic SerpAPI orchestrator.

This module isolates everything that varies between search engines (locale
parameters, page size, date filtering, pagination quirks) behind a
``SearchProvider`` interface. The orchestrator (``run_search``) holds the
single HTTP / pagination / windowing loop and consults the router to look up
provider behaviour by engine name.

Adding a new engine: implement a class with the ``SearchProvider`` Protocol
(or subclass ``_BaseSerpProvider``) and call ``SearchRouter.register``.
Nothing else outside this module needs to change.
"""
from __future__ import annotations

import calendar
import random
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable, Dict, List, Optional, Protocol, Tuple, Union
from urllib.parse import urlparse, parse_qs

import requests

import settings


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

class SearchError(Exception):
    """Raised when a search request or response fails."""


class TransientSearchError(SearchError):
    """A retryable failure (timeout, connection error, 429/5xx) that
    persisted after all retry attempts. `run_search` skips the current
    date window on this error instead of aborting the whole collection."""


SearchResult = Dict[str, Optional[Union[str, int]]]


@dataclass(frozen=True)
class SearchRequest:
    """Immutable description of a search to run.

    The orchestrator (`run_search`) consumes a ``SearchRequest`` and resolves
    the engine via ``SearchRouter`` — there is no engine-specific code path
    here.
    """

    api_key: str
    query: str
    engine: str = "google"
    lang: str = "fr"
    # Optional ISO 3166 country restriction (Google `gl` param). None means
    # language-only search (hl + lr) with no country bias — the default.
    gl: Optional[str] = None
    datestart: Optional[str] = None
    dateend: Optional[str] = None
    timestep: str = "week"
    sleep_seconds: float = 1.0
    progress_hook: Optional[Callable[[Optional[date], Optional[date], int], None]] = None


# ---------------------------------------------------------------------------
# Provider interface
# ---------------------------------------------------------------------------

class SearchProvider(Protocol):
    """What a search engine adapter must expose to the router."""

    name: str
    page_size: int
    supports_date_filter: bool
    # Whether the engine emits result dates that the controller should attempt
    # to parse for `published_at` upsert. Most SerpAPI engines do not.
    parses_result_dates: bool

    def build_locale_params(
        self,
        lang: str,
        start_index: int,
        page_size: int,
        *,
        use_date_filter: bool,
        gl: Optional[str] = None,
    ) -> Dict[str, Union[str, int]]: ...

    def build_date_filter_params(
        self,
        window_start: date,
        window_end: date,
    ) -> Dict[str, Union[str, int]]: ...

    def extract_next_index(
        self,
        payload: dict,
        current_index: int,
        results_len: int,
    ) -> Optional[int]: ...

    def is_empty_window_error(self, error_message: str) -> bool: ...


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class SearchRouter:
    """Process-wide registry mapping engine name → provider instance."""

    _providers: Dict[str, SearchProvider] = {}

    @classmethod
    def register(cls, provider: SearchProvider) -> None:
        cls._providers[provider.name] = provider

    @classmethod
    def get(cls, engine: str) -> SearchProvider:
        provider = cls._providers.get(engine)
        if provider is None:
            raise SearchError(f'Unsupported search engine "{engine}"')
        return provider

    @classmethod
    def engines(cls) -> frozenset:
        return frozenset(cls._providers.keys())


# ---------------------------------------------------------------------------
# Base SerpAPI provider — shared pagination logic
# ---------------------------------------------------------------------------

class _BaseSerpProvider:
    """Defaults shared by all SerpAPI-backed providers.

    The pagination heuristic mirrors the legacy `fetch_serpapi_url_list`
    behaviour:

    1. ``serpapi_pagination.next_offset`` if present (preferred, integer).
    2. Otherwise parse ``start|first|offset`` from ``next_link`` query string.
    3. Fall back to ``current + len(organic_results)`` increment.
    """

    name: str = ""
    page_size: int = 50
    supports_date_filter: bool = False
    parses_result_dates: bool = False

    def extract_next_index(
        self,
        payload: dict,
        current_index: int,
        results_len: int,
    ) -> Optional[int]:
        pagination = payload.get("serpapi_pagination") or {}
        next_link = pagination.get("next_link") or pagination.get("next")
        if not next_link:
            return None

        next_offset_raw = pagination.get("next_offset")
        if next_offset_raw is not None:
            try:
                candidate = int(next_offset_raw)
                if candidate > current_index:
                    return candidate
            except (TypeError, ValueError):
                pass

        if isinstance(next_link, str):
            try:
                parsed = urlparse(next_link)
                query_params = parse_qs(parsed.query)
            except Exception:
                query_params = {}
            for key in ("start", "first", "offset"):
                values = query_params.get(key)
                if not values:
                    continue
                try:
                    candidate = int(values[0])
                except (TypeError, ValueError):
                    continue
                if candidate > current_index:
                    return candidate

        if results_len > 0:
            return current_index + results_len
        return None

    def is_empty_window_error(self, error_message: str) -> bool:
        # SerpAPI puts this string in the `error` field (HTTP 200,
        # organic_results_state "Fully empty") when the engine has no
        # results for the current window OR pagination ran past the last
        # page (observed on Google with start=210, 2026-06-11). It is a
        # clean end-of-window signal, not a failure.
        return "hasn't returned any results" in (error_message or "").lower()

    def build_date_filter_params(
        self,
        window_start: date,
        window_end: date,
    ) -> Dict[str, Union[str, int]]:
        return {}


# ---------------------------------------------------------------------------
# Concrete providers
# ---------------------------------------------------------------------------

class GoogleProvider(_BaseSerpProvider):
    name = "google"
    page_size = 100
    supports_date_filter = True
    parses_result_dates = True  # SerpAPI's Google engine returns parseable date strings.

    _DOMAIN_BY_LANG = {
        "fr": "google.fr",
        "en": "google.com",
    }

    def build_locale_params(
        self,
        lang: str,
        start_index: int,
        page_size: int,
        *,
        use_date_filter: bool,
        gl: Optional[str] = None,
    ) -> Dict[str, Union[str, int]]:
        normalized = (lang or "fr").strip().lower() or "fr"
        params: Dict[str, Union[str, int]] = {
            "google_domain": self._DOMAIN_BY_LANG.get(normalized, "google.com"),
            "hl": normalized,
            "lr": f"lang_{normalized}",
            "safe": "off",
            "start": start_index,
        }
        # `gl` expects an ISO 3166 COUNTRY code and biases results toward
        # that country. Searches are language-scoped by default (hl + lr
        # only); the country restriction is opt-in (`land urlist --gl=us`).
        # The legacy behaviour of copying the language into `gl` broke
        # non-country language codes (SerpAPI rejects gl=en with a 400).
        if gl:
            params["gl"] = gl.strip().lower()
        # Legacy parity: when a date filter is active, Google ignores `num`.
        if not use_date_filter:
            params["num"] = page_size
        return params

    def build_date_filter_params(
        self,
        window_start: date,
        window_end: date,
    ) -> Dict[str, Union[str, int]]:
        return {
            "tbs": "cdr:1,cd_min:{},cd_max:{}".format(
                window_start.strftime("%m/%d/%Y"),
                window_end.strftime("%m/%d/%Y"),
            )
        }


class BingProvider(_BaseSerpProvider):
    name = "bing"
    page_size = 50
    supports_date_filter = False

    _MARKET_BY_LANG = {
        "fr": "fr-FR",
        "en": "en-US",
    }

    def build_locale_params(
        self,
        lang: str,
        start_index: int,
        page_size: int,
        *,
        use_date_filter: bool,
        gl: Optional[str] = None,  # Google-specific, ignored here.
    ) -> Dict[str, Union[str, int]]:
        normalized = (lang or "fr").strip().lower() or "fr"
        return {
            "mkt": self._MARKET_BY_LANG.get(normalized, "en-US"),
            "count": page_size,
            "first": start_index + 1,  # Bing pagination is 1-indexed.
        }


class DuckDuckGoProvider(_BaseSerpProvider):
    name = "duckduckgo"
    page_size = 50
    supports_date_filter = True

    _REGION_BY_LANG = {
        "fr": "fr-fr",
        "en": "us-en",
    }

    def build_locale_params(
        self,
        lang: str,
        start_index: int,
        page_size: int,
        *,
        use_date_filter: bool,
        gl: Optional[str] = None,  # Google-specific, ignored here.
    ) -> Dict[str, Union[str, int]]:
        normalized = (lang or "fr").strip().lower() or "fr"
        return {
            "kl": self._REGION_BY_LANG.get(normalized, "us-en"),
            "start": start_index,
            "m": page_size,
        }

    def build_date_filter_params(
        self,
        window_start: date,
        window_end: date,
    ) -> Dict[str, Union[str, int]]:
        return {
            "df": f"{window_start.isoformat()}..{window_end.isoformat()}"
        }


SearchRouter.register(GoogleProvider())
SearchRouter.register(BingProvider())
SearchRouter.register(DuckDuckGoProvider())


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise SearchError(f'Invalid date "{value}" — expected YYYY-MM-DD') from exc


def _advance_date(current: date, timestep: str) -> date:
    if timestep == "day":
        return current + timedelta(days=1)
    if timestep == "week":
        return current + timedelta(weeks=1)
    if timestep == "month":
        year = current.year + (current.month // 12)
        month = current.month % 12 + 1
        day = min(current.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)
    raise SearchError("timestep must be one of: day, week, month")


def _build_windows(
    datestart: Optional[str],
    dateend: Optional[str],
    timestep: str,
) -> List[Tuple[date, date]]:
    if not datestart or not dateend:
        return []

    start_date = _parse_date(datestart)
    end_date = _parse_date(dateend)
    if start_date > end_date:
        raise SearchError("datestart must be earlier than or equal to dateend")

    current_start = start_date
    step = (timestep or "week").strip().lower() or "week"
    windows: List[Tuple[date, date]] = []

    while current_start <= end_date:
        next_start = _advance_date(current_start, step)
        window_end = min(end_date, next_start - timedelta(days=1))
        windows.append((current_start, window_end))
        current_start = next_start

    return windows


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

# Statuses worth retrying: rate limit and server-side hiccups. Client
# errors (400 bad param, 401/403 bad key) fail fast — retrying cannot fix
# them and would burn quota.
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _redact_key(text: str) -> str:
    """Mask the api_key if it leaks into an error message (requests
    ConnectionError messages can embed the full request URL)."""
    return re.sub(r"api_key=[^&\s]+", "api_key=***", text)


def _http_get(params: Dict[str, Union[str, int]]) -> dict:
    """Issue the SerpAPI GET request and return the parsed JSON payload.

    Centralised so tests can monkey-patch a single seam. Transient
    failures (timeout, connection error, 429/5xx) are retried with
    exponential backoff: a single network hiccup must not abort a long
    multi-window collection whose earlier calls already spent quota.
    Raises `TransientSearchError` once attempts are exhausted so the
    orchestrator can skip the current window instead of aborting.
    """
    base_url = getattr(settings, "serpapi_base_url", "https://serpapi.com/search")
    timeout = getattr(settings, "serpapi_timeout", 15)
    max_attempts = max(1, int(getattr(settings, "serpapi_max_retries", 3)))

    last_error = "SerpAPI request failed"
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.get(base_url, params=params, timeout=timeout)
        except requests.RequestException as exc:
            last_error = _redact_key(f"HTTP error during SerpAPI request: {exc}")
        else:
            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError as exc:
                    raise SearchError("Invalid JSON payload returned by SerpAPI") from exc
            snippet = _redact_key(response.text[:200])
            last_error = (
                f"SerpAPI request failed with status {response.status_code}: {snippet}"
            )
            if response.status_code not in _RETRYABLE_STATUS:
                raise SearchError(last_error)
        if attempt < max_attempts:
            backoff = 2.0 * (2 ** (attempt - 1))  # 2s, 4s, 8s…
            print(
                f"[serpapi] attempt {attempt}/{max_attempts} failed, retrying "
                f"in {backoff:.0f}s — {last_error}",
                flush=True,
            )
            time.sleep(backoff)

    raise TransientSearchError(last_error)


def _jitter_sleep(base: float) -> None:
    effective = max(0.0, float(base)) * random.uniform(0.8, 1.2)
    if effective > 0:
        time.sleep(effective)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def _normalize_engine(engine: str) -> str:
    return (engine or "google").strip().lower() or "google"


def run_search(request: SearchRequest) -> List[SearchResult]:
    """Execute the search described by ``request`` and return the aggregated results.

    The orchestrator owns the pagination / date-window / jitter loop; engine
    behaviour is delegated to the provider returned by ``SearchRouter.get``.
    """
    normalized_query = (request.query or "").strip()
    if not normalized_query:
        raise SearchError("Query must be a non-empty string")

    provider = SearchRouter.get(_normalize_engine(request.engine))

    if bool(request.datestart) ^ bool(request.dateend):
        raise SearchError("Both datestart and dateend must be provided together")

    if (request.datestart or request.dateend) and not provider.supports_date_filter:
        raise SearchError(
            "Date filtering is only supported with the google or duckduckgo engines"
        )

    normalized_start: Optional[date] = None
    normalized_end: Optional[date] = None
    if request.datestart and request.dateend:
        normalized_start = _parse_date(request.datestart)
        normalized_end = _parse_date(request.dateend)
        if normalized_start > normalized_end:
            raise SearchError("datestart must be earlier than or equal to dateend")

    date_windows: List[Tuple[Optional[date], Optional[date]]] = []
    if provider.supports_date_filter and normalized_start and normalized_end:
        date_windows = list(_build_windows(request.datestart, request.dateend, request.timestep))
    if not date_windows:
        date_windows = [(normalized_start, normalized_end)]

    aggregated: List[SearchResult] = []
    lang = (request.lang or "fr").strip().lower() or "fr"
    gl = (request.gl or "").strip() or None
    failed_windows: List[str] = []

    for window_start, window_end in date_windows:
        start_index = 0
        window_count = 0
        use_date_filter = bool(window_start and window_end)

        try:
            while True:
                params: Dict[str, Union[str, int]] = {
                    "api_key": request.api_key,
                    "engine": provider.name,
                    "q": normalized_query,
                }
                params.update(provider.build_locale_params(
                    lang,
                    start_index,
                    provider.page_size,
                    use_date_filter=use_date_filter,
                    gl=gl,
                ))
                if use_date_filter:
                    params.update(provider.build_date_filter_params(window_start, window_end))

                payload = _http_get(params)

                if "error" in payload:
                    message = str(payload.get("error", "")).strip()
                    if provider.is_empty_window_error(message):
                        break
                    raise SearchError(f"SerpAPI error: {message}")

                organic = payload.get("organic_results") or []
                if not organic:
                    break

                for entry in organic:
                    aggregated.append({
                        "position": entry.get("position"),
                        "title": entry.get("title"),
                        "link": entry.get("link"),
                        "date": entry.get("date"),
                    })
                    window_count += 1

                next_index = provider.extract_next_index(payload, start_index, len(organic))
                if next_index is None or next_index <= start_index:
                    break
                start_index = next_index

                _jitter_sleep(request.sleep_seconds)
        except TransientSearchError as error:
            # A window lost to network trouble must not sink the whole
            # collection — quota was already spent on the previous windows
            # and their results are in `aggregated`. Partial results from
            # the failed window are kept too (SerpAPI bills per request).
            label = (
                f"{window_start.isoformat()} → {window_end.isoformat()}"
                if window_start and window_end else "no-date-filter"
            )
            failed_windows.append(label)
            print(
                f"[serpapi] window {label} abandoned after retries "
                f"({window_count} results kept): {error}",
                flush=True,
            )
        except SearchError as error:
            # Non-transient mid-run failure (quota exhausted, account
            # issue…): the remaining windows would fail the same way, so
            # stop here — but keep everything already collected, it was
            # billed. Only an immediately-failing run (nothing aggregated)
            # still raises, so a misconfigured command fails fast.
            if not aggregated:
                raise
            label = (
                f"{window_start.isoformat()} → {window_end.isoformat()}"
                if window_start and window_end else "no-date-filter"
            )
            failed_windows.append(label)
            print(
                f"[serpapi] fatal error on window {label}: {error} — "
                f"stopping the collection, keeping the {len(aggregated)} "
                "results already fetched",
                flush=True,
            )
            break

        if request.progress_hook:
            request.progress_hook(window_start, window_end, window_count)

    if failed_windows and not aggregated:
        raise SearchError(
            "All SerpAPI requests failed ({} window(s)): {}".format(
                len(failed_windows), "; ".join(failed_windows)
            )
        )
    if failed_windows:
        print(
            f"[serpapi] {len(failed_windows)}/{len(date_windows)} window(s) "
            f"failed and were skipped: {', '.join(failed_windows)} — re-run "
            "the same command with a narrower date range to backfill",
            flush=True,
        )

    return aggregated
