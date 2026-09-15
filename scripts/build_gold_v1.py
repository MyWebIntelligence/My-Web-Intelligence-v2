"""Project the 3-judge coding CSV into benchmarks/body_links/gold_v1.csv.

Run ONCE; the produced CSV is committed and frozen. A change of labelling
function produces ``gold_v2.csv``, never an in-place edit of v1 (sprint
body-links, T0).

The coding CSV is a *stratified* sample of a frozen export frame: rows were
drawn separately from the ``weightbody=1`` (MWI kept the edge) and
``weightbody=0`` (raw-HTML only) strata, at different sampling rates. The
projection therefore carries the sampling design (``stratum``,
``stratum_sample_n``, ``stratum_population_n``) so the benchmark can compute
Horvitz-Thompson estimates without reading this script or the frame again.

Usage:
    python scripts/build_gold_v1.py --coding CODING.csv --frame FRAME.csv \
        [--out benchmarks/body_links/gold_v1.csv]
"""
import argparse
import csv
import hashlib
import sys
from collections import Counter

EXCLUDE_HOST = 'linkedin.com'

# Gold schema — order is the CSV header order and is part of the contract.
GOLD_COLUMNS = (
    'source_url',
    'target_url',
    'place_group',
    'place_code',
    'cites',
    'gold',
    'place_agreement',
    'cites_agreement',
    'stratum',
    'stratum_sample_n',
    'stratum_population_n',
    'anchor_tag',
    'external_target',
)

# Population counts expected from the frame, hors LinkedIn. Guard against a
# silently different frame file: the weights depend on these two integers.
EXPECTED_POPULATION = {'retained': 7442, 'eliminated': 8559}


def _excluded(row) -> bool:
    """LinkedIn rows were dropped from the coding campaign; same rule here."""
    src = (row.get('source_url') or '').lower()
    tgt = (row.get('target_url') or '').lower()
    return EXCLUDE_HOST in src or EXCLUDE_HOST in tgt


def count_frame(frame_csv: str) -> dict:
    """Count the sampling-frame population per stratum, hors LinkedIn."""
    counts = Counter()
    with open(frame_csv, encoding='utf-8', errors='replace') as handle:
        for row in csv.DictReader(handle):
            if _excluded(row):
                continue
            body = (row.get('weightbody') or '').strip()
            counts['retained' if body == '1' else 'eliminated'] += 1
    return dict(counts)


def project(coding_csv: str, frame_csv: str, out_csv: str) -> int:
    """Write the gold CSV. Returns the number of data rows written."""
    population = count_frame(frame_csv)
    if population != EXPECTED_POPULATION:
        raise SystemExit(
            'Frame population mismatch: got {}, expected {}. Wrong frame file?'
            .format(population, EXPECTED_POPULATION))

    with open(coding_csv, encoding='utf-8-sig') as handle:
        coded = [r for r in csv.DictReader(handle) if not _excluded(r)]

    sample = Counter((r.get('body_extraction_mwi') or '').strip() for r in coded)

    rows = []
    for row in coded:
        stratum = (row.get('body_extraction_mwi') or '').strip()
        if stratum not in population:
            raise SystemExit('Unknown stratum {!r}'.format(stratum))
        # human_* columns exist but were never filled (no human arbitration);
        # they are honoured anyway so a later arbitration pass just works.
        group = ((row.get('human_place_group') or '').strip()
                 or (row.get('panel_place_group') or '').strip())
        cites = ((row.get('human_cites') or '').strip()
                 or (row.get('panel_cites') or '').strip())
        rows.append({
            'source_url': row.get('source_url') or '',
            'target_url': row.get('target_url') or '',
            'place_group': group,
            'place_code': (row.get('panel_place_code') or '').strip(),
            'cites': cites,
            # Labelling function, materialised so it cannot silently drift.
            'gold': '1' if (group == 'EDITORIAL' and cites == '1') else '0',
            'place_agreement': (row.get('panel_place_agreement') or '').strip(),
            'cites_agreement': (row.get('panel_cites_agreement') or '').strip(),
            'stratum': stratum,
            'stratum_sample_n': sample[stratum],
            'stratum_population_n': population[stratum],
            'anchor_tag': (row.get('anchor_tag') or '').strip(),
            'external_target': (row.get('external_target') or '').strip(),
        })

    rows.sort(key=lambda r: (r['source_url'], r['target_url']))

    # csv.writer emits \r\n by default even with newline='\n'; force LF so the
    # file is byte-stable across platforms.
    with open(out_csv, 'w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(GOLD_COLUMNS),
                                quoting=csv.QUOTE_ALL, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def sha256_of(path_: str) -> str:
    digest = hashlib.sha256()
    with open(path_, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--coding', required=True, help='3-judge coding CSV')
    parser.add_argument('--frame', required=True, help='sampling frame CSV')
    parser.add_argument('--out', default='benchmarks/body_links/gold_v1.csv')
    args = parser.parse_args(argv)

    written = project(args.coding, args.frame, args.out)
    print('rows written : {}'.format(written))
    print('coding sha256: {}'.format(sha256_of(args.coding)))
    print('frame  sha256: {}'.format(sha256_of(args.frame)))
    print('gold   sha256: {}'.format(sha256_of(args.out)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
