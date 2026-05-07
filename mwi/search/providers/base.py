"""Abstract base class for all search-provider adapters."""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import List, Optional

import aiohttp

from mwi.search.models import ProviderStatus, ProviderUsage, SearchResult


_LOG = logging.getLogger("mwi.search")


class BaseProvider(ABC):
    """Common contract every search-provider adapter must implement.

    Subclasses set the class attributes ``name`` and ``monthly_quota``,
    then implement :meth:`search`. The router uses :meth:`is_configured`
    to decide whether to register the adapter.

    Attributes:
        name: Canonical provider name. Stored verbatim in
            ``SearchResultLog.providers`` and ``ProviderUsage.name``.
        monthly_quota: Informative monthly quota for telemetry. ``None``
            when the provider has no fixed quota (e.g. SearXNG).
        min_delay_between_calls: Politeness delay between successive
            ``search()`` calls of the **same** instance. ``0`` disables
            the throttle.
        timeout: Per-call HTTP timeout in seconds.
    """

    name: str = "abstract"
    monthly_quota: Optional[int] = None
    min_delay_between_calls: float = 0.0
    timeout: float = 30.0

    def __init__(self) -> None:
        self.calls_made: int = 0
        self.errors: int = 0
        self.last_status: ProviderStatus = ProviderStatus.OK
        self._last_call_at: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @abstractmethod
    async def search(
        self,
        session: aiohttp.ClientSession,
        query: str,
        num: int = 20,
        language: str = "fr",
    ) -> List[SearchResult]:
        """Execute the search and return normalised :class:`SearchResult` rows.

        Subclasses must set ``self.last_status`` and update the call/error
        counters. Implementations MUST NOT raise on quota or rate-limit
        failures — they should return an empty list and flag
        :attr:`last_status` accordingly.
        """

    def is_configured(self) -> bool:
        """Return ``True`` when the adapter has the credentials it needs.

        Default implementation returns ``True`` — adapters with API keys
        override this to inspect ``settings.py`` / environment.
        """
        return True

    def usage(self) -> ProviderUsage:
        """Return a snapshot of this provider's runtime usage."""
        return ProviderUsage(
            name=self.name,
            calls=self.calls_made,
            errors=self.errors,
            status=self.last_status,
            monthly_quota=self.monthly_quota,
        )

    # ------------------------------------------------------------------
    # Helpers for subclasses
    # ------------------------------------------------------------------

    async def _wait_politeness_window(self) -> None:
        """Sleep just enough to honour :attr:`min_delay_between_calls`."""
        if self.min_delay_between_calls <= 0:
            return
        elapsed = time.monotonic() - self._last_call_at
        delay = self.min_delay_between_calls - elapsed
        if delay > 0:
            await asyncio.sleep(delay)

    def _mark_call(self) -> None:
        """Record a successful call (counters + politeness clock)."""
        self.calls_made += 1
        self._last_call_at = time.monotonic()

    def _mark_error(
        self,
        status: ProviderStatus = ProviderStatus.ERROR,
        message: Optional[str] = None,
    ) -> None:
        """Record a failed call with the supplied :class:`ProviderStatus`."""
        self.errors += 1
        self.last_status = status
        if message:
            _LOG.warning("%s: %s", self.name, message)


__all__ = ["BaseProvider"]
