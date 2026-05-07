"""Provider adapters for the multi-API search router.

Each adapter encapsulates the quirks of a single search backend behind the
:class:`mwi.search.providers.base.BaseProvider` contract. Imports are kept
lazy to avoid pulling ``aiohttp`` at module-load time of unrelated MWI
commands — only the providers actually instantiated by the router are loaded.
"""

from mwi.search.providers.base import BaseProvider

__all__ = ["BaseProvider"]
