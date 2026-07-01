"""Measure HTML-based domain resolution on a land (sprint-heuristique task 7).

Read-only diagnostic. For every opaque-platform expression that has stored HTML
(``expression.html``, populated under ``--fullhtml``), it reports — per matched
platform suffix — how often the generic HTML cascade recovers a *better* domain
than the URL heuristic alone. Low-rate suffixes are candidates for a per-site
special case; high-rate suffixes prove the generic cascade suffices (sprint §7
anti-dispersion). Nothing is written to the database.

Usage:
    python scripts/measure_heuristic_resolution.py --name LAND [--limit N]

Output: a table `suffix | with_html | signal | improved | rate` sorted worst
rate first, plus a total line. "signal" = the HTML cascade returned a resolvable
editorial URL; "improved" = that URL resolved to a domain different from the URL
heuristic (i.e. the HTML actually changed the grouping).
"""
import argparse
import sys
from collections import defaultdict
from os import path
from urllib.parse import urlparse

sys.path.insert(0, path.dirname(path.dirname(path.abspath(__file__))))

from mwi import core, model  # noqa: E402


def _matched_suffix(url: str):
    """Return the opaque platform suffix that url matches, or None."""
    host = urlparse(url).netloc.lower()
    if host.startswith('www.'):
        host = host[4:]
    if not host:
        return None
    for suffix in core._opaque_platforms():
        if host == suffix or host.endswith('.' + suffix):
            return suffix
    return None


def measure(land_name: str, limit=None):
    land = model.Land.get_or_none(model.Land.name == land_name)
    if land is None:
        print('Land "%s" not found' % land_name)
        return 1

    query = (model.Expression
             .select()
             .where((model.Expression.land == land)
                    & model.Expression.html.is_null(False))
             .order_by(model.Expression.id))

    # counters[suffix] = [with_html, signal, improved]
    counters = defaultdict(lambda: [0, 0, 0])
    scanned = 0
    for expression in query:
        url = str(expression.url)
        suffix = _matched_suffix(url)
        if suffix is None:
            continue
        counters[suffix][0] += 1
        html_dom = core.domain_from_html(url, expression.html)
        if html_dom is not None:
            counters[suffix][1] += 1
            if html_dom != core.domain_from_url(url):
                counters[suffix][2] += 1
        scanned += 1
        if limit and scanned >= limit:
            break

    if not counters:
        print('No opaque-platform expression with stored HTML in "%s".' % land_name)
        print('Tip: this land must have been crawled with --fullhtml.')
        return 0

    rows = []
    tot = [0, 0, 0]
    for suffix, (n, sig, imp) in counters.items():
        for i in range(3):
            tot[i] += (n, sig, imp)[i]
        rows.append((suffix, n, sig, imp, (imp / n) if n else 0.0))
    rows.sort(key=lambda r: (r[4], -r[1]))  # worst rate first, then volume

    width = max(len(r[0]) for r in rows)
    print(f'{"suffix":<{width}}  with_html   signal  improved   rate')
    for suffix, n, sig, imp, rate in rows:
        print(f'{suffix:<{width}}  {n:>9}  {sig:>7}  {imp:>8}  {rate:>5.1%}')
    total_rate = (tot[2] / tot[0]) if tot[0] else 0.0
    print(f'{"TOTAL":<{width}}  {tot[0]:>9}  {tot[1]:>7}  {tot[2]:>8}  {total_rate:>5.1%}')
    return 0


def main():
    parser = argparse.ArgumentParser(
        description='Measure HTML-based domain resolution on a land (read-only).')
    parser.add_argument('--name', required=True, help='Land name')
    parser.add_argument('--limit', type=int, default=None,
                        help='Cap the opaque expressions scanned')
    args = parser.parse_args()
    sys.exit(measure(args.name, args.limit))


if __name__ == '__main__':
    main()
