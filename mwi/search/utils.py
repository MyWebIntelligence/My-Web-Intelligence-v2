"""URL canonicalisation and merge helpers for the multi-API search router.

The canonicalisation rules are intentionally conservative — only the
transforms documented in ``SearchRouter.md`` §5.2 are applied. More
aggressive normalisation (UTM stripping, query-param sorting) lives in
``mwi.url_normalizer`` and is invoked separately at the
``Expression``-insertion boundary.
"""

from __future__ import annotations

from typing import Iterable, List
from urllib.parse import urlsplit, urlunsplit

from mwi.search.models import SearchResult


def canonicalize_url(url: str) -> str:
    """Return a canonical form of ``url`` for dedup / equality comparison.

    Steps:
    1. Lowercase scheme and netloc.
    2. Drop fragment (``#...``).
    3. Strip the trailing slash from the path, except on the root.
    4. Preserve the query string verbatim (sorting / UTM stripping is the
       responsibility of ``mwi.url_normalizer``).

    Empty strings and ``None`` are returned as-is, never raising — the
    router handles invalid provider payloads by filtering them out.

    Args:
        url: The URL to canonicalise. Must be a string.

    Returns:
        The canonicalised URL string.
    """
    if not url:
        return url or ""
    try:
        parts = urlsplit(url.strip())
    except (ValueError, AttributeError):
        return url

    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    path = parts.path
    if path and path != "/" and path.endswith("/"):
        path = path[:-1]

    # Always drop the fragment.
    return urlunsplit((scheme, netloc, path, parts.query, ""))


def merge_into(existing: SearchResult, incoming: SearchResult) -> None:
    """Fold `incoming` into `existing`, in place. `existing.url` is untouched.

    Providers are concatenated with ``+`` preserving order and uniqueness, the
    lowest non-None rank wins, and title/snippet are backfilled only when the
    existing value is empty.

    Extracted from :func:`merge_results` (A08) because the same fold is needed
    one layer down, at persistence time: two results that survive the router's
    `canonicalize_url` dedup can still collapse onto a single Expression once
    `normalize_url` has stripped trackers, sorted parameters or unwrapped a
    Wayback URL — and `SearchResultLog` is UNIQUE on (search_query, url).
    """
    seen = existing.providers.split("+") if existing.providers else []
    for p in (incoming.providers or "").split("+"):
        if p and p not in seen:
            seen.append(p)
    existing.providers = "+".join(seen)

    ranks = [v for v in (existing.rank, incoming.rank) if v is not None]
    existing.rank = min(ranks) if ranks else None

    if not existing.title and incoming.title:
        existing.title = incoming.title
    if not existing.snippet and incoming.snippet:
        existing.snippet = incoming.snippet


def merge_results(batches: Iterable[List[SearchResult]]) -> List[SearchResult]:
    """Merge per-provider result lists, dedup by canonical URL, keep best rank.

    For each duplicate URL: providers are concatenated with ``+`` (preserving
    insertion order), the lowest non-None rank is kept as ``rank_min``, and
    title/snippet fall back to the first non-empty value seen.

    Args:
        batches: An iterable of result lists, each carrying a single
            provider's name in ``SearchResult.providers``.

    Returns:
        A list of :class:`SearchResult` deduplicated by canonical URL,
        sorted by ``rank`` ascending (``None`` ranks last).
    """
    by_url: dict[str, SearchResult] = {}

    for batch in batches:
        for r in batch:
            if not r.url:
                continue
            key = canonicalize_url(r.url)
            if not key:
                continue

            if key not in by_url:
                # Replace the URL with its canonical form so callers see the
                # same key as the dedup map.
                by_url[key] = SearchResult(
                    url=key,
                    title=r.title,
                    snippet=r.snippet,
                    rank=r.rank,
                    providers=r.providers or "",
                    raw=r.raw,
                )
                continue

            merge_into(by_url[key], r)

    def _sort_key(r: SearchResult) -> tuple:
        # None rank sorts last, deterministically.
        return (0, r.rank) if r.rank is not None else (1, 0)

    return sorted(by_url.values(), key=_sort_key)


__all__ = ["canonicalize_url", "merge_into", "merge_results"]
