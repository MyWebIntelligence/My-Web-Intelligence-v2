"""Tests hors-ligne du moteur de recodage des liens (sprint recode-links).

Miroir de test_28/test_29. Aucun appel réseau : ``ask_openrouter_chat`` est
monkeypatché pour renvoyer du JSON canné. Couvre les 7 critères GATE du sprint
§8/§10 :

1. draw() déterministe (RNG dérivés du seed ; n_ret n'affecte pas les éliminés).
2. Pureté des strates.
3. Évidence raw-only : échelle 3 clés + garde-fou host_path (C1) ; html NULL →
   ctx_source='indet', review=1, ZÉRO appel API.
4. Roll-up code fin → 6 MACRO.
5. Agrégation : ≥3/4 consensus ; 2-2 → NOMAJ+review ; juge manquant exclu du
   dénominateur ; cit=INDET exclu de la base 0/1.
6. Parseur JSON : fences ```json, prose, schéma invalide — sans lever.
7. Schéma CSV v2 (46 col., 12/09/2026) : 9 colonnes du frame renommées en tête ;
   in_body_mwi / cites_from_place / panel_cites présentes et distinctes ; relecture v1.
"""
import pytest

from mwi import link_coding as lc
from mwi.link_context import LinkDomInfo, host_path_key
from mwi.url_normalizer import normalize_url

lc._RETRY_BASE_DELAY = 0  # pas de sleep dans les tests

PROJECT = {"name": "airegulation", "description": "AI regulation & governance",
           "keywords": "AI Act, governance"}
JUDGES = ["j/one", "j/two", "j/three"]     # panel de record = 3 juges (nettoyage 10/07)


def _frame(n_elim=50, n_ret=20):
    rows = []
    for i in range(n_elim):
        rows.append({"Source": str(1000 + i), "Target": str(2000 + i), "Weight": "",
                     "weightbody": "0", "weighthtml": "1", "citation": "0",
                     "source_url": "https://s%d.test/p" % i, "source_domain_id": "1",
                     "target_url": "https://t%d.test/q" % i, "target_domain_id": "2"})
    for i in range(n_ret):
        rows.append({"Source": str(5000 + i), "Target": str(6000 + i), "Weight": "",
                     "weightbody": "1", "weighthtml": "0", "citation": "1",
                     "source_url": "https://s%d.test/p" % i, "source_domain_id": "3",
                     "target_url": "https://t%d.test/q" % i, "target_domain_id": "4"})
    return rows


# --- 1. draw() déterministe --------------------------------------------------
def test_01_draw_deterministic_and_seed_independent():
    frame = _frame()
    a = lc.draw(frame, 42, 10, 5)
    b = lc.draw(frame, 42, 10, 5)
    key = lambda s: {(r["Source"], r["Target"]) for r in s}
    assert key(a) == key(b), "même seed → même tirage"

    # changer n_ret ne doit PAS perturber le tirage des éliminés (RNG indépendants)
    a_elim = {(r["Source"], r["Target"]) for r in a if r["stratum"] == "eliminated"}
    c = lc.draw(frame, 42, 10, 12)
    c_elim = {(r["Source"], r["Target"]) for r in c if r["stratum"] == "eliminated"}
    assert a_elim == c_elim, "n_ret ne doit pas changer les éliminés"

    # seed différent → tirage (au moins partiellement) différent
    d = lc.draw(frame, 7, 10, 5)
    assert key(a) != key(d)


# --- 2. pureté des strates ---------------------------------------------------
def test_02_strata_purity():
    sample = lc.draw(_frame(), 42, 10, 5)
    elim = [r for r in sample if r["stratum"] == "eliminated"]
    ret = [r for r in sample if r["stratum"] == "retained"]
    assert len(elim) == 10 and len(ret) == 5
    assert all(r["weightbody"] == "0" for r in elim)
    assert all(r["weightbody"] == "1" for r in ret)


