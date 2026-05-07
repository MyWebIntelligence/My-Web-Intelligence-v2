"""Retroactive URL normalization pipeline.

The on-line equivalent of `mwi.url_normalizer` is applied at insertion time
(`core.add_expression`). This module handles the **retroactive** case:
walking an existing Land and bringing every Expression up to the current
canonicalization rules.

Two operations:

  * **Rename** — when the new canonical URL doesn't yet exist as another
    Expression in the Land, UPDATE the row in place and populate
    `original_url`. Optionally clear `http_status` / `fetched_at` so the
    crawl picks them up again.
  * **Merge** — when the canonical URL is already present as a separate
    Expression, remap every `ExpressionLink` touching the duplicate to the
    canonical, drop self-loops and pre-existing duplicates, then delete
    the redundant Expression. CASCADE removes the duplicate's Media,
    Paragraph, and TaggedContent rows.

Each pair processed in its own `DB.atomic()`, so the script is safely
interruptible. Chains (Wayback of Wayback that span multiple Expressions)
are resolved before any modification.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from . import core, model
from .url_normalizer import normalize_url


def _collect_pairs(land: model.Land) -> Tuple[List[Tuple[model.Expression, str]],
                                              List[Tuple[model.Expression, model.Expression]]]:
    """Walk every Expression in the Land. Return two lists:

    - `to_rename`: pairs (expr, new_url) where normalization changes the URL
      and no other Expression in the Land has the canonical URL. Will be
      UPDATE'd in place.
    - `to_merge`: pairs (duplicate, canonical) where the canonical already
      exists. Will be merged into the canonical and the duplicate deleted.
    """
    Expr = model.Expression
    all_exprs = list(Expr.select().where(Expr.land == land))

    # Map url -> Expression for fast canonical lookup
    url_to_expr: Dict[str, model.Expression] = {e.url: e for e in all_exprs}

    to_rename: List[Tuple[model.Expression, str]] = []
    to_merge: List[Tuple[model.Expression, model.Expression]] = []

    for expr in all_exprs:
        new_url = normalize_url(expr.url)
        if new_url == expr.url:
            continue
        canonical = url_to_expr.get(new_url)
        if canonical is None or canonical.id == expr.id:
            to_rename.append((expr, new_url))
        else:
            to_merge.append((expr, canonical))

    return to_rename, _resolve_chains(to_merge)


def _resolve_chains(
    pairs: List[Tuple[model.Expression, model.Expression]]
) -> List[Tuple[model.Expression, model.Expression]]:
    """Resolve archive→canonical chains so the target of each merge is stable.

    If A→B and B→C are both candidate merges (B is canonical for A but
    duplicate for C), processing order matters: deleting B before merging
    A would create a dangling FK. Walk the chain so A merges directly
    into C.

    Returns pairs with stable canonicals; drops pairs that resolve to
    self (cycle).
    """
    direct = {a.id: c for a, c in pairs}
    archive_by_id = {a.id: a for a, _ in pairs}
    archive_ids = set(direct.keys())

    resolved = []
    for aid, archive_expr in archive_by_id.items():
        seen = {aid}
        canon = direct[aid]
        while canon.id in archive_ids:
            if canon.id in seen:  # cycle
                canon = None
                break
            seen.add(canon.id)
            canon = direct[canon.id]
        if canon is None or canon.id == aid:
            continue
        resolved.append((archive_expr, canon))
    return resolved


def _rename_one(expr: model.Expression, new_url: str, reset_status: bool) -> None:
    """Rename an Expression in place to its canonical URL.

    Updates `domain` because the new URL may have a different host, and
    fills `original_url` for provenance.
    """
    raw_url = expr.url
    domain_name = core.get_domain_name(new_url)
    domain, _ = model.Domain.get_or_create(name=domain_name)
    expr.url = new_url
    expr.domain = domain
    if expr.original_url is None:
        expr.original_url = raw_url
    if reset_status:
        expr.http_status = None
        expr.fetched_at = None
    expr.save()


def _merge_one(duplicate: model.Expression,
               canonical: model.Expression) -> Dict[str, int]:
    """Remap links from duplicate → canonical, then delete the duplicate."""
    Link = model.ExpressionLink
    remapped_in = dropped_in = remapped_out = dropped_out = 0

    # Incoming: target=duplicate → target=canonical
    incoming = list(Link.select().where(Link.target == duplicate))
    for link in incoming:
        src_id = link.source_id
        if src_id == canonical.id:
            Link.delete().where((Link.source == src_id)
                                & (Link.target == duplicate)).execute()
            dropped_in += 1
            continue
        if Link.select().where((Link.source == src_id)
                               & (Link.target == canonical)).exists():
            Link.delete().where((Link.source == src_id)
                                & (Link.target == duplicate)).execute()
            dropped_in += 1
        else:
            Link.update(target=canonical).where(
                (Link.source == src_id)
                & (Link.target == duplicate)).execute()
            remapped_in += 1

    # Outgoing: source=duplicate → source=canonical
    outgoing = list(Link.select().where(Link.source == duplicate))
    for link in outgoing:
        tgt_id = link.target_id
        if tgt_id == canonical.id:
            Link.delete().where((Link.source == duplicate)
                                & (Link.target == tgt_id)).execute()
            dropped_out += 1
            continue
        if Link.select().where((Link.source == canonical)
                               & (Link.target == tgt_id)).exists():
            Link.delete().where((Link.source == duplicate)
                                & (Link.target == tgt_id)).execute()
            dropped_out += 1
        else:
            Link.update(source=canonical).where(
                (Link.source == duplicate)
                & (Link.target == tgt_id)).execute()
            remapped_out += 1

    media_count = model.Media.select().where(
        model.Media.expression == duplicate).count()
    paragraph_count = model.Paragraph.select().where(
        model.Paragraph.expression == duplicate).count()
    tagged_count = model.TaggedContent.select().where(
        model.TaggedContent.expression == duplicate).count()

    duplicate.delete_instance()  # CASCADE on Media/Paragraph/TaggedContent

    return {
        'remapped_in': remapped_in,
        'dropped_in': dropped_in,
        'remapped_out': remapped_out,
        'dropped_out': dropped_out,
        'media_lost': media_count,
        'paragraphs_lost': paragraph_count,
        'tagged_lost': tagged_count,
    }


def normalize_land(land: model.Land,
                   dry_run: bool = False,
                   limit: int = 0,
                   reset_status: bool = False,
                   verbose: bool = False) -> Dict[str, int]:
    """Apply the URL normalization pipeline retroactively to a Land.

    Returns a dict with operation counts. When `dry_run=True`, no DB write
    occurs but the same counts are computed.
    """
    print(f'Scanning land "{land.name}" for URL normalization...', flush=True)
    to_rename, to_merge = _collect_pairs(land)
    print(f'  {len(to_rename)} URLs to rename, {len(to_merge)} duplicates to merge.',
          flush=True)

    if limit:
        to_rename = to_rename[:limit]
        to_merge = to_merge[:max(0, limit - len(to_rename))]

    totals = {
        'renamed': 0,
        'merged': 0,
        'remapped_in': 0,
        'dropped_in': 0,
        'remapped_out': 0,
        'dropped_out': 0,
        'media_lost': 0,
        'paragraphs_lost': 0,
        'tagged_lost': 0,
        'skipped': 0,
    }

    for expr, new_url in to_rename:
        if dry_run:
            totals['renamed'] += 1
            if verbose:
                print(f'  RENAME {expr.url}\n      -> {new_url}', flush=True)
            continue
        try:
            with model.DB.atomic():
                _rename_one(expr, new_url, reset_status)
            totals['renamed'] += 1
            if verbose:
                print(f'  RENAME {expr.url} -> {new_url}', flush=True)
        except Exception as exc:
            print(f'  ! rename failed for id={expr.id}: {exc}', flush=True)
            totals['skipped'] += 1

    for duplicate, canonical in to_merge:
        if dry_run:
            totals['merged'] += 1
            if verbose:
                print(f'  MERGE {duplicate.url}\n      -> {canonical.url}', flush=True)
            continue
        # Defensive existence checks
        if not model.Expression.select().where(
                model.Expression.id == duplicate.id).exists():
            totals['skipped'] += 1
            continue
        if not model.Expression.select().where(
                model.Expression.id == canonical.id).exists():
            totals['skipped'] += 1
            continue
        try:
            with model.DB.atomic():
                stats = _merge_one(duplicate, canonical)
            totals['merged'] += 1
            for k in ('remapped_in', 'dropped_in', 'remapped_out',
                      'dropped_out', 'media_lost', 'paragraphs_lost',
                      'tagged_lost'):
                totals[k] += stats[k]
            if verbose:
                print(f'  MERGE {duplicate.url} -> {canonical.url} '
                      f'(in {stats["remapped_in"]}+{stats["dropped_in"]} / '
                      f'out {stats["remapped_out"]}+{stats["dropped_out"]})',
                      flush=True)
        except Exception as exc:
            print(f'  ! merge failed for id={duplicate.id}: {exc}', flush=True)
            totals['skipped'] += 1

    return totals
