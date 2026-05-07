"""Brave Search adapter — proprietary index, 1 req/s on the free tier."""

from __future__ import annotations

import asyncio
import os
from typing import List, Optional

import aiohttp

from mwi.search.models import ProviderStatus, SearchResult
from mwi.search.providers.base import BaseProvider


_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"


def _resolve_api_key() -> Optional[str]:
    key = os.getenv("BRAVE_API_KEY")
    if key:
        return key
    try:
        import settings  # type: ignore
        return getattr(settings, "BRAVE_API_KEY", None)
    except ImportError:
        return None


class BraveProvider(BaseProvider):
    """Adapter for the Brave Search API.

    Authentication header: ``X-Subscription-Token``. Free tier limits
    requests to ~1 per second; we throttle locally accordingly.
    """

    name = "brave"
    monthly_quota = 1000  # informative — adjust if the user has paid credits
    min_delay_between_calls = 1.0
    timeout = 30.0

    def __init__(self, api_key: Optional[str] = None) -> None:
        super().__init__()
        self.api_key = api_key if api_key is not None else _resolve_api_key()

    def is_configured(self) -> bool:
        if not self.api_key:
            self.last_status = ProviderStatus.NOT_CONFIGURED
            return False
        return True

    async def search(
        self,
        session: aiohttp.ClientSession,
        query: str,
        num: int = 20,
        language: str = "fr",
    ) -> List[SearchResult]:
        if not self.is_configured():
            return []
        if not query or not query.strip():
            self._mark_error(ProviderStatus.ERROR, "empty query")
            return []

        await self._wait_politeness_window()

        params = {
            "q": query,
            "count": str(min(int(num), 20)),  # Brave caps at 20 / page
            "search_lang": language,
            "safesearch": "off",
        }
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self.api_key or "",
        }

        try:
            async with session.get(
                _ENDPOINT,
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as resp:
                if resp.status in (402, 429):
                    self._mark_error(
                        ProviderStatus.QUOTA_EXCEEDED,
                        f"quota / rate-limit (HTTP {resp.status})",
                    )
                    return []
                if resp.status == 401:
                    self._mark_error(ProviderStatus.NOT_CONFIGURED, "invalid API key")
                    return []
                if resp.status != 200:
                    self._mark_error(
                        ProviderStatus.ERROR,
                        f"unexpected HTTP {resp.status}",
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

    def _parse(self, payload: dict, num: int) -> List[SearchResult]:
        web = (payload or {}).get("web") or {}
        items = web.get("results") or []
        out: List[SearchResult] = []
        for idx, item in enumerate(items[:num], start=1):
            url = item.get("url")
            if not url:
                continue
            out.append(SearchResult(
                url=url,
                title=item.get("title") or None,
                snippet=item.get("description") or None,
                rank=idx,
                providers=self.name,
                raw=item,
            ))
        return out


__all__ = ["BraveProvider"]
