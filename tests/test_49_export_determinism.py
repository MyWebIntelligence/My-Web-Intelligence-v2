"""O05 - every export has a TOTAL ordering, by contract and not by luck.

Twelve queries feeding an export file had no total `ORDER BY`, and
`_write_pageslinksfullhtml` iterated a Python `set`. Today the files happen to
come out byte-identical under two insertion orders and two `PYTHONHASHSEED`
values — the hash of an `(int, int)` tuple is not salted, and SQLite serves
those rows through the primary-key index. Both of those are accidents of the
current plan, not guarantees: biasing `sqlite_stat1` into a `SCAN
expressionlink` is enough to make the same land produce two different files.

For a tool that claims reproducibility, "deterministic in practice" is not the
same claim as "deterministic by contract", and a reviewer cannot tell them
apart from the outside. These tests pin the contract.

Deliberately NOT asserted (decision D-10): byte identity of `corpus` /
`htmldump` (zip entries carry a wall-clock timestamp) and of GEXF
(`lastmodifieddate`). Determinism here is about the ORDER OF ROWS, not about
the fingerprint of the file. Nor is there a subprocess test over two
PYTHONHASHSEED values: `order == sorted(order)` subsumes it and costs nothing.
"""

import csv
import glob
import os
import xml.etree.ElementTree as ET
from datetime import datetime

import pytest


@pytest.fixture()
def ordered_land(fresh_db):
    """12 expressions over 2 domains, 24 edges, one anchor-only raw link."""
    m = fresh_db["model"]
    controller = fresh_db["controller"]
    core = fresh_db["core"]

    controller.LandController.create(
        core.Namespace(name="det", desc="d", lang=["fr"]))
    land = m.Land.get(m.Land.name == "det")
    d1 = m.Domain.create(name="alpha.example")
    d2 = m.Domain.create(name="beta.example")

    exprs = []
    for i in range(12):
        domain = d1 if i % 2 == 0 else d2
        host = "alpha.example" if i % 2 == 0 else "beta.example"
        exprs.append(m.Expression.create(
            land=land, domain=domain,
            url="https://%s/p%02d" % (host, i),
            title="Page %02d" % i,
            description="d%02d" % i,
            readable="Contenu de la page %02d. " % i * 8,
            relevance=5, depth=i % 3, http_status="200",
            fetched_at=datetime.now(), readable_at=datetime.now(),
            html="<html><body><p>p%02d</p>"
                 "<a href='https://alpha.example/p00'>retour</a>"
                 "</body></html>" % i))

    # 24 edges, created in an order that is NOT the sorted one.
    made = 0
    for step in (5, 7):
        for i in range(12):
            src, dst = exprs[i], exprs[(i + step) % 12]
            if src.id == dst.id:
                continue
            _, created = m.ExpressionLink.get_or_create(source=src, target=dst)
            made += created
    assert made >= 20

    for i in range(0, 12, 3):
        m.Media.create(expression=exprs[i],
                       url="https://alpha.example/i%02d.jpg" % i, type="img")

    return {**fresh_db, "land": land, "name": "det", "expressions": exprs}


def _export(env, export_type, **extra):
    controller, core = env["controller"], env["core"]
    assert controller.LandController.export(core.Namespace(
        name=env["name"], type=export_type, minrel=0, **extra)) == 1


def _latest(env, pattern):
    matches = sorted(glob.glob(os.path.join(str(env["data_dir"]), pattern)))
    assert matches, "no export matching %s" % pattern
    return matches[-1]


