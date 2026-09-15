"""Build the offline bench corpus once from an MWI database (read-only).

Sprint body-links, T0. The benchmark must never open a 7-9 GB land database:
it would tie every run to one machine, to the availability of a file on a
nearly-full volume, and to whichever snapshot happens to be lying around. This
script extracts, ONCE, the ~1100 source pages the gold set needs plus the node
table of the closed network, into a ~60 MB SQLite that is regenerable, hashed
per page, and gitignored.

The source database is opened read-only; nothing is ever written to it.

Usage:
    python scripts/build_bench_cache.py --source-db PATH --gold GOLD.csv \
        --out benchmarks/body_links/cache/bench_corpus_v1.sqlite \
        --manifest benchmarks/body_links/cache_manifest_v1.csv \
        [--frame FRAME.csv] [--land airegulation] [--minrel 1]
"""
import argparse
import csv
import hashlib
import os
import sqlite3
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mwi import link_context  # noqa: E402
from mwi.benchmark_body_links import BENCH_URL_RULES, GOLD_COLUMNS  # noqa: E402

SCHEMA = """
CREATE TABLE bench_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE node (id INTEGER PRIMARY KEY, url TEXT NOT NULL,
                   relevance INTEGER NOT NULL, depth INTEGER);
CREATE TABLE page (url TEXT PRIMARY KEY, html BLOB NOT NULL,
                   encoding TEXT NOT NULL, sha256 TEXT NOT NULL,
                   bytes INTEGER NOT NULL);
CREATE TABLE frame_edge (source_id INTEGER, target_id INTEGER,
                         weightbody INTEGER,
                         PRIMARY KEY (source_id, target_id));
CREATE INDEX node_url ON node(url);
"""


def open_source(path: str) -> sqlite3.Connection:
    """Read-only, and immutable when the WAL is provably empty.

    immutable=1 skips lock files entirely -- the strongest no-write guarantee
    available -- but it also ignores the content of a non-empty -wal, which
    would silently hide recent rows. So it is only used once the -wal is
    checked to be zero bytes.
    """
    wal = path + '-wal'
    quiet = (not os.path.exists(wal)) or os.path.getsize(wal) == 0
    uri = 'file:{}?mode=ro{}'.format(path, '&immutable=1' if quiet else '')
    if not quiet:
        print('WARNING: {} is not empty; opening read-only without immutable.'
              .format(os.path.basename(wal)))
    return sqlite3.connect(uri, uri=True)


