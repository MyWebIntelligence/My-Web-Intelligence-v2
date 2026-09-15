"""Body-links benchmark: gold loading, stratified estimator, determinism.

Sprint body-links, T0. Everything here runs on synthetic fixtures: no network,
no MWI database, no API key, so no new pytest marker is needed (pytest.ini uses
--strict-markers).

The estimator is the point of this file. The coding campaign drew a STRATIFIED
sample -- 600 of 7442 kept edges, 943 of 8559 eliminated ones -- so precision
and recall are ratios of Horvitz-Thompson totals, not raw counts. A raw recall
under-reports by about 4.5 points.
"""
import csv
import os
import sqlite3
import subprocess
import sys
import zlib

import pytest

from mwi import benchmark_body_links as bench


# --------------------------------------------------------------------------- #
# Synthetic fixtures                                                            #
# --------------------------------------------------------------------------- #

def _gold_rows(weights):
    """Build a 10-row gold with hand-checkable counts.

    weights: (N_retained, N_eliminated). Sample sizes are fixed at 4 and 6.

    retained  (n=4): 3 gold=1 + 1 gold=0     -> the extractor kept all four
    eliminated(n=6): 2 gold=1 + 4 gold=0     -> the extractor kept none
    """
    n_ret, n_elim = weights
    rows = []
    spec = [('retained', 1, 3), ('retained', 0, 1),
            ('eliminated', 1, 2), ('eliminated', 0, 4)]
    i = 0
    for stratum, gold, count in spec:
        for _ in range(count):
            i += 1
            rows.append({
                'source_url': 'https://s{}.test/a'.format(i),
                'target_url': 'https://t{}.test/b'.format(i),
                'place_group': 'EDITORIAL' if gold else 'NAV',
                'place_code': 'EDIT_EXT' if gold else 'NAV',
                'cites': '1' if gold else '0',
                'gold': str(gold),
                'place_agreement': '3/3',
                'cites_agreement': '3/3',
                'stratum': stratum,
                'stratum_sample_n': 4 if stratum == 'retained' else 6,
                'stratum_population_n': n_ret if stratum == 'retained' else n_elim,
                'anchor_tag': 'p',
                'external_target': '1',
            })
    return rows


def _write_gold(path, rows):
    with open(path, 'w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(bench.GOLD_COLUMNS),
                                quoting=csv.QUOTE_ALL, lineterminator='\n')
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda r: (r['source_url'],
                                                     r['target_url'])))
    return str(path)


PAGE_HTML = """<html><body>
<nav><a href="https://nav.test/menu">Menu</a></nav>
<article><p>Un paragraphe de prose suffisamment long pour que Trafilatura le
retienne comme corps de texte, citant <a href="{target}">une source</a> au
milieu d'une phrase qui continue encore un peu pour depasser le seuil.</p>
<p>Un second paragraphe, tout aussi bavard, qui existe uniquement pour que
l'extraction de contenu principal ne rejette pas la page comme trop courte.</p>
</article></body></html>"""


def _make_corpus(tmp_path, gold_rows):
    """A bench corpus holding one page per gold source, plus the node table."""
    path = str(tmp_path / 'bench_corpus.sqlite')
    conn = sqlite3.connect(path)
    conn.executescript("""
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
    """)
    conn.execute("INSERT INTO bench_meta VALUES ('schema_version', '1')")
    node_id = 0
    seen = {}
    for row in gold_rows:
        for url in (row['source_url'], row['target_url']):
            if url not in seen:
                node_id += 1
                seen[url] = node_id
                conn.execute('INSERT INTO node VALUES (?, ?, ?, ?)',
                             (node_id, url, 1, 0))
    for row in gold_rows:
        html = PAGE_HTML.format(target=row['target_url']).encode('utf-8')
        conn.execute('INSERT OR REPLACE INTO page VALUES (?, ?, ?, ?, ?)',
                     (row['source_url'], zlib.compress(html), 'zlib',
                      bench.sha256_bytes(html), len(html)))
    conn.commit()
    conn.close()
    return path


# --------------------------------------------------------------------------- #

