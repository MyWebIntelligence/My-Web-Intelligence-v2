"""Tests for sprint-403 Sprint 3b — extract_dynamic_medias uses BrowserPool.

Locks the contract that ``mwi.core.extract_dynamic_medias`` borrows pages
from the shared ``BrowserPool`` instead of launching its own Chromium per
call. The win is ~1-2 s/page on long crawls where dynamic media extraction
is enabled.
"""

import asyncio
from contextlib import asynccontextmanager

import pytest


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Fake page + pool
# ---------------------------------------------------------------------------

class _FakeElement:
    def __init__(self, attrs):
        self._attrs = attrs

    async def get_attribute(self, name):
        return self._attrs.get(name)


class _FakePage:
    """Minimal Playwright Page stub for extract_dynamic_medias."""

    def __init__(self, img_srcs=None):
        self._img_srcs = img_srcs or []
        self.goto_calls = 0

    async def goto(self, url, **kwargs):
        self.goto_calls += 1
        return None

    async def wait_for_load_state(self, *_a, **_kw):
        return None

    async def wait_for_timeout(self, *_a):
        return None

    async def query_selector_all(self, selector):
        if selector == 'img[src]':
            return [_FakeElement({'src': s}) for s in self._img_srcs]
        return []


class _SharedFakePool:
    """Stand-in BrowserPool that counts how many pages it lent."""

    def __init__(self, page_factory):
        self._page_factory = page_factory
        self.page_calls = 0
        self.shutdown_calls = 0

    @asynccontextmanager
    async def page(self):
        self.page_calls += 1
        yield self._page_factory()

    async def shutdown(self):
        self.shutdown_calls += 1


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestExtractDynamicMediasUsesPool:
    def test_borrows_page_from_pool(self, fresh_db, monkeypatch):
        """extract_dynamic_medias goes through BrowserPool.get().page()."""
        m = fresh_db["model"]
        core = fresh_db["core"]

        domain = m.Domain.create(name="dyn-pool.com")
        land = m.Land.create(name="dyn_pool", description="t", lang="fr")
        expr = m.Expression.create(land=land, domain=domain,
                                   url="https://dyn-pool.com/x")

        page = _FakePage(img_srcs=['https://cdn.test/a.jpg'])
        pool = _SharedFakePool(lambda: page)

        # Inject the fake as the singleton
        from mwi.browser_pool import BrowserPool
        monkeypatch.setattr(BrowserPool, "_instance", pool)
        monkeypatch.setattr('mwi.core.PLAYWRIGHT_AVAILABLE', True)
        monkeypatch.setattr('mwi.browser_pool.PLAYWRIGHT_AVAILABLE', True)

        urls = run(core.extract_dynamic_medias("https://dyn-pool.com/x", expr))

        assert pool.page_calls == 1, "should borrow exactly one page from the pool"
        assert urls == ['https://cdn.test/a.jpg']
        assert page.goto_calls == 1

    def test_two_calls_share_the_same_pool(self, fresh_db, monkeypatch):
        """The pool is reused across calls; no per-call browser launch."""
        m = fresh_db["model"]
        core = fresh_db["core"]

        domain = m.Domain.create(name="dyn-share.com")
        land = m.Land.create(name="dyn_share", description="t", lang="fr")
        expr1 = m.Expression.create(land=land, domain=domain,
                                    url="https://dyn-share.com/a")
        expr2 = m.Expression.create(land=land, domain=domain,
                                    url="https://dyn-share.com/b")

        pool = _SharedFakePool(lambda: _FakePage(img_srcs=[]))

        from mwi.browser_pool import BrowserPool
        monkeypatch.setattr(BrowserPool, "_instance", pool)
        monkeypatch.setattr('mwi.core.PLAYWRIGHT_AVAILABLE', True)
        monkeypatch.setattr('mwi.browser_pool.PLAYWRIGHT_AVAILABLE', True)

        run(core.extract_dynamic_medias("https://dyn-share.com/a", expr1))
        run(core.extract_dynamic_medias("https://dyn-share.com/b", expr2))

        assert pool.page_calls == 2

    def test_returns_empty_when_playwright_unavailable(self, fresh_db, monkeypatch):
        """No PLAYWRIGHT_AVAILABLE → graceful empty list, no pool touched."""
        m = fresh_db["model"]
        core = fresh_db["core"]

        domain = m.Domain.create(name="dyn-noplay.com")
        land = m.Land.create(name="dyn_noplay", description="t", lang="fr")
        expr = m.Expression.create(land=land, domain=domain,
                                   url="https://dyn-noplay.com/x")

        monkeypatch.setattr('mwi.core.PLAYWRIGHT_AVAILABLE', False)

        urls = run(core.extract_dynamic_medias("https://dyn-noplay.com/x", expr))
        assert urls == []
