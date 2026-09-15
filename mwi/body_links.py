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

import settings

from . import link_context
from .url_normalizer import normalize_url

KINDS = ('body', 'nav', 'toc', 'reco', 'ref')
KIND_DEFAULT = 'body'

# Which occurrence of a URL wins when the same link appears twice in a page.
# Ordered by decreasing proximity to the discourse: if a page both cites a
# source in its body AND lists it in a menu, the edge IS a citation -- the
# menu does not cancel it. "First occurrence wins" is the worst possible
# policy here, since menus sit at the top of the document (median anchor
# position 0.16, against 0.49 for an editorial link).
KIND_RANK = {'body': 0, 'ref': 1, 'reco': 2, 'toc': 3, 'nav': 4}

# Structural markup tokens looked for in the class/id of an ancestor. These
# name a REGION OF THE INTERFACE, never a subject: they are the exception the
# sprint allows explicitly, and the no-vocabulary test guards the boundary.
# Deliberately absent: related / read-next / further-reading / references /
# bibliography families. Those are English content words, they do not
# generalise beyond the anglophone web, and the density rule covers them.
STRUCTURE_TOKENS = frozenset((
    'nav', 'navbar', 'navigation', 'menu', 'submenu',
    'breadcrumb', 'crumb', 'sidebar', 'toc',
))

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
    kind: Optional[str] = None
    kind_rule: Optional[str] = None


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


# --------------------------------------------------------------------------- #
# Structural classification (sprint body-links, T3)                            #
# --------------------------------------------------------------------------- #

def _thresholds() -> dict:
    """Rule thresholds. Dimensionless ratios and counts only.

    A threshold on an absolute length would encode the average sentence
    length of one language; a ratio of anchors to prose does not.
    """
    return {
        'grid_min': getattr(settings, 'link_kind_grid_anchors', 8),
        'cout_min': getattr(settings, 'link_kind_cout_min', 0.50),
    }


def is_retained(kind: Optional[str]) -> bool:
    """NULL means body: never exclude an old edge for lack of information."""
    return (kind or KIND_DEFAULT) == KIND_DEFAULT


def outside_ratio(anchor_chars: int, text_len: int) -> float:
    """Share of a block's text that is NOT anchor text.

    Measured on the coded corpus: 0.95 for an editorial paragraph, 0.36 for a
    recommendation block, 0.29 for a table of contents, 0.04 for a menu. It is
    the single most discriminating structural feature, and it is a ratio, so
    it transfers across languages and content management systems.
    """
    if text_len <= 0:
        return 0.0
    return 1.0 - (anchor_chars / float(text_len))


def _matched_structure_token(tokens) -> Optional[str]:
    for token in tokens or ():
        if token in STRUCTURE_TOKENS:
            return token
    return None


def classify(info, thresholds: Optional[dict] = None):
    """Structural kind of one link occurrence -> (kind, kind_rule).

    Reads the RAW DOM metadata only: Trafilatura's HTML output carries no
    class, no id and no nav/header/footer/aside, so a rule written against it
    would be silently inert.

    ``info is None`` -- the link is in the markdown but was not located in the
    raw DOM -- yields ``body``: we never exclude for lack of evidence.

    Rules are ordered, first match wins. Pure, deterministic, never raises.
    """
    if info is None:
        return KIND_DEFAULT, 'r0_default'
    limits = thresholds or _thresholds()
    try:
        # R1 - the link sits in a sectioning/annex element, or under an ARIA
        # landmark, AND that element is prose-poor. The qualifier is not
        # optional: templates routinely wrap a whole article in <header>, and
        # measured on the gold set the unqualified rule exiled 4 genuine
        # citations sitting under such a wrapper. An annex is short on prose
        # by nature; an element that is mostly prose is the page itself.
        if info.in_semantic_aside and outside_ratio(
                info.aside_anchor_chars, info.aside_text_len) < limits['cout_min']:
            return 'nav', 'r1_semantic_ancestor'

        # R1b - an ancestor names itself a region of the interface.
        token = _matched_structure_token(info.ancestor_tokens)
        if token is not None:
            return ('toc' if token == 'toc' else 'nav'), 'r1b_container_token'

        # R2 - a grid of same-site anchors with almost no prose between them.
        # Measured on the CONTAINER -- the closest ancestor that groups
        # several links -- and not on the block ancestor: a table of contents
        # routinely wraps each entry in its own <p>, which makes the block
        # hold exactly one anchor and hides the grid entirely. The container
        # is the unit that actually groups, the block is a markup accident.
        if (info.cont_anchor_count >= limits['grid_min']
                and info.same_domain
                and outside_ratio(info.cont_anchor_chars,
                                  info.cont_text_len) < limits['cout_min']):
            return 'toc', 'r2_anchor_grid'
    except Exception:
        return KIND_DEFAULT, 'r0_default'
    return KIND_DEFAULT, 'r0_default'


def dom_rank(info) -> int:
    """Rank of one occurrence, for ``link_context.extract_link_dom_map``."""
    return KIND_RANK.get(classify(info)[0], KIND_RANK[KIND_DEFAULT])


def resolve(links: List[BodyLink], dom_map) -> List[BodyLink]:
    """Attach the structural kind to each link, in place. Never raises."""
    for link in links:
        try:
            info = link_context.lookup_link_info(dom_map, link.url)
            link.kind, link.kind_rule = classify(info)
        except Exception:
            link.kind, link.kind_rule = KIND_DEFAULT, 'r0_default'
    return links
