"""Serper.dev adapter — Google search results via a JSON POST endpoint."""

from __future__ import annotations

import asyncio
import os
from typing import List, Optional

import aiohttp

from mwi.search.models import ProviderStatus, SearchResult
from mwi.search.providers.base import BaseProvider


_ENDPOINT = "https://google.serper.dev/search"


def _resolve_api_key() -> Optional[str]:
    key = os.getenv("SERPER_API_KEY")
    if key:
        return key
    try:
        import settings  # type: ignore
        return getattr(settings, "SERPER_API_KEY", None)
    except ImportError:
        return None


class SerperProvider(BaseProvider):
    """Adapter for the Serper.dev API (Google SERP scraper).

    Authentication header: ``X-API-KEY``. Free tier offers a one-time
    2 500 credits — informative ``monthly_quota`` only.
    """

    name = "serper"
    monthly_quota = 2500
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

        body = {
            "q": query,
            "num": int(num),
            "hl": language,
        }
        headers = {
            "X-API-KEY": self.api_key or "",
            "Content-Type": "application/json",
        }

        try:
            async with session.post(
                _ENDPOINT,
                json=body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as resp:
                if resp.status in (402, 429):
                    self._mark_error(
                        ProviderStatus.QUOTA_EXCEEDED,
                        f"quota / rate-limit (HTTP {resp.status})",
                    )
                    return []
                if resp.status in (401, 403):
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
        items = (payload or {}).get("organic") or []
        out: List[SearchResult] = []
        for idx, item in enumerate(items[:num], start=1):
            url = item.get("link")
            if not url:
                continue
            out.append(SearchResult(
                url=url,
                title=item.get("title") or None,
                snippet=item.get("snippet") or None,
                rank=int(item.get("position") or idx),
                providers=self.name,
                raw=item,
            ))
        return out


__all__ = ["SerperProvider"]
