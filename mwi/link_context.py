"""Link-context helpers (sprint link-context, migration 012).

Computes, for each ``<a href>`` of a page, the metadata stored on
``ExpressionLink``:

- ``dom``       — CSS-like path from the document root down to the *parent*
                  of the ``<a>`` tag, e.g.
                  ``html > body > div#main.layout > article.post > p``.
- ``dom_html``  — outerHTML of the closest block-level ancestor, truncated
                  to ``settings.link_dom_html_max_chars``.
- ``context``   — markdown paragraph of the readable containing the link
                  (computed by :func:`extract_md_paragraph`); when the
                  readable does not carry the URL (BS4 fallback path), the
                  block ancestor's text (``block_text``) is used instead.

Design constraints:

- This module must NOT import ``mwi.core`` (it is imported *by* core and by
  ``readable_pipeline`` — keeping it leaf-level avoids import cycles).
- ``extract_link_dom_map`` must never raise: a context-extraction failure
  must never fail a crawl. It returns ``{}`` on any error.
- URL matching strategy: ``Expression.url`` is stored normalized by
  ``url_normalizer.normalize_url`` (idempotent), so map keys are the
  normalized absolute href, plus a relaxed key (lowercase, no trailing
  slash) absorbing residual divergences (e.g. legacy data lowercased by
  ``core.resolve_url``). ``core.resolve_url`` is intentionally NOT used
  here because it lowercases the URL path.
"""

import re
import warnings
from dataclasses import dataclass
from typing import Dict, Optional
from urllib.parse import urljoin

import settings

from .url_normalizer import normalize_url

BLOCK_TAGS = ('p', 'li', 'td', 'th', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
              'blockquote', 'figcaption', 'dd', 'dt')
FALLBACK_BLOCK_TAGS = ('div', 'section', 'article')
SKIP_HREF_PREFIXES = ('mailto:', 'javascript:', 'tel:', 'data:', '#')
MAX_CLASSES_PER_SEGMENT = 3

_VALID_TOKEN = re.compile(r'^[A-Za-z0-9_-]+$')


@dataclass
class LinkDomInfo:
    """DOM-level metadata for one ``<a href>`` occurrence in a page."""
    dom: str                      # CSS path root -> parent of the <a>
    dom_html: Optional[str]       # outerHTML of the block ancestor, truncated
    block_text: Optional[str]     # text of the block ancestor, truncated


def _context_cap() -> int:
    return getattr(settings, 'link_context_max_chars', 1000) or 1000


def _dom_html_cap() -> int:
    return getattr(settings, 'link_dom_html_max_chars', 4000) or 4000


def _segment(element) -> str:
    """Build one CSS-path segment: ``tag#id.cls1.cls2.cls3``."""
    part = element.name
    el_id = element.get('id')
    if isinstance(el_id, str) and _VALID_TOKEN.match(el_id):
        part += f'#{el_id}'
    classes = element.get('class') or []
    kept = [c for c in classes if isinstance(c, str) and _VALID_TOKEN.match(c)]
    for cls in kept[:MAX_CLASSES_PER_SEGMENT]:
        part += f'.{cls}'
    return part


def build_dom_path(a_tag) -> str:
    """CSS-like path from the document root to the direct parent of `a_tag`.

    The ``<a>`` itself is not included. ``[document]`` (the BeautifulSoup
    root) is skipped.
    """
    segments = []
    for parent in a_tag.parents:
        if parent.name is None or parent.name == '[document]':
            continue
        segments.append(_segment(parent))
    segments.reverse()
    return ' > '.join(segments)


def find_block_ancestor(a_tag):
    """Closest block-level ancestor of `a_tag`.

    Strict blocks (``BLOCK_TAGS``) win; the first ``div``/``section``/
    ``article`` met on the way up is kept as fallback. Returns None when
    neither exists (e.g. ``<a>`` directly under ``<body>``).
    """
    fallback = None
    for parent in a_tag.parents:
        if parent.name in BLOCK_TAGS:
            return parent
        if fallback is None and parent.name in FALLBACK_BLOCK_TAGS:
            fallback = parent
    return fallback


def _relaxed_key(normalized_url: str) -> str:
    return normalized_url.lower().rstrip('/')


def _quiet_soup(raw_html: str, parser: str):
    """BeautifulSoup parse with the noisy XMLParsedAsHTMLWarning silenced.

    Stored HTML is sometimes actually XML (sitemaps, RSS/Atom feeds); bs4
    then emits a multi-line warning. It is benign for link extraction, so we
    suppress it locally (no global filterwarnings side effect).
    """
    from bs4 import BeautifulSoup
    with warnings.catch_warnings():
        try:
            from bs4 import XMLParsedAsHTMLWarning
            warnings.simplefilter('ignore', XMLParsedAsHTMLWarning)
        except ImportError:
            pass
        return BeautifulSoup(raw_html, parser)


