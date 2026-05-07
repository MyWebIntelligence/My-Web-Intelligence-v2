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

            existing = by_url[key]
            # Concatenate provider names while preserving order and uniqueness.
            seen = existing.providers.split("+") if existing.providers else []
            for p in (r.providers or "").split("+"):
                if p and p not in seen:
                    seen.append(p)
            existing.providers = "+".join(seen)

            # Keep the best rank (lowest), ignoring None values.
            ranks = [v for v in (existing.rank, r.rank) if v is not None]
            existing.rank = min(ranks) if ranks else None

            # Backfill title/snippet only when the existing one is empty.
            if not existing.title and r.title:
                existing.title = r.title
            if not existing.snippet and r.snippet:
                existing.snippet = r.snippet

    def _sort_key(r: SearchResult) -> tuple:
        # None rank sorts last, deterministically.
        return (0, r.rank) if r.rank is not None else (1, 0)

    return sorted(by_url.values(), key=_sort_key)


__all__ = ["canonicalize_url", "merge_results"]
