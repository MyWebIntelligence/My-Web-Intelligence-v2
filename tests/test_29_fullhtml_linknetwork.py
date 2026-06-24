"""Tests for the raw-HTML link network export (sprint fullhtml-linknetwork).

Covers:
- mwi.link_context.extract_all_links (append-only, duplicates, filtering).
- The closed-network page/domain link CSVs added to nodelinkcsv under
  --fullhtml=TRUE: weight, in_mywi, the 3-way diff, minrel scoping.
- Backward compatibility: nodelinkcsv without --fullhtml emits exactly 4 files.

The two graphs are DIFFERENT extractions (raw <a href> vs Trafilatura markdown
readable stored in ExpressionLink), so neither is a superset of the other; the
fixture exercises both raw\\mywi (footer link MyWI dropped) and mywi\\raw (an
ExpressionLink edge absent from the raw HTML).
"""
import csv
import glob
import os

import pytest

from mwi import link_context
from mwi.export import Export


# --------------------------------------------------------------------------- #
# Unit tests: extract_all_links                                               #
# --------------------------------------------------------------------------- #

class TestExtractAllLinks:
    """Append-only raw <a href> extractor (duplicates preserved)."""

    def test_duplicates_preserved(self):
        html = ('<html><body>'
                '<a href="https://x.test/a">1</a>'
                '<a href="https://x.test/a">2</a>'
                '<a href="https://x.test/b">3</a>'
                '</body></html>')
        links = link_context.extract_all_links(html, 'https://x.test/')
        assert links.count('https://x.test/a') == 2
        assert links.count('https://x.test/b') == 1
        assert len(links) == 3

    def test_relative_resolved_against_base(self):
        html = '<html><body><a href="/sub/page">x</a></body></html>'
        links = link_context.extract_all_links(html, 'https://x.test/dir/')
        assert links == ['https://x.test/sub/page']

    def test_non_http_and_skip_prefixes_filtered(self):
        html = ('<html><body>'
                '<a href="mailto:a@b.test">m</a>'
                '<a href="#frag">f</a>'
                '<a href="javascript:void(0)">j</a>'
                '<a href="tel:+33">t</a>'
                '<a href="ftp://x.test/file">ftp</a>'
                '<a href="https://ok.test/p">ok</a>'
                '</body></html>')
        links = link_context.extract_all_links(html, 'https://x.test/')
        assert links == ['https://ok.test/p']

    def test_path_case_preserved(self):
        html = '<html><body><a href="https://x.test/CamelCase/Path">x</a></body></html>'
        links = link_context.extract_all_links(html, 'https://x.test/')
        assert links == ['https://x.test/CamelCase/Path']

    def test_broken_or_empty_html_never_raises(self):
        assert link_context.extract_all_links(None, 'https://x.test/') == []
        assert link_context.extract_all_links('', 'https://x.test/') == []
        # Malformed markup must not raise — returns whatever it could parse.
        out = link_context.extract_all_links('<a href=https://x.test/p>', 'https://x.test/')
        assert isinstance(out, list)

    def test_xml_document_does_not_emit_xml_warning(self):
        # Stored HTML is sometimes actually XML (sitemap/feed); parsing it
        # must not spew XMLParsedAsHTMLWarning (benign, but alarming on stdout).
        import warnings
        xml = ('<?xml version="1.0" encoding="UTF-8"?>'
               '<feed><entry><link href="https://x.test/a"/></entry></feed>')
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            link_context.extract_all_links(xml, 'https://x.test/')
        assert 'XMLParsedAsHTMLWarning' not in [w.category.__name__ for w in caught]


# --------------------------------------------------------------------------- #
# Fixture: a small land with stored HTML and a known MyWI graph                #
# --------------------------------------------------------------------------- #