def test_02b_draw_zero_means_all():
    # n <= 0 (pas de limite) → TOUTE la strate (demande utilisateur 08/07)
    frame = _frame(50, 20)
    s = lc.draw(frame, 42, 0, 0)
    assert sum(1 for r in s if r["stratum"] == "eliminated") == 50
    assert sum(1 for r in s if r["stratum"] == "retained") == 20
    # mixte : tout éliminé + 5 retenus tirés
    s2 = lc.draw(frame, 42, 0, 5)
    assert sum(1 for r in s2 if r["stratum"] == "eliminated") == 50
    assert sum(1 for r in s2 if r["stratum"] == "retained") == 5
    # n >= |strate| → tout aussi (pas d'IndexError)
    assert len(lc.draw(frame, 42, 999, 999)) == 70
    # déterminisme de l'échantillon article préservé (1000/300 reste stable)
    assert {(r["Source"], r["Target"]) for r in lc.draw(_frame(2000, 500), 42, 1000, 300)} \
        == {(r["Source"], r["Target"]) for r in lc.draw(_frame(2000, 500), 42, 1000, 300)}


def test_02c_draw_nested():
    # Tirages EMBOÎTÉS : n=1000/300 ⊂ n=1500/450 par strate → permet d'étendre un
    # run avec --resume (les premiers réutilisés, seuls les nouveaux codés).
    frame = _frame(2000, 800)
    small, big = lc.draw(frame, 42, 1000, 300), lc.draw(frame, 42, 1500, 450)
    ks = lambda s, st: {(r["Source"], r["Target"]) for r in s if r["stratum"] == st}
    assert ks(small, "eliminated") < ks(big, "eliminated")     # sous-ensemble STRICT
    assert ks(small, "retained") < ks(big, "retained")
    assert len(ks(small, "eliminated")) == 1000 and len(ks(big, "eliminated")) == 1500
    assert len(ks(small, "retained")) == 300 and len(ks(big, "retained")) == 450


# --- 3. évidence raw-only : 3 clés + host_path + html NULL → indet -----------
def test_03a_rawonly_dom_recovery_two_key():
    html = ('<html><body><article><p>See the '
            '<a href="http://www.example.org/report/">EU report</a> here today.'
            '</p></article></body></html>')
    dm, hp = lc.build_source_dommap(html, "https://src.test/page")
    info = lc.resolve_dominfo(dm, hp, "https://example.org/report")
    assert info is not None
    assert info.dom.endswith("p")
    assert "EU report" in (info.dom_html or "")
    assert "EU report" in (info.block_text or "")


def test_03b_rawonly_host_path_guard():
    # lookup_link_info (exact+relaxed) rate ; SEUL le palier host_path (C1) résout.
    info = LinkDomInfo(dom="html > body > p", dom_html="<p>x</p>", block_text="ctx")
    dommap = {}  # vide → lookup_link_info renvoie None
    hp_index = {host_path_key(normalize_url("https://example.org/report")): info}
    got = lc.resolve_dominfo(dommap, hp_index, "http://www.example.org/report/")
    assert got is info, "le 3e palier host_path doit résoudre l'arête"


def test_03c_html_null_indet_zero_api_call(monkeypatch):
    calls = []
    monkeypatch.setattr(lc.llm_openrouter, "ask_openrouter_chat",
                        lambda *a, **k: calls.append(1) or "{}")
    dm, hp = lc.build_source_dommap(None, "https://src.test/page")  # (None, None)
    assert dm is None
    edge = {"Source": "10", "Target": "20", "weightbody": "0",
            "source_url": "https://src.test/p", "target_url": "https://t.test/q",
            "source_domain_id": "1", "target_domain_id": "2", "stratum": "eliminated"}
    ev = lc.assemble_evidence(edge, dommap=dm, hp_index=hp)
    assert ev["ctx_source"] == "indet"
    loc, cit, agg = lc.code_one_edge(ev, JUDGES, PROJECT)
    assert calls == [], "aucun appel API sur un cas INDET"
    assert agg["review"] == 2 and agg["citation_consensus"] == "INDET"   # 2 axes sans majorité