def read_gold_sources(gold_csv: str):
    with open(gold_csv, encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != GOLD_COLUMNS:
            raise SystemExit('Unexpected gold header in {}'.format(gold_csv))
        return sorted({row['source_url'] for row in reader})


def build(source_db: str, gold_csv: str, out_sqlite: str, manifest_csv: str,
          land: str, minrel: int, frame_csv=None) -> int:
    sources = read_gold_sources(gold_csv)
    src = open_source(source_db)

    land_row = src.execute('SELECT id FROM land WHERE name = ?',
                           (land,)).fetchone()
    if land_row is None:
        raise SystemExit('Land {!r} not found in {}'.format(land, source_db))
    land_id = land_row[0]

    print('loading expressions of land {} ...'.format(land_id))
    rows = src.execute(
        'SELECT id, url, relevance, depth FROM expression WHERE land_id = ? '
        'ORDER BY id', (land_id,)).fetchall()
    print('  {} expressions'.format(len(rows)))

    nodes = [r for r in rows if (r[2] or 0) >= minrel]
    print('  {} nodes at relevance >= {}'.format(len(nodes), minrel))

    # Resolve the gold source URLs onto expression ids through the same 3-key
    # ladder production uses, so a URL variant is not mistaken for a miss.
    index = link_context.build_url_index([(r[0], r[1]) for r in rows],
                                         rules=BENCH_URL_RULES)
    wanted = {}
    missing = []
    for url in sources:
        eid = link_context.resolve_url_in_index(index, url,
                                                rules=BENCH_URL_RULES)
        if eid is None:
            missing.append(url)
        else:
            wanted[eid] = url
    if missing:
        raise SystemExit(
            '{} gold source pages are absent from this database '
            '(wrong snapshot?). First: {}'.format(len(missing), missing[0]))
    print('  {} gold source pages resolved'.format(len(wanted)))

    if os.path.exists(out_sqlite):
        os.remove(out_sqlite)
    os.makedirs(os.path.dirname(out_sqlite) or '.', exist_ok=True)
    out = sqlite3.connect(out_sqlite)
    out.executescript(SCHEMA)

    out.executemany('INSERT INTO bench_meta VALUES (?, ?)', sorted({
        'schema_version': '1',
        'land': land,
        'minrel': str(minrel),
        'gold_file': os.path.basename(gold_csv),
        'source_db_basename': os.path.basename(source_db),
    }.items()))
    out.executemany('INSERT INTO node VALUES (?, ?, ?, ?)',
                    [(r[0], r[1], r[2] or 0, r[3]) for r in nodes])

    manifest = []
    empty = []
    for eid in sorted(wanted):
        row = src.execute('SELECT html FROM expression WHERE id = ?',
                          (eid,)).fetchone()
        html = row[0] if row else None
        if not html:
            empty.append(wanted[eid])
            continue
        raw = html.encode('utf-8') if isinstance(html, str) else bytes(html)
        digest = hashlib.sha256(raw).hexdigest()
        out.execute('INSERT INTO page VALUES (?, ?, ?, ?, ?)',
                    (wanted[eid], zlib.compress(raw, 6), 'zlib', digest,
                     len(raw)))
        manifest.append((wanted[eid], digest, len(raw)))
    if empty:
        raise SystemExit(
            '{} gold source pages have no stored HTML (land not crawled with '
            '--fullhtml?). First: {}'.format(len(empty), empty[0]))
    print('  {} pages stored'.format(len(manifest)))

    if frame_csv:
        node_ids = {r[0] for r in nodes}
        edges = []
        with open(frame_csv, encoding='utf-8', errors='replace') as handle:
            for row in csv.DictReader(handle):
                try:
                    sid = int(row['Source'])
                    tid = int(row['Target'])
                except (KeyError, TypeError, ValueError):
                    continue
                if sid in node_ids and tid in node_ids:
                    body = 1 if (row.get('weightbody') or '').strip() == '1' else 0
                    edges.append((sid, tid, body))
        edges.sort()
        out.executemany(
            'INSERT OR REPLACE INTO frame_edge VALUES (?, ?, ?)', edges)
        print('  {} frame edges'.format(len(edges)))

    out.commit()
    out.execute('VACUUM')
    out.close()
    src.close()

    manifest.sort()
    with open(manifest_csv, 'w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle, quoting=csv.QUOTE_ALL, lineterminator='\n')
        writer.writerow(('source_url', 'sha256', 'bytes'))
        writer.writerows(manifest)

    size_mb = os.path.getsize(out_sqlite) / (1024 * 1024)
    print('corpus : {} ({:.1f} MB)'.format(out_sqlite, size_mb))
    print('manifest: {} ({} rows)'.format(manifest_csv, len(manifest)))
    return len(manifest)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-db', required=True)
    parser.add_argument('--gold', default='benchmarks/body_links/gold_v1.csv')
    parser.add_argument(
        '--out', default='benchmarks/body_links/cache/bench_corpus_v1.sqlite')
    parser.add_argument(
        '--manifest', default='benchmarks/body_links/cache_manifest_v1.csv')
    parser.add_argument('--frame', default=None)
    parser.add_argument('--land', default='airegulation')
    parser.add_argument('--minrel', type=int, default=1)
    args = parser.parse_args(argv)

    build(args.source_db, args.gold, args.out, args.manifest,
          args.land, args.minrel, args.frame)
    return 0


if __name__ == '__main__':
    sys.exit(main())
