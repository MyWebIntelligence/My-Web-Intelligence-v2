"""Tavily adapter — LLM-tailored search with extracted content."""

from __future__ import annotations

import asyncio
import os
from typing import List, Optional

import aiohttp

from mwi.search.models import ProviderStatus, SearchResult
from mwi.search.providers.base import BaseProvider


_ENDPOINT = "https://api.tavily.com/search"


def _resolve_api_key() -> Optional[str]:
    key = os.getenv("TAVILY_API_KEY")
    if key:
        return key
    try:
        import settings  # type: ignore
        return getattr(settings, "TAVILY_API_KEY", None)
    except ImportError:
        return None


class TavilyProvider(BaseProvider):
    """Adapter for the Tavily Search API.

    Authentication: ``api_key`` field in the JSON POST body.
    Free tier: 1 000 credits/month.
    """

    name = "tavily"
    monthly_quota = 1000
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
            "api_key": self.api_key or "",
            "query": query,
            "search_depth": "basic",
            "max_results": int(num),
            "include_answer": False,
            "include_raw_content": False,
        }
        headers = {"Content-Type": "application/json"}

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
        items = (payload or {}).get("results") or []
        out: List[SearchResult] = []
        for idx, item in enumerate(items[:num], start=1):
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


__all__ = ["TavilyProvider"]
