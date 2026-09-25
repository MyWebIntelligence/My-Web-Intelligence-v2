"""Twin re-attachment at export (`--resolve-twins`).

The crawl places a link on a fiche by EXACT normalized URL and the normalizer
preserves the trailing slash, so a body link written `https://site-b.test/page/`
while the corpus page is `https://site-b.test/page` lands on a second fiche,
never crawled (relevance NULL). Without the flag the closed network drops that
edge and the raw-HTML pass re-emits it raw-only. With the flag it is a body
edge of the corpus page, in both networks.

Contracts pinned here:

* a twin edge is re-attached to the page the 3-key ladder names;
* one (source, target) survives per pair: best kind first, direct before twin
  on a tie, and the surviving row supplies context;
* a resolution onto the source itself is dropped, an unplaceable target stays
  out, an ambiguous key never produces a wrong match;
* the profile filters the SURVIVING kind; the fullhtml file is never filtered;
* without the flag, nothing changes.
"""
import csv
import glob
import os

import pytest

from mwi.export import Export


@pytest.fixture()
def twin_land(fresh_db):
    """Corpus page T and its uncrawled trailing-slash twin W.

      S1 -> W   body   (twin only)                -> re-attached S1->T body
      S2 -> T   toc    (direct) + S2 -> W body   -> S2->T body, twin row wins
      S3 -> T   body   (direct) + S3 -> W nav    -> S3->T body, direct row wins
      S4 -> W   nav    (twin only)                -> S4->T nav, out of `citation`
      T  -> W2  body   (www twin of T itself)     -> self-loop, dropped
      S1 -> X   body   (external, not in corpus)  -> stays out
      S1 -> Y   body   (case variant, ambiguous)  -> stays out
    """
    model = fresh_db["model"]
    controller = fresh_db["controller"]
    core = fresh_db["core"]
    controller.LandController.create(
        core.Namespace(name="twins", desc="d", lang=["fr"]))
    land = model.Land.get(model.Land.name == "twins")
    d_a = model.Domain.create(name="site-a.test")
    d_b = model.Domain.create(name="site-b.test")
    d_x = model.Domain.create(name="external.test")

    def mk(url, domain, rel, depth=0, html=None, readable=None):
        return model.Expression.create(land=land, domain=domain, url=url,
                                       relevance=rel, depth=depth,
                                       http_status="200" if rel is not None else None,
                                       html=html, readable=readable)

    s1 = mk("https://site-a.test/s1", d_a, 5,
            html='<p><a href="https://site-b.test/page/">page</a></p>',
            readable="Voir [page](https://site-b.test/page/).")
    s2 = mk("https://site-a.test/s2", d_a, 5)
    s3 = mk("https://site-a.test/s3", d_a, 5)
    s4 = mk("https://site-a.test/s4", d_a, 5)
    t = mk("https://site-b.test/page", d_b, 5)
    # two corpus pages whose relaxed key collides -> ambiguous, unusable
    mk("https://site-b.test/Case", d_b, 5)
    mk("https://site-b.test/case", d_b, 5)
    w = mk("https://site-b.test/page/", d_b, None, depth=1)
    w2 = mk("https://www.site-b.test/page", d_b, None, depth=1)
    x = mk("https://external.test/x", d_x, None, depth=1)
    y = mk("https://site-b.test/CASE/", d_b, None, depth=1)

    def link(src, dst, kind, context=None):
        model.ExpressionLink.create(source=src, target=dst, kind=kind,
                                    context=context)

    link(s1, w, "body", "ctx S1 twin")
    link(s2, t, "toc", "ctx S2 direct")
    link(s2, w, "body", "ctx S2 twin")
    link(s3, t, "body", "ctx S3 direct")
    link(s3, w, "nav", "ctx S3 twin")
    link(s4, w, "nav", "ctx S4 twin")
    link(t, w2, "body")
    link(s1, x, "body")
    link(s1, y, "body")
    return {"land": land, "model": model, "controller": controller,
            "core": core, "data_dir": str(fresh_db["data_dir"]),
            "e": {"s1": s1, "s2": s2, "s3": s3, "s4": s4, "t": t, "w": w},
            "d": {"a": d_a.id, "b": d_b.id}}


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _pageslinks(land, tmp_path, resolve_twins, profile=None):
    kwargs = {"resolve_twins": resolve_twins}
    if profile:
        kwargs["link_profile"] = profile
    exp = Export("nodelinkcsv", land, 1, **kwargs)
    out = str(tmp_path / "pl.csv")
    exp._write_pageslinks(out)
    return exp, {(int(r["source_id"]), int(r["target_id"])): r for r in _read(out)}


