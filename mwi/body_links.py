"""Outgoing links of a page body: markdown leg plus Trafilatura's HTML leg.

Sprint body-links, T2. Historically the crawl read links from Trafilatura's
*markdown* serialisation only, while the *HTML* output of the very same call --
already computed for media extraction -- was thrown away. Measured on the gold
set of the ``airegulation`` land, of the 123 editorial citations the extractor
missed, the markdown leg recovers 6 and the HTML leg 26; widening that leg with
``favor_recall`` recovers 33 more, for 0.002 of precision.

The markdown leg is left strictly untouched. It is what feeds
``expression.readable``, hence relevance scoring, the LLM gate, embeddings and
the corpus export: widening it would inject boilerplate into every corpus, an
irreversible regression. The two frontiers are decoupled on purpose -- the link
frontier favours recall, the text frontier favours precision.

Leaf module: it imports nothing from ``core`` or ``model``, so it can never
write to the database, and it never raises.
"""
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urljoin

from . import link_context
from .url_normalizer import normalize_url

ORIGIN_MD = 'md'
ORIGIN_HTML = 'html'
ORIGIN_BOTH = 'both'
ORIGIN_RAW = 'raw'


@dataclass
class BodyLink:
    """One outgoing link of a page body.

    ``url``   absolute, path case preserved, NOT normalized (it is what gets
              stored and re-fetched).
    ``key``   ``normalize_url(url)`` -- deduplication and join key.
    ``origin`` which leg found it: md, html, both, or raw (BS4 fallback).
    ``order``  rank in the document: markdown first, then HTML-only links.
    ``raw``    the literal markdown token, needed by ``extract_md_paragraph``
               to find the paragraph that carries the link.
    """
    url: str
    key: str
    origin: str
    order: int
    raw: Optional[str] = None


def _key(url: str) -> str:
    try:
        return normalize_url(url)
    except Exception:
        return url


def _markdown_leg(md_content: Optional[str], base_url: str):
    """Yield (url, raw_token) exactly as ``extract_markdown_links`` would."""
    try:
        for token in link_context.iter_markdown_link_tokens(md_content):
            resolved = urljoin(base_url, token) if base_url else token
            if link_context._SCHEME_RE.match(resolved):
                yield resolved, token
    except Exception:
        return


def _html_leg(readable_html: Optional[str], base_url: str, soup=None):
    """Yield the anchors of Trafilatura's HTML output.

    Same filtering as the raw-DOM helpers (``link_context._resolve_href``), so
    the three link sources cannot drift apart.
    """
    try:
        if soup is None:
            if not readable_html:
                return
            soup = link_context._quiet_soup(readable_html, 'html.parser')
        base_norm = link_context._same_page_norm(base_url)
        for a_tag in soup.find_all('a', href=True):
            absolute = link_context._resolve_href(a_tag.get('href'), base_url,
                                                  base_norm)
            if absolute is not None:
                yield absolute
    except Exception:
        return


def extract_body_links(md_content: Optional[str],
                       readable_html: Optional[str],
                       base_url: str,
                       soup=None) -> List[BodyLink]:
    """Ordered union of the markdown and HTML legs, deduplicated.

    Takes the two Trafilatura outputs the caller has ALREADY computed -- it
    never runs Trafilatura itself, which would blow the two-parses-per-page
    budget. ``soup`` lets the caller hand over the parse of ``readable_html``
    it already did for media extraction, so the HTML leg is free.

    Order is document order: markdown links first, then the links only the
    HTML leg saw. Deduplication is on the normalized URL; the first occurrence
    keeps its url, order and raw token, and a link seen by both legs is marked
    ``both``. Never raises.
    """
    links: List[BodyLink] = []
    seen = {}

    def _add(url: str, origin: str, raw: Optional[str] = None) -> None:
        key = _key(url)
        if not key:
            return
        existing = seen.get(key)
        if existing is not None:
            if existing.origin != origin:
                existing.origin = ORIGIN_BOTH
            return
        link = BodyLink(url=url, key=key, origin=origin, order=len(links),
                        raw=raw)
        seen[key] = link
        links.append(link)

    for url, raw in _markdown_leg(md_content, base_url):
        _add(url, ORIGIN_MD, raw)
    for url in _html_leg(readable_html, base_url, soup=soup):
        _add(url, ORIGIN_HTML)
    return links


def from_urls(urls, origin: str = ORIGIN_RAW) -> List[BodyLink]:
    """Wrap a plain URL list (BS4 fallback path) as BodyLink objects."""
    links: List[BodyLink] = []
    seen = set()
    for url in urls or ():
        key = _key(url)
        if not key or key in seen:
            continue
        seen.add(key)
        links.append(BodyLink(url=url, key=key, origin=origin,
                              order=len(links), raw=None))
    return links