@pytest.fixture()
def fullhtml_land(fresh_db):
    """Build a closed-network test land.

    Expressions (relevance, html outbound <a href>):
      E1 site-a/home   rel5  -> E2 x2 (content), E3 (footer), E4 (rel0), external
      E2 site-a/article rel5 -> E1
      E3 site-b/page    rel5 -> E1
      E4 site-b/lowrel  rel0 -> E1            (excluded: relevance < minrel)
      E5 site-a/nohtml  rel5  html=None        (no contribution)

    MyWI ExpressionLink graph (the markdown-readable extraction):
      E1->E2, E2->E1, E3->E1  (also present in raw HTML -> in_mywi=1)
      E3->E2                  (NOT in raw HTML -> contributes to mywi\\raw)
    Note E1->E3 (footer) is NOT in ExpressionLink -> in_mywi=0 in the raw graph.
    """
    model = fresh_db["model"]
    controller = fresh_db["controller"]
    core = fresh_db["core"]

    name = "fullhtml_net"
    controller.LandController.create(
        core.Namespace(name=name, desc="raw link net", lang=["fr"])
    )
    land = model.Land.get(model.Land.name == name)

    d_a = model.Domain.create(name="site-a.test")
    d_b = model.Domain.create(name="site-b.test")

    def mk(url, domain, rel, html):
        return model.Expression.create(land=land, domain=domain, url=url,
                                        relevance=rel, depth=0,
                                        http_status="200", html=html)

    e1_html = (
        '<html><body><article>'
        '<p>Intro <a href="https://site-a.test/article">art</a> and again '
        '<a href="https://site-a.test/article">art bis</a>.</p>'
        '<p>Low <a href="https://site-b.test/lowrel">low</a> and '
        '<a href="https://external.test/page">ext</a>.</p>'
        '</article>'
        '<footer><a href="https://site-b.test/page">site b</a></footer>'
        '</body></html>'
    )
    e2_html = '<html><body><p><a href="https://site-a.test/home">home</a></p></body></html>'
    e3_html = '<html><body><p><a href="https://site-a.test/home">home</a></p></body></html>'
    e4_html = '<html><body><p><a href="https://site-a.test/home">home</a></p></body></html>'

    e1 = mk("https://site-a.test/home", d_a, 5, e1_html)
    e2 = mk("https://site-a.test/article", d_a, 5, e2_html)
    e3 = mk("https://site-b.test/page", d_b, 5, e3_html)
    e4 = mk("https://site-b.test/lowrel", d_b, 0, e4_html)
    e5 = mk("https://site-a.test/nohtml", d_a, 5, None)

    for s, t in [(e1, e2), (e2, e1), (e3, e1), (e3, e2)]:
        model.ExpressionLink.create(source=s, target=t)

    return {
        "land": land, "name": name, "model": model,
        "controller": controller, "core": core,
        "data_dir": str(fresh_db["data_dir"]),
        "e": {"e1": e1, "e2": e2, "e3": e3, "e4": e4, "e5": e5},
        "d": {"d_a": d_a.id, "d_b": d_b.id},
    }


def _edge_map(csv_path):
    """Read a *_pageslinksfullhtml.csv into {(source_id,target_id): row}."""
    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return {(int(r["source_id"]), int(r["target_id"])): r for r in rows}


# --------------------------------------------------------------------------- #
# Closed-network semantics (direct writer calls)                              #
# --------------------------------------------------------------------------- #