class TestGoldLoading:

    def test_loads_the_thirteen_columns(self, tmp_path):
        path = _write_gold(tmp_path / 'g.csv', _gold_rows((40, 60)))

        rows, digest = bench.load_gold(path)

        assert len(rows) == 10
        assert len(digest) == 64
        assert rows[0].stratum in ('retained', 'eliminated')

    def test_rows_are_returned_sorted(self, tmp_path):
        path = _write_gold(tmp_path / 'g.csv', _gold_rows((40, 60)))

        rows, _ = bench.load_gold(path)

        keys = [(r.source_url, r.target_url) for r in rows]
        assert keys == sorted(keys)

    def test_weight_is_population_over_sample(self, tmp_path):
        path = _write_gold(tmp_path / 'g.csv', _gold_rows((40, 15)))

        rows, _ = bench.load_gold(path)

        ret = next(r for r in rows if r.stratum == 'retained')
        elim = next(r for r in rows if r.stratum == 'eliminated')
        assert ret.weight == pytest.approx(10.0)
        assert elim.weight == pytest.approx(2.5)

    def test_unexpected_header_is_rejected(self, tmp_path):
        path = str(tmp_path / 'bad.csv')
        with open(path, 'w', encoding='utf-8', newline='') as handle:
            handle.write('source_url,target_url\n"a","b"\n')

        with pytest.raises(ValueError):
            bench.load_gold(path)

    def test_empty_place_group_is_not_gold(self, tmp_path):
        rows = _gold_rows((40, 60))
        rows[0]['place_group'] = ''
        rows[0]['place_code'] = 'NOMAJ'
        rows[0]['gold'] = '0'
        path = _write_gold(tmp_path / 'g.csv', rows)

        loaded, _ = bench.load_gold(path)

        blank = [r for r in loaded if r.place_group == '']
        assert blank and all(r.gold == 0 for r in blank)


class TestStratifiedEstimator:
    """The heart of the ticket: ratios of weighted totals, not raw counts."""

    @staticmethod
    def _kept(rows):
        """The extractor keeps exactly the rows of the `retained` stratum."""
        return {(r.source_url, r.target_url)
                for r in rows if r.stratum == 'retained'}

    def test_recall_is_weighted(self, tmp_path):
        # Unequal weights: retained x10, eliminated x2.5.
        path = _write_gold(tmp_path / 'g.csv', _gold_rows((40, 15)))
        rows, _ = bench.load_gold(path)

        result = bench.score(rows, self._kept(rows))

        # 3 TP x 10 / (3 x 10 + 2 x 2.5) = 30 / 35
        assert result.recall == pytest.approx(30.0 / 35.0)
        assert result.recall_raw == pytest.approx(0.6)
        assert result.recall != pytest.approx(result.recall_raw)

    def test_precision_reduces_to_raw_when_predictions_stay_in_one_stratum(
            self, tmp_path):
        path = _write_gold(tmp_path / 'g.csv', _gold_rows((40, 15)))
        rows, _ = bench.load_gold(path)

        result = bench.score(rows, self._kept(rows))

        # All predictions live in one stratum -> the weight cancels out.
        assert result.precision == pytest.approx(0.75)
        assert result.precision == pytest.approx(result.precision_raw)

    def test_precision_is_weighted_when_predictions_cross_strata(self, tmp_path):
        path = _write_gold(tmp_path / 'g.csv', _gold_rows((40, 15)))
        rows, _ = bench.load_gold(path)
        kept = self._kept(rows)
        # The enriched extractor also keeps one eliminated-stratum gold row.
        extra = next(r for r in rows
                     if r.stratum == 'eliminated' and r.gold == 1)
        kept.add((extra.source_url, extra.target_url))

        result = bench.score(rows, kept)

        # num = 3x10 + 1x2.5 = 32.5 ; den = 4x10 + 1x2.5 = 42.5
        assert result.precision == pytest.approx(32.5 / 42.5)
        assert result.precision_raw == pytest.approx(4.0 / 5.0)
        assert result.precision != pytest.approx(result.precision_raw)

    def test_counts_are_reported(self, tmp_path):
        path = _write_gold(tmp_path / 'g.csv', _gold_rows((40, 60)))
        rows, _ = bench.load_gold(path)

        result = bench.score(rows, self._kept(rows))

        assert (result.tp, result.fp, result.fn) == (3, 1, 2)

    def test_empty_denominator_is_nan_not_zero_division(self, tmp_path):
        path = _write_gold(tmp_path / 'g.csv', _gold_rows((40, 60)))
        rows, _ = bench.load_gold(path)

        result = bench.score(rows, set())

        assert result.precision != result.precision  # NaN
        assert result.recall == pytest.approx(0.0)

    def test_confidence_interval_is_reported_and_positive(self, tmp_path):
        path = _write_gold(tmp_path / 'g.csv', _gold_rows((40, 60)))
        rows, _ = bench.load_gold(path)

        result = bench.score(rows, self._kept(rows))

        assert result.recall_ci >= 0.0