class TestPagesLinks:

    def test_without_flag_twin_edges_are_lost(self, twin_land, tmp_path):
        e = twin_land["e"]
        _, edges = _pageslinks(twin_land["land"], tmp_path, False)
        # only the direct body edge survives the historical writer
        assert set(edges) == {(e["s3"].id, e["t"].id)}

    def test_twin_edge_is_reattached_to_the_corpus_page(self, twin_land, tmp_path):
        e = twin_land["e"]
        _, edges = _pageslinks(twin_land["land"], tmp_path, True)
        row = edges[(e["s1"].id, e["t"].id)]
        assert row["target_url"] == "https://site-b.test/page"
        assert row["target_domain_id"] == str(twin_land["d"]["b"])
        assert row["context"] == "ctx S1 twin"
        assert row["kind"] == "body"

    def test_better_kind_of_twin_wins_over_direct(self, twin_land, tmp_path):
        e = twin_land["e"]
        _, edges = _pageslinks(twin_land["land"], tmp_path, True)
        row = edges[(e["s2"].id, e["t"].id)]
        assert row["kind"] == "body"
        assert row["context"] == "ctx S2 twin"

    def test_direct_row_wins_when_its_kind_is_better(self, twin_land, tmp_path):
        e = twin_land["e"]
        _, edges = _pageslinks(twin_land["land"], tmp_path, True)
        row = edges[(e["s3"].id, e["t"].id)]
        assert row["kind"] == "body"
        assert row["context"] == "ctx S3 direct"

    def test_profile_filters_the_surviving_kind(self, twin_land, tmp_path):
        e = twin_land["e"]
        _, edges = _pageslinks(twin_land["land"], tmp_path, True)
        assert (e["s4"].id, e["t"].id) not in edges
        _, edges_all = _pageslinks(twin_land["land"], tmp_path, True, profile="all")
        assert edges_all[(e["s4"].id, e["t"].id)]["kind"] == "nav"

    def test_self_loop_unplaced_and_ambiguous_stay_out(self, twin_land, tmp_path):
        e = twin_land["e"]
        exp, edges = _pageslinks(twin_land["land"], tmp_path, True, profile="all")
        assert all(s != t for s, t in edges)
        assert set(edges) == {(e[k].id, e["t"].id) for k in ("s1", "s2", "s3", "s4")}
        assert exp._twin_stats["added_edges"] == 2      # S1->T, S4->T
        assert exp._twin_stats["upgraded_edges"] == 1   # S2->T

    def test_rows_are_totally_ordered(self, twin_land, tmp_path):
        _, edges = _pageslinks(twin_land["land"], tmp_path, True, profile="all")
        keys = list(edges)
        assert keys == sorted(keys)


class TestDomainLinks:

    def _domainlinks(self, land, tmp_path, resolve_twins):
        exp = Export("nodelinkcsv", land, 1, resolve_twins=resolve_twins)
        out = str(tmp_path / "dl.csv")
        exp._write_domainlinks(out)
        return {(int(r["source_domain_id"]), int(r["target_domain_id"])): r
                for r in _read(out)}

    def test_counts_follow_the_page_edges(self, twin_land, tmp_path):
        d = twin_land["d"]
        before = self._domainlinks(twin_land["land"], tmp_path, False)
        after = self._domainlinks(twin_land["land"], tmp_path, True)
        assert before[(d["a"], d["b"])]["link_count"] == "1"
        # S1->T, S2->T, S3->T under `citation`; S4->T is nav
        assert after[(d["a"], d["b"])]["link_count"] == "3"
        assert after[(d["a"], d["b"])]["target_domain_name"] == "site-b.test"


class TestFullHtml:

    def _fullhtml(self, land, tmp_path, resolve_twins):
        exp = Export("nodelinkcsv", land, 1, fullhtml=True,
                     resolve_twins=resolve_twins)
        out = str(tmp_path / "plf.csv")
        exp._write_pageslinksfullhtml(out)
        return {(int(r["Source"]), int(r["Target"])): r for r in _read(out)}

    def test_without_flag_twin_link_is_raw_only(self, twin_land, tmp_path):
        e = twin_land["e"]
        row = self._fullhtml(twin_land["land"], tmp_path, False)[(e["s1"].id, e["t"].id)]
        assert (row["weightbody"], row["kind"], row["citation"]) == ("0", "", "1")

    def test_with_flag_twin_link_is_body(self, twin_land, tmp_path):
        e = twin_land["e"]
        edges = self._fullhtml(twin_land["land"], tmp_path, True)
        row = edges[(e["s1"].id, e["t"].id)]
        assert (row["weightbody"], row["weighthtml"], row["kind"], row["citation"]) \
            == ("1", "0", "body", "1")
        # never profile-filtered: the nav twin edge is there
        assert edges[(e["s4"].id, e["t"].id)]["kind"] == "nav"


class TestCli:

    def test_flag_reaches_the_export(self, twin_land):
        ctrl, core = twin_land["controller"], twin_land["core"]
        ret = ctrl.LandController.export(core.Namespace(
            name="twins", type="nodelinkcsv", minrel=1, resolve_twins="TRUE"))
        assert ret == 1
        path = sorted(glob.glob(os.path.join(twin_land["data_dir"],
                                             "*_pageslinks.csv")))[-1]
        e = twin_land["e"]
        pairs = {(int(r["source_id"]), int(r["target_id"])) for r in _read(path)}
        assert (e["s1"].id, e["t"].id) in pairs
