"""LINKFUNC deterministic pre-coder — leaf engine (sprint recode-links, 2026-07-07).

Portage **verbatim** du moteur pur de ``02_data/linkfunc_sample/02_precode.py``
(codebook §3/§5) dans un module ``mwi`` *importable* et *leaf* :

- Le script ``02_precode.py`` exécute tout son I/O (lecture DB, écriture CSV) au
  niveau module, sans garde ``__main__`` — et son nom commence par un chiffre :
  il n'est donc pas importable. Ce module extrait le moteur (regex + parsers +
  ``precode`` + ``detect_conflict``) pour qu'il soit réutilisable par
  ``02_precode.py`` (refactoré) **et** par ``mwi/link_coding.py`` (4e ancre
  déterministe de LOCATION, sprint §4.2/§5.6).
- Contrainte leaf : ce module n'importe **que** la librairie standard (comme le
  faisait ``02_precode.py``). Il n'importe PAS ``mwi.core``, ni ``settings``, ni
  ``model`` — il ne fait aucune I/O. ``precode`` reste pur sur son dict ``f``.

Les fonctions ``parse_leaf``/``parse_block``/``parse_anchor``/``precode``/
``detect_conflict`` sont copiées à l'identique de ``02_precode.py`` (mêmes
regex, même ordre de règles : premier match gagne). ``build_f`` assemble le dict
``f`` attendu par ``precode`` à partir des champs de localisation d'une arête
(``dom``/``dom_html``/``context`` + urls + domaines), qu'ils viennent de
``ExpressionLink`` (arêtes body) ou d'une ré-extraction DOM (arêtes raw-only).
"""
import html as _html
import re
from urllib.parse import urlparse, unquote


# ---------- regex families (codebook §3) — VERBATIM 02_precode.py ----------
def rx(p):
    return re.compile(p, re.I)


RX_BODY = rx(r"(entry-content|post[-_]?content|article[-_](body|content)|blog(post)?[-_]?content|"
             r"story-content|rich[-_]?text|w-richtext|prose|sqs-html-content|wysiwyg|markup|"
             r"markdown-body|\brte\b|rte--|tdb[-_]?block|td_block|c-article(-body|-section)?|"
             r"body__inner|standard-body|available-content|has-drop-cap|field--name-body|"
             r"post-body|article-body|blog-body|the-content|content__body|paragraph)")
RX_NAV = rx(r"((^|[-_ ])menu([-_]item)?|sub-?menu|nav(bar|igation)?([-_]item)?|mega[-_]?menu|"
            r"breadcrumb|main-nav|mobile-nav|masternavigation|hs-menu|ecl-menu|top-?bar|"
            r"portal_link|stickylist|menu-container|site-nav|widget_nav)")
RX_RECO = rx(r"(related|read-?next|further-reading|o-tease|\btease\b|crosslink|top_content|"
             r"latest-posts|wp-block-latest-posts|component-card|resource-card|blog-?post-card|"
             r"card__|swiper|gallery|photogallery|carousel|w-dyn-item|show-more-less|"
             r"featuredimg|link-overlay|recirc|more-from|you-may|popular|trending)")
RX_TAGCLS = rx(r"(tag-?cloud|results_list|blogfilters|co_topics|li\.topic|glossar|keywords)")
RX_TAGHREF = rx(r"/(tags?|categor(y|ies)|topic|lexicon|glossary)/|dosearch")
RX_REFLIST_CLS = rx(r"(ref-list|references|bibul|rlist|ltx_bibitem|ltx_bibblock|"
                    r"c-article-references|footnotes?|footnote_tooltip|mixed-citation|"
                    r"suggested-citation)")
RX_REFLIST_ID = rx(r"^(CR|B|R|ref|bib|cite_note|fn|footnote|FN|CIT|risa|hast|qxag|pgae)\d")
RX_REFTOOL = rx(r"^(DOI|PubMed|PMC( free article)?|Google Scholar|Crossref|CAS|PDF|Full Text|"
                r"View Article|Abstract|CrossRef|ISI|\[PMC\]|\[PubMed\])$")
