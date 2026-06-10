"""HTTP fetch pipeline for MyWebIntelligence.

Single entry point for all HTML retrieval. The crawl loop in
:mod:`mwi.core` calls :func:`fetch_html`, which orchestrates a chain of
strategies: a primary `aiohttp` request, and (when nothing else worked) an
archive.org Wayback fallback. New strategies (curl_cffi, Playwright HTML)
will plug into the same chain in upcoming sprints.

Sprint 1 scope: refactor only — the cascade behavior is identical to the
inline logic that lived in :func:`mwi.core.crawl_expression*`.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import List, Optional

import aiohttp
import requests
import settings


# ---------------------------------------------------------------------------
# Circuit breaker (kept here so all archive.org-aware code shares one state)
# ---------------------------------------------------------------------------

class _ArchiveOrgBreaker:
    """Process-wide circuit breaker for archive.org fallback calls.

    When archive.org has an outage (frequent since 2024), each fallback
    times out after ~10s. On a Land with thousands of failed crawls that
    adds up to hours of wasted blocking calls.

    Tracks consecutive failures and opens the circuit after
    ``OPEN_THRESHOLD`` failures. While open, callers skip the fallback
    entirely. After ``COOLDOWN_SEC`` of inactivity the breaker resets so a
    recovered service can be used again. A single success outside the
    cooldown also closes it.

    Failure semantics: only true service failures (network exception,
    timeout, snapshot download empty) increment the counter. The
    ``archived_snapshots: {}`` response — meaning "Wayback has no
    snapshot for this URL" — is a *neutral* outcome (the API answered
    correctly, it just had no data) and does NOT trip the breaker.
    Otherwise a Land full of dead URLs without Wayback coverage would
    open the breaker even when archive.org is perfectly healthy.

    Thread-safe in CPython for these simple read/writes (GIL).
    """
    failures: int = 0
    last_failure_ts: float = 0.0
    OPEN_THRESHOLD: int = 5
    COOLDOWN_SEC: float = 300.0

    @classmethod
    def is_open(cls) -> bool:
        if cls.failures < cls.OPEN_THRESHOLD:
            return False
        if time.time() - cls.last_failure_ts > cls.COOLDOWN_SEC:
            cls.failures = 0
            return False
        return True

    @classmethod
    def record_failure(cls) -> None:
        cls.failures += 1
        cls.last_failure_ts = time.time()

    @classmethod
    def record_success(cls) -> None:
        cls.failures = 0

    @classmethod
    def reset(cls) -> None:
        """Force-reset (used by tests)."""
        cls.failures = 0
        cls.last_failure_ts = 0.0


# ---------------------------------------------------------------------------
# Fetch result + strategy contract
# ---------------------------------------------------------------------------

@dataclass
class FetchResult:
    """Outcome of a fetch attempt for a single URL.

    Attributes:
        url: The URL that was requested (the original, not any snapshot).
        status_code: HTTP status as a string. Conventional values:
            ``"200"`` etc. for real responses, ``"000"`` for connection
            errors, ``"ERR"`` for unhandled exceptions.
        html: Raw HTML body, or ``None`` if no body was retrieved.
        method_used: Identifier of the strategy that produced this result.
            One of ``"aiohttp"`` / ``"archive_org"`` for now; future
            sprints add ``"curl_cffi"``, ``"playwright"``.
        error: Human-readable error message when ``html is None``.
    """
    url: str
    status_code: str
    html: Optional[str]
    method_used: str
    error: Optional[str] = None


class FetchStrategy:
    """Base class for fetch strategies.

    Subclasses implement :meth:`fetch` and return a :class:`FetchResult`
    on success (HTML retrieved), or ``None`` to defer to the next
    strategy in the chain.

    The ``only_on_retry`` class attribute marks strategies that should
    only be invoked when the previous attempt produced a status code
    matching ``settings.crawl_retry_status_codes`` (e.g. 403/429/ERR).
    Strategies that always run regardless (the primary aiohttp,
    archive.org as a last resort) keep ``only_on_retry = False``.
    """

    name: str = "base"
    only_on_retry: bool = False

    async def fetch(self, url: str) -> Optional[FetchResult]:
        raise NotImplementedError


# Default retry trigger codes when ``settings.crawl_retry_status_codes``
# is not set. Lists the symptoms typical of TLS/JS bot detection or
# transient origin failures worth retrying with a heavier strategy.
DEFAULT_RETRY_STATUS_CODES = frozenset({
    "403", "406", "429", "503",
    "520", "521", "523", "526",
    "ERR",
})


# ---------------------------------------------------------------------------
# Strategy 0: aiohttp (primary)
# ---------------------------------------------------------------------------

class AiohttpStrategy(FetchStrategy):
    """Direct asynchronous fetch using the shared aiohttp session.

    Returns a :class:`FetchResult` with ``html`` set when the response is
    ``200`` and the content-type contains ``html``. For any other case
    (non-200, connection error, exception) it still returns a result so
    the caller can record the HTTP status; the next strategies will
    decide whether to retry.
    """

    name = "aiohttp"

    def __init__(self, session: aiohttp.ClientSession,
                 timeout: float = 15.0,
                 user_agent: Optional[str] = None):
        self._session = session
        self._timeout = timeout
        self._user_agent = user_agent if user_agent is not None else getattr(settings, 'user_agent', '')

    async def fetch(self, url: str) -> Optional[FetchResult]:
        headers = {"User-Agent": self._user_agent}
        try:
            async with self._session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self._timeout),
            ) as response:
                status = str(response.status)
                content_type = response.headers.get('content-type', '')
                if response.status == 200 and 'html' in content_type:
                    html = await response.text()
                    return FetchResult(url=url, status_code=status,
                                       html=html, method_used=self.name)
                # Non-200 or non-HTML: report status for the caller log
                print(f"Direct request for {url} returned status {status}")
                return FetchResult(url=url, status_code=status,
                                   html=None, method_used=self.name)
        except aiohttp.ClientError as e:
            print(f"ClientError for {url}: {e}. Status: 000.")
            return FetchResult(url=url, status_code="000",
                               html=None, method_used=self.name, error=str(e))
        except Exception as e:
            print(f"Generic exception during initial fetch for {url}: {e}")
            return FetchResult(url=url, status_code="ERR",
                               html=None, method_used=self.name, error=str(e))


# ---------------------------------------------------------------------------
# Strategy 1: curl_cffi (TLS-impersonating retry on bot-detection codes)
# ---------------------------------------------------------------------------

class CurlCffiStrategy(FetchStrategy):
    """Retry using ``curl_cffi`` with a real browser TLS fingerprint.

    Triggered by the orchestrator only when the previous strategy
    returned a status code in the retry set (typically 403/429/ERR
    caused by Cloudflare TLS/JA3 detection). Imitates Chrome's TLS
    handshake via curl-impersonate, which passes most Cloudflare
    deployments.

    Failures are non-fatal: any unexpected exception (network, parsing,
    library missing) yields a ``FetchResult(status_code='ERR', html=None)``
    so the next strategy in the chain (Playwright, archive.org) gets a
    chance.
    """

    name = "curl_cffi"
    only_on_retry = True

    def __init__(self, impersonate: Optional[str] = None,
                 timeout: Optional[float] = None):
        self._impersonate = impersonate or getattr(
            settings, 'crawl_fallback_curl_cffi_impersonate', 'chrome120'
        )
        self._timeout = timeout if timeout is not None else 15.0

    async def fetch(self, url: str) -> Optional[FetchResult]:
        try:
            from curl_cffi.requests import AsyncSession
        except ImportError:
            print(f"curl_cffi not installed; skipping fallback for {url}")
            return None

        try:
            async with AsyncSession() as s:
                r = await s.get(
                    url,
                    impersonate=self._impersonate,
                    timeout=self._timeout,
                )
            status = str(r.status_code)
            content_type = (r.headers.get('content-type') or '').lower()
            if r.status_code == 200 and 'html' in content_type:
                print(f"curl_cffi fallback succeeded for {url}")
                return FetchResult(
                    url=url, status_code=status,
                    html=r.text, method_used=self.name,
                )
            print(f"curl_cffi fallback returned status {status} for {url}")
            return FetchResult(
                url=url, status_code=status,
                html=None, method_used=self.name,
            )
        except Exception as e:
            print(f"curl_cffi fallback error for {url}: {e}")
            return FetchResult(
                url=url, status_code="ERR",
                html=None, method_used=self.name, error=str(e),
            )


# ---------------------------------------------------------------------------
# Strategy 2: Playwright (real browser, last resort before archive.org)
# ---------------------------------------------------------------------------

class PlaywrightStrategy(FetchStrategy):
    """Retry using a real headless Chromium via the shared :class:`BrowserPool`.

    Triggered by the orchestrator only after both aiohttp and curl_cffi
    have failed with a status in ``crawl_retry_status_codes``. Used to
    handle Cloudflare's JavaScript challenge (``cf_clearance`` cookie),
    which TLS-impersonating clients cannot solve.

    Cost: ~3-5 seconds per page (browser navigation + JS execution +
    networkidle wait). Therefore opt-in via
    ``settings.crawl_fallback_playwright`` (default OFF).
    """

    name = "playwright"
    only_on_retry = True

    # Heuristics for Cloudflare's "Checking your browser" interstitial.
    _CF_CHALLENGE_MARKERS = (
        "Just a moment",
        "Checking your browser",
        "cf-browser-verification",
        "cf-challenge-running",
    )

    def __init__(self, pool=None, timeout_sec: Optional[float] = None):
        self._pool = pool  # injection for tests; otherwise use the singleton
        self._timeout_sec = timeout_sec if timeout_sec is not None else float(
            getattr(settings, 'crawl_fallback_playwright_timeout_sec', 30)
        )

    def _get_pool(self):
        if self._pool is not None:
            return self._pool
        from mwi.browser_pool import BrowserPool, PLAYWRIGHT_AVAILABLE
        if not PLAYWRIGHT_AVAILABLE:
            return None
        return BrowserPool.get()

    async def fetch(self, url: str) -> Optional[FetchResult]:
        pool = self._get_pool()
        if pool is None:
            print(f"Playwright not available; skipping fallback for {url}")
            return None

        try:
            timeout_ms = int(self._timeout_sec * 1000)
            async with pool.page() as page:
                response = await page.goto(
                    url,
                    wait_until='domcontentloaded',
                    timeout=timeout_ms,
                )
                # Wait for the page to settle. networkidle can hang on
                # streaming endpoints, so we cap it strictly.
                try:
                    await page.wait_for_load_state(
                        'networkidle',
                        timeout=min(timeout_ms, 10000),
                    )
                except Exception:
                    pass  # not fatal — we still have DOM content

                # Cloudflare interstitial check: wait up to 15s for it to
                # disappear before capturing the body.
                content = await page.content()
                if any(marker in content for marker in self._CF_CHALLENGE_MARKERS):
                    try:
                        await page.wait_for_function(
                            "() => !document.body.innerText.includes('Just a moment')"
                            " && !document.body.innerText.includes('Checking your browser')",
                            timeout=15000,
                        )
                        content = await page.content()
                    except Exception:
                        pass  # CF still won — we report what we have

                status_code = str(response.status) if response is not None else "200"
                if response is not None and response.status == 200 and content:
                    print(f"Playwright fallback succeeded for {url}")
                    return FetchResult(
                        url=url, status_code=status_code,
                        html=content, method_used=self.name,
                    )
                # Got a response but not a usable 200 (e.g. challenge
                # held us at 403/503). Surface the status, no HTML.
                if response is not None:
                    print(f"Playwright fallback returned status {status_code} for {url}")
                    return FetchResult(
                        url=url, status_code=status_code,
                        html=None, method_used=self.name,
                    )
                return None
        except Exception as e:
            print(f"Playwright fallback error for {url}: {e}")
            return FetchResult(
                url=url, status_code="ERR",
                html=None, method_used=self.name, error=str(e),
            )


# ---------------------------------------------------------------------------
# Strategy: archive.org fallback (Wayback snapshot)
# ---------------------------------------------------------------------------

class ArchiveOrgStrategy(FetchStrategy):
    """Wayback Machine fallback.

    Asks ``archive.org/wayback/available`` for the closest snapshot of
    ``url`` and downloads it via :func:`trafilatura.fetch_url` (network
    only — extraction stays in :mod:`mwi.core`). Honors
    :class:`_ArchiveOrgBreaker`: when the breaker is open, returns
    ``None`` immediately so the chain can move on.

    Skipped when the input URL is itself a Wayback wrapper (we don't ask
    for an archive of an archive).
    """

    name = "archive_org"

    def __init__(self, timeout: Optional[float] = None):
        self._timeout = timeout if timeout is not None else float(getattr(settings, 'default_timeout', 10))

    async def fetch(self, url: str) -> Optional[FetchResult]:
        # Don't archive an archive
        from mwi.url_normalizer import is_archive_wrapper
        if is_archive_wrapper(url):
            return None
        if _ArchiveOrgBreaker.is_open():
            print(f"Skipping archive.org fallback (breaker open) for {url}")
            return None

        # Lazy import to avoid pulling trafilatura in unrelated paths
        import trafilatura

        try:
            print(f"Trying URL-based fallback: archive.org for {url}")
            archive_data_url = f"http://archive.org/wayback/available?url={url}"
            archive_response = await asyncio.to_thread(
                lambda: requests.get(archive_data_url, timeout=10)
            )
            archive_response.raise_for_status()
            archive_data = archive_response.json()
            archived_url = (
                archive_data.get('archived_snapshots', {})
                            .get('closest', {})
                            .get('url')
            )
            if not archived_url:
                # Service answered correctly: Wayback simply has no snapshot
                # for this URL. This is a neutral outcome, not a service
                # failure — do not trip the breaker on Lands full of dead
                # URLs without archive coverage.
                return None

            downloaded = await asyncio.wait_for(
                asyncio.to_thread(trafilatura.fetch_url, archived_url),
                timeout=self._timeout,
            )
            if not downloaded:
                _ArchiveOrgBreaker.record_failure()
                return None

            _ArchiveOrgBreaker.record_success()
            return FetchResult(url=url, status_code="200",
                               html=downloaded, method_used=self.name)
        except Exception as e:
            _ArchiveOrgBreaker.record_failure()
            print(f"Archive.org fallback failed for {url}: {e}")
            return None


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def default_chain(session: aiohttp.ClientSession) -> List[FetchStrategy]:
    """Default strategy chain for production crawls.

    Order:
      0. AiohttpStrategy — always runs first.
      1. CurlCffiStrategy — TLS-impersonating retry on bot-detection
         status codes; opt-out via ``settings.crawl_fallback_curl_cffi``.
      2. PlaywrightStrategy — real browser for Cloudflare JS challenges;
         opt-in via ``settings.crawl_fallback_playwright`` (off by default
         because each invocation costs ~3-5s).
      3. ArchiveOrgStrategy — last resort (live unreachable, breaker
         honored).
    """
    chain: List[FetchStrategy] = [AiohttpStrategy(session)]
    if getattr(settings, 'crawl_fallback_curl_cffi', True):
        chain.append(CurlCffiStrategy())
    if getattr(settings, 'crawl_fallback_playwright', False):
        chain.append(PlaywrightStrategy())
    chain.append(ArchiveOrgStrategy())
    return chain


def _retry_codes() -> frozenset:
    """Read the configured retry status codes (or fall back to the default)."""
    raw = getattr(settings, 'crawl_retry_status_codes', None)
    if raw is None:
        return DEFAULT_RETRY_STATUS_CODES
    return frozenset(str(c) for c in raw)


async def fetch_html(url: str,
                     session: aiohttp.ClientSession,
                     strategies: Optional[List[FetchStrategy]] = None,
                     retry_codes: Optional[frozenset] = None) -> FetchResult:
    """Run the strategy chain until one returns HTML, or all are exhausted.

    Cascade rules:
      * The first strategy always runs.
      * Strategies with ``only_on_retry=True`` are skipped unless the
        previous status code is in ``retry_codes``.
      * Other strategies (e.g. archive.org) run whenever no HTML has been
        recovered yet.
      * The ``status_code`` of the returned :class:`FetchResult` reflects
        the strategy that actually delivered the HTML. If aiohttp returned
        403 but curl_cffi rescued the page with a 200, we report 200 and
        ``method_used='curl_cffi'``. The caller can detect "primary
        failed" via ``method_used != 'aiohttp'``. When all strategies
        fail, we report the first attempt's status (the live URL's
        reality).
    """
    if strategies is None:
        strategies = default_chain(session)
    if retry_codes is None:
        retry_codes = _retry_codes()

    first_result: Optional[FetchResult] = None
    last_status: Optional[str] = None
    for strategy in strategies:
        # Skip retry-only strategies when previous attempt didn't fail
        # in a way that warrants a heavier retry.
        if strategy.only_on_retry:
            if last_status is None or last_status not in retry_codes:
                continue

        result = await strategy.fetch(url)
        if result is None:
            continue
        if first_result is None:
            first_result = result
        last_status = result.status_code
        if result.html:
            return result

    if first_result is not None:
        return first_result
    return FetchResult(url=url, status_code="ERR", html=None,
                       method_used="none", error="no strategies ran")
