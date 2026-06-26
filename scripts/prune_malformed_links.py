#!/usr/bin/env python3
"""Prune malformed orphan link nodes after consolidate (sprint EXTRACTLINKS-2026-06, DATA-2).

Once ``land consolidate`` has rebuilt the ``ExpressionLink`` graph with the
fixed parser, the old corrupted target nodes no longer receive any inbound
edge. This script removes them.

Predicate (sprint Annexe C) — an ``Expression`` of the land that:
  - was never crawled to readable (``readable IS NULL``),
  - carries a corruption signature in its URL (``)(``  ``](``  ``)[``
    ``javascript:``  or more ``(`` than ``)``),
  - and has NO inbound ``ExpressionLink``.

Safe by default: ``--dry-run`` (the default) only counts and samples. ``--apply``
deletes (CASCADE removes the row's Media / Paragraph / TaggedContent). The DB is
the one configured in ``settings.data_location`` — run from the land's clone.

ALWAYS back up first:
    cp data/mwi.db data/mwi.db.bak_$(date +%Y%m%d_%H%M%S)

Usage:
    python scripts/prune_malformed_links.py --land=airegulation --dry-run
    python scripts/prune_malformed_links.py --land=airegulation --apply [--vacuum]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from peewee import fn  # noqa: E402

from mwi import model  # noqa: E402

CHUNK = 500  # bound the IN(...) clause (SQLITE_MAX_VARIABLE_NUMBER)


def build_predicate(land):
    """Peewee predicate for the Annexe C malformed-orphan node set."""
    Expression = model.Expression
    ExpressionLink = model.ExpressionLink

    open_count = (fn.LENGTH(Expression.url)
                  - fn.LENGTH(fn.REPLACE(Expression.url, '(', '')))
    close_count = (fn.LENGTH(Expression.url)
                   - fn.LENGTH(fn.REPLACE(Expression.url, ')', '')))
    corruption = (
        Expression.url.contains(')(')
        | Expression.url.contains('](')
        | Expression.url.contains(')[')
        | Expression.url.contains('javascript:')
        | (open_count > close_count)
    )
    inbound = ExpressionLink.select(ExpressionLink.target)
    return (
        (Expression.land == land)
        & Expression.readable.is_null(True)
        & corruption
        & Expression.id.not_in(inbound)
    )


def main():
    parser = argparse.ArgumentParser(
        description="Prune malformed orphan link nodes (sprint EXTRACTLINKS, DATA-2).")
    parser.add_argument('--land', required=True, help="Land name")
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--dry-run', action='store_true',
                       help="Count + sample only (default)")
    group.add_argument('--apply', action='store_true',
                       help="Actually delete the matched nodes")
    parser.add_argument('--vacuum', action='store_true',
                        help="VACUUM after --apply (slow on a large DB)")
    args = parser.parse_args()

    land = model.Land.get_or_none(model.Land.name == args.land)
    if land is None:
        print(f"Land '{args.land}' not found.")
        return 1

    query = model.Expression.select().where(build_predicate(land))
    total = query.count()
    print(f"Land '{args.land}' (id={land.id}): "
          f"{total} malformed orphan node(s) matched.")
    if total == 0:
        return 0

    print("\nSample (up to 20):")
    for expr in query.limit(20):
        print(f"  #{expr.id}  {expr.url}")

    if not args.apply:
        print(f"\nDRY-RUN — nothing deleted. Re-run with --apply to remove "
              f"{total} node(s).")
        print("Back up first:  "
              "cp data/mwi.db data/mwi.db.bak_$(date +%Y%m%d_%H%M%S)")
        return 0

    ids = [expr.id for expr in query]
    deleted = 0
    with model.DB.atomic():
        for start in range(0, len(ids), CHUNK):
            chunk = ids[start:start + CHUNK]
            deleted += (model.Expression
                        .delete()
                        .where(model.Expression.id.in_(chunk))
                        .execute())
    print(f"\nDeleted {deleted} malformed orphan node(s).")

    if args.vacuum:
        print("VACUUM… (this can take a while on a multi-GB DB)")
        model.DB.execute_sql("VACUUM;")
        print("VACUUM done.")

    remaining = model.Expression.select().where(build_predicate(land)).count()
    print(f"Re-scan: {remaining} malformed orphan node(s) remaining.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
