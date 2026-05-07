"""Merge web.archive.org duplicate Expressions into their canonical counterpart.

Companion to unwrap_archive_urls.py. After unwrap, some archive Expressions
remain because their canonical (unwrapped) URL was already present in the Land
as a separate Expression — meaning the link graph is split between the archive
copy and the canonical copy.

This script:
  * finds every archive Expression whose unwrapped URL already exists as
    another Expression in the same Land,
  * remaps every ExpressionLink that touched the archive copy to point to the
    canonical copy (deduplicating collisions and self-loops),
  * deletes the archive Expression (CASCADE removes its Media / Paragraph /
    TaggedContent — those came from the Wayback snapshot and are noisy by
    design; the canonical copy has — or will have — its own).

Always run unwrap_archive_urls.py FIRST. Always backup data/mwi.db FIRST.

Examples:
    python scripts/merge_archive_duplicates.py --name=melenchon --dry-run
    python scripts/merge_archive_duplicates.py --name=melenchon
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mwi import core, model


ARCHIVE_PREFIXES = (
    'http://web.archive.org/',
    'https://web.archive.org/',
    'http://archive.org/web/',
    'https://archive.org/web/',
    'http://ghostarchive.org/',
    'https://ghostarchive.org/',
)


def _is_archive_url(url: str) -> bool:
    return any(url.startswith(p) for p in ARCHIVE_PREFIXES)


def _collect_pairs(land):
    """Return list of (archive_expr, canonical_expr) inside this land.

    Filters archive URLs at SQL level (only ~tens of thousands of rows scanned
    even on a 100k-Expression Land). Looks up the canonical counterpart with
    one indexed query per archive.
    """
    Expr = model.Expression
    archive_filter = Expr.url.startswith(ARCHIVE_PREFIXES[0])
    for prefix in ARCHIVE_PREFIXES[1:]:
        archive_filter = archive_filter | Expr.url.startswith(prefix)

    archives = list(Expr.select().where((Expr.land == land) & archive_filter))
    print(f'  scanning {len(archives)} archive expressions...', flush=True)

    pairs = []
    for i, expr in enumerate(archives, start=1):
        clean = core.unwrap_archive_url(expr.url)
        if clean == expr.url:
            continue  # unrecognized archive form
        canonical = Expr.get_or_none((Expr.land == land) & (Expr.url == clean))
        if canonical is None or canonical.id == expr.id:
            continue
        pairs.append((expr, canonical))
        if i % 500 == 0:
            print(f'    progress: {i}/{len(archives)} '
                  f'({len(pairs)} pairs found so far)', flush=True)
    return _resolve_chains(pairs)


def _resolve_chains(pairs):
    """Resolve archive→canonical chains so the target of each merge is stable.

    Some archive URLs unwrap to another archive URL (Wayback of Wayback).
    Without resolution, processing order can delete a canonical before its
    archive ancestors are merged, triggering FK constraint failures.

    For each archive, walk the chain until we reach an expression that is NOT
    on the archive side of any pair. Drop pairs that resolve to themselves
    (cycle) or to None.
    """
    direct = {a.id: c for a, c in pairs}
    archive_by_id = {a.id: a for a, _ in pairs}
    archive_ids = set(direct.keys())

    resolved = []
    chain_count = 0
    for aid, archive_expr in archive_by_id.items():
        seen = {aid}
        canon = direct[aid]
        depth = 0
        while canon.id in archive_ids:
            if canon.id in seen:  # cycle
                canon = None
                break
            seen.add(canon.id)
            canon = direct[canon.id]
            depth += 1
        if canon is None or canon.id == aid:
            continue
        if depth > 0:
            chain_count += 1
        resolved.append((archive_expr, canon))

    if chain_count:
        print(f'  resolved {chain_count} chained archive→canonical pairs',
              flush=True)
    return resolved


def _merge_one(archive_expr, canonical_expr, dry_run: bool):
    """Remap links from archive → canonical, then delete archive.

    Returns dict with counts of remapped/dropped/cascaded rows.
    """
    Link = model.ExpressionLink
    remapped_in = dropped_in = 0
    remapped_out = dropped_out = 0

    # --- Incoming links: target = archive  →  target = canonical
    incoming = list(Link.select().where(Link.target == archive_expr))
    for link in incoming:
        src_id = link.source_id
        if src_id == canonical_expr.id:
            # would become a self-loop on canonical → drop
            if not dry_run:
                Link.delete().where((Link.source == src_id)
                                    & (Link.target == archive_expr)).execute()
            dropped_in += 1
            continue
        already = Link.select().where((Link.source == src_id)
                                      & (Link.target == canonical_expr)).exists()
        if already:
            if not dry_run:
                Link.delete().where((Link.source == src_id)
                                    & (Link.target == archive_expr)).execute()
            dropped_in += 1
        else:
            if not dry_run:
                Link.update(target=canonical_expr).where(
                    (Link.source == src_id)
                    & (Link.target == archive_expr)).execute()
            remapped_in += 1

    # --- Outgoing links: source = archive  →  source = canonical
    outgoing = list(Link.select().where(Link.source == archive_expr))
    for link in outgoing:
        tgt_id = link.target_id
        if tgt_id == canonical_expr.id:
            if not dry_run:
                Link.delete().where((Link.source == archive_expr)
                                    & (Link.target == tgt_id)).execute()
            dropped_out += 1
            continue
        already = Link.select().where((Link.source == canonical_expr)
                                      & (Link.target == tgt_id)).exists()
        if already:
            if not dry_run:
                Link.delete().where((Link.source == archive_expr)
                                    & (Link.target == tgt_id)).execute()
            dropped_out += 1
        else:
            if not dry_run:
                Link.update(source=canonical_expr).where(
                    (Link.source == archive_expr)
                    & (Link.target == tgt_id)).execute()
            remapped_out += 1

    # Count cascade-deleted rows for reporting
    media_count = model.Media.select().where(
        model.Media.expression == archive_expr).count()
    paragraph_count = model.Paragraph.select().where(
        model.Paragraph.expression == archive_expr).count()
    tagged_count = model.TaggedContent.select().where(
        model.TaggedContent.expression == archive_expr).count()

    if not dry_run:
        archive_expr.delete_instance()  # CASCADE on Media/Paragraph/TaggedContent

    return {
        'remapped_in': remapped_in,
        'dropped_in': dropped_in,
        'remapped_out': remapped_out,
        'dropped_out': dropped_out,
        'media_lost': media_count,
        'paragraphs_lost': paragraph_count,
        'tagged_lost': tagged_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', required=True, help='Land name')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would change, do nothing')
    parser.add_argument('--limit', type=int, default=0,
                        help='Limit number of merges (0 = no limit)')
    parser.add_argument('--verbose', action='store_true',
                        help='Print one line per merged expression')
    args = parser.parse_args()

    land = model.Land.get_or_none(model.Land.name == args.name)
    if land is None:
        print(f'Land "{args.name}" not found')
        return 1

    print(f'Scanning land "{args.name}" for archive duplicates...', flush=True)
    pairs = _collect_pairs(land)
    print(f'Found {len(pairs)} archive expressions with a canonical counterpart.',
          flush=True)
    if not pairs:
        return 0

    if args.limit and args.limit < len(pairs):
        pairs = pairs[:args.limit]
        print(f'Limited to first {len(pairs)} pairs.')

    totals = {k: 0 for k in
              ('remapped_in', 'dropped_in', 'remapped_out', 'dropped_out',
               'media_lost', 'paragraphs_lost', 'tagged_lost')}
    merged = 0

    skipped_missing = 0
    for archive_expr, canonical_expr in pairs:
        # Defensive: confirm both still exist in DB (a previous merge in this
        # run may have removed one if chain resolution missed an edge case).
        if not model.Expression.select().where(
                model.Expression.id == archive_expr.id).exists():
            skipped_missing += 1
            continue
        if not model.Expression.select().where(
                model.Expression.id == canonical_expr.id).exists():
            skipped_missing += 1
            continue
        try:
            if args.dry_run:
                stats = _merge_one(archive_expr, canonical_expr, dry_run=True)
            else:
                with model.DB.atomic():
                    stats = _merge_one(archive_expr, canonical_expr, dry_run=False)
        except Exception as exc:
            print(f'  ! merge failed for archive id={archive_expr.id}: {exc}',
                  flush=True)
            skipped_missing += 1
            continue
        for k in totals:
            totals[k] += stats[k]
        merged += 1
        if args.verbose:
            print(f'  [{merged}/{len(pairs)}] {archive_expr.url}\n'
                  f'      -> {canonical_expr.url}\n'
                  f'      links remapped in/out: {stats["remapped_in"]}/{stats["remapped_out"]}, '
                  f'dropped in/out: {stats["dropped_in"]}/{stats["dropped_out"]}, '
                  f'cascade media/paragraphs/tagged: '
                  f'{stats["media_lost"]}/{stats["paragraphs_lost"]}/{stats["tagged_lost"]}',
                  flush=True)

    verb = 'Would merge' if args.dry_run else 'Merged'
    print(f'\n{verb} {merged} archive duplicates.')
    print(f'  Links remapped (incoming): {totals["remapped_in"]}')
    print(f'  Links dropped  (incoming, already covered): {totals["dropped_in"]}')
    print(f'  Links remapped (outgoing): {totals["remapped_out"]}')
    print(f'  Links dropped  (outgoing, already covered): {totals["dropped_out"]}')
    print(f'  Cascade-deleted Media:      {totals["media_lost"]}')
    print(f'  Cascade-deleted Paragraph:  {totals["paragraphs_lost"]}')
    print(f'  Cascade-deleted TaggedContent: {totals["tagged_lost"]}')
    if skipped_missing:
        print(f'  Skipped (already gone or failed): {skipped_missing}')
    if args.dry_run:
        print('\nRun again without --dry-run to apply.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