class TestNoSideEffects:

    def test_corpus_is_opened_read_only(self, tmp_path):
        rows = _gold_rows((40, 60))
        corpus = _make_corpus(tmp_path, rows)

        conn = bench.open_corpus(corpus)
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO bench_meta VALUES ('x', 'y')")
        conn.close()

    def test_bench_never_imports_the_orm(self):
        """A bench that can import model is a bench that can write."""
        source = bench.__file__
        with open(source, encoding='utf-8') as handle:
            text = handle.read()
        assert 'from mwi import model' not in text
        assert 'import peewee' not in text


class TestEndToEndDeterminism:

    @staticmethod
    def _run(corpus, gold, out_dir, seed):
        env = dict(os.environ)
        env['PYTHONHASHSEED'] = str(seed)
        env['PYTHONPATH'] = '.'
        return subprocess.run(
            [sys.executable, '-m', 'mwi.benchmark_body_links',
             '--corpus', corpus, '--gold', gold, '--out-dir', str(out_dir)],
            env=env, capture_output=True, text=True)

    def test_two_runs_differing_hash_seed_are_byte_identical(self, tmp_path):
        rows = _gold_rows((40, 60))
        gold = _write_gold(tmp_path / 'g.csv', rows)
        corpus = _make_corpus(tmp_path, rows)

        first = self._run(corpus, gold, tmp_path / 'a', 0)
        second = self._run(corpus, gold, tmp_path / 'b', 1)

        assert first.returncode == 0, first.stderr
        assert second.returncode == 0, second.stderr
        for name in ('bench_edges.csv', 'bench_summary.txt'):
            left = (tmp_path / 'a' / name).read_bytes()
            right = (tmp_path / 'b' / name).read_bytes()
            assert left == right, '{} differs between hash seeds'.format(name)

    def test_perf_file_is_excluded_from_determinism(self, tmp_path):
        rows = _gold_rows((40, 60))
        gold = _write_gold(tmp_path / 'g.csv', rows)
        corpus = _make_corpus(tmp_path, rows)

        self._run(corpus, gold, tmp_path / 'a', 0)

        # Wall clock belongs in its own file, never in the compared outputs.
        assert (tmp_path / 'a' / 'bench_perf.json').exists()
        summary = (tmp_path / 'a' / 'bench_summary.txt').read_text('utf-8')
        assert 'pages_per_second' not in summary

    def test_named_lists_are_written(self, tmp_path):
        rows = _gold_rows((40, 60))
        gold = _write_gold(tmp_path / 'g.csv', rows)
        corpus = _make_corpus(tmp_path, rows)

        self._run(corpus, gold, tmp_path / 'a', 0)

        assert (tmp_path / 'a' / 'bench_false_kept.csv').exists()
        assert (tmp_path / 'a' / 'bench_missed.csv').exists()


class TestWorkBudget:

    def test_summary_reports_deterministic_work_counters(self, tmp_path):
        rows = _gold_rows((40, 60))
        gold = _write_gold(tmp_path / 'g.csv', rows)
        corpus = _make_corpus(tmp_path, rows)

        TestEndToEndDeterminism._run(corpus, gold, tmp_path / 'a', 0)
        summary = (tmp_path / 'a' / 'bench_summary.txt').read_text('utf-8')

        assert 'trafilatura_calls' in summary
        assert 'soup_parses' in summary
        assert 'pages ' in summary