def test_03d_rawonly_full_evidence_makes_6_calls(monkeypatch):
    calls = []

    def fake(prompt, model=None, timeout=None, max_tokens=None):
        calls.append(model)
        if "ACTE DE CITATION" in prompt:
            return '{"cit":1,"cit_type":"ACTOR","confidence":0.95,"review":false,"note":""}'
        return ('{"status":"M","code":"EDIT_EXT","ref_target":"actor",'
                '"confidence":0.95,"rule":"7a","review":false,"note":""}')
    monkeypatch.setattr(lc.llm_openrouter, "ask_openrouter_chat", fake)

    html = ('<html><body><article><p>As the '
            '<a href="https://example.org/report">EU report</a> argues at length here.'
            '</p></article></body></html>')
    dm, hp = lc.build_source_dommap(html, "https://src.test/page")
    edge = {"Source": "10", "Target": "20", "weightbody": "0",
            "source_url": "https://src.test/p", "target_url": "https://example.org/report",
            "source_domain_id": "1", "target_domain_id": "2", "stratum": "eliminated"}
    ev = lc.assemble_evidence(edge, dommap=dm, hp_index=hp, target_title="EU report")
    assert ev["ctx_source"] == "rawhtml"
    loc, cit, agg = lc.code_one_edge(ev, JUDGES, PROJECT)
    assert len(calls) == 6, "3 juges × 2 prompts"
    assert agg["macro"] == "EDITORIAL" and agg["citation_consensus"] == 1


# --- 4. roll-up code fin → MACRO-6 ------------------------------------------
def test_04_macro_rollup_total():
    assert len(lc.FINE_CODES) == 20
    for code in lc.FINE_CODES:
        assert lc.macro_of(code) in lc.MACRO_CODES
    # points de contrôle codebook §5.2
    checks = {"EDIT_EXT": "EDITORIAL", "REF_BIB": "EDITORIAL", "REF_DATA": "EDITORIAL",
              "NAV": "NAV", "TOC": "NAV", "DATA_LISTING": "NAV", "TAG": "NAV",
              "RECO": "RECO", "ADS": "ADS", "SOCIAL": "SOCIAL", "UGC": "SOCIAL",
              "META_REFTOOL": "OTHER", "X_MALF": "OTHER", "X_OTHER": "OTHER"}
    for code, macro in checks.items():
        assert lc.macro_of(code) == macro, code


def test_04b_cit_derived_regime1():
    # Régime 1 (codebook §5.7 / B.6 l.866) : M, REF_BIB(actor), REF_DATA → 1 ; A → 0
    assert lc.cit_derived_of("M", "") == 1
    assert lc.cit_derived_of(lc.status_of("REF_DATA"), "") == 1          # C → 1 (fix revue)
    assert lc.cit_derived_of(lc.status_of("REF_BIB", "actor"), "actor") == 1
    assert lc.cit_derived_of(lc.status_of("REF_BIB", "infra"), "infra") == 0  # infra → A → 0
    assert lc.cit_derived_of(lc.status_of("NAV"), "") == 0
    # via aggregate : consensus REF_DATA → cit_derived 1
    agg = lc.aggregate([_lv("REF_DATA", ref="")] * 4, [_cv(1)] * 4)
    assert agg["cit_derived"] == 1


# --- 5. agrégation majorité stricte 4 juges ---------------------------------
def _lv(code, ref="actor", review=False):
    return {"code": code, "status": lc.status_of(code, ref), "ref_target": ref,
            "macro": lc.macro_of(code), "confidence": "0.950", "review": review, "note": ""}


def _cv(cit, ctype="ACTOR", review=False):
    return {"cit": cit, "cit_type": ctype if cit == 1 else "NONE",
            "confidence": "0.950", "review": review, "note": ""}


def test_05a_unanimous_and_three_quarter():
    agg = lc.aggregate([_lv("EDIT_EXT")] * 4, [_cv(1)] * 4)
    assert agg["linkfunc_fine"] == "EDIT_EXT" and agg["loc_agree"] == "4/4"
    assert agg["macro"] == "EDITORIAL" and agg["loc_majority"] == 1
    assert agg["citation_consensus"] == 1 and agg["cit_type"] == "ACTOR"
    assert agg["cit_derived"] == 1 and agg["review"] == 0

    agg2 = lc.aggregate([_lv("EDIT_EXT"), _lv("EDIT_EXT"), _lv("EDIT_EXT"), _lv("NAV")],
                        [_cv(1), _cv(1), _cv(1), _cv(0)])
    assert agg2["linkfunc_fine"] == "EDIT_EXT" and agg2["loc_agree"] == "3/4"
    assert agg2["citation_consensus"] == 1 and agg2["cit_agree"] == "3/4"


