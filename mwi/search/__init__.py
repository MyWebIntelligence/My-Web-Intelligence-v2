"""Multi-API search router for MyWebIntelligence.

Public surface — keep imports lazy where possible to avoid pulling
``aiohttp`` and provider modules at import time of unrelated commands.
"""

from mwi.search.models import (
    ProviderStatus,
    ProviderUsage,
    SearchResult,
)
from mwi.search.router import SearchRouter

__all__ = [
    "ProviderStatus",
    "ProviderUsage",
    "SearchResult",
    "SearchRouter",
]
