"""Body-links benchmark: replay the extractor against a frozen gold set.

Sprint body-links, T0. Read-only and offline by construction: the benchmark
opens a *bench corpus* (a small SQLite built once by
``scripts/build_bench_cache.py``), never an MWI database, and never imports the
ORM. Two runs on the same inputs produce byte-identical outputs.

Estimator
---------
The gold set is a STRATIFIED sample of a frozen export frame: rows were drawn
separately from the ``retained`` stratum (edges the extractor kept when the
frame was exported) and the ``eliminated`` one, at different sampling rates.
Precision and recall are therefore ratios of Horvitz-Thompson totals::

    T(A) = sum over strata h of  w_h * |{i in sample_h : A(i)}|
    precision = T(pred & gold) / T(pred)
    recall    = T(pred & gold) / T(gold)

At the baseline every prediction lives in one stratum, so the weight cancels
and precision degenerates to the raw count. It stops being true as soon as the
extractor keeps edges from the eliminated stratum, which is exactly what the
recall tickets do -- hence the general ratio from day one.

The stratum is a property of the SAMPLING DESIGN, frozen with the frame. It
stays valid when the extractor changes: changing the extractor changes the
prediction, never the stratum.

Usage:
    python -m mwi.benchmark_body_links --corpus CORPUS.sqlite --gold GOLD.csv
"""
import argparse
import csv
import hashlib
import json
import math
import os
import platform
import sqlite3
import sys
import time
import zlib
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple
from urllib.parse import urljoin

import trafilatura
from bs4 import BeautifulSoup

import settings

from . import body_links, link_context

SCHEMA_VERSION = 1

# Gold schema — order is the contract; see benchmarks/body_links/README.md.
GOLD_COLUMNS = (
    'source_url', 'target_url', 'place_group', 'place_code', 'cites', 'gold',
    'place_agreement', 'cites_agreement', 'stratum', 'stratum_sample_n',
    'stratum_population_n', 'anchor_tag', 'external_target',
)

# Normalization FROZEN for the bench. normalize_url reads the local
# configuration when no rules are passed, which would make the measured
# metrics depend on the machine. Deduced from the frame: every URL is https,
# none carries www, root paths excepted every path is slash-stripped.
BENCH_URL_RULES = {
    'unwrap_archive': True,
    'lowercase_host': True,
    'force_https': True,
    'strip_www': True,
    'normalize_query_order': True,
    'trailing_slash': 'strip',
}

VARIANTS = ('current', 'md', 'html', 'md+html', 'raw')

# Link profiles. `editorial` is the default network: body plus reference
# blocks. Reference blocks stay IN -- the ground truth labels them
# EDITORIAL, and excluding them would convert 64 true positives into losses.
PROFILES = {
    'editorial': ('body', 'ref'),
    'editorial+reco': ('body', 'ref', 'reco'),
    'all': None,
}
Z95 = 1.959964


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b''):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------- #
# Gold                                                                         #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class GoldRow:
    source_url: str
    target_url: str
    place_group: str
    place_code: str
    cites: int
    gold: int
    place_agreement: str
    cites_agreement: str
    stratum: str
    stratum_sample_n: int
    stratum_population_n: int
    anchor_tag: str
    external_target: int

    @property
    def key(self) -> Tuple[str, str]:
        return (self.source_url, self.target_url)

    @property
    def weight(self) -> float:
        """Sampling weight N_h / n_h."""
        if not self.stratum_sample_n:
            return 0.0
        return self.stratum_population_n / self.stratum_sample_n


def _as_int(value: str) -> int:
    try:
        return int(str(value).strip() or 0)
    except ValueError:
        return 0