def test_05b_two_two_split_nomaj():
    agg = lc.aggregate([_lv("EDIT_EXT"), _lv("EDIT_EXT"), _lv("NAV"), _lv("NAV")],
                       [_cv(1), _cv(1), _cv(0), _cv(0)])
    assert agg["linkfunc_fine"] == "NOMAJ" and agg["loc_majority"] == 0
    assert agg["citation_consensus"] == "NOMAJ" and agg["cit_majority"] == 0
    assert agg["review"] == 2               # les DEUX axes sans majorité → 2


def test_05c_missing_judge_excluded_from_denominator():
    # 3 présents (1 manquant) : majorité 2/3 suffit → review=0. Depuis le nettoyage
    # 10/07, un juge manquant ne flagge PLUS review ; seule l'absence de majorité compte.
    agg = lc.aggregate([_lv("EDIT_EXT"), _lv("EDIT_EXT"), _lv("NAV"), None],
                       [_cv(1), _cv(1), _cv(0), None])
    assert agg["linkfunc_fine"] == "EDIT_EXT" and agg["loc_agree"] == "2/3"
    assert agg["citation_consensus"] == 1 and agg["cit_agree"] == "2/3"
    assert agg["review"] == 0


def test_05d_indet_excluded_from_binary_base():
    # 3×cit=1 + 1×INDET : INDET exclu de la base 0/1, majorité 1 → review=0. Depuis le
    # nettoyage 10/07, un vote INDET ne flagge plus review (la citation a une majorité).
    agg = lc.aggregate([_lv("RECO")] * 4,
                       [_cv(1), _cv(1), _cv(1), _cv("INDET")])
    assert agg["citation_consensus"] == 1
    assert agg["cit_agree"] == "3/4"
    assert agg["review"] == 0


# --- 6. parseur JSON robuste -------------------------------------------------
def test_06_json_parser_robust():
    assert lc.parse_json_object('```json\n{"a":1}\n```') == {"a": 1}
    assert lc.parse_json_object('Sure! {"cit":1,"cit_type":"ACTOR"} voilà.') == \
        {"cit": 1, "cit_type": "ACTOR"}
    assert lc.parse_json_object("aucun json ici") is None
    assert lc.parse_json_object('{"a": ') is None      # accolade non fermée
    assert lc.parse_json_object("") is None
    assert lc.parse_json_object(None) is None


# --- 7. schéma CSV -----------------------------------------------------------
def test_07_schema_header():
    h = lc.csv_header()
    # schéma v2 (12/09/2026) : 9 colonnes du frame RENOMMÉES en tête, Weight retirée
    assert h[:9] == [lc.FRAME_OUT[c] for c in lc.FRAME_COLS if c in lc.FRAME_OUT]
    assert h[:3] == ["source_page_id", "target_page_id", "count_in_body"]
    for c in ("in_body_mwi", "cites_from_place", "panel_cites"):
        assert c in h
    # trois opérationnalisations distinctes de la citation (positions différentes)
    assert h.index("in_body_mwi") != h.index("cites_from_place") != h.index("panel_cites")
    assert len(h) == len(set(h)), "pas de doublon de colonne"
    # v2 : 46 colonnes, 3 juges ; ni ref_target/cit_type/slot j4 (10/07), ni Weight,
    # source_id, target_id (12/09), ni aucun nom du schéma v1
    assert len(h) == 46
    for c in ("ref_target", "cit_type", "loc_fine_j4", "ref_target_j1", "cit_type_j2",
              "conf_cit_j4", "Weight", "source_id", "target_id", "citation", "stratum",
              "linkfunc_fine", "macro", "citation_consensus", "cit_derived", "review",
              "ctx_source", "leaf_tag", "dom", "context_excerpt", "human_gold_cit"):
        assert c not in h, "colonne v1 %s ne doit pas figurer dans le schéma v2" % c
    assert [c for c in h if c.startswith("judge3_")] and not [c for c in h if c.startswith("judge4_")]
    # grammaire <qui>_<axe>_<quoi> : toute colonne de jugement porte son axe (place / cites)
    for c in h:
        if c.startswith(("judge", "panel_", "rule_", "human_")):
            assert ("place" in c) or ("cites" in c), c
    # une ligne construite porte bien toutes les colonnes
    edge = {c: "" for c in lc.FRAME_COLS}
    edge["Source"], edge["Target"], edge["weightbody"] = "1", "2", "0"
    ev = {"source_id": 1, "target_id": 2, "ctx_source": "indet", "is_external": True,
          "leaf_tag": "", "anchor_text": "", "target_typeactor": "", "dom": "",
          "context": "", "precode": {"status": "A", "code": "X_NUL"}, "stratum": "eliminated"}
    row = lc.build_row(dict(edge, stratum="eliminated"), ev, [], [], lc._indet_aggregate(4))
    assert set(row.keys()) == set(h)
    assert row["source_page_id"] == "1" and row["body_extraction_mwi"] == "eliminated"
    assert row["evidence_source"] == "indet" and row["contested_axes"] == 2
    # relecture d'une ligne v1 (49 col.) → clés v2, colonnes retirées éliminées
    v1 = {"Source": "1", "Target": "2", "Weight": "", "stratum": "eliminated",
          "loc_fine_j1": "NAV", "cit_j1": "0", "citation_consensus": "0", "review": "1",
          "ctx_source": "rawhtml", "source_id": "1", "target_id": "2", "citation": "0"}
    v2 = lc.to_v2(v1)
    assert v2["source_page_id"] == "1" and v2["judge1_place_code"] == "NAV"
    assert v2["panel_cites"] == "0" and v2["contested_axes"] == "1"
    assert v2["in_body_mwi"] == "0" and v2["body_extraction_mwi"] == "eliminated"
    assert "Weight" not in v2 and "source_id" not in v2 and "target_id" not in v2
    assert lc.to_v2(v2) is v2, "une ligne v2 est renvoyée telle quelle"


