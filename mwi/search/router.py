"""Multi-API search router — orchestrates a list of provider adapters."""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, Iterable, List, Optional

import aiohttp

from mwi.search.models import ProviderStatus, ProviderUsage, SearchResult
from mwi.search.providers.base import BaseProvider
from mwi.search.utils import merge_results


_LOG = logging.getLogger("mwi.search.router")


class SearchRouter:
    """Orchestrate a set of search-provider adapters.

    Two strategies are supported:

    - ``fallback``: try providers in registration order, return as soon as
      one of them yields ≥ 1 result. Used to preserve quotas.
    - ``parallel``: query every configured provider concurrently, then merge
      and dedup the results. Used for triangulation.

    Only configured providers are kept (``is_configured()`` filter applied
    at registration). The router never raises on provider failures; it logs
    and moves on. Counters and last status remain accessible via
    :meth:`usage_report`.
    """

    DEFAULT_TIMEOUT = 30
    SUPPORTED_STRATEGIES = ("fallback", "parallel")

    def __init__(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        self._providers: List[BaseProvider] = []
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Provider management
    # ------------------------------------------------------------------

    def register(self, provider: BaseProvider) -> bool:
        """Register a provider if it reports as configured.

        The router's configured ``timeout`` is propagated onto the provider
        instance so that the per-request ``ClientTimeout`` each adapter
        builds (``ClientTimeout(total=self.timeout)``) honours
        ``settings.SEARCH_PROVIDER_TIMEOUT``.

        Returns ``True`` when the provider was registered, ``False``
        otherwise. Already-registered providers (same ``name``) are
        rejected silently.
        """
        if not provider.is_configured():
            _LOG.info("router: skipping unconfigured provider %s", provider.name)
            return False
        if any(p.name == provider.name for p in self._providers):
            _LOG.info("router: provider %s already registered", provider.name)
            return False
        provider.timeout = self._timeout
        self._providers.append(provider)
        return True

    @property
    def providers(self) -> List[BaseProvider]:
        """Return the list of currently registered providers."""
        return list(self._providers)

    @property
    def provider_names(self) -> List[str]:
        """Return the list of registered provider names."""
        return [p.name for p in self._providers]

    # ------------------------------------------------------------------
    # Telemetry
    # ------------------------------------------------------------------

    def usage_report(self) -> Dict[str, dict]:
        """Return a JSON-friendly dict of per-provider usage snapshots."""
        return {p.name: p.usage().to_dict() for p in self._providers}

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        *,
        strategy: str = "fallback",
        num: int = 20,
        language: str = "fr",
        providers: Optional[Iterable[str]] = None,
    ) -> List[SearchResult]:
        """Execute a search across the registered providers.

        Args:
            query: The user query.
            strategy: One of ``'fallback'`` or ``'parallel'``.
            num: Maximum number of results to fetch from each provider.
                The merged output is at most ``num × providers``.
            language: ISO 639-1 language code passed verbatim.
            providers: Optional whitelist of provider names. When set,
                only matching providers participate in this call.

        Returns:
            A merged, deduplicated list of :class:`SearchResult`.

        Raises:
            ValueError: When ``strategy`` is not one of the supported values.
        """
        if strategy not in self.SUPPORTED_STRATEGIES:
            raise ValueError(
                f"unsupported strategy '{strategy}' "
                f"(expected one of {self.SUPPORTED_STRATEGIES})"
            )

        active = self._select(providers)
        if not active:
            _LOG.warning("router: no provider configured — empty result")
            return []

        if strategy == "fallback":
            return await self._search_fallback(active, query, num, language)
        return await self._search_parallel(active, query, num, language)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _select(self, providers: Optional[Iterable[str]]) -> List[BaseProvider]:
        if providers is None:
            return list(self._providers)
        wanted = {p.lower() for p in providers}
        return [p for p in self._providers if p.name.lower() in wanted]

    async def _search_fallback(
        self,
        providers: List[BaseProvider],
        query: str,
        num: int,
        language: str,
    ) -> List[SearchResult]:
        connector = aiohttp.TCPConnector(limit=4)
        async with aiohttp.ClientSession(connector=connector) as session:
            for provider in providers:
                try:
                    results = await provider.search(session, query, num=num, language=language)
                except Exception as exc:  # safety net — providers should not raise
                    _LOG.warning("router: provider %s raised: %s", provider.name, exc)
                    provider.errors += 1
                    provider.last_status = ProviderStatus.ERROR
                    continue

                if results:
                    return merge_results([results])
                _LOG.warning(
                    "router: provider %s returned no results — moving on",
                    provider.name,
                )
        return []

    async def _search_parallel(
        self,
        providers: List[BaseProvider],
        query: str,
        num: int,
        language: str,
    ) -> List[SearchResult]:
        connector = aiohttp.TCPConnector(limit=8)
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [
                provider.search(session, query, num=num, language=language)
                for provider in providers
            ]
            settled = await asyncio.gather(*tasks, return_exceptions=True)

        batches: List[List[SearchResult]] = []
        for provider, outcome in zip(providers, settled):
            if isinstance(outcome, Exception):
                _LOG.warning(
                    "router: provider %s raised in parallel: %s",
                    provider.name, outcome,
                )
                provider.errors += 1
                provider.last_status = ProviderStatus.ERROR
                continue
            batches.append(outcome)

        return merge_results(batches)


__all__ = ["SearchRouter"]
