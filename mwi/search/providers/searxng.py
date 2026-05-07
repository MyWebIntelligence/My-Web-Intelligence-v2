"""SearXNG adapter — primary provider, self-hosted, no quota."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import List, Optional

import aiohttp

from mwi.search.models import ProviderStatus, SearchResult
from mwi.search.providers.base import BaseProvider


_LOG = logging.getLogger("mwi.search.searxng")


def _resolve_base_url() -> str:
    """Resolve the SearXNG base URL from env, settings, then default."""
    env = os.getenv("SEARXNG_BASE_URL")
    if env:
        return env.rstrip("/")
    try:
        import settings  # type: ignore
        url = getattr(settings, "SEARXNG_BASE_URL", None)
        if url:
            return url.rstrip("/")
    except ImportError:
        pass
    return "http://localhost:8888"


class SearxngProvider(BaseProvider):
    """Adapter for a self-hosted SearXNG instance (JSON API).

    The SearXNG JSON endpoint exposes ``GET /search?format=json`` and
    aggregates ~250 upstream engines. We hit it directly — no API key —
    and retry once with exponential back-off on HTTP 429 (limiter).
    """

    name = "searxng"
    monthly_quota = None  # self-hosted = unbounded
    timeout = 30.0

    def __init__(self, base_url: Optional[str] = None) -> None:
        super().__init__()
        self.base_url = (base_url or _resolve_base_url()).rstrip("/")

    def is_configured(self) -> bool:
        """SearXNG only needs a base URL — always considered configured.

        We do not ping the instance here; the router calls this synchronously
        at registration time. Connectivity is exercised on the first
        ``search()`` call and recorded via :attr:`last_status`.
        """
        return bool(self.base_url)

    async def search(
        self,
        session: aiohttp.ClientSession,
        query: str,
        num: int = 20,
        language: str = "fr",
    ) -> List[SearchResult]:
        """Hit ``/search?format=json`` and convert results to ``SearchResult``."""
        if not query or not query.strip():
            self._mark_error(ProviderStatus.ERROR, "empty query")
            return []

        await self._wait_politeness_window()

        params = {
            "q": query,
            "format": "json",
            "language": language,
            "safesearch": "0",
        }
        url = f"{self.base_url}/search"

        for attempt in range(2):
            try:
                async with session.get(
                    url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    if resp.status == 429:
                        # Limiter active — back off once then retry.
                        if attempt == 0:
                            await asyncio.sleep(1.5)
                            continue
                        self._mark_error(ProviderStatus.QUOTA_EXCEEDED,
                                         "rate-limited (HTTP 429)")
                        return []
                    if resp.status != 200:
                        self._mark_error(
                            ProviderStatus.ERROR,
                            f"unexpected HTTP {resp.status} from {url}",
                        )
                        return []

                    payload = await resp.json(content_type=None)
            except asyncio.TimeoutError:
                self._mark_error(ProviderStatus.ERROR, f"timeout after {self.timeout}s")
                return []
            except aiohttp.ClientError as exc:
                self._mark_error(ProviderStatus.ERROR, f"network error: {exc}")
                return []

            self._mark_call()
            self.last_status = ProviderStatus.OK
            return self._parse(payload, num)

        # Defensive — the loop only exits via return/continue.
        return []

    def _parse(self, payload: dict, num: int) -> List[SearchResult]:
        """Convert a SearXNG JSON payload into :class:`SearchResult` rows."""
        raw_results = payload.get("results") or []
        out: List[SearchResult] = []
        for idx, item in enumerate(raw_results[:num], start=1):
            url = item.get("url")
            if not url:
                continue
            out.append(SearchResult(
                url=url,
                title=item.get("title") or None,
                snippet=item.get("content") or None,
                rank=idx,
                providers=self.name,
                raw=item,
            ))
        return out


__all__ = ["SearxngProvider"]