# --- 8. judge_location : validation du CODE seul (status juge = champ mort) ---
def test_08_judge_location_validates_code_only(monkeypatch):
    ev = {"source_url": "", "target_url": "", "dom": "", "dom_html": "", "context": "",
          "target_title": "", "is_external": True, "target_typeactor": "", "source_actor": ""}
    # status hors {M,C,A} (P-LOC purgé de M/C/A, C6) mais code valide → accepté
    monkeypatch.setattr(lc.llm_openrouter, "ask_openrouter_chat", lambda *a, **k:
        '{"status":"APPARATUS","code":"NAV","ref_target":null,"confidence":0.95,"review":false}')
    v = lc.judge_location(ev, "m", None, retries=1)
    assert v is not None and v["code"] == "NAV" and v["macro"] == "NAV"
    # code invalide → rejeté (juge manquant)
    monkeypatch.setattr(lc.llm_openrouter, "ask_openrouter_chat", lambda *a, **k:
        '{"status":"M","code":"NOTACODE","confidence":0.9}')
    assert lc.judge_location(ev, "m", None, retries=1) is None
    # JSON illisible → None sans lever
    monkeypatch.setattr(lc.llm_openrouter, "ask_openrouter_chat", lambda *a, **k: "oops")
    assert lc.judge_location(ev, "m", None, retries=1) is None


# --- 9. code_links de bout en bout (orchestration : Phase A/B, tri, manifeste, stats) ---
def test_09_code_links_end_to_end(monkeypatch, tmp_path):
    import csv as _csv
    import json as _json
    import os as _os
    # DB neutralisée → toutes les arêtes tombent en INDET (0 appel LLM) : on exerce
    # TOUTE la chaîne code_links (draw, évidence, Phase B, tri, manifeste, stats)
    # sans base ni réseau. Aurait attrapé le NameError 'stopped' du manifeste.
    monkeypatch.setattr(lc, "_preload", lambda sample: ({}, {}, {}))
    monkeypatch.setattr(lc, "_body_dom_row", lambda sid, tid: None)   # body dom NULL → INDET
    monkeypatch.setattr(lc, "_sha256", lambda p: "deadbeef")
    called = []
    monkeypatch.setattr(lc.llm_openrouter, "ask_openrouter_chat",
                        lambda *a, **k: called.append(1) or "{}")

    out = str(tmp_path / "coded.csv")
    n = lc.code_links("ignored.csv", out, judges=JUDGES, project_meta=PROJECT,
                      seed=42, n_elim=3, n_ret=2, frame_rows=_frame(3, 2))
    # tout INDET → aucun appel LLM ET aucune ligne écrite (INDET hors table livrée,
    # nettoyage 10/07) ; elles restent comptées dans misses_indet.
    assert n == 0 and called == []
    assert _os.path.exists(out) and _os.path.exists(out + ".manifest.json") \
        and _os.path.exists(out + ".stats.txt")
    m = _json.load(open(out + ".manifest.json", encoding="utf-8"))
    assert m["rows"] == 0 and m["misses_indet"] == 5 and m["budget_stopped"] is False
    rows = list(_csv.DictReader(open(out, encoding="utf-8")))
    assert len(rows) == 0, "les lignes INDET ne sont pas écrites dans la table livrée"
    # l'en-tête (schéma §6) est tout de même présent
    with open(out, encoding="utf-8") as _f:
        assert _f.readline().strip().split(",")[:9] == \
            [lc.FRAME_OUT[c] for c in lc.FRAME_COLS if c in lc.FRAME_OUT]


