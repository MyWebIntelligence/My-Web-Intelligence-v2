"""Unwrap web.archive.org / ghostarchive.org URLs in the database.

Converts archive snapshot URLs back to their original target URL. Useful when
SerpAPI returns archive.org snapshots as seeds and the crawler keeps hitting
archive.org timeouts (Status: 000).

Examples:
    # Preview what would change for a specific land
    python scripts/unwrap_archive_urls.py --name=melenchon --dry-run

    # Apply the cleanup
    python scripts/unwrap_archive_urls.py --name=melenchon

    # Same, but reset http_status so the unwrapped URLs get re-crawled
    python scripts/unwrap_archive_urls.py --name=melenchon --reset-status
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mwi import core, model


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', required=True, help='Land name')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would change, do nothing')
    parser.add_argument('--reset-status', action='store_true',
                        help='Clear http_status / fetched_at so the unwrapped '
                             'URL is re-crawled on next `land crawl`')
    args = parser.parse_args()

    land = model.Land.get_or_none(model.Land.name == args.name)
    if land is None:
        print(f'Land "{args.name}" not found')
        return 1

    candidates = (model.Expression
                  .select()
                  .where((model.Expression.land == land)
                         & ((model.Expression.url.startswith('http://web.archive.org/'))
                            | (model.Expression.url.startswith('https://web.archive.org/'))
                            | (model.Expression.url.startswith('http://archive.org/web/'))
                            | (model.Expression.url.startswith('https://archive.org/web/'))
                            | (model.Expression.url.startswith('http://ghostarchive.org/'))
                            | (model.Expression.url.startswith('https://ghostarchive.org/')))))

    total = candidates.count()
    print(f'Found {total} archive URLs in land "{args.name}".')
    if total == 0:
        return 0

    # Build the set of URLs already present in this land to detect collisions
    existing_urls = set(row.url for row in
                        model.Expression
                        .select(model.Expression.url)
                        .where(model.Expression.land == land))

    changed, skipped_noop, skipped_dup = 0, 0, 0
    for expr in candidates:
        new_url = core.unwrap_archive_url(expr.url)
        if new_url == expr.url:
            skipped_noop += 1
            continue
        if new_url in existing_urls:
            skipped_dup += 1
            if args.dry_run:
                print(f'  DUP   {expr.url}\n     -> {new_url} (already in land)')
            continue

        if args.dry_run:
            print(f'  UNWRAP {expr.url}\n      -> {new_url}')
        else:
            domain_name = core.get_domain_name(new_url)
            domain, _ = model.Domain.get_or_create(name=domain_name)
            expr.url = new_url
            expr.domain = domain
            if args.reset_status:
                expr.http_status = None
                expr.fetched_at = None
            expr.save()
            existing_urls.add(new_url)
        changed += 1

    verb = 'Would update' if args.dry_run else 'Updated'
    print(f'\n{verb}: {changed}    no-op: {skipped_noop}    duplicates skipped: {skipped_dup}')
    if args.dry_run:
        print('Run again without --dry-run to apply.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