RX_SOCIAL_HREF = rx(r"(linkedin\.com/(signup|redir|company|showcase|in|posts|feed)|"
                    r"trk=public_post(?!_comment)|session_redirect|cold-join|little-mention|"
                    r"feed/hashtag|/sharer|/share\?|/intent/|addtoany|facebook\.com/sharer|"
                    r"twitter\.com/intent|t\.me/share|wa\.me/|/login\?|/signup)")
RX_SOCIAL_CLS = rx(r"(attributed-text-segment|feed-cta|user-hover-card|share-|social-|"
                   r"sharedaddy|share-button)")
RX_UGC = rx(r"(comment__|trk=public_post_comment-text|/comments?/|disqus|respond-|"
            r"comment-body|comment-author|livefyre)")
RX_CTA = rx(r"(\bcta\b|\bbtn\b|button|call-to-action|downloadall|subscribe|sign-?up|"
            r"newsletter-signup|get-started|book-a-demo)")
RX_CTA_CTX = rx(r"(read more|check out|see our|want to read|stay ahead|become a client|"
                r"subscribe|sign ?up|harness the power|sharpen your skills|learn more|"
                r"contact us|request a demo|download (our|the|now))")
RX_TOC_CLS = rx(r"(recitals?-grid|recital|\btoc\b|table-of-contents|accordion-content|"
                r"child-(article|chapter)|dynamic-sidebar-menu|pagination|page-numbers|pager)")
RX_TOC_ANCHOR = rx(r"^(Article|Annex|Recital|Section|Chapter|Art\.?|Title|Part)\s*\d+")
RX_META_CLS = rx(r"(disclaimer|cat-mark|lab-name|colophon|legal|terms|privacy)")
RX_BYLINE_HREF = rx(r"/(author|team|people|profile|staff|contributor|about-us/)/|/in/")
RX_INFRA_HOST = rx(r"(^|\.)(doi\.org|perma\.cc|archive\.ics\.uci\.edu|support\.google\.com|"
                   r"scholar\.google\.com|datadryad\.org|zenodo\.org|dx\.doi\.org|"
                   r"hdl\.handle\.net)$")
RX_OFFICIAL = rx(r"(\.gov($|\.)|\.gouv\.|europa\.eu|eur-lex|edpb\.|congress\.gov|"
                 r"legislature|senate\.|assembly\.|parliament|whitehouse\.gov|"
                 r"federalregister|govinfo\.gov|oecd\.org|un\.org|who\.int)")

A_RE = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.I | re.S)
HREF_RE = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)
ATTR_RE = re.compile(r"""([\w:-]+)\s*=\s*["']([^"']*)["']""", re.I)
TAG_RE = re.compile(r"<[^>]+>")
FIRST_TAG = re.compile(r"\s*<([a-zA-Z0-9]+)([^>]*)>")


# ---------- pure string/url helpers — VERBATIM 02_precode.py ----------
def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def host(u):
    try:
        h = urlparse(u if "://" in (u or "") else "http://" + (u or "")).netloc.lower()
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return ""


def norm_url(u):
    if not u:
        return ""
    u = u.strip().lower()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    return u.split("#")[0].rstrip("/")


# ---------- DOM parsers (PURS) — VERBATIM 02_precode.py ----------
def parse_leaf(dom):
    """Return (tag, id, classes_lower, last2_lower)."""
    if not dom:
        return "", "", "", ""
    segs = [s.strip() for s in dom.split(">") if s.strip()]
    last = segs[-1] if segs else ""
    tag = re.split(r"[.#]", last)[0].strip().lower()
    mid = re.search(r"#([^.\s]+)", last)
    cls = ".".join(re.findall(r"\.([^.#\s]+)", last))
    last2 = " ".join(segs[-2:]).lower()
    return tag, (mid.group(1) if mid else ""), cls.lower(), last2