class TestClosedNetworkPageLinks:

    def _write(self, fullhtml_land, tmp_path, minrel=1):
        exp = Export('nodelinkcsv', fullhtml_land["land"], minrel, fullhtml=True)
        out = str(tmp_path / "pl.csv")
        exp._write_pageslinksfullhtml(out)
        return exp, _edge_map(out)

    def test_external_target_excluded(self, fullhtml_land, tmp_path):
        """A raw href to a domain outside the corpus never appears (closed)."""
        _, edges = self._write(fullhtml_land, tmp_path)
        urls = {r["target_url"] for r in edges.values()}
        assert not any("external.test" in u for u in urls)

    def test_footer_edge_present_with_in_mywi_zero(self, fullhtml_land, tmp_path):
        """E1->E3 (footer) is in the raw graph but absent from ExpressionLink."""
        e = fullhtml_land["e"]
        _, edges = self._write(fullhtml_land, tmp_path)
        row = edges[(e["e1"].id, e["e3"].id)]
        assert row["in_mywi"] == "0"

    def test_content_edge_in_mywi_one(self, fullhtml_land, tmp_path):
        e = fullhtml_land["e"]
        _, edges = self._write(fullhtml_land, tmp_path)
        assert edges[(e["e1"].id, e["e2"].id)]["in_mywi"] == "1"
        assert edges[(e["e2"].id, e["e1"].id)]["in_mywi"] == "1"

    def test_weight_counts_anchor_multiplicity(self, fullhtml_land, tmp_path):
        """Two <a> from E1 to E2 -> a single row with weight=2."""
        e = fullhtml_land["e"]
        _, edges = self._write(fullhtml_land, tmp_path)
        assert edges[(e["e1"].id, e["e2"].id)]["weight"] == "2"

    def test_minrel_excludes_low_relevance_endpoints(self, fullhtml_land, tmp_path):
        """E4 (relevance 0) is neither a source nor a target with minrel=1."""
        e = fullhtml_land["e"]
        _, edges = self._write(fullhtml_land, tmp_path, minrel=1)
        ids_seen = {s for s, _ in edges} | {t for _, t in edges}
        assert e["e4"].id not in ids_seen

    def test_robust_matching_trailing_slash_and_case(self, fullhtml_land, tmp_path):
        """A href differing by trailing slash / host case still maps in-corpus."""
        e = fullhtml_land["e"]
        # E2 already links to E1; rewrite its html to a slashed/upper-host variant.
        e["e2"].html = ('<html><body><a href="https://SITE-A.test/home/">h</a>'
                        '</body></html>')
        e["e2"].save()
        _, edges = self._write(fullhtml_land, tmp_path)
        assert (e["e2"].id, e["e1"].id) in edges

    def test_three_way_diff_counters(self, fullhtml_land, tmp_path):
        exp, edges = self._write(fullhtml_land, tmp_path)
        stats = exp._fullhtml_stats
        # 4 qualifying sources (E1,E2,E3,E5); E5 has no html.
        assert stats["pages_total"] == 4
        assert stats["pages_with_html"] == 3
        # raw edges: E1->E2, E1->E3, E2->E1, E3->E1
        assert stats["raw_edges"] == 4
        assert stats["matched"] == 3            # all but the footer edge
        assert stats["raw_only"] == 1           # footer E1->E3
        assert stats["mywi_only"] == 1          # E3->E2 absent from raw HTML
        assert len(edges) == 4


class TestClosedNetworkDomainLinks:

    def test_domain_links_inter_domain_with_in_mywi(self, fullhtml_land, tmp_path):
        d = fullhtml_land["d"]
        exp = Export('nodelinkcsv', fullhtml_land["land"], 1, fullhtml=True)
        exp._write_pageslinksfullhtml(str(tmp_path / "pl.csv"))
        out = str(tmp_path / "dl.csv")
        exp._write_domainlinksfullhtml(out)
        with open(out, encoding="utf-8") as f:
            rows = {(int(r["source_domain_id"]), int(r["target_domain_id"])): r
                    for r in csv.DictReader(f)}
        # Inter-domain only: (a->b) from footer E1->E3, (b->a) from E3->E1.
        assert set(rows.keys()) == {(d["d_a"], d["d_b"]), (d["d_b"], d["d_a"])}
        # MyWI only ever links site-b -> site-a (E3->E1, E3->E2): (b->a) is
        # in_mywi=1, but (a->b) — the raw footer edge — is in_mywi=0. This shows
        # page/domain in_mywi are computed independently at their own granularity.
        assert rows[(d["d_b"], d["d_a"])]["in_mywi"] == "1"
        assert rows[(d["d_a"], d["d_b"])]["in_mywi"] == "0"
        # No intra-domain self pair.
        assert (d["d_a"], d["d_a"]) not in rows