def load_gold(path: str) -> Tuple[List[GoldRow], str]:
    """Read the gold CSV. Returns (rows sorted by key, sha256 of the file)."""
    with open(path, encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        header = tuple(reader.fieldnames or ())
        if header != GOLD_COLUMNS:
            raise ValueError(
                'Unexpected gold header.\n  got      : {}\n  expected : {}'
                .format(header, GOLD_COLUMNS))
        rows = [
            GoldRow(
                source_url=r['source_url'],
                target_url=r['target_url'],
                place_group=r['place_group'],
                place_code=r['place_code'],
                cites=_as_int(r['cites']),
                gold=_as_int(r['gold']),
                place_agreement=r['place_agreement'],
                cites_agreement=r['cites_agreement'],
                stratum=r['stratum'],
                stratum_sample_n=_as_int(r['stratum_sample_n']),
                stratum_population_n=_as_int(r['stratum_population_n']),
                anchor_tag=r['anchor_tag'],
                external_target=_as_int(r['external_target']),
            )
            for r in reader
        ]
    rows.sort(key=lambda r: r.key)
    return rows, sha256_file(path)


# --------------------------------------------------------------------------- #
# Corpus (read-only)                                                           #
# --------------------------------------------------------------------------- #

def open_corpus(path: str) -> sqlite3.Connection:
    """Open the bench corpus read-only. Writes raise OperationalError."""
    if not os.path.exists(path):
        raise SystemExit('Bench corpus not found: {}\n'
                         'Build it once: make bench-cache '
                         'MWI_BENCH_SOURCE_DB=/path/to/mwi.db'.format(path))
    uri = 'file:{}?mode=ro'.format(path.replace('?', '%3f').replace('#', '%23'))
    return sqlite3.connect(uri, uri=True)


def load_node_index(conn: sqlite3.Connection) -> tuple:
    """Build the 3-key URL index over the closed-network nodes."""
    pairs = conn.execute('SELECT id, url FROM node ORDER BY id').fetchall()
    return link_context.build_url_index(pairs, rules=BENCH_URL_RULES)


def read_page(conn: sqlite3.Connection, url: str) -> Optional[str]:
    row = conn.execute(
        'SELECT html, encoding FROM page WHERE url = ?', (url,)).fetchone()
    if row is None:
        return None
    blob, encoding = row
    raw = zlib.decompress(blob) if encoding == 'zlib' else blob
    return raw.decode('utf-8', errors='replace')


# --------------------------------------------------------------------------- #
# Extraction (replica of the crawl path, without any write)                    #
# --------------------------------------------------------------------------- #

@dataclass
class Counters:
    """Deterministic substitutes for wall-clock throughput.

    Wall clock is not reproducible across machines; these are. The HTML-parse
    budget becomes a testable assertion instead of a stopwatch.
    """
    pages: int = 0
    html_bytes: int = 0
    trafilatura_calls: int = 0
    soup_parses: int = 0
    links_seen: int = 0
    links_resolved: int = 0
    links_unresolved: int = 0
    pages_bs4_fallback: int = 0
    pages_no_html: int = 0
    links_filtered: int = 0

    def as_lines(self) -> List[str]:
        return ['  {:<20} {}'.format(name, getattr(self, name))
                for name in ('pages', 'html_bytes', 'trafilatura_calls',
                             'soup_parses', 'links_seen', 'links_resolved',
                             'links_unresolved', 'pages_bs4_fallback',
                             'pages_no_html', 'links_filtered')]


def _trafilatura(raw_html: str, output_format: str, counters: Counters,
                 favor_recall: bool = False):
    counters.trafilatura_calls += 1
    kwargs = {'include_links': True, 'include_comments': False,
              'include_images': True, 'output_format': output_format}
    if favor_recall:
        # Widens Trafilatura's notion of "body". Diagnostic only here; the
        # extraction tickets decide whether to ship it, and on which leg.
        kwargs['favor_recall'] = True
    return trafilatura.extract(raw_html, **kwargs)


def _bs4_fallback(raw_html: str, base_url: str, counters: Counters) -> List[str]:
    """Rare path (1 page in 1109): Trafilatura yielded nothing usable.

    Imports mwi.core lazily so the common path never pulls the ORM in.
    """
    from . import core  # noqa: PLC0415  (deliberate: keep the hot path clean)
    counters.pages_bs4_fallback += 1
    counters.soup_parses += 1
    soup = BeautifulSoup(raw_html, 'html.parser')
    core.clean_html(soup)
    text = core.get_readable(soup)
    if not text or len(text) <= 100:
        return []
    hrefs = [a.get('href') for a in soup.find_all('a')]
    urls = [urljoin(base_url, h) for h in hrefs if isinstance(h, str) and h]
    return [u for u in urls if core.is_crawlable(u)]


def extract_links(raw_html: str, base_url: str, *, variant: str,
                  counters: Counters, favor_recall: bool = False):
    """The extractor's outgoing-link set for one page.

    ``current`` is the production path: it calls the very same
    ``body_links.extract_body_links`` the crawl calls, so the bench cannot
    drift away from what it is supposed to measure. The other variants are
    diagnostics that isolate one leg at a time.
    """
    if variant == 'raw':
        counters.soup_parses += 1
        return [(url, '') for url in
                link_context.extract_all_links(raw_html, base_url)]

    if variant == 'current':
        favor_recall = getattr(settings, 'link_favor_recall', True)
        wants_md, wants_html = True, True
    else:
        wants_md = variant in ('md', 'md+html')
        wants_html = variant in ('html', 'md+html')

    markdown = _trafilatura(raw_html, 'markdown', counters) if wants_md else None
    readable_html = (_trafilatura(raw_html, 'html', counters,
                                  favor_recall=favor_recall)
                     if wants_html else None)

    if markdown is not None and len(markdown or '') <= 100 and not readable_html:
        links = body_links.from_urls(
            _bs4_fallback(raw_html, base_url, counters))
    else:
        body = markdown if markdown and len(markdown) > 100 else None
        if readable_html:
            counters.soup_parses += 1
        links = body_links.extract_body_links(body, readable_html, base_url)

    # The classification reads the RAW DOM: Trafilatura's HTML output carries
    # no class, no id and no sectioning element (sprint body-links T3).
    counters.soup_parses += 1
    dom_map = link_context.extract_link_dom_map(raw_html, base_url,
                                                rank=body_links.dom_rank)
    body_links.resolve(links, dom_map)
    return [(link.url, link.kind or body_links.KIND_DEFAULT)
            for link in links]


def predict(conn: sqlite3.Connection, idx: tuple, rows: Sequence[GoldRow], *,
            variant: str, counters: Counters, favor_recall: bool = False,
            profile: str = 'editorial'):
    """Return the gold keys the extractor would keep.

    A gold pair is kept when the source page yields a link resolving to the
    same corpus node as the gold target -- the same 3-key ladder production
    uses, so a URL-variant never counts as a miss.
    """
    by_source: Dict[str, List[GoldRow]] = {}
    for row in rows:
        by_source.setdefault(row.source_url, []).append(row)

    kept: Set[Tuple[str, str]] = set()
    kinds: Dict[Tuple[str, str], str] = {}
    for source_url in sorted(by_source):
        raw_html = read_page(conn, source_url)
        if not raw_html:
            counters.pages_no_html += 1
            continue
        counters.pages += 1
        counters.html_bytes += len(raw_html)
        source_id = link_context.resolve_url_in_index(idx, source_url,
                                                      rules=BENCH_URL_RULES)
        found = {}
        kinds_allowed = PROFILES.get(profile, PROFILES['editorial'])
        for url, kind in extract_links(raw_html, source_url, variant=variant,
                                       counters=counters,
                                       favor_recall=favor_recall):
            counters.links_seen += 1
            target_id = link_context.resolve_url_in_index(idx, url,
                                                          rules=BENCH_URL_RULES)
            if target_id is None:
                counters.links_unresolved += 1
                continue
            counters.links_resolved += 1
            if target_id == source_id:
                continue          # self-citation: production never emits it
            if kinds_allowed is not None and kind and kind not in kinds_allowed:
                counters.links_filtered += 1
                continue
            found.setdefault(target_id, kind)
        for row in by_source[source_url]:
            gold_target = link_context.resolve_url_in_index(
                idx, row.target_url, rules=BENCH_URL_RULES)
            if gold_target is not None and gold_target in found:
                kept.add(row.key)
                kinds[row.key] = found[gold_target]
    return kept, kinds


# --------------------------------------------------------------------------- #
# Estimator                                                                    #
# --------------------------------------------------------------------------- #

def ht_ratio(rows: Sequence[GoldRow], numerator, denominator) -> Tuple[float, float]:
    """Horvitz-Thompson ratio of totals, with a 95% half-interval.

    Linearized variance under stratified SRS without replacement:
        V(R) = 1/T_den^2 * sum_h N_h^2 (1 - f_h) / n_h * s2_h(e)
    with e_i = a_i - R * b_i.
    """
    num = sum(r.weight * numerator(r) for r in rows)
    den = sum(r.weight * denominator(r) for r in rows)
    if den == 0:
        return float('nan'), float('nan')
    ratio = num / den

    by_stratum: Dict[str, List[float]] = {}
    meta: Dict[str, Tuple[int, int]] = {}
    for row in rows:
        residual = numerator(row) - ratio * denominator(row)
        by_stratum.setdefault(row.stratum, []).append(residual)
        meta[row.stratum] = (row.stratum_population_n, row.stratum_sample_n)

    variance = 0.0
    for stratum, residuals in by_stratum.items():
        pop, sample = meta[stratum]
        if sample < 2 or pop <= 0:
            continue
        mean = sum(residuals) / len(residuals)
        s2 = sum((x - mean) ** 2 for x in residuals) / (len(residuals) - 1)
        fraction = sample / pop
        variance += (pop ** 2) * (1.0 - fraction) / sample * s2
    variance /= den ** 2
    return ratio, Z95 * math.sqrt(variance) if variance > 0 else 0.0


@dataclass
class BenchResult:
    rows: List[GoldRow] = field(default_factory=list)
    kept: Set[Tuple[str, str]] = field(default_factory=set)
    kinds: Dict[Tuple[str, str], str] = field(default_factory=dict)
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0
    precision: float = float('nan')
    precision_ci: float = float('nan')
    recall: float = float('nan')
    recall_ci: float = float('nan')
    precision_raw: float = float('nan')
    recall_raw: float = float('nan')
    kept_weighted: float = 0.0
    gold_weighted: float = 0.0
    tp_weighted: float = 0.0
    fn_weighted: float = 0.0

    def outcome(self, row: GoldRow) -> str:
        predicted = row.key in self.kept
        if predicted and row.gold:
            return 'TP'
        if predicted:
            return 'FP'
        return 'FN' if row.gold else 'TN'


def score(rows: Sequence[GoldRow], kept: Set[Tuple[str, str]],
          kinds: Optional[Dict[Tuple[str, str], str]] = None) -> BenchResult:
    """Confusion matrix and both estimators."""
    result = BenchResult(rows=list(rows), kept=set(kept), kinds=dict(kinds or {}))
    for row in rows:
        setattr(result, result.outcome(row).lower(),
                getattr(result, result.outcome(row).lower()) + 1)

    def pred(row):
        return 1 if row.key in kept else 0

    def gold(row):
        return 1 if row.gold else 0

    def both(row):
        return pred(row) * gold(row)

    result.precision, result.precision_ci = ht_ratio(rows, both, pred)
    result.recall, result.recall_ci = ht_ratio(rows, both, gold)
    result.precision_raw = (result.tp / (result.tp + result.fp)
                            if (result.tp + result.fp) else float('nan'))
    result.recall_raw = (result.tp / (result.tp + result.fn)
                         if (result.tp + result.fn) else 0.0)
    result.kept_weighted = sum(r.weight * pred(r) for r in rows)
    result.gold_weighted = sum(r.weight * gold(r) for r in rows)
    result.tp_weighted = sum(r.weight * both(r) for r in rows)
    result.fn_weighted = sum(r.weight * (gold(r) - both(r)) for r in rows)
    return result


# --------------------------------------------------------------------------- #
# Outputs                                                                      #
# --------------------------------------------------------------------------- #

EDGE_COLUMNS = ('source_url', 'target_url', 'stratum', 'place_group',
                'place_code', 'cites', 'gold', 'predicted', 'kind', 'outcome')


def _write_rows(path: str, rows) -> None:
    with open(path, 'w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle, quoting=csv.QUOTE_ALL, lineterminator='\n')
        writer.writerow(EDGE_COLUMNS)
        writer.writerows(rows)


def _edge_row(result: BenchResult, row: GoldRow) -> list:
    return [row.source_url, row.target_url, row.stratum, row.place_group,
            row.place_code, row.cites, row.gold,
            1 if row.key in result.kept else 0,
            result.kinds.get(row.key, ''), result.outcome(row)]


def write_edges(out_dir: str, result: BenchResult) -> None:
    ordered = sorted(result.rows, key=lambda r: r.key)
    _write_rows(os.path.join(out_dir, 'bench_edges.csv'),
                [_edge_row(result, r) for r in ordered])
    _write_rows(os.path.join(out_dir, 'bench_false_kept.csv'),
                [_edge_row(result, r) for r in ordered
                 if result.outcome(r) == 'FP'])
    _write_rows(os.path.join(out_dir, 'bench_missed.csv'),
                [_edge_row(result, r) for r in ordered
                 if result.outcome(r) == 'FN'])


def _fmt(value: float, digits: int = 4) -> str:
    if value != value:                      # NaN
        return 'n/a'
    return '{:.{}f}'.format(value, digits)


def write_summary(out_dir: str, result: BenchResult, *, gold_sha256: str,
                  gold_name: str, corpus_name: str, variant: str,
                  counters: Counters, favor_recall: bool = False,
                  profile: str = 'editorial') -> None:
    """Deterministic report: no clock, no host, no absolute path."""
    rows = result.rows
    strata = {}
    for row in rows:
        strata[row.stratum] = (row.stratum_sample_n, row.stratum_population_n)

    lines = []
    add = lines.append
    add('body-links benchmark')
    add('====================')
    add('gold            {}'.format(gold_name))
    add('gold_sha256     {}'.format(gold_sha256))
    add('corpus          {}'.format(corpus_name))
    add('schema_version  {}'.format(SCHEMA_VERSION))
    add('extractor       {}{}'.format(
        variant, ' +favor_recall' if favor_recall else ''))
    add('link_profile    {} = {}'.format(
        profile, PROFILES.get(profile) or 'all kinds'))
    add('url_rules       {}'.format(
        json.dumps(BENCH_URL_RULES, sort_keys=True)))
    add('')
    add('sampling design')
    for stratum in sorted(strata):
        sample, population = strata[stratum]
        weight = population / sample if sample else 0.0
        add('  {:<12} n={:<6} N={:<7} w={}'.format(
            stratum, sample, population, _fmt(weight, 6)))
    add('')
    add('confusion (sample counts)')
    add('  TP {}   FP {}   FN {}   TN {}'.format(
        result.tp, result.fp, result.fn, result.tn))
    add('')
    add('metrics')
    add('  precision (weighted)  {}  +/- {}'.format(
        _fmt(result.precision), _fmt(result.precision_ci)))
    add('  recall    (weighted)  {}  +/- {}'.format(
        _fmt(result.recall), _fmt(result.recall_ci)))
    add('  precision (raw)       {}   [unweighted; unbiased only while every '
        'prediction stays in one stratum]'.format(_fmt(result.precision_raw)))
    add('  recall    (raw)       {}   [unweighted; BIASED, for reference '
        'only]'.format(_fmt(result.recall_raw)))
    add('')
    add('population estimates')
    add('  citations captured    {}'.format(_fmt(result.tp_weighted, 0)))
    add('  citations missed      {}'.format(_fmt(result.fn_weighted, 0)))
    add('  edges kept (volume)   {}'.format(_fmt(result.kept_weighted, 0)))
    add('  editorial citations   {}'.format(_fmt(result.gold_weighted, 0)))
    add('')
    add('work counters (deterministic; wall clock lives in bench_perf.json)')
    lines.extend(counters.as_lines())
    add('')
    contested = sum(1 for r in rows if r.place_code == 'NOMAJ')
    add('contested       {} ({}% of the gold)'.format(
        contested, _fmt(100.0 * contested / len(rows) if rows else 0.0, 1)))
    add('')
    add('false kept by place_code')
    for code, count in sorted(Counter(
            r.place_code for r in rows
            if result.outcome(r) == 'FP').items(), key=lambda kv: (-kv[1], kv[0])):
        add('  {:<16} {}'.format(code or '(empty)', count))
    add('')
    add('kept by kind')
    for kind, count in sorted(Counter(
            result.kinds.get(r.key, '')
            for r in rows if r.key in result.kept).items(),
            key=lambda kv: (-kv[1], kv[0])):
        add('  {:<16} {}'.format(kind or '(none)', count))
    add('')
    add('missed by anchor_tag')
    for tag, count in sorted(Counter(
            r.anchor_tag for r in rows
            if result.outcome(r) == 'FN').items(), key=lambda kv: (-kv[1], kv[0])):
        add('  {:<16} {}'.format(tag or '(empty)', count))
    add('')

    with open(os.path.join(out_dir, 'bench_summary.txt'), 'w',
              encoding='utf-8', newline='') as handle:
        handle.write('\n'.join(lines))


def write_perf(out_dir: str, counters: Counters, wall_clock: float) -> None:
    """NOT deterministic, and deliberately kept out of the compared outputs."""
    payload = {
        'wall_clock_seconds': round(wall_clock, 3),
        'pages_per_second': (round(counters.pages / wall_clock, 3)
                             if wall_clock > 0 else None),
        'python': platform.python_version(),
        'trafilatura': getattr(trafilatura, '__version__', 'unknown'),
    }
    with open(os.path.join(out_dir, 'bench_perf.json'), 'w',
              encoding='utf-8') as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write('\n')


# --------------------------------------------------------------------------- #

def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='Body-links benchmark.')
    parser.add_argument('--corpus',
                        default=os.environ.get(
                            'MWI_BENCH_DB',
                            'benchmarks/body_links/cache/bench_corpus_v1.sqlite'))
    parser.add_argument('--gold',
                        default=os.environ.get(
                            'MWI_BENCH_GOLD',
                            'benchmarks/body_links/gold_v1.csv'))
    parser.add_argument('--out-dir', default='benchmarks/body_links/out')
    parser.add_argument('--extractor', choices=VARIANTS, default='current')
    parser.add_argument('--link-profile', choices=sorted(PROFILES),
                        default='editorial')
    parser.add_argument('--favor-recall', action='store_true',
                        help='Diagnostic: widen Trafilatura on the HTML leg.')
    args = parser.parse_args(argv)

    rows, gold_sha256 = load_gold(args.gold)
    os.makedirs(args.out_dir, exist_ok=True)

    started = time.time()
    counters = Counters()
    conn = open_corpus(args.corpus)
    try:
        idx = load_node_index(conn)
        kept, kinds = predict(conn, idx, rows, variant=args.extractor,
                              counters=counters,
                              favor_recall=args.favor_recall,
                              profile=args.link_profile)
    finally:
        conn.close()
    elapsed = time.time() - started

    result = score(rows, kept, kinds)
    write_edges(args.out_dir, result)
    write_summary(args.out_dir, result, gold_sha256=gold_sha256,
                  gold_name=os.path.basename(args.gold),
                  corpus_name=os.path.basename(args.corpus),
                  variant=args.extractor, counters=counters,
                  favor_recall=args.favor_recall, profile=args.link_profile)
    write_perf(args.out_dir, counters, elapsed)

    print('precision {}  recall {}  (TP {} FP {} FN {})'.format(
        _fmt(result.precision), _fmt(result.recall),
        result.tp, result.fp, result.fn))
    print('outputs in {}'.format(args.out_dir))
    return 0


if __name__ == '__main__':
    sys.exit(main())
