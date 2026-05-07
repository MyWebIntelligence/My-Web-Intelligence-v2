"""URL normalization pipeline for MyWebIntelligence.

Single entry point for all URL canonicalization. Configurable via
`settings.url_normalization`; idempotent by design (any URL pushed through
`normalize_url` twice yields the same string).

Normalization stages (each opt-in via the rules dict):
  1. remove_anchor          — strip the #fragment
  2. unwrap_archive         — web.archive.org / ghostarchive.org snapshots
                              collapse to their original target (recursively
                              when nested)
  3. lowercase_host         — host part lowercased; path is preserved
  4. force_https            — http:// → https:// (off by default)
  5. strip_www              — www.example.com → example.com (off by default)
  6. strip_mobile_subdomain — m.example.com → example.com (off by default)
  7. strip_trackers         — drop query params matching configured globs
                              (utm_*, fbclid, gclid, etc.)
  8. normalize_query_order  — alphabetical order of remaining params
  9. trailing_slash policy  — preserve | strip | add

Design notes:
  * The path is intentionally case-preserved (paths are case-sensitive on
    most servers).
  * The function operates on `urlparse(url)` and rebuilds with
    `urlunparse`, so any malformed URL is left mostly intact rather than
    raising.
  * Reading config: each call reads from `settings.url_normalization` to
    pick up live changes during tests; pass an explicit `rules=` dict to
    bypass settings (also useful for tests).
"""

from __future__ import annotations

import fnmatch
import re
from typing import Dict, Optional
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

import settings


ARCHIVE_HOSTS = ('web.archive.org', 'archive.org')
GHOSTARCHIVE_HOSTS = ('ghostarchive.org',)

# Wikipedia footnote backref markers that pollute URLs extracted from
# wiki-style markdown. The URL-encoded variants appear when the parasite
# was already URL-encoded in the source href (Wikipedia citation templates).
_WIKI_FOOTNOTE_MARKERS = (
    '[↑]',          # [↑]
    '%5B%E2%86%91%5D',   # URL-encoded [↑] (uppercase)
    '%5b%e2%86%91%5d',   # URL-encoded [↑] (lowercase)
)

_DOUBLE_SCHEME_RE = re.compile(r'^(https?://)(https?://)', re.IGNORECASE)
# Trailing junk: punctuation that's never part of a real URL tail.
# Brackets/parens are handled separately (balance-aware) to preserve URLs
# like https://en.wikipedia.org/wiki/Foo_(bar).
_TRAILING_SAFE_PUNCT_RE = re.compile(r'[\.,;»]+$')

DEFAULT_RULES: Dict[str, object] = {
    'unwrap_archive': True,
    'force_https': False,
    'strip_www': False,
    'lowercase_host': True,
    'strip_mobile_subdomain': False,
    'strip_trackers': [
        'utm_*', 'fbclid', 'gclid', 'mc_eid', 'ref_src', '_ga',
        'yclid', '_openstat', 'wt_*', 'msclkid', 'igshid', 'spm',
    ],
    'normalize_query_order': True,
    'trailing_slash': 'preserve',  # 'preserve' | 'strip' | 'add'
}


def _get_rules(rules: Optional[Dict] = None) -> Dict:
    if rules is not None:
        merged = dict(DEFAULT_RULES)
        merged.update(rules)
        return merged
    user_rules = getattr(settings, 'url_normalization', {}) or {}
    merged = dict(DEFAULT_RULES)
    merged.update(user_rules)
    return merged


def is_archive_wrapper(url: str) -> bool:
    """True iff the URL is a Wayback or ghostarchive snapshot."""
    try:
        netloc = urlparse(url).netloc.lower()
    except Exception:
        return False
    return netloc in ARCHIVE_HOSTS or netloc in GHOSTARCHIVE_HOSTS


def _unwrap_once(url: str) -> str:
    """One layer of archive unwrapping. Returns url unchanged if no match."""
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()

    full_path = parsed.path
    if parsed.query:
        full_path += '?' + parsed.query
    if parsed.fragment:
        full_path += '#' + parsed.fragment

    if netloc in ARCHIVE_HOSTS:
        match = re.search(r'/web/\d+(?:[a-z]+_)?/(.+)$', full_path)
        if match:
            return match.group(1)
    elif netloc in GHOSTARCHIVE_HOSTS:
        match = re.search(r'/archive/[^/]+/(.+)$', full_path)
        if match:
            return match.group(1)
    return url


def _unwrap_archive(url: str) -> str:
    """Recursively unwrap Wayback-of-Wayback chains. Bounded to 8 iterations
    as a safety against pathological inputs.
    """
    for _ in range(8):
        new = _unwrap_once(url)
        if new == url:
            return url
        url = new
    return url


def _remove_anchor(url: str) -> str:
    if '#' in url:
        return url.split('#', 1)[0]
    return url