# --- 10. Ctrl-C : le CSV partiel N'EST PAS perdu (sauvegarde + drapeaux manifeste) ---
def test_10_keyboard_interrupt_saves_partial(monkeypatch, tmp_path):
    import csv as _csv
    import json as _json
    base = {"ctx_source": "rawhtml", "is_external": True, "leaf_tag": "p",
            "anchor_text": "x", "target_typeactor": "", "dom": "d", "context": "c",
            "precode": {"status": "A", "code": "NAV"}, "source_url": "", "target_url": "",
            "source_actor": "", "target_title": ""}
    monkeypatch.setattr(lc, "_preload", lambda s: ({}, {}, {}))
    monkeypatch.setattr(lc, "assemble_evidence",
                        lambda edge, **k: dict(base, stratum=edge.get("stratum", ""),
                                               source_id=int(edge["Source"]),
                                               target_id=int(edge["Target"])))
    monkeypatch.setattr(lc, "_sha256", lambda p: "x")
    cnt = {"i": 0}

    def fake(ev, judges, project_meta, budget=None, retries=3):
        cnt["i"] += 1
        if cnt["i"] >= 3:
            raise KeyboardInterrupt
        loc, cit = [_lv("NAV")] * 3, [_cv(0)] * 3      # vrais verdicts → lignes écrites
        return loc, cit, lc.aggregate(loc, cit, n_judges=3)
    monkeypatch.setattr(lc, "code_one_edge", fake)

    out = str(tmp_path / "c.csv")
    # as_completed() rend les futures dans l'ordre d'ACHÈVEMENT, pas de
    # soumission : sur un runner chargé, les cinq peuvent être terminées avant
    # l'entrée dans la boucle, et c'est alors la 4e — celle qui lève
    # KeyboardInterrupt — qui sort la première, avant qu'aucune ligne n'ait été
    # écrite. Le test devient rouge sans que rien ne soit cassé. On force la
    # consommation dans l'ordre de soumission : fut.result() bloque toujours,
    # donc rien n'est court-circuité.
    monkeypatch.setattr(lc, "as_completed", lambda fs: iter(list(fs)))
    # max_workers=1 → traitement séquentiel : interruption au 3e lien
    lc.code_links("ig.csv", out, judges=JUDGES, project_meta=PROJECT,
                  seed=42, n_elim=5, n_ret=0, max_workers=1, frame_rows=_frame(5, 0))
    import os as _os
    assert _os.path.exists(out), "le CSV partiel doit être conservé"
    rows = list(_csv.DictReader(open(out, encoding="utf-8")))
    assert 0 < len(rows) < 5, "les liens codés avant Ctrl-C sont sauvegardés"
    m = _json.load(open(out + ".manifest.json", encoding="utf-8"))
    assert m["interrupted"] is True and m["complete"] is False


