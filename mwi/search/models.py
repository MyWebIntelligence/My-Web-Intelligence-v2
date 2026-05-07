"""In-memory dataclasses for the multi-API search router.

These objects circulate during a single ``SearchRouter.search()`` invocation;
they are converted to :class:`mwi.model.SearchResultLog` rows by the
controller after deduplication. Keep them serialisable (pure stdlib types)
so they can be dumped to JSON for the ``usage_report`` column.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional


class ProviderStatus(str, Enum):
    """Runtime status of a single provider after its last call.

    The string values are persisted verbatim in the JSON ``usage_report``
    column of :class:`mwi.model.SearchQuery`, so they double as a stable
    public API. Do not rename without a migration.
    """

    OK = "ok"
    QUOTA_EXCEEDED = "quota_exceeded"
    ERROR = "error"
    NOT_CONFIGURED = "not_configured"


@dataclass
class SearchResult:
    """One result row returned by a provider.

    Attributes:
        url: The result URL. Canonicalised before insertion in the router
            (see :func:`mwi.search.utils.canonicalize_url`).
        title: Optional title.
        snippet: Optional snippet/summary text.
        rank: 1-based rank within the provider's result list. ``None`` when
            the provider does not expose ranks (e.g. semantic providers).
        providers: Plus-joined provider names. A single result keeps the
            originating provider; the router merges duplicates and rewrites
            this field (e.g. ``"searxng+brave"``).
        raw: Original raw payload, kept for debugging/audit. Not serialised
            into ``SearchResultLog`` — the controller stores only the
            normalised fields.
    """

    url: str
    title: Optional[str] = None
    snippet: Optional[str] = None
    rank: Optional[int] = None
    providers: str = ""
    raw: Optional[Dict[str, Any]] = field(default=None, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serialisable snapshot (without the raw payload)."""
        d = asdict(self)
        d.pop("raw", None)
        return d


@dataclass
class ProviderUsage:
    """Per-provider runtime usage snapshot for the ``usage_report`` column.

    Attributes:
        name: Provider canonical name (e.g. ``"searxng"``).
        calls: Number of API calls made during the current process.
        errors: Number of failed calls.
        status: Last observed :class:`ProviderStatus`.
        monthly_quota: Informative monthly quota declared by the provider.
            ``None`` when the provider has no fixed quota.
    """

    name: str
    calls: int = 0
    errors: int = 0
    status: ProviderStatus = ProviderStatus.OK
    monthly_quota: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """JSON-friendly representation of the usage snapshot."""
        return {
            "name": self.name,
            "calls": self.calls,
            "errors": self.errors,
            "status": self.status.value,
            "monthly_quota": self.monthly_quota,
        }


__all__ = ["ProviderStatus", "ProviderUsage", "SearchResult"]