def extract_link_dom_map(raw_html: Optional[str], base_url: str,
                         soup=None) -> Dict[str, LinkDomInfo]:
    """Map each crawlable ``<a href>`` of `raw_html` to its LinkDomInfo.

    Keys are the normalized absolute URL plus a relaxed variant
    (lowercase, no trailing slash). First occurrence wins (consistent with
    the composite primary key on expressionlink: first link wins too).

    Never raises — returns ``{}`` on any failure. Reuses `soup` when the
    caller already parsed the page (crawl path).
    """
    try:
        if soup is None:
            if not raw_html:
                return {}
            soup = _quiet_soup(raw_html, 'html.parser')

        dom_html_cap = _dom_html_cap()
        context_cap = _context_cap()
        mapping: Dict[str, LinkDomInfo] = {}

        for a_tag in soup.find_all('a', href=True):
            href = (a_tag.get('href') or '').strip()
            if not href or href.lower().startswith(SKIP_HREF_PREFIXES):
                continue
            if href.startswith(('http://', 'https://')):
                absolute = href
            else:
                absolute = urljoin(base_url, href)
                if not absolute.startswith(('http://', 'https://')):
                    continue

            try:
                key = normalize_url(absolute)
            except Exception:
                continue

            block = find_block_ancestor(a_tag)
            info = LinkDomInfo(
                dom=build_dom_path(a_tag),
                dom_html=str(block)[:dom_html_cap] if block is not None else None,
                block_text=(block.get_text(' ', strip=True)[:context_cap]
                            if block is not None else None),
            )
            mapping.setdefault(key, info)
            mapping.setdefault(_relaxed_key(key), info)
        return mapping
    except Exception:
        return {}


def extract_all_links(raw_html: Optional[str], base_url: str,
                      soup=None) -> list:
    """All http(s) ``<a href>`` URLs of `raw_html`, **duplicates preserved**.

    Unlike :func:`extract_link_dom_map` (which deduplicates via
    ``setdefault``), this APPENDS every anchor so the caller can count
    multiplicity (edge weight). URLs are resolved to absolute with
    ``urljoin`` but **not** normalized — the caller applies
    ``url_normalizer.normalize_url`` to align with the stored
    ``Expression.url``. ``core.resolve_url`` is intentionally NOT used (it
    lowercases the URL path).

    Reuses the same filtering as ``extract_link_dom_map`` (skip
    ``mailto:``/``javascript:``/``tel:``/``data:``/``#``; drop anything that
    does not resolve to http(s)). Never raises — returns ``[]`` on any error.
    """
    links: list = []
    try:
        if soup is None:
            if not raw_html:
                return links
            try:
                soup = _quiet_soup(raw_html, 'lxml')
            except Exception:
                soup = _quiet_soup(raw_html, 'html.parser')

        for a_tag in soup.find_all('a', href=True):
            href = (a_tag.get('href') or '').strip()
            if not href or href.lower().startswith(SKIP_HREF_PREFIXES):
                continue
            if href.startswith(('http://', 'https://')):
                absolute = href
            else:
                absolute = urljoin(base_url, href)
                if not absolute.startswith(('http://', 'https://')):
                    continue
            links.append(absolute)
        return links
    except Exception:
        return links


def lookup_link_info(mapping: Dict[str, LinkDomInfo],
                     url: str) -> Optional[LinkDomInfo]:
    """Find the LinkDomInfo of `url` in a map built by extract_link_dom_map."""
    if not mapping or not url:
        return None
    try:
        key = normalize_url(url)
    except Exception:
        key = url
    return mapping.get(key) or mapping.get(_relaxed_key(key))


def extract_md_paragraph(markdown: Optional[str], url: Optional[str],
                         max_chars: Optional[int] = None) -> Optional[str]:
    """First markdown paragraph (blank-line delimited) containing `url`.

    Returns the stripped paragraph truncated to `max_chars` (defaults to
    ``settings.link_context_max_chars``), or None when the URL does not
    appear literally in the markdown (e.g. BS4-fallback readable without
    hrefs).
    """
    if not markdown or not url:
        return None
    cap = max_chars or _context_cap()
    paragraphs = re.split(r'\n\s*\n', markdown)
    for needle in (url, url.rstrip('/')):
        if not needle:
            continue
        for para in paragraphs:
            if needle in para:
                return para.strip()[:cap]
    return None