# --- 12. les arêtes dont TOUS les juges reviennent vides ne sont PAS écrites -----
def test_12_empty_verdicts_not_written(monkeypatch, tmp_path):
    import csv as _csv
    import json as _json
    base = {"ctx_source": "rawhtml", "is_external": True, "leaf_tag": "p",
            "anchor_text": "x", "target_typeactor": "", "dom": "d", "context": "c",
            "precode": {"status": "A", "code": "NAV"}, "source_url": "", "target_url": "",
            "source_actor": "", "target_title": ""}
    monkeypatch.setattr(lc, "_preload", lambda s: ({}, {}, {}))
    monkeypatch.setattr(lc, "assemble_evidence",
                        lambda edge, **k: dict(base, stratum=edge.get("stratum", ""),
                                               source_id=int(edge["Source"]),
                                               target_id=int(edge["Target"])))
    monkeypatch.setattr(lc, "_sha256", lambda p: "x")
    # tous les juges échouent (verdicts vides) → aucune ligne ne doit être écrite
    monkeypatch.setattr(lc, "code_one_edge",
                        lambda ev, j, pm, budget=None, retries=3:
                        ([None] * 3, [None] * 3, lc.aggregate([], [], n_judges=3)))
    out = str(tmp_path / "c.csv")
    lc.code_links("ig.csv", out, judges=["a", "b", "c"], project_meta=PROJECT,
                  seed=42, n_elim=5, n_ret=0, max_workers=1, frame_rows=_frame(5, 0))
    rows = list(_csv.DictReader(open(out, encoding="utf-8")))
    assert len(rows) == 0, "aucune ligne 'tous juges vides' ne doit être écrite"
    m = _json.load(open(out + ".manifest.json", encoding="utf-8"))
    assert m["skipped_empty"] == 5 and m["rows"] == 0


# --- 11. --resume ne saute QUE les lignes réellement codées (pas les échecs 402) ---
def test_11_resume_skips_only_coded(tmp_path):
    import csv as _csv
    h = lc.csv_header()

    def row(s, t, ctx, cit1=""):
        r = {c: "" for c in h}
        r["source_page_id"], r["target_page_id"] = str(s), str(t)
        r["evidence_source"], r["judge1_cites"] = ctx, cit1
        return r
    out = str(tmp_path / "c.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = _csv.DictWriter(f, fieldnames=h, quoting=_csv.QUOTE_ALL)
        w.writeheader()
        w.writerow(row(1, 2, "rawhtml", "1"))    # codé (a un verdict)
        w.writerow(row(3, 4, "indet"))           # INDET → fait (routage humain)
        w.writerow(row(5, 6, "rawhtml", ""))     # ÉCHEC (aucun verdict) → à re-coder
    done, keep = lc._load_done(out)
    assert ("1", "2") in done and ("3", "4") in done
    assert ("5", "6") not in done                # la ligne ratée sera re-codée
    assert len(keep) == 2                        # la ratée n'est pas conservée
    assert lc._row_is_coded(row(9, 9, "rawhtml", "0")) is True
    assert lc._row_is_coded(row(9, 9, "rawhtml", "")) is False


# --- 13. --resume relit un CSV partiel écrit au schéma v1 (49 colonnes, 10/07/2026) ---
def test_13_resume_reads_legacy_v1_csv(tmp_path):
    import csv as _csv
    v1_header = ["Source", "Target", "Weight", "weightbody", "weighthtml", "citation",
                 "source_url", "source_domain_id", "target_url", "target_domain_id",
                 "stratum", "loc_fine_j1", "cit_j1", "ctx_source", "citation_consensus",
                 "review", "source_id", "target_id"]

    def row(s, t, ctx, cit1=""):
        r = {c: "" for c in v1_header}
        r["Source"], r["Target"], r["ctx_source"], r["cit_j1"] = str(s), str(t), ctx, cit1
        r["source_id"], r["target_id"], r["Weight"] = str(s), str(t), "x"
        return r
    out = str(tmp_path / "legacy.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = _csv.DictWriter(f, fieldnames=v1_header)
        w.writeheader()
        w.writerow(row(1, 2, "rawhtml", "1"))     # codé
        w.writerow(row(3, 4, "indet"))            # INDET → fait
        w.writerow(row(5, 6, "rawhtml", ""))      # échec → à re-coder
    done, keep = lc._load_done(out)
    assert done == {("1", "2"), ("3", "4")}
    assert len(keep) == 2
    for r in keep:                                # lignes normalisées en v2, prêtes à réécrire
        assert "source_page_id" in r and "Weight" not in r and "source_id" not in r
        assert set(r.keys()) <= set(lc.csv_header())
