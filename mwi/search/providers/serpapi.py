"""SerpAPI adapter — used by ``search run``.

Distinct from the snake-case ``settings.serpapi_api_key`` consumed by the
historical ``land urlist`` command. The fallback chain is:

1. ``BaseProvider`` constructor argument.
2. ``SERPAPI_API_KEY`` env var (UPPER, new).
3. ``settings.SERPAPI_API_KEY`` (UPPER, new).
4. ``settings.serpapi_api_key`` (snake-case, historical) — for a soft
   transition period.
"""

from __future__ import annotations

import asyncio
import os
from typing import List, Optional

import aiohttp

from mwi.search.models import ProviderStatus, SearchResult
from mwi.search.providers.base import BaseProvider


_ENDPOINT = "https://serpapi.com/search.json"


def _resolve_api_key() -> Optional[str]:
    key = os.getenv("SERPAPI_API_KEY")
    if key:
        return key
    try:
        import settings  # type: ignore
        upper = getattr(settings, "SERPAPI_API_KEY", None)
        if upper:
            return upper
        # Soft fallback to the historical snake-case key.
        legacy = getattr(settings, "serpapi_api_key", None)
        if legacy:
            return legacy
    except ImportError:
        pass
    return None


class SerpApiProvider(BaseProvider):
    """Adapter for serpapi.com (multi-engine SERP API).

    Free tier: 100 requests/month. Authentication is via the ``api_key``
    query-string parameter.
    """

    name = "serpapi"
    monthly_quota = 100
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
            "engine": "google",
            "q": query,
            "num": str(int(num)),
            "hl": language,
            "api_key": self.api_key or "",
        }

        try:
            async with session.get(
                _ENDPOINT,
                params=params,
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

        # SerpAPI may surface quota errors in the payload with HTTP 200.
        if isinstance(payload, dict) and payload.get("error"):
            err = str(payload["error"]).lower()
            if "monthly" in err or "limit" in err or "quota" in err:
                self._mark_error(ProviderStatus.QUOTA_EXCEEDED, payload["error"])
                return []
            self._mark_error(ProviderStatus.ERROR, payload["error"])
            return []

        self._mark_call()
        self.last_status = ProviderStatus.OK
        return self._parse(payload, num)

    def _parse(self, payload: dict, num: int) -> List[SearchResult]:
        items = (payload or {}).get("organic_results") or []
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


__all__ = ["SerpApiProvider"]
