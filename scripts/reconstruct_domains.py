"""Reconstruct Expression.domain from URLs via the platform heuristics table.

One-off recovery / rebaseline tool. For every expression of a land it recomputes
``core.domain_from_url(url)`` (the unified 163-platform table) and compares it to
the stored domain. DRY-RUN by default: it only reports what WOULD change (counts,
top transitions, samples) and writes nothing. Pass ``--apply`` to reassign, in
chunked transactions (WAL single-writer friendly). URL-only: no network, so it
works on lands crawled without ``--fullhtml``.

Usage:
    python scripts/reconstruct_domains.py --name LAND --db data/mwi_x.db
    python scripts/reconstruct_domains.py --name LAND --db data/mwi_x.db --apply
"""
import argparse
import sys
from collections import Counter
from os import path

sys.path.insert(0, path.dirname(path.dirname(path.abspath(__file__))))

from mwi import core, model  # noqa: E402

_PRAGMAS = {
    'journal_mode': 'wal',
    'cache_size': -1 * 512000,
    'foreign_keys': 1,
    'ignore_check_constrains': 0,
    'synchronous': 0,
}


def _switch_db(db_path):
    abs_path = path.abspath(db_path)
    model.DB.close()
    model.DB.init(abs_path, pragmas=_PRAGMAS)
    print(f"Using database: {abs_path}")


def reconstruct(land_name, apply=False, limit=None, chunk=500, samples=25):
    land = model.Land.get_or_none(model.Land.name == land_name)
    if land is None:
        print('Land "%s" not found' % land_name)
        return 1

    domains = {d.id: d.name for d in model.Domain.select()}
    query = (model.Expression
             .select(model.Expression.id, model.Expression.url,
                     model.Expression.domain)
             .where(model.Expression.land == land)
             .order_by(model.Expression.id))
    if limit:
        query = query.limit(limit)

    changes = []          # (expr_id, url, old_domain, new_domain)
    transitions = Counter()  # (old_pattern, new) -> count, for the summary
    scanned = 0
    for e in query.iterator():
        scanned += 1
        old = domains.get(e.domain_id)
        new = core.domain_from_url(str(e.url))
        if new != old:
            changes.append((e.id, str(e.url), old, new))
            transitions[(old, new)] += 1

    print(f"\nScanned {scanned} expressions in land '{land_name}'.")
    print(f"Domains that WOULD change: {len(changes)}"
          f"{'' if apply else '  (dry-run — nothing written)'}")

    if changes:
        print("\nTop 25 transitions (old_domain -> new_domain : count):")
        for (old, new), n in transitions.most_common(25):
            print(f"  {n:>6}  {old!r} -> {new!r}")
        print(f"\nFirst {min(samples, len(changes))} sample URLs:")
        for _id, url, old, new in changes[:samples]:
            print(f"  {old!r} -> {new!r}   {url}")

    if not apply:
        print("\nDry-run only. Re-run with --apply to write these reassignments.")
        return 0

    print(f"\nApplying {len(changes)} reassignments in chunks of {chunk}...")
    dom_cache = {}
    updated = 0
    ids_urls = [(cid, new) for cid, _url, _old, new in changes]
    for start in range(0, len(ids_urls), chunk):
        batch = ids_urls[start:start + chunk]
        with model.DB.atomic():
            for expr_id, new_domain in batch:
                to_domain = dom_cache.get(new_domain)
                if to_domain is None:
                    to_domain, _ = model.Domain.get_or_create(name=new_domain)
                    dom_cache[new_domain] = to_domain
                (model.Expression
                 .update(domain=to_domain)
                 .where(model.Expression.id == expr_id)
                 .execute())
                updated += 1
    print(f"Done. {updated} expressions reassigned.")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description='Reconstruct Expression.domain from URLs (dry-run by default).')
    parser.add_argument('--name', required=True, help='Land name')
    parser.add_argument('--db', default=None, help='SQLite DB path (else the default)')
    parser.add_argument('--apply', action='store_true', default=False,
                        help='Write the reassignments (default: dry-run only)')
    parser.add_argument('--limit', type=int, default=None,
                        help='Cap the expressions scanned')
    args = parser.parse_args()
    if args.db:
        _switch_db(args.db)
    sys.exit(reconstruct(args.name, apply=args.apply, limit=args.limit))


if __name__ == '__main__':
    main()