def _strip_corrupt_suffix(url: str) -> str:
    """Cut off Wikipedia footnote parasites and trailing unbalanced punctuation.

    Handles URLs harvested from wiki-style markdown where the source href
    already contained `[↑]` (or its URL-encoded form) glued to a legit URL,
    and the markdown link extractor swallowed it whole. Balance-aware on
    parens and brackets so legit URLs like ``Article_(disambiguation)`` and
    ``foo[bar]`` are preserved.
    """
    for marker in _WIKI_FOOTNOTE_MARKERS:
        idx = url.find(marker)
        if idx > 0:
            url = url[:idx]
            break

    # Strip unbalanced trailing brackets/parens iteratively.
    while url and url[-1] in ')]':
        char = url[-1]
        opener = '(' if char == ')' else '['
        if url.count(opener) >= url.count(char):
            break
        url = url[:-1]

    return _TRAILING_SAFE_PUNCT_RE.sub('', url)


def _fix_double_scheme(url: str) -> str:
    """Collapse 'https://https://example.com' to 'https://example.com'."""
    m = _DOUBLE_SCHEME_RE.match(url)
    if m:
        return url[len(m.group(1)):]
    return url


def _drop_tracker_params(query: str, patterns) -> str:
    if not query:
        return query
    pairs = parse_qsl(query, keep_blank_values=True)
    kept = []
    for key, value in pairs:
        if any(fnmatch.fnmatchcase(key, pat) for pat in patterns):
            continue
        kept.append((key, value))
    return urlencode(kept, doseq=True)


def _sort_query(query: str) -> str:
    if not query:
        return query
    pairs = parse_qsl(query, keep_blank_values=True)
    pairs.sort(key=lambda kv: kv[0])
    return urlencode(pairs, doseq=True)


def _apply_trailing_slash(path: str, policy: str) -> str:
    if not path:
        return '/' if policy == 'add' else path
    if policy == 'preserve':
        return path
    if policy == 'strip' and len(path) > 1 and path.endswith('/'):
        return path.rstrip('/')
    if policy == 'add' and not path.endswith('/') and '.' not in path.rsplit('/', 1)[-1]:
        # Don't add a slash on what looks like a file (has extension)
        return path + '/'
    return path


def normalize_url(url: str, rules: Optional[Dict] = None) -> str:
    """Normalize a URL according to the configured rules.

    Idempotent: ``normalize_url(normalize_url(u)) == normalize_url(u)``.
    """
    if not url or not isinstance(url, str):
        return url
    rules = _get_rules(rules)

    # Stage 1: anchor
    url = _remove_anchor(url)

    # Stage 1b: structural sanitization (corrupt suffixes, double scheme)
    url = _fix_double_scheme(url)
    url = _strip_corrupt_suffix(url)

    # Stage 2: archive unwrapping (recursive)
    if rules.get('unwrap_archive', True):
        url = _unwrap_archive(url)

    # Re-strip the anchor in case unwrap revealed a fragment
    url = _remove_anchor(url)
    url = _strip_corrupt_suffix(url)

    parsed = urlparse(url)
    scheme = parsed.scheme
    netloc = parsed.netloc
    path = parsed.path
    query = parsed.query

    # Stage 3: scheme
    if rules.get('force_https') and scheme == 'http':
        scheme = 'https'

    # Stage 4: host case
    if rules.get('lowercase_host', True) and netloc:
        # Preserve userinfo / port if any
        if '@' in netloc:
            userinfo, hostport = netloc.rsplit('@', 1)
            netloc = userinfo + '@' + hostport.lower()
        else:
            netloc = netloc.lower()

    # Stage 5: www stripping
    if rules.get('strip_www') and netloc.lower().startswith('www.'):
        netloc = netloc[4:]

    # Stage 6: mobile subdomain stripping
    if rules.get('strip_mobile_subdomain') and netloc.lower().startswith('m.'):
        netloc = netloc[2:]

    # Stage 7: tracker params
    trackers = rules.get('strip_trackers') or []
    if trackers and query:
        query = _drop_tracker_params(query, trackers)

    # Stage 8: query ordering
    if rules.get('normalize_query_order', True) and query:
        query = _sort_query(query)

    # Stage 9: trailing slash
    policy = rules.get('trailing_slash', 'preserve')
    path = _apply_trailing_slash(path, policy)

    return urlunparse((scheme, netloc, path, parsed.params, query, ''))


def classify_url(url: str) -> Dict:
    """Diagnostic info — used by tests and the `land normalize` CLI."""
    parsed = urlparse(url)
    return {
        'is_archive': is_archive_wrapper(url),
        'scheme': parsed.scheme,
        'host': parsed.netloc,
        'has_anchor': bool(parsed.fragment),
        'has_query': bool(parsed.query),
    }
