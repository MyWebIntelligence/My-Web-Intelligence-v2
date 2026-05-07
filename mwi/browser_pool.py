"""Shared headless-browser pool for MyWebIntelligence.

Runs **one** Chromium instance per process and lends pages on demand,
bounded by a semaphore. Used by:

  * ``mwi.fetcher.PlaywrightStrategy`` — last-resort HTML fetch when
    aiohttp and curl_cffi both lose to a JavaScript challenge.
  * Optionally by ``mwi.core.extract_dynamic_medias`` (Sprint 3 phase
    3b) to stop spinning up a new browser per expression.

Design notes:

  * Lazy: nothing happens until the first ``page()`` call.
  * Single browser, multiple pages: avoids the ~1 s launch cost per
    expression. Each crawled URL gets a fresh, isolated context.
  * Semaphore-bounded: ``settings.crawl_fallback_playwright_max_concurrent``
    caps the number of pages alive at the same time so memory stays
    predictable on long crawls.
  * Process-wide singleton: tests can swap it via
    ``BrowserPool._instance = ...`` for injection.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Optional

import settings

try:
    from playwright.async_api import async_playwright  # type: ignore
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    async_playwright = None  # type: ignore
    PLAYWRIGHT_AVAILABLE = False


class BrowserPool:
    """Lazy singleton wrapping a single Chromium instance + page semaphore."""

    _instance: Optional["BrowserPool"] = None

    def __init__(self, max_concurrent: Optional[int] = None,
                 user_agent: Optional[str] = None):
        self._playwright = None
        self._browser = None
        self._lock = asyncio.Lock()
        self._max_concurrent = max_concurrent if max_concurrent is not None else int(
            getattr(settings, 'crawl_fallback_playwright_max_concurrent', 4)
        )
        self._semaphore = asyncio.Semaphore(self._max_concurrent)
        self._user_agent = user_agent or getattr(settings, 'user_agent', '') or ''

    # ----- Singleton accessor -------------------------------------------------

    @classmethod
    def get(cls) -> "BrowserPool":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Drop the singleton (used by tests)."""
        cls._instance = None

    # ----- Lifecycle ----------------------------------------------------------

    async def _ensure_started(self) -> None:
        """Lazily launch Playwright + Chromium under the lock."""
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright not installed; cannot start BrowserPool")
        if self._browser is not None:
            return
        async with self._lock:
            if self._browser is not None:
                return
            self._playwright = await async_playwright().start()  # type: ignore
            self._browser = await self._playwright.chromium.launch(headless=True)

    async def shutdown(self) -> None:
        """Close the browser and Playwright cleanly. Idempotent."""
        async with self._lock:
            if self._browser is not None:
                try:
                    await self._browser.close()
                except Exception:
                    pass
                self._browser = None
            if self._playwright is not None:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass
                self._playwright = None

    # ----- Page borrow --------------------------------------------------------

    @asynccontextmanager
    async def page(self):
        """Borrow a fresh page, bounded by the concurrency semaphore.

        Yields a ``playwright.async_api.Page``. The semaphore is released
        and the page is closed when the context exits, even on error.
        """
        await self._ensure_started()
        async with self._semaphore:
            context = await self._browser.new_context(  # type: ignore[union-attr]
                user_agent=self._user_agent or None,
            )
            page = await context.new_page()
            try:
                yield page
            finally:
                try:
                    await page.close()
                finally:
                    await context.close()