def _rows(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


class TestRowOrderIsTotal:
    """Each file is sorted by a key that cannot tie."""

    @pytest.mark.parametrize('export_type,pattern,column', [
        pytest.param('pagecsv', "export_land_*_pagecsv_*", 'id', id="pagecsv"),
        pytest.param('fullpagecsv', "export_land_*_fullpagecsv_*", 'id',
                     id="fullpagecsv"),
        pytest.param('nodecsv', "export_land_*_nodecsv_*", 'id', id="nodecsv"),
        pytest.param('mediacsv', "export_land_*_mediacsv_*", 'id',
                     id="mediacsv"),
    ])
    def test_rows_come_out_in_ascending_id(self, ordered_land, export_type,
                                           pattern, column):
        _export(ordered_land, export_type)

        ids = [int(r[column]) for r in _rows(_latest(ordered_land, pattern))]

        assert ids == sorted(ids)
        assert len(ids) == len(set(ids))

    def test_pageslinks_is_sorted_by_source_then_target(self, ordered_land):
        _export(ordered_land, 'nodelinkcsv')

        rows = _rows(_latest(ordered_land, "*_pageslinks.csv"))
        keys = [(int(r['source_id']), int(r['target_id'])) for r in rows]

        assert keys == sorted(keys)

    def test_domainlinks_ties_are_broken_by_domain_pair(self, ordered_land):
        """ORDER BY link_count DESC alone leaves every tie to the query plan."""
        _export(ordered_land, 'nodelinkcsv')

        rows = _rows(_latest(ordered_land, "*_domainlinks.csv"))
        keys = [(-int(r['link_count']), int(r['source_domain_id']),
                 int(r['target_domain_id'])) for r in rows]

        assert keys == sorted(keys)

    def test_pseudolinks_ties_are_broken(self, ordered_land, monkeypatch):
        """Two methods on one pair: the score alone cannot order them."""
        import settings
        from mwi import embedding_pipeline

        monkeypatch.setattr(settings, "embed_provider", "fake")
        monkeypatch.setattr(embedding_pipeline, "settings", settings)
        embedding_pipeline.generate_embeddings_for_paragraphs(
            ordered_land["land"])
        embedding_pipeline.compute_paragraph_similarities(
            ordered_land["land"], threshold=0.0, method='cosine')

        _export(ordered_land, 'pseudolinks')
        rows = _rows(_latest(ordered_land, "export_land_*_pseudolinks_*"))
        assert rows, "no pseudolink exported"
        keys = [(-float(r['RelationScore']), int(r['Source_ParagraphID']),
                 int(r['Target_ParagraphID']), r['Method']) for r in rows]

        assert keys == sorted(keys)


class TestGexfOrder:

    def _elements(self, path, tag):
        return [e for e in ET.parse(path).iter() if e.tag.endswith(tag)]

    def test_pagegexf_nodes_and_edges_are_sorted(self, ordered_land):
        _export(ordered_land, 'pagegexf')
        path = _latest(ordered_land, "export_land_*_pagegexf_*.gexf")

        node_ids = [int(n.get('id')) for n in self._elements(path, 'node')]
        edges = [(int(e.get('source')), int(e.get('target')))
                 for e in self._elements(path, 'edge')]

        assert node_ids == sorted(node_ids)
        assert edges == sorted(edges)

    def test_nodegexf_nodes_and_edges_are_sorted(self, ordered_land):
        _export(ordered_land, 'nodegexf')
        path = _latest(ordered_land, "export_land_*_nodegexf_*.gexf")

        edges = [(int(e.get('source')), int(e.get('target')))
                 for e in self._elements(path, 'edge')]

        assert edges == sorted(edges)


class TestFullhtmlNetworkOrder:
    """The raw-HTML comparator used to iterate a Python set."""

    def test_each_pass_is_sorted_by_source_target(self, ordered_land):
        """The file is TWO ordered passes, not one global sort.

        Citation edges (weightbody=1) are written first, from the preloaded
        set; raw-only edges (weightbody=0) follow, streamed page by page. Two
        ordered passes are reproducible, which is the contract — asking for a
        globally sorted file would mean buffering the whole raw network in
        memory for a cosmetic gain.
        """
        _export(ordered_land, 'nodelinkcsv', fullhtml='TRUE')

        rows = _rows(_latest(ordered_land, "*_pageslinksfullhtml.csv"))
        body = [(int(r['Source']), int(r['Target'])) for r in rows
                if r['weightbody'] == '1']
        raw = [(int(r['Source']), int(r['Target'])) for r in rows
               if r['weightbody'] == '0']

        assert body, "no citation edge exported"
        assert body == sorted(body)
        assert [s for s, _ in raw] == sorted(s for s, _ in raw)
        # The two passes are disjoint by construction.
        assert not (set(body) & set(raw))

    def test_domain_level_ties_are_broken_by_domain_pair(self, ordered_land):
        _export(ordered_land, 'nodelinkcsv', fullhtml='TRUE')

        rows = _rows(_latest(ordered_land, "*_domainlinksfullhtml.csv"))
        keys = [(-(int(r['in_mwi']) + int(r['out_mwi'])), int(r['Source']),
                 int(r['Target'])) for r in rows]

        assert keys == sorted(keys)


class TestBytesAreStableAcrossInsertionOrder:
    """Same rows, different insertion order, identical file.

    This is the assertion the accident hides: it passes today, and it would
    still pass if the ORDER BY were removed — unless the query plan changes.
    The plan is forced below so the test measures the contract, not the
    current statistics.
    """

    def _force_scan(self, model):
        model.DB.execute_sql("ANALYZE")
        model.DB.execute_sql(
            "UPDATE sqlite_stat1 SET stat='1000000 1000000 1000000' "
            "WHERE tbl='expressionlink' AND idx IS NOT NULL")
        model.DB.execute_sql("ANALYZE sqlite_schema")

    def test_pageslinks_is_stable_under_a_scan_plan(self, ordered_land):
        m = ordered_land["model"]
        self._force_scan(m)
        plan = m.DB.execute_sql(
            "EXPLAIN QUERY PLAN SELECT * FROM expressionlink AS link "
            "ORDER BY link.source_id, link.target_id").fetchall()
        if not any('SCAN' in str(row) for row in plan):
            pytest.skip("could not force a SCAN plan on this SQLite build")

        _export(ordered_land, 'nodelinkcsv')
        rows = _rows(_latest(ordered_land, "*_pageslinks.csv"))
        keys = [(int(r['source_id']), int(r['target_id'])) for r in rows]

        assert keys == sorted(keys)