def parse_block(dom_html):
    """Return (block_tag, block_class_lower)."""
    if not dom_html:
        return "", ""
    m = FIRST_TAG.match(dom_html)
    if not m:
        return "", ""
    tag = m.group(1).lower()
    cm = re.search(r"""class\s*=\s*["']([^"']*)["']""", m.group(2), re.I)
    return tag, (cm.group(1).lower() if cm else "")


def _unresolved_anchor(n):
    """Aucune ancre du bloc n'appartient sûrement à cette arête."""
    return {"text": "", "rel": "", "cls": "", "aria": "", "href": "",
            "n": n, "resolved": False}


def _anchor_href(attrs):
    """href canonique d'une ancre, comparable à une cible stockée en base."""
    m = HREF_RE.search(attrs)
    return norm_url(unquote(_html.unescape(m.group(1)))) if m else ""


def parse_anchor(dom_html, target_url):
    anchors = A_RE.findall(dom_html or "")
    if not anchors:
        return _unresolved_anchor(0)
    # Les deux côtés de la comparaison sont traités pareil. `unquote` n'était
    # appliqué qu'au href candidat, jamais à la cible : une URL à échappements
    # %XX ne pouvait donc matcher ni exactement ni par inclusion. `unescape`
    # pour la même raison : `dom_html` vient de `str(block)`, où BeautifulSoup
    # réécrit `&` en `&amp;`, alors que `target_url` porte un vrai `&` — toute
    # cible à deux paramètres échouait.
    tgt = norm_url(unquote(_html.unescape(target_url or "")))
    best = None
    for attrs, inner in anchors:
        if tgt and _anchor_href(attrs) == tgt:
            best = (attrs, inner)
            break
    if best is None:
        # Le href le PLUS LONG qui contient la cible ou qu'elle contient, et
        # non le premier rencontré. Un href court — commutateur de langue
        # `/en-us`, racine de rubrique `/actualites`, fil d'Ariane — est un
        # sous-texte de presque toute URL profonde du même site, et gagnait
        # donc sur l'ancre éditoriale placée plus loin dans le même bloc.
        # `max` est stable : à longueur égale l'ordre du document départage,
        # le résultat reste déterministe.
        cands = []
        for attrs, inner in anchors:
            hh = _anchor_href(attrs)
            if tgt and hh and (tgt in hh or hh in tgt):
                cands.append((len(hh), attrs, inner))
        if cands:
            best = max(cands, key=lambda c: c[0])[1:]
    if best is None:
        # On n'emprunte plus l'ancre d'un voisin. Attribuer son texte, sa
        # classe et son href à cette arête ne donnait pas un défaut neutre
        # mais un code FAUX et CONFIANT : un `/team/jane/` emprunté sortait
        # META_BYLINE, règle « 3 byline/profile », confiance « high », pour un
        # lien qui n'est pas une signature. Cas atteint en routine — le
        # `dom_html` est tronqué à `link_dom_html_max_chars`, donc l'ancre
        # d'un lien tardif n'y est tout simplement pas. Un bloc à une seule
        # ancre, lui, reste sans ambiguïté.
        if len(anchors) != 1:
            return _unresolved_anchor(len(anchors))
        best = anchors[0]
    attrs, inner = best
    text = re.sub(r"\s+", " ", TAG_RE.sub(" ", inner)).replace("&amp;", "&").strip()
    ad = {k.lower(): v for k, v in ATTR_RE.findall(attrs)}
    # One search kept in a name: the ternary ran HREF_RE.search twice, which did
    # the work twice and which mypy cannot narrow across two separate calls.
    href_m = HREF_RE.search(attrs)
    return {"text": text, "rel": ad.get("rel", "").lower(),
            "cls": ad.get("class", "").lower(),
            "aria": ad.get("aria-label", "").lower(),
            "href": href_m.group(1) if href_m else "", "n": len(anchors),
            "resolved": True}


# ---------- context predicates — VERBATIM 02_precode.py ----------
def ctx_links(context):
    return re.findall(r"\]\((https?://[^)\s]+)\)", context or "")