# --------------------------------------------------------------------------- #
# Integration via the CLI controller                                          #
# --------------------------------------------------------------------------- #

class TestNodelinkcsvIntegration:

    def _glob(self, data_dir, suffix):
        return glob.glob(os.path.join(data_dir, f"export_land_*nodelinkcsv*{suffix}"))

    def test_without_flag_emits_only_four_files(self, fullhtml_land):
        ctrl, core = fullhtml_land["controller"], fullhtml_land["core"]
        data_dir = fullhtml_land["data_dir"]
        ret = ctrl.LandController.export(
            core.Namespace(name=fullhtml_land["name"], type="nodelinkcsv", minrel=1)
        )
        assert ret == 1
        assert self._glob(data_dir, "_pageslinks.csv")
        assert not self._glob(data_dir, "fullhtml.csv")

    def test_with_flag_emits_only_fullhtml_files(self, fullhtml_land):
        """--fullhtml switches networks: emit ONLY the 4 fullhtml files."""
        ctrl, core = fullhtml_land["controller"], fullhtml_land["core"]
        data_dir = fullhtml_land["data_dir"]
        ret = ctrl.LandController.export(
            core.Namespace(name=fullhtml_land["name"], type="nodelinkcsv",
                           minrel=1, fullhtml="TRUE")
        )
        assert ret == 1
        for suffix in ("_pagesnodesfullhtml.csv", "_pageslinksfullhtml.csv",
                       "_domainnodesfullhtml.csv", "_domainlinksfullhtml.csv"):
            assert self._glob(data_dir, suffix), f"missing {suffix}"
        # The base MyWI files must NOT be emitted under the flag.
        assert not self._glob(data_dir, "_pageslinks.csv")
        assert not self._glob(data_dir, "_domainlinks.csv")

    def test_pagesnodesfullhtml_matches_base_pagesnodes(self, fullhtml_land):
        """Closed network -> node set identical to the base pagesnodes file.

        The flag now switches networks, so the base file comes from a
        separate export without --fullhtml.
        """
        ctrl, core = fullhtml_land["controller"], fullhtml_land["core"]
        data_dir = fullhtml_land["data_dir"]
        ctrl.LandController.export(
            core.Namespace(name=fullhtml_land["name"], type="nodelinkcsv", minrel=1)
        )
        ctrl.LandController.export(
            core.Namespace(name=fullhtml_land["name"], type="nodelinkcsv",
                           minrel=1, fullhtml="TRUE")
        )

        def ids(path):
            with open(path, encoding="utf-8") as f:
                return sorted(int(r["id"]) for r in csv.DictReader(f))

        base = self._glob(data_dir, "_pagesnodes.csv")[-1]
        full = self._glob(data_dir, "_pagesnodesfullhtml.csv")[-1]
        assert ids(base) == ids(full)


class TestLandWithoutStoredHtml:

    def test_empty_raw_network_header_only_no_crash(self, fresh_db, tmp_path):
        """All qualifying pages have html=None -> header-only file, no crash."""
        model = fresh_db["model"]
        controller = fresh_db["controller"]
        core = fresh_db["core"]
        controller.LandController.create(
            core.Namespace(name="no_html_land", desc="x", lang=["fr"])
        )
        land = model.Land.get(model.Land.name == "no_html_land")
        dom = model.Domain.create(name="z.test")
        model.Expression.create(land=land, domain=dom, url="https://z.test/a",
                                relevance=5, depth=0, http_status="200", html=None)

        exp = Export('nodelinkcsv', land, 1, fullhtml=True)
        out = str(tmp_path / "pl.csv")
        n = exp._write_pageslinksfullhtml(out)
        assert n == 0
        assert exp._fullhtml_stats["pages_with_html"] == 0
        with open(out, encoding="utf-8") as f:
            rows = list(csv.reader(f))
        assert rows == [['source_id', 'source_url', 'source_domain_id',
                         'target_id', 'target_url', 'target_domain_id',
                         'weight', 'in_mywi']]