def ctx_is_pipelist(context):
    """Genuine list of SHORT labels (pipes or >=3 short bullets) — NOT prose with links."""
    c = context or ""
    if c.count(" | ") >= 2:
        return True
    bullets = re.findall(r"(?m)^\s*[-*]\s+(.*)$", c)
    if len(bullets) >= 3:
        short = sum(1 for b in bullets
                    if len(re.findall(r"[^\W\d_]{2,}",
                                      re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", b))) <= 8)
        if short >= max(2, len(bullets) // 2):
            return True
    return False


def ctx_is_label(context, anchor):
    c = (context or "").strip()
    if not c:
        return True
    if re.fullmatch(r"\[[^\]]*\]\([^)]*\)[\*\s.,;:]*", c):
        return True
    plain = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", c).strip()
    if anchor and norm(plain) == norm(anchor):
        return True
    return False


def _link_match(context, anchor, target):
    tgt = norm_url(target)
    for m in re.finditer(r"\[([^\]]*)\]\(([^)\s]+)", context or ""):
        txt, url = m.group(1), m.group(2)
        if (anchor and norm(txt) == norm(anchor)) or (tgt and norm_url(url) == tgt) \
                or (anchor and len(anchor) > 4 and norm(anchor) in norm(txt)):
            return m
    return None


def ctx_is_sentence(context, anchor, target):
    """Anchor embedded in running prose: words BEFORE and AFTER it on its line."""
    c = context or ""
    if len(c.strip()) < 80:
        return False
    m = _link_match(c, anchor, target)
    if m is None:
        # anchor not locatable in markdown: fall back to a prose-density test
        if c.count("](") >= 2 or ctx_is_pipelist(c):
            return False
        plain = re.sub(r"\s+", " ", re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", c)).strip()
        return len(plain) >= 150 and len(re.findall(r"[^\W\d_]{2,}", plain)) >= 25
    s, e = m.start(), c.find(")", m.end())
    e = e + 1 if e != -1 else m.end()
    ls = c.rfind("\n", 0, s) + 1
    le = c.find("\n", e)
    le = le if le != -1 else len(c)
    before = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", c[ls:s])
    after = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", c[e:le])
    wb = re.findall(r"[^\W\d_]{2,}", before)
    wa = re.findall(r"[^\W\d_]{2,}", after)
    # bullet/list line: link at start with little following prose -> not a sentence
    if re.match(r"^[-*]?\s*$", c[ls:s]) and len(wa) < 4:
        return False
    return (len(wb) + len(wa)) >= 5 and (len(wb) >= 2 or len(wa) >= 2)


def anchor_is_number(a):
    return bool(re.fullmatch(r"\s*\d{1,4}\s*", a or ""))


def anchor_is_url(a):
    a = (a or "").strip()
    return bool(re.match(r"https?://", a) or re.match(r"(www\.|doi\.org|10\.\d{4})", a))


def anchor_is_phrase(a):
    a = (a or "").strip()
    if len(a) < 3 or len(a) > 250:
        return False
    if a.startswith("#") or anchor_is_number(a) or anchor_is_url(a):
        return False
    if RX_REFTOOL.match(a):
        return False
    return bool(re.search(r"[^\W\d_]{2,}", a))


# ---------- precoder (codebook §5) — VERBATIM 02_precode.py ----------
def out(code, status, conf, rule, ev="", ref=""):
    return {"code": code, "status": status, "confidence": conf,
            "triggered_rule": rule, "evidence": ev, "ref_target": ref}


def flag_weak():
    return "flag=weak"


def precode(f):
    leafcls = f["leaf_cls"] + " " + f["leaf_last2"]
    blockcls = f["block_cls"]
    anycls = leafcls + " " + blockcls
    a = f["anchor"]
    href = a["href"]
    ctx = f["context"]

    # 0. pre-clean / degenerate
    if f["malformed"]:
        return out("X_MALF", "A", "high", "0a malformed")
    if not a["text"] and not (ctx or "").strip() and not f["dom_html"]:
        return out("X_NUL", "A", "high", "0b no signal")

    # 1. hard lexicons (DOM-independent)
    if (RX_REFTOOL.match(a["text"].strip()) or "gsc_a_" in a["cls"]
            or f["src"] == "scholar.google.com"):
        return out("META_REFTOOL", "A", "high", "1a reftool/scholar", a["text"][:40])
    # UGC (comment) is more specific than the generic social match -> test first
    if RX_UGC.search(anycls) or "comment-text" in href.lower() or RX_UGC.search(href):
        return out("UGC", "A", "high", "1c ugc class/trk", "")
    if (RX_SOCIAL_HREF.search(href) or a["text"].strip().startswith("#")
            or RX_SOCIAL_CLS.search(a["cls"])):
        return out("SOCIAL", "A", "high", "1b social href/#", href[:50])
    if RX_TAGHREF.search(href) or RX_TAGCLS.search(leafcls):
        return out("TAG", "A", "high", "1d tag href/class", href[:50])
    if (a["rel"] and ("license" in a["rel"])
            or "creativecommons.org" in href.lower()
            or RX_META_CLS.search(anycls)):
        return out("META_BOILER", "A", "high", "1e meta/license/disclaimer", "")

    # 2. formal reference
    reflist = (f["leaf_tag"] == "cite" or RX_REFLIST_ID.match(f["leaf_id"]) or
               RX_REFLIST_CLS.search(anycls))
    if reflist and (anchor_is_url(a["text"]) or "doi.org" in href.lower() or
                    RX_REFLIST_ID.match(f["leaf_id"]) or f["leaf_tag"] == "cite"):
        ref = "infra" if RX_INFRA_HOST.search(host(f["target_url"])) else "actor"
        return out("REF_BIB", "C", "high", "2 ref-list", host(f["target_url"]), ref)

    # 3. people / byline
    dh = f["dom_html"] or ""
    if re.search(r"(^|>)\s*by\b[\s:]*<a", dh, re.I) or RX_BYLINE_HREF.search(href) or \
            re.search(r"\d+\s*min read", ctx or "", re.I):
        return out("META_BYLINE", "A", "high", "3 byline/profile", href[:50])

    # 4. promo / product (can be a sentence)
    if RX_CTA.search(anycls) or RX_CTA.search(a["cls"]) or \
            (RX_CTA_CTX.search(ctx or "") and not f["is_external"]):
        return out("ADS", "A", "med", "4 cta/self-promo", "")

    # 5. table
    if f["leaf_tag"] == "td" or " td" in f["leaf_last2"]:
        if RX_OFFICIAL.search(host(f["target_url"])) and a["n"] <= 4:
            return out("REF_DATA", "C", "med", "5a table->primary", host(f["target_url"]))
        return out("DATA_LISTING", "A", "med", "5b catalog listing", "")

    # 6. intra-document legal cross-ref
    if (not f["is_external"]) and RX_TOC_ANCHOR.match(a["text"].strip()):
        return out("TOC", "A", "high", "6 legal intra-doc", a["text"][:40])

    # 7. editorial gate (positive)
    sent = ctx_is_sentence(ctx, a["text"], f["target_url"])
    phrase = anchor_is_phrase(a["text"])
    if sent and phrase and f["leaf_tag"] in ("p", "span", "em", "li"):
        conf = "high" if RX_BODY.search(blockcls or leafcls) else "med"
        if f["is_external"]:
            return out("EDIT_EXT", "M", conf, "7a editorial external")
        return out("EDIT_INT", "M", "med", "7b editorial internal")
    # 7c curated editorial list
    links = ctx_links(ctx)
    ext_doms = {host(u) for u in links if host(u) and host(u) != f["src"]}
    if RX_BODY.search(blockcls) and len(links) >= 2 and len(ext_doms) >= 2:
        return out("EDIT_LIST", "M", "med", "7c curated list", "%d ext domains" % len(ext_doms))

    # 8. soft apparatus
    if RX_NAV.search(leafcls) or RX_NAV.search(blockcls):
        return out("NAV", "A", "med", "8a nav class")
    if RX_RECO.search(leafcls) or RX_RECO.search(blockcls) or not a["text"] or \
            "go to article" in a["aria"] or len(a["text"]) > 120:
        return out("RECO", "A", "med", "8b reco/card/empty-img")
    lbl = ctx_is_label(ctx, a["text"])
    if lbl and not f["is_external"]:
        if (anchor_is_number(a["text"]) or RX_TOC_CLS.search(anycls)
                or RX_TOC_ANCHOR.match(a["text"].strip())):
            return out("TOC", "A", "med", "8c label->toc")
        return out("NAV", "A", "med", "8c label->nav")
    if ctx_is_pipelist(ctx):
        return out("NAV", "A", "med", "8d pipelist")
    if anchor_is_number(a["text"]) or RX_TOC_CLS.search(anycls):
        return out("TOC", "A", "high", "8e number/toc")

    # 9. external title pointer
    if f["leaf_tag"] in ("h2", "h3") and f["is_external"] and len(a["text"]) > 25 and \
            not RX_RECO.search(anycls):
        return out("EDIT_HEADING", "M", "low", "9 heading pointer", flag_weak(), )

    return out("X_OTHER", "A", "low", "10 residual")


def detect_conflict(f, res):
    """≥2 rules of opposite status would match."""
    a = f["anchor"]
    anycls = f["leaf_cls"] + " " + f["leaf_last2"] + " " + f["block_cls"]
    hard_app = bool(RX_SOCIAL_HREF.search(a["href"]) or RX_UGC.search(anycls) or
                    RX_REFTOOL.match(a["text"].strip()) or RX_TAGHREF.search(a["href"]))
    strong_edit = bool(ctx_is_sentence(f["context"], a["text"], f["target_url"]) and
                       anchor_is_phrase(a["text"]) and
                       RX_BODY.search(f["block_cls"]) and f["is_external"])
    if res["status"] == "M" and hard_app:
        return True
    if res["status"] in ("A", "C") and strong_edit:
        return True
    return False


# ---------- roll-ups (codebook §5.2 / §5.7) — pour link_coding ----------
# MACRO-6 déterministe (codebook.md:296, verbatim) :
#   EDITORIAL <- EDIT_* U REF_* ; NAV <- NAV, TOC, DATA_LISTING, TAG ;
#   RECO <- RECO ; ADS <- ADS ; SOCIAL <- SOCIAL, UGC ; OTHER <- META_*, X_*.
FINE_TO_MACRO = {
    "EDIT_EXT": "EDITORIAL", "EDIT_INT": "EDITORIAL", "EDIT_LIST": "EDITORIAL",
    "EDIT_HEADING": "EDITORIAL", "REF_BIB": "EDITORIAL", "REF_DATA": "EDITORIAL",
    "NAV": "NAV", "TOC": "NAV", "DATA_LISTING": "NAV", "TAG": "NAV",
    "RECO": "RECO", "ADS": "ADS", "SOCIAL": "SOCIAL", "UGC": "SOCIAL",
    "META_REFTOOL": "OTHER", "META_BYLINE": "OTHER", "META_BOILER": "OTHER",
    "X_MALF": "OTHER", "X_NUL": "OTHER", "X_OTHER": "OTHER",
}

# Vocabulaire fermé des 20 codes fins LINKFUNC (codebook §5.2).
FINE_CODES = tuple(FINE_TO_MACRO.keys())

# MACRO valides (roll-up cible).
MACRO_CODES = ("EDITORIAL", "NAV", "RECO", "ADS", "SOCIAL", "OTHER")


def macro_of(code):
    """Roll-up déterministe code fin -> MACRO-6 (OTHER si code inconnu)."""
    return FINE_TO_MACRO.get(code, "OTHER")


def status_of(code, ref_target=""):
    """Roll-up code fin -> STATUS M/C/A (codebook §5.2).

    REF_BIB est C si ref_target=actor, A si infra (colonne 'Statut' du §5.2).
    """
    if code in ("EDIT_EXT", "EDIT_INT", "EDIT_LIST", "EDIT_HEADING"):
        return "M"
    if code == "REF_DATA":
        return "C"
    if code == "REF_BIB":
        return "C" if ref_target == "actor" else "A"
    return "A"


def loc3_of(code, ref_target=""):
    """Roll-up de pur lieu LOC3 {BODY, REF, APPARATUS} (amendement v1.1)."""
    if code in ("EDIT_EXT", "EDIT_INT", "EDIT_LIST", "EDIT_HEADING"):
        return "BODY"
    if code == "REF_DATA":
        return "REF"
    if code == "REF_BIB":
        return "REF" if ref_target == "actor" else "APPARATUS"
    return "APPARATUS"


def cit_derived_of(status, ref_target=""):
    """Régime 1 — cit_derived (comparateur seulement, codebook §5.7 / B.6 pseudo).

    CIT_DERIVED = 1 si status ∈ {M, C}, 0 sinon.

    Le statut C ne peut être atteint (via :func:`status_of`) que par REF_DATA ou
    REF_BIB(actor) — REF_BIB(infra) est déjà rangé en statut A. Or B.6 (codebook
    l.866) énumère explicitement « (REF_BIB actor, REF_DATA) » dans la branche
    CIT_EQUIV=1, et le « réseau étendu » (§5.2 l.298) = M + REF_BIB(actor) +
    REF_DATA. On code donc tout C à 1 (le ``ref_target`` est déjà consommé par
    ``status_of`` pour décider REF_BIB actor/infra). Comparateur uniquement :
    ne JAMAIS confondre avec citation_consensus (Régime 2). ``ref_target`` reste
    dans la signature pour compat mais n'est plus discriminant ici.
    """
    if status in ("M", "C"):
        return 1
    return 0


def build_f(dom, dom_html, context, source_url, target_url,
            src_domain=None, tgt_domain=None):
    """Assemble le dict ``f`` attendu par :func:`precode` à partir des champs de
    localisation d'une arête — que ceux-ci viennent d'``ExpressionLink`` (arête
    body) ou d'une ré-extraction DOM (arête raw-only, sprint §4.2).

    Reproduit la construction de ``02_precode.py`` (l.370-385), moins les clés
    non lues par ``precode`` (rowid/source_id/target_id/trel).

    src_domain/tgt_domain : noms de domaine (table ``domain``) si connus ; sinon
    l'host de l'url sert de repli (comme ``02_precode.py`` l.374-375).
    """
    leaf_tag, leaf_id, leaf_cls, leaf_last2 = parse_leaf(dom)
    block_tag, block_cls = parse_block(dom_html)
    anchor = parse_anchor(dom_html, target_url)
    src = src_domain or host(source_url)
    tgt = tgt_domain or host(target_url)
    # Le href n'est une preuve que s'il appartient VRAIMENT à cette arête :
    # sinon la parenthèse déséquilibrée d'un lien voisin codait X_MALF, en
    # confiance « high », une arête parfaitement saine.
    malformed = bool((anchor["resolved"] and anchor["href"]
                      and ("](" in anchor["href"]
                           or anchor["href"].count("(")
                           != anchor["href"].count(")")))
                     or (not dom and not dom_html))
    return {
        "context": context, "dom": dom, "dom_html": dom_html,
        "leaf_tag": leaf_tag, "leaf_id": leaf_id, "leaf_cls": leaf_cls, "leaf_last2": leaf_last2,
        "block_tag": block_tag, "block_cls": block_cls, "anchor": anchor,
        "src": src, "tgt": tgt, "su": source_url, "target_url": target_url,
        "is_external": bool(src and tgt and src != tgt), "malformed": malformed,
    }
