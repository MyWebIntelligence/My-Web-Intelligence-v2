"""Recodage des liens à quatre juges — moteur leaf (sprint recode-links, 2026-07-07).

Implémente le sprint ``03_analyse/ART1_sprint-recodage-liens_2026-07-07.md`` (v1.2).
Tire *n* arêtes de l'ensemble **fullhtml** ``A = body ∪ raw-only`` (frame gelé
``*_pageslinksfullhtml.csv``), ré-extrait la localisation DOM des arêtes raw-only
depuis ``expression.html``, et fait recoder chaque arête sur **deux axes
orthogonaux** par **trois juges-LLM** indépendants par axe (panel de record :
qwen3.7-max, gemini-3.1-flash-lite, minimax-m3) :

- **AXE 1 — LIEU** : ``LINKFUNC`` fin → ``MACRO``-6 (prompt P-LOC, B.5 purgé de
  toute charge « corps / réseau de controverse / retenu-éliminé »).
- **AXE 2 — CITATION** : ``CIT_ACT`` ∈ {1, 0, INDET} (prompt P-CIT, réécrit,
  location-orthogonal, deux voies : référent déterminé OU passerelle topique).

Sortie : un CSV **46 colonnes (schéma v2, 12/09/2026)** : les 9 colonnes utiles de
``_pageslinksfullhtml`` renommées en tête (``source_page_id``, ``in_body_mwi``…), la
strate ``body_extraction_mwi``, les votes ``judgeN_place_*`` / ``judgeN_cites*``, le
pré-codeur ``rule_place_*``, le consensus ``panel_*`` et les preuves, plus deux
sidecars (manifeste JSON, stats). Grammaire ``<qui>_<axe>_<quoi>`` (axes ``place`` =
LIEU, ``cites`` = ACTE ; suffixe ``_mwi`` = mécanique hérité de l'export). Historique :
nettoyage 10/07/2026 (49 col., slot j4 / ``ref_target`` / ``cit_type`` / INDET retirés,
``review`` gradué 0/1/2) ; v2 12/09/2026 (renommage, ``Weight``/``source_id``/``target_id``
retirés). Les anciens CSV v1 restent relisibles (``to_v2``). CSV non-quoté.

Contraintes :

- Module **leaf** : importe ``model``, ``link_context``, ``llm_openrouter``,
  ``link_precode`` — **jamais** ``core`` (évite le cycle d'import).
- Trois opérationnalisations distinctes de la citation, JAMAIS confondues
  (sprint §6/C5) : ``in_body_mwi`` (ex-``citation`` : mécanique, appartenance-corps
  héritée de l'export) ≠ ``cites_from_place`` (ex-``cit_derived`` : Régime 1, dérivé
  de P-LOC) ≠ ``panel_cites`` (ex-``citation_consensus`` : Régime 2, juge-citation
  indépendant, LA mesure de H1).
- La récupération DOM des arêtes raw-only réplique l'**échelle 3 clés** de
  l'export (correctif C1) : ``lookup_link_info`` n'en a que 2 (exact + relâché),
  on ajoute le 3e palier ``host_path`` sur le dommap. Parseur **lxml d'abord**
  (aligné sur ``extract_all_links`` de l'export), fallback ``html.parser``.
"""
import csv
import hashlib
import json
import os
import re
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import settings

from . import model
from . import llm_openrouter
from .link_context import (extract_link_dom_map, lookup_link_info, host_path_key,
                           _quiet_soup)
from .url_normalizer import normalize_url
from .link_precode import (build_f, precode, macro_of, status_of, cit_derived_of,
                           parse_leaf, FINE_CODES, MACRO_CODES)

# Valeurs autorisées côté juge-citation.
CIT_TYPES = ("ACTOR", "DOCUMENT", "LEGAL", "POSITION", "TOPIC", "NONE")


# =====================================================================
# 1. Frame : chargement, régénération, tirage stratifié
# =====================================================================
def load_frame(csv_path: str) -> List[dict]:
    """Charge le frame ``_pageslinksfullhtml.csv`` (option a, recommandée).

    Tri canonique par (Source, Target) entiers — le tirage RNG est sensible à
    l'ordre (sprint §4.1).
    """
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    rows.sort(key=lambda r: (int(r["Source"]), int(r["Target"])))
    return rows


def regen_frame(land, minrel: int = 1) -> List[dict]:
    """Option (b) — régénère le frame depuis la base via l'export apparié.

    ``_write_pageslinksfullhtml`` (export.py) fusionne calcul et écriture CSV : il
    n'existe pas de helper produisant les lignes en mémoire. On instancie donc
    l'export, on écrit un CSV temporaire, puis on le recharge via :func:`load_frame`.
    Voie secondaire : privilégier l'option (a) sur le frame gelé (SHA-256 épinglé
    au pré-enregistrement).
    """
    import os
    import tempfile
    from .export import Export  # import différé : garde link_coding leaf à froid
    export = Export("nodelinkcsv", land, minrel, fullhtml=True)
    tmpdir = tempfile.mkdtemp(prefix="mwi_regen_frame_")
    base = os.path.join(tmpdir, "regen_%s" % land.name)
    export.write("nodelinkcsv", base)
    csv_path = base + "_pageslinksfullhtml.csv"
    return load_frame(csv_path)


def draw(frame: List[dict], seed, n_elim: int, n_ret: int) -> List[dict]:
    """Sélection stratifiée : ``n_elim`` éliminés (weightbody==0) + ``n_ret`` retenus
    (weightbody==1).

    **``n <= 0`` (ou ``n >= |strate|``) → TOUTE la strate** (pas de limite = tout
    le fichier, demande utilisateur 08/07). Sinon, tirage seedé avec deux RNG
    **indépendants** par strate (changer ``n_ret`` ne perturbe pas le tirage
    éliminés — sprint §4.1).

    **Tirages EMBOÎTÉS (préfixe stable)** : on tire une permutation fixe de la
    strate (seedée) et on en prend les ``n`` premiers → l'échantillon à ``n=1000``
    est un SOUS-ENSEMBLE de celui à ``n=1500``. On peut donc coder 1000 puis
    étendre à 1500 avec ``--resume`` : les 1000 premiers sont réutilisés, seuls
    les 500 nouveaux sont codés (demande utilisateur 08/07).
    """
    import random
    elim = [r for r in frame if str(r["weightbody"]) == "0"]
    ret = [r for r in frame if str(r["weightbody"]) == "1"]

    def _pick(pool, n, tag, salt):
        if n is None or n <= 0 or n >= len(pool):
            idx = list(range(len(pool)))                 # toute la strate
        else:
            perm = list(range(len(pool)))
            random.Random("%s:%s" % (seed, salt)).shuffle(perm)
            idx = sorted(perm[:n])                        # préfixe stable → emboîtement
        return [dict(pool[i], stratum=tag) for i in idx]

    sample = (_pick(elim, n_elim, "eliminated", "eliminated")
              + _pick(ret, n_ret, "retained", "retained"))
    sample.sort(key=lambda r: (r["stratum"], int(r["Source"]), int(r["Target"])))
    return sample


# =====================================================================
# 2. Récupération DOM (arêtes raw-only) — échelle 3 clés, lxml-first
# =====================================================================
def _make_soup_lxml_first(html: str):
    """Parse HTML en **lxml d'abord** (aligné sur ``extract_all_links`` de
    l'export, correctif C1), fallback ``html.parser``. None si tout échoue.
    """
    if not html:
        return None
    try:
        return _quiet_soup(html, "lxml")
    except Exception:
        try:
            return _quiet_soup(html, "html.parser")
        except Exception:
            return None


def build_source_dommap(html: str, source_url: str):
    """Construit, pour une page source, le dommap ``{url→LinkDomInfo}`` (2 clés :
    exact + relâché) plus un index host_path (3e palier). Retourne
    ``(dommap, hp_index)`` ou ``(None, None)`` si le HTML est absent/illisible.
    """
    soup = _make_soup_lxml_first(html)
    if soup is None:
        return None, None
    dommap = extract_link_dom_map(html, source_url, soup=soup)
    if not dommap:
        return {}, {}
    hp_index: Dict[str, object] = {}
    for k, info in dommap.items():
        hp = host_path_key(k)
        if hp and hp not in hp_index:
            hp_index[hp] = info
    return dommap, hp_index


def resolve_dominfo(dommap, hp_index, target_url):
    """Résout ``target_url`` contre le dommap via l'échelle **3 clés** : exact →
    relâché (``lookup_link_info``) → host_path (palier ajouté, correctif C1).
    None sur miss.
    """
    if dommap is None:
        return None
    info = lookup_link_info(dommap, target_url)
    if info is not None:
        return info
    try:
        hp = host_path_key(normalize_url(target_url))
    except Exception:
        hp = None
    if hp and hp_index:
        return hp_index.get(hp)
    return None


# =====================================================================
# 3. Assemblage de l'évidence par arête (body vs raw-only, chemin INDET)
# =====================================================================
def _excerpt(text: str, cap: int = 300) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()[:cap]


def assemble_evidence(edge: dict, *, dom_row: Optional[Tuple] = None,
                      dommap=None, hp_index=None, target_title: str = "",
                      target_typeactor: str = "", src_domain: Optional[str] = None,
                      tgt_domain: Optional[str] = None) -> dict:
    """Assemble l'évidence d'une arête.

    - **body** (``weightbody==1``) : ``dom_row = (context, dom, dom_html)`` lu
      d'``ExpressionLink``. ``dom`` NULL → chemin INDET (correctif C10).
    - **raw-only** (``weightbody==0``) : résolution DOM 3 clés contre le dommap
      de la source (``dommap``/``hp_index``) ; ``context`` = ``block_text``.
      dommap None (html manquant/illisible) ou résolution ratée → INDET.

    ``ctx_source ∈ {body, rawhtml, indet}``. Chemin INDET : ``dom``/``dom_html``
    vides, **aucun appel API** en aval (routage humain).
    """
    src_url = edge.get("source_url", "")
    tgt_url = edge.get("target_url", "")
    is_external = str(edge.get("source_domain_id")) != str(edge.get("target_domain_id"))
    is_body = str(edge.get("weightbody")) == "1"

    dom = dom_html = context = None
    ctx_source = "indet"

    if is_body:
        if dom_row is not None:
            context, dom, dom_html = dom_row[0], dom_row[1], dom_row[2]
            # dom NULL (chemin BS4-fallback au crawl, ~1.6% des body edges) → INDET
            ctx_source = "body" if dom else "indet"
    else:
        info = resolve_dominfo(dommap, hp_index, tgt_url)
        if info is not None:
            dom, dom_html = info.dom, info.dom_html
            context = info.block_text          # pas de paragraphe markdown pour un raw-only
            ctx_source = "rawhtml"

    if ctx_source == "indet":
        dom = dom_html = context = None

    f = build_f(dom, dom_html, context, src_url, tgt_url,
                src_domain=src_domain, tgt_domain=tgt_domain)
    f["is_external"] = is_external          # le domain_id du frame fait autorité
    precode_res = precode(f)                 # 4e ancre déterministe de LOCATION (§5.6)

    anchor = f["anchor"]
    return {
        "source_id": int(edge["Source"]), "target_id": int(edge["Target"]),
        "source_url": src_url, "target_url": tgt_url,
        "source_actor": src_domain or "", "target_title": target_title or "",
        "target_typeactor": target_typeactor or "",
        "is_external": is_external, "stratum": edge.get("stratum", ""),
        "ctx_source": ctx_source,
        "dom": dom or "", "dom_html": dom_html or "", "context": context or "",
        "leaf_tag": parse_leaf(dom)[0], "anchor_text": anchor["text"],
        "precode": precode_res,
    }


# =====================================================================
# 4. Prompts P-LOC (B.5 purgé) et P-CIT (sprint §5.2)
# =====================================================================
def _project_block(project_meta: dict) -> str:
    return (
        "Projet (controverse) :\n"
        "- Land : %s\n- Description : %s\n- Mots-clés : %s\n"
        % (project_meta.get("name", ""), project_meta.get("description", ""),
           project_meta.get("keywords", ""))
    )


def build_ploc_prompt(ev: dict) -> str:
    """P-LOC — juge-LOCATION. B.5 **purgé** (correctif C6) : aucune mention de
    « corps du texte » / « réseau de controverse » / « retenu-éliminé ». Verdict
    de **pur lieu** (structurel), le roll-up MACRO garde RECO=RECO.
    """
    return (
        "RÔLE\n"
        "Tu codes la FONCTION DE LOCALISATION d'un hyperlien dans le gabarit de sa "
        "page source. Question PUREMENT STRUCTURELLE : où l'ancre siège-t-elle dans "
        "la page ? Tu ne juges NI si le lien « compte » pour une controverse, NI s'il "
        "sera retenu ou éliminé d'un quelconque réseau — seulement sa fonction de "
        "gabarit observée.\n\n"
        "LOI CARDINALE — ANCRAGE-FEUILLE\n"
        "Décide UNIQUEMENT sur : (a) la FEUILLE du chemin DOM = les 1-2 derniers "
        "segments de {dom} (conteneur immédiat du <a>) ; (b) le BLOC ANCÊTRE = la "
        "balise racine de {anchor_html} et sa classe ; (c) la FORME de {context}. "
        "N'utilise JAMAIS un mot de zone (nav/header/footer/sidebar/ads/reco/social) "
        "trouvé AILLEURS dans le chemin. La balise-feuille seule ne suffit pas (un "
        "<p> peut être un menu) : conjugue feuille + bloc + contexte + ancre.\n\n"
        "ARBRE DE DÉCISION (premier match gagne)\n"
        "0. malformé → X_MALF ; ancre+contexte+HTML tous vides → X_NUL\n"
        "1. Lexiques durs : ancre ∈ {DOI,PubMed,PMC,PDF,Full Text,Google Scholar} → "
        "META_REFTOOL ; classe/href de commentaire → UGC ; href social "
        "(share/intent/linkedin signup-in-company-posts) ∨ ancre ^# → SOCIAL ; href "
        "/tag//category//topic//glossary/ ∨ classe glossaire → TAG ; rel=license ∨ "
        "creativecommons ∨ disclaimer/legal/terms/privacy → META_BOILER\n"
        "2. Référence formelle (feuille cite | id CR/ref/bib/cite_note | bloc "
        "ref-list/references) ∧ ancre=source/URL-nue/DOI → REF_BIB "
        "(ref_target=infra si doi.org/perma.cc/résolveur, sinon actor)\n"
        "3. Byline : bloc « By <a> » ∨ href /author//team//people//profile//in/ ∨ "
        "« N min read » → META_BYLINE\n"
        "4. Promo : classe cta/btn ∨ (contexte impératif marketing ∧ même site) → ADS\n"
        "5. Table (tr>td) : doc primaire officiel ∧ peu d'ancres → REF_DATA ; sinon "
        "→ DATA_LISTING\n"
        "6. Renvoi légal intra-doc : interne ∧ ancre « Article/Annexe/Recital N » → TOC\n"
        "7. PORTE : contexte=phrase suivie ∧ ancre=syntagme ∧ feuille ∈ {p,span,em,li} : "
        "externe → EDIT_EXT ; interne → EDIT_INT ; bloc de corps ∧ ≥2 domaines "
        "externes glosés → EDIT_LIST\n"
        "8. Appareil mou : classe de nav → NAV ; classe related/carte ∨ ancre "
        "vide(img) ∨ ancre=concat-titres → RECO ; libellé interne (nombre/sommaire) "
        "→ TOC sinon NAV ; liste à puces courtes → NAV\n"
        "9. Titre-pointeur : feuille h2/h3 ∧ externe ∧ ancre=titre complet → EDIT_HEADING\n"
        "10. Résidu → X_OTHER (note obligatoire)\n\n"
        "DONNÉES À ANALYSER\n"
        "Page source   : %s\nPage cible    : %s  — %s\nCible externe ?: %s\n"
        "Ancre + bloc HTML : %s\nContexte      : %s\nChemin DOM    : %s\n\n"
        "CONFIANCE & ROUTAGE\n"
        "Évalue ta confiance dans [0,1]. review = true si confiance < 0,90 ou code ∈ "
        "{X_OTHER, EDIT_HEADING}. Ne renonce jamais par confort.\n\n"
        "SORTIE — un seul objet JSON sur une ligne, rien d'autre :\n"
        "{\"status\":\"M|C|A\",\"code\":\"<CODE>\",\"ref_target\":\"actor|infra|null\","
        "\"confidence\":<0..1>,\"rule\":\"<n°>\",\"review\":<true|false>,\"note\":\"<=200 car.\"}"
        % (ev.get("source_url", ""), ev.get("target_url", ""), ev.get("target_title", ""),
           "oui" if ev.get("is_external") else "non", ev.get("dom_html", ""),
           ev.get("context", ""), ev.get("dom", ""))
    )


def build_pcit_prompt(ev: dict, project_meta: dict) -> str:
    """P-CIT — juge-CITATION (B.6 réécrit, sprint §5.2). Location-orthogonal ;
    deux voies (référent déterminé OU passerelle topique) ; verdict sur le GESTE
    de l'inscription, jamais sur l'identité de la cible (correctif C2). Ne reçoit
    JAMAIS le code LINKFUNC.
    """
    return (
        "RÔLE\n"
        "Tu juges si un hyperlien pose, envers la controverse du projet, un ACTE DE "
        "CITATION : il OFFRE au lecteur un acteur, un document, un instrument "
        "juridique ou une prise de position qui FAIT PARTIE de la controverse, comme "
        "geste référentiel. Cette question est INDÉPENDANTE de l'emplacement du lien "
        "dans la page : un lien de pied de page « pour aller plus loin / à lire aussi » "
        "vers un acteur de la controverse EST une citation ; un lien en plein corps de "
        "texte vers la page cookies / mentions légales / accueil du site lui-même n'en "
        "est PAS une. Ne juge NI la fonction de gabarit, NI le statut retenu/éliminé, "
        "NI un quelconque code de localisation.\n\n"
        "DÉCIDE SUR L'INSCRIPTION, PAS SUR L'IDENTITÉ DE LA CIBLE\n"
        "Toutes les cibles de ce corpus sont déjà des pages pertinentes pour la "
        "controverse. La question a DEUX voies vers cit=1 : (i) l'ANCRE et le CONTEXTE "
        "présentent la cible comme un référent INVOQUÉ, ENDOSSÉ, CONTESTÉ ou MOBILISÉ "
        "comme preuve par l'auteur (référent déterminé) ; OU (ii) l'inscription offre "
        "une PASSERELLE TOPIQUE vers la controverse — un renvoi thématique « pour "
        "aller plus loin / voir notre couverture de l'AI Act », un hub, une page-thème "
        "ou un tag PORTANT SUR le débat gouvernance-IA. Restent à 0, MÊME si la cible "
        "est pertinente : la navigation structurelle propre au site (menu général, fil "
        "d'Ariane, pagination, accueil), le partage/abonnement, le self-permalien, un "
        "tag/hub HORS-controverse, et le résolveur nu (doi.org, perma.cc) sans "
        "référent nommé.\n\n"
        "CONTROVERSE DU PROJET\n%s\n"
        "DONNÉES À ANALYSER\n"
        "Page source        : %s  (acteur : %s)\n"
        "Page cible         : %s  — %s  [type acteur cible : %s]\n"
        "Cible externe ?    : %s\nAncre + bloc HTML  : %s\nContexte           : %s\n"
        "Chemin DOM         : %s\n\n"
        "TÂCHE — CITATION (ternaire) + TYPE\n"
        "  cit = 1 si le lien offre (i) un référent DE la controverse "
        "(acteur/document/instrument/position invoqué) OU (ii) une passerelle topique "
        "vers la controverse (hub/page-thème/tag « pour aller plus loin ») ; "
        "l'emplacement (corps, encadré, pied de page, « further reading », barre "
        "latérale, NAV/TAG) est SANS effet.\n"
        "  cit = 0 pour : navigation structurelle propre au site (menu, fil d'Ariane, "
        "pagination, accueil), mentions légales/cookies/confidentialité, connexion, "
        "partage/abonnement, tag/hub HORS-controverse, pur résolveur sans référent "
        "nommé, self-permalien — MÊME dans le corps du texte.\n"
        "  cit = INDET seulement si l'inscription est illisible (ancre dégénérée + "
        "contexte vide + bloc inanalysable) ou la cible irrésoluble.\n"
        "  cit_type ∈ {ACTOR, DOCUMENT, LEGAL, POSITION, TOPIC, NONE} (NONE si cit≠1 ; "
        "le plus spécifique, priorité LEGAL > DOCUMENT > POSITION > ACTOR > TOPIC).\n\n"
        "CONFIANCE & ROUTAGE\n"
        "Évalue ta confiance dans [0,1]. review = true si confiance < 0,90. Ne renonce "
        "jamais par confort.\n\n"
        "SORTIE — un seul objet JSON sur une ligne, rien d'autre :\n"
        "{\"cit\":0|1|\"INDET\",\"cit_type\":\"ACTOR|DOCUMENT|LEGAL|POSITION|TOPIC|NONE\","
        "\"confidence\":<0..1>,\"review\":<true|false>,\"note\":\"<=200 car.\"}"
        % (_project_block(project_meta), ev.get("source_url", ""),
           ev.get("source_actor", ""), ev.get("target_url", ""),
           ev.get("target_title", ""), ev.get("target_typeactor", ""),
           "oui" if ev.get("is_external") else "non", ev.get("dom_html", ""),
           ev.get("context", ""), ev.get("dom", ""))
    )


# =====================================================================
# 5. Appel LLM (retry/backoff) + parsing JSON
# =====================================================================
class _Budget:
    """Compteur d'appels + plafond (0 = pas de limite, convention MWI).

    Thread-safe : ``code_links`` code jusqu'à ``max_workers`` arêtes en
    parallèle ; les juges d'une même arête, eux, sont séquentiels
    (``code_one_edge``).
    """
    def __init__(self, max_calls: int = 0):
        self.calls = 0
        self.max = max_calls or 0
        self._lock = threading.Lock()

    def bump(self) -> None:
        with self._lock:
            self.calls += 1

    def exhausted(self) -> bool:
        # Sous le verrou comme bump() : sans lui, la lecture peut voir un
        # compteur en cours d'incrémentation depuis un autre juge.
        with self._lock:
            return self.max > 0 and self.calls >= self.max


_RETRY_BASE_DELAY = 1.0  # s ; testable (mis à 0 hors-ligne)


def _safe_call(prompt: str, model_slug: str, budget: Optional[_Budget],
               retries: int = 3) -> Optional[str]:
    """Appelle ``ask_openrouter_chat`` avec retry/backoff exponentiel (1/2/4 s).
    Compte chaque tentative dans ``budget``. Échec final → None (juge manquant).
    """
    delay = _RETRY_BASE_DELAY
    timeout = getattr(settings, "linkcode_timeout", 120)   # généreux (modèles lents)
    max_tok = getattr(settings, "linkcode_max_tokens", 0) or None  # borne le coût raisonnement
    for attempt in range(max(1, retries)):
        if budget is not None:
            budget.bump()
        try:
            return llm_openrouter.ask_openrouter_chat(
                prompt, model=model_slug, timeout=timeout, max_tokens=max_tok)
        except Exception:
            if attempt < retries - 1:
                if delay:
                    time.sleep(delay)
                delay *= 2
    return None


def parse_json_object(text: Optional[str]) -> Optional[dict]:
    """Extrait le premier objet JSON équilibré de ``text`` (strip des fences
    ```json, tolérance à la prose autour). None si introuvable/invalide.
    """
    if not text:
        return None
    t = text.strip()
    t = re.sub(r"^```(?:json)?", "", t).strip()
    t = re.sub(r"```$", "", t).strip()
    start = t.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(t)):
        ch = t[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(t[start:i + 1])
                except Exception:
                    return None
    return None


def _to_float(v) -> str:
    try:
        return "%.3f" % float(v)
    except (TypeError, ValueError):
        return ""


# =====================================================================
# 6. Juges (un verdict par prompt) + agrégation majorité stricte
# =====================================================================
def judge_location(ev: dict, model_slug: str, budget: Optional[_Budget] = None,
                   retries: int = 3) -> Optional[dict]:
    """P-LOC → {code, status, ref_target, macro, confidence, review, note}. None si
    appel raté ou schéma invalide (juge manquant, exclu du vote)."""
    obj = parse_json_object(_safe_call(build_ploc_prompt(ev), model_slug, budget, retries))
    if not obj:
        return None
    code = str(obj.get("code", "")).strip().upper()
    status = str(obj.get("status", "")).strip().upper()
    # On ne valide QUE le code (spec §5.3 : « code ∈ set codebook »). Le status du
    # juge n'est PAS validé : il est recalculé de façon déterministe par status_of()
    # en agrégation et n'est jamais émis par juge dans le CSV. P-LOC a été purgé des
    # définitions M/C/A (C6) ; rejeter sur status jetterait des verdicts valides
    # (juge manquant → review forcé, κ dégradé systématiquement).
    if code not in FINE_CODES:
        return None
    ref = obj.get("ref_target")
    ref = "" if ref in (None, "null", "") else str(ref).strip().lower()
    if ref not in ("actor", "infra", ""):
        ref = ""
    return {"code": code, "status": status, "ref_target": ref, "macro": macro_of(code),
            "confidence": _to_float(obj.get("confidence")),
            "review": bool(obj.get("review")), "note": str(obj.get("note", ""))[:200]}


def judge_citation(ev: dict, project_meta: dict, model_slug: str,
                   budget: Optional[_Budget] = None, retries: int = 3) -> Optional[dict]:
    """P-CIT → {cit, cit_type, confidence, review, note}. None si appel raté /
    schéma invalide."""
    obj = parse_json_object(_safe_call(build_pcit_prompt(ev, project_meta),
                                       model_slug, budget, retries))
    if not obj:
        return None
    cit = obj.get("cit")
    if isinstance(cit, str):
        cu = cit.strip().upper()
        cit = ("INDET" if cu == "INDET"
               else 1 if cu in ("1", "TRUE", "YES", "OUI")
               else 0 if cu in ("0", "FALSE", "NO", "NON") else None)
    elif isinstance(cit, bool):
        cit = int(cit)
    if cit not in (0, 1, "INDET"):
        return None
    ctype = str(obj.get("cit_type", "NONE")).strip().upper()
    if ctype not in CIT_TYPES:
        ctype = "NONE"
    if cit != 1:
        ctype = "NONE"
    return {"cit": cit, "cit_type": ctype, "confidence": _to_float(obj.get("confidence")),
            "review": bool(obj.get("review")), "note": str(obj.get("note", ""))[:200]}


def _modal(values: list) -> Tuple[Optional[str], int]:
    """(label modal unique, effectif) ; label None en cas d'égalité de mode."""
    if not values:
        return None, 0
    c = Counter(values)
    lab, cnt = c.most_common(1)[0]
    modes = [x for x, n in c.items() if n == cnt]
    return (lab if len(modes) == 1 else None), cnt


def _strict_majority(values: list) -> Tuple[Optional[str], int]:
    """(label si majorité STRICTE > moitié des non-manquants, effectif modal)."""
    lab, cnt = _modal(values)
    if lab is not None and cnt * 2 > len(values):
        return lab, cnt
    return None, cnt


def aggregate(loc_verdicts: List[Optional[dict]], cit_verdicts: List[Optional[dict]],
              n_judges: int = 4) -> dict:
    """Consensus à **majorité stricte** (sprint §5.3) : ≥ 3/4 à panel complet,
    ≥ 2/3 si un juge manque, 2-2 → NOMAJ + routage humain. Manquant exclu du
    dénominateur, ``cit=INDET`` exclu de la base 0/1.
    """
    loc_p = [v for v in loc_verdicts if v is not None]
    cit_p = [v for v in cit_verdicts if v is not None]

    # --- LOCATION : majorité sur le code fin, roll-up déterministe ---
    codes = [v["code"] for v in loc_p]
    fine, fine_cnt = _strict_majority(codes)
    if fine is not None:
        macro = macro_of(fine)
        refs = [v["ref_target"] for v in loc_p if v["code"] == fine]
        ref_target = _modal(refs)[0] or ""
        status = status_of(fine, ref_target)
        linkfunc_fine, loc_majority, loc_agree = fine, 1, fine_cnt
    else:
        # pas de majorité au code : tenter la majorité MACRO
        macro_maj, macro_cnt = _strict_majority([macro_of(v["code"]) for v in loc_p])
        macro = macro_maj or ""
        ref_target = _modal([v["ref_target"] for v in loc_p])[0] or ""
        status = ""                      # STATUS indéfini sans majorité de code
        linkfunc_fine, loc_majority = "NOMAJ", 0
        loc_agree = _modal(codes)[1]
    cit_derived = cit_derived_of(status, ref_target) if status else ""

    # --- CITATION : majorité stricte sur le binaire {0,1} (INDET exclu) ---
    binary = [v["cit"] for v in cit_p if v["cit"] in (0, 1)]
    cit_cons, cit_bin_cnt = _strict_majority(binary)
    if cit_cons is None:
        citation_consensus, cit_type, cit_majority = "NOMAJ", "", 0
    else:
        citation_consensus, cit_majority = cit_cons, 1
        if cit_cons == 1:
            cit_type = _modal([v["cit_type"] for v in cit_p if v["cit"] == 1])[0] or "MIXED"
        else:
            cit_type = "NONE"
    cit_all = [v["cit"] for v in cit_p]
    cit_agree = _modal(cit_all)[1]

    # --- review : compte GRADUÉ 0/1/2 des axes sans majorité stricte (nettoyage
    # 10/07/2026). review = (localisation sans majorité) + (citation sans majorité) :
    # 0 = les deux tranchés ; 1 = un seul axe contesté ; 2 = les deux. Remplace
    # l'ancien binaire, qui flaggait aussi juge manquant, INDET et confiance < 0,90
    # (≈ 50 % des lignes) — trop bruyant. Le n_judges n'entre plus dans review.
    review = (1 if loc_majority == 0 else 0) + (1 if cit_majority == 0 else 0)
    return {
        "linkfunc_fine": linkfunc_fine, "macro": macro, "ref_target": ref_target,
        "cit_derived": cit_derived, "citation_consensus": citation_consensus,
        "cit_type": cit_type,
        "loc_agree": "%d/%d" % (loc_agree, len(loc_p)) if loc_p else "0/0",
        "cit_agree": "%d/%d" % (cit_agree, len(cit_p)) if cit_p else "0/0",
        "loc_majority": loc_majority, "cit_majority": cit_majority, "review": review,
    }


def _indet_aggregate(n_judges: int) -> dict:
    """Agrégat d'un cas INDET (miss) — aucun juge, zéro appel. review=2 (les deux
    axes sans majorité). NB : depuis le nettoyage 10/07/2026, les lignes INDET ne
    sont PLUS écrites dans la table livrée (comptées dans manifest.misses_indet)."""
    return {
        "linkfunc_fine": "INDET", "macro": "", "ref_target": "",
        "cit_derived": "", "citation_consensus": "INDET", "cit_type": "",
        "loc_agree": "0/0", "cit_agree": "0/0",
        "loc_majority": 0, "cit_majority": 0, "review": 2,
    }


def code_one_edge(ev: dict, judges: List[str], project_meta: dict,
                  budget: Optional[_Budget] = None, retries: int = 3
                  ) -> Tuple[List[Optional[dict]], List[Optional[dict]], dict]:
    """Code UNE arête : chemin INDET (aucun appel API) sinon N_JUDGES juges × 2 prompts,
    en **séquentiel** (la concurrence vit au niveau arête dans ``code_links``, pour
    ne pas imbriquer les pools). Retourne ``(loc_verdicts, cit_verdicts, agg)``."""
    n = len(judges)
    if ev["ctx_source"] == "indet" or n == 0:
        return [], [], _indet_aggregate(n)
    loc, cit = [], []
    for m in judges:
        loc.append(judge_location(ev, m, budget, retries))
        cit.append(judge_citation(ev, project_meta, m, budget, retries))
    return loc, cit, aggregate(loc, cit, n_judges=n)


# =====================================================================
# 7. Schéma CSV v2 (12/09/2026) et construction de ligne
# =====================================================================
# Colonnes du frame MWI (export ``*_pageslinksfullhtml.csv``) telles que LUES en entrée.
FRAME_COLS = ["Source", "Target", "Weight", "weightbody", "weighthtml", "citation",
              "source_url", "source_domain_id", "target_url", "target_domain_id"]

# TABLE LIVRÉE — schéma v2 (46 colonnes), grammaire ``<qui>_<axe>_<quoi>`` :
#   axes : ``place`` = LIEU (où siège l'ancre) ; ``cites`` = ACTE (le lien cite : 1/0) ;
#   qui  : ``judgeN`` (juge LLM), ``panel`` (consensus), ``rule`` (pré-codeur
#          déterministe), ``human`` (or humain) ;
#   ``_mwi`` : valeur mécanique héritée de l'export MyWebIntelligence (pas un jugement).
# ``cites`` ne désigne JAMAIS autre chose que l'acte jugé ; ``in_body_mwi`` JAMAIS autre
# chose que la localisation mécanique. Le 2×2 de H1 = body_extraction_mwi × panel_cites.
# Retirées du schéma v1 : ``Weight`` (toujours vide), ``source_id``/``target_id``
# (doublons de Source/Target). Décision Amar 12/09/2026 (03_analyse/ART1_variables_codage_*).
FRAME_OUT = {"Source": "source_page_id", "Target": "target_page_id",
             "weightbody": "count_in_body", "weighthtml": "count_in_page",
             "citation": "in_body_mwi",
             "source_url": "source_url", "source_domain_id": "source_domain_id",
             "target_url": "target_url", "target_domain_id": "target_domain_id"}
STRATUM_COL = "body_extraction_mwi"          # eliminated (hors corps) / retained (corps)
SRC_COL, TGT_COL = "source_page_id", "target_page_id"

# Panel de record = 3 juges (judge1 qwen, judge2 gemini, judge3 minimax). Nettoyage
# 10/07/2026 : slot j4 réservé, ``ref_target`` et ``cit_type`` retirés de la table
# livrée (ref_target reste calculé en interne : il alimente cit_derived via status_of).
N_JUDGES = 3

# Clés internes de ``aggregate`` (API testée, stable) → colonnes v2 de la table livrée.
AGG_TO_COL = {"linkfunc_fine": "panel_place_code", "macro": "panel_place_group",
              "cit_derived": "cites_from_place", "citation_consensus": "panel_cites",
              "loc_agree": "panel_place_agreement", "cit_agree": "panel_cites_agreement",
              "loc_majority": "panel_place_majority", "cit_majority": "panel_cites_majority",
              "review": "contested_axes"}
_AGG_ORDER = ("linkfunc_fine", "macro", "cit_derived", "citation_consensus",
              "loc_agree", "cit_agree", "loc_majority", "cit_majority", "review")


def _judge_cols() -> List[str]:
    c = []
    for base in ("place_code", "place_group", "place_conf"):
        c += ["judge%d_%s" % (j, base) for j in range(1, N_JUDGES + 1)]
    for base in ("cites", "cites_conf"):
        c += ["judge%d_%s" % (j, base) for j in range(1, N_JUDGES + 1)]
    return c


def csv_header() -> List[str]:
    return ([FRAME_OUT[c] for c in FRAME_COLS if c in FRAME_OUT] + [STRATUM_COL]
            + _judge_cols()
            + ["rule_place_status", "rule_place_code", "rule_place_group"]
            + [AGG_TO_COL[k] for k in _AGG_ORDER]
            + ["evidence_source", "external_target", "anchor_tag", "anchor_text",
               "target_actor_type", "dom_path", "context_text",
               "human_place_group", "human_cites"])


# Schéma v1 (49 col., 10/07/2026) → v2 : relecture d'anciens CSV (``--resume``).
LEGACY_DROP = ("Weight", "source_id", "target_id")
LEGACY_RENAME = {
    "Source": "source_page_id", "Target": "target_page_id",
    "weightbody": "count_in_body", "weighthtml": "count_in_page",
    "citation": "in_body_mwi", "stratum": "body_extraction_mwi",
    "precode_status": "rule_place_status", "precode_code": "rule_place_code",
    "precode_macro": "rule_place_group", "ctx_source": "evidence_source",
    "is_external": "external_target", "leaf_tag": "anchor_tag",
    "target_typeactor": "target_actor_type", "dom": "dom_path",
    "context_excerpt": "context_text", "human_gold_macro": "human_place_group",
    "human_gold_cit": "human_cites",
}
LEGACY_RENAME.update(AGG_TO_COL)
for _j in range(1, N_JUDGES + 1):
    LEGACY_RENAME.update({"loc_fine_j%d" % _j: "judge%d_place_code" % _j,
                          "macro_j%d" % _j: "judge%d_place_group" % _j,
                          "conf_loc_j%d" % _j: "judge%d_place_conf" % _j,
                          "cit_j%d" % _j: "judge%d_cites" % _j,
                          "conf_cit_j%d" % _j: "judge%d_cites_conf" % _j})


def to_v2(r: dict) -> dict:
    """Normalise une ligne lue (schéma v1 49 col. ou v2) vers les clés v2 ; v2 inchangée."""
    if SRC_COL in r or STRATUM_COL in r:
        return r
    return {LEGACY_RENAME.get(k, k): v for k, v in r.items() if k not in LEGACY_DROP}


def build_row(edge: dict, ev: dict, loc: List[Optional[dict]],
              cit: List[Optional[dict]], agg: dict) -> dict:
    """Construit une ligne du CSV (schéma v2) : 9 colonnes du frame renommées en tête."""
    row = {FRAME_OUT[c]: edge.get(c, "") for c in FRAME_COLS if c in FRAME_OUT}
    row[STRATUM_COL] = edge.get("stratum", "")

    def _pad(lst):
        return list(lst) + [None] * (N_JUDGES - len(lst))
    lv, cv = _pad(loc), _pad(cit)
    for j in range(N_JUDGES):
        v = lv[j]
        row["judge%d_place_code" % (j + 1)] = v["code"] if v else ""
        row["judge%d_place_group" % (j + 1)] = v["macro"] if v else ""
        row["judge%d_place_conf" % (j + 1)] = v["confidence"] if v else ""
        c = cv[j]
        row["judge%d_cites" % (j + 1)] = c["cit"] if c else ""
        row["judge%d_cites_conf" % (j + 1)] = c["confidence"] if c else ""

    pc = ev["precode"]
    row["rule_place_status"] = pc["status"]
    row["rule_place_code"] = pc["code"]
    row["rule_place_group"] = macro_of(pc["code"])
    row.update({col: agg[k] for k, col in AGG_TO_COL.items()})
    row["evidence_source"] = ev["ctx_source"]
    row["external_target"] = int(ev["is_external"])
    row["anchor_tag"] = ev["leaf_tag"]
    row["anchor_text"] = ev["anchor_text"][:160]
    row["target_actor_type"] = ev.get("target_typeactor", "")
    row["dom_path"] = ev["dom"]
    row["context_text"] = _excerpt(ev["context"], 300)
    row["human_place_group"] = ""
    row["human_cites"] = ""
    return row


# =====================================================================
# 8. Orchestration : code_links (frame → CSV + manifeste + stats)
# =====================================================================
def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _preload(sample: List[dict]) -> Tuple[dict, dict, dict]:
    """Précharge (drainé AVANT toute autre requête) : noms de domaine, titres des
    cibles, et—pour les arêtes raw-only—les dommaps par source (lxml-first)."""
    dom_name = {r[0]: r[1] for r in model.DB.execute_sql("SELECT id, name FROM domain")}

    target_ids = sorted({int(e["Target"]) for e in sample})
    title_of: Dict[int, str] = {}
    for i in range(0, len(target_ids), 500):
        chunk = target_ids[i:i + 500]
        ph = ",".join("?" * len(chunk))
        for tid, title in model.DB.execute_sql(
                "SELECT id, title FROM expression WHERE id IN (%s)" % ph, chunk):
            title_of[tid] = title or ""

    raw_src = sorted({int(e["Source"]) for e in sample if str(e["weightbody"]) == "0"})
    dommap_cache: Dict[int, Tuple] = {}
    for sid in raw_src:
        row = model.DB.execute_sql(
            "SELECT url, html FROM expression WHERE id = ?", (sid,)).fetchone()
        if not row or not row[1]:
            dommap_cache[sid] = (None, None)          # html manquant → INDET
            continue
        dommap_cache[sid] = build_source_dommap(row[1], row[0])
    return dom_name, title_of, dommap_cache


def _body_dom_row(sid: int, tid: int) -> Optional[Tuple]:
    return model.DB.execute_sql(
        "SELECT context, dom, dom_html FROM expressionlink "
        "WHERE source_id = ? AND target_id = ?", (sid, tid)).fetchone()


def _row_is_coded(r: dict) -> bool:
    """Une ligne est réellement « faite » si elle est INDET (incodable, routage
    humain légitime) OU si au moins un juge a rendu un verdict. Une ligne écrite
    SANS aucun verdict (tous les appels ont échoué — 402/rate-limit/timeout) n'est
    PAS considérée comme faite : ``--resume`` la re-codera."""
    r = to_v2(r)
    if r.get("evidence_source") == "indet":
        return True
    js = range(1, N_JUDGES + 1)
    # `not in (None, "")` et non la simple véracité : en mémoire, un verdict de
    # citation « non » est l'ENTIER 0, qui est faux en Python. Une ligne portant
    # trois verdicts valides à 0 était donc jugée non codée, écartée de
    # l'écriture, puis re-codée et re-payée au `--resume` suivant. Relue depuis
    # le CSV le même verdict vaut la CHAÎNE "0", vraie : le défaut ne se voyait
    # qu'avant le premier aller-retour sur disque.
    return (any(r.get("judge%d_place_code" % j) not in (None, "") for j in js)
            or any(r.get("judge%d_cites" % j) not in (None, "") for j in js))


def _load_done(out_path: str) -> Tuple[set, List[dict]]:
    """Lit un CSV partiel : renvoie ({(Source,Target) réellement codés}, lignes à
    conserver). Les lignes sans verdict (échecs) sont EXCLUES du « done » (→
    re-codées) et non conservées (la version re-codée les remplace ; les doublons
    d'un run précédent sont dédupliqués — on garde la meilleure version)."""
    if not os.path.exists(out_path):
        return set(), []
    best: Dict[tuple, tuple] = {}
    try:
        with open(out_path, newline="", encoding="utf-8") as rf:
            for r in csv.DictReader(rf):
                r = to_v2(r)                       # accepte un CSV v1 (49 col.) ou v2
                s, t = r.get(SRC_COL), r.get(TGT_COL)
                if not s or not t:
                    continue
                coded = _row_is_coded(r)
                key = (s, t)
                if key not in best or (coded and not best[key][1]):
                    best[key] = (r, coded)
    except Exception as exc:
        # Ne JAMAIS répondre « rien de fait » sur une lecture ratée : l'appelant
        # enchaîne sur un open(out_path, "w") qui tronque le fichier, et le
        # partiel d'un run de plusieurs heures disparaît. On s'arrête net.
        raise RuntimeError(
            "CSV partiel illisible (%s) : %s — déplacez-le ou réparez-le avant "
            "de relancer avec --resume, sinon il serait écrasé."
            % (out_path, exc)) from exc
    done = {k for k, (r, c) in best.items() if c}
    keep = [r for k, (r, c) in best.items() if c]
    return done, keep


def code_links(csv_path: str, out_path: str, *, judges: List[str], project_meta: dict,
               seed=42, n_elim: int = 1000, n_ret: int = 300, minrel: int = 1,
               max_calls: int = 0, retries: int = 3, max_workers: int = 0,
               resume: bool = False, frame_rows: Optional[List[dict]] = None) -> int:
    """Chemin d'exécution primaire du sprint. Requiert ``model.DB`` déjà initialisé
    (le runner ``03_code_links.py`` fait ``model.DB.init(<mwi.db>)``).

    - Écriture INCRÉMENTALE (flush tous les 10) : un run interrompu laisse un CSV
      partiel valide.
    - ``resume=True`` : reprend un CSV partiel existant (skip des (Source,Target)
      déjà codés, append sans ré-écrire l'en-tête) — le run complet dure ~heures.
    - Les ARÊTES sont codées en parallèle (``max_workers``, défaut 16) ; à
      l'intérieur d'une arête les 2·N_JUDGES appels (6 pour le panel de
      record) sont SÉQUENTIELS. Le profil de charge vu par OpenRouter est
      donc de ``max_workers`` appels en vol — pas 6, pas 8 : les deux
      anciennes formulations sous-estimaient la charge d'un facteur 2,7 et
      se contredisaient l'une l'autre.

    Écrit : ``out_path`` (CSV §6), ``out_path``+``.manifest.json``,
    ``out_path``+``.stats.txt``. Retourne le nombre total d'arêtes dans le CSV.
    """
    frame = frame_rows if frame_rows is not None else load_frame(csv_path)
    sample = draw(frame, seed, n_elim, n_ret)

    done, existing = _load_done(out_path) if resume else (set(), [])
    todo = [e for e in sample if (e["Source"], e["Target"]) not in done]
    if resume and existing:
        print("[link_coding] reprise : %d déjà codées, %d à faire"
              % (len(existing), len(todo)))
    dom_name, title_of, dommap_cache = _preload(todo)

    budget = _Budget(max_calls)
    header = csv_header()
    rows: List[dict] = list(existing)

    # --- Phase A : évidence (thread principal — SQLite mono-connexion, séquentiel).
    # Toute la DB est drainée ICI ; la Phase B ne fait QUE du HTTP (thread-safe).
    prepared: List[Tuple[dict, dict]] = []
    for edge in todo:
        sid, tid = int(edge["Source"]), int(edge["Target"])
        sdom = dom_name.get(_int(edge.get("source_domain_id")))
        tdom = dom_name.get(_int(edge.get("target_domain_id")))
        if str(edge["weightbody"]) == "1":
            ev = assemble_evidence(edge, dom_row=_body_dom_row(sid, tid),
                                   target_title=title_of.get(tid, ""),
                                   src_domain=sdom, tgt_domain=tdom)
        else:
            dm, hp = dommap_cache.get(sid, (None, None))
            ev = assemble_evidence(edge, dommap=dm, hp_index=hp,
                                   target_title=title_of.get(tid, ""),
                                   src_domain=sdom, tgt_domain=tdom)
        prepared.append((edge, ev))

    indet = [(e, ev) for e, ev in prepared if ev["ctx_source"] == "indet"]
    to_code = [(e, ev) for e, ev in prepared if ev["ctx_source"] != "indet"]
    misses = sum(1 for r in existing if r.get("evidence_source") == "indet") + len(indet)

    # Plafond : INDET = 0 appel (toujours codées) ; on borne le nombre d'arêtes codées.
    budget_stopped = False
    if max_calls:
        cap = max(0, max_calls // (2 * max(1, len(judges))))
        if len(to_code) > cap:
            print("[link_coding] plafond %d appels → %d/%d arêtes codées (reste non codé)"
                  % (max_calls, cap, len(to_code)))
            to_code = to_code[:cap]
            budget_stopped = True

    # --- Phase B : codage LLM CONCURRENT (W arêtes en vol) + écriture au fil de l'eau.
    workers = max_workers or 16
    total = len(to_code)                                 # INDET non écrites (cf. infra)
    # On n'ajoute à la suite QUE si l'en-tête du fichier est déjà celui qu'on
    # s'apprête à écrire. Une reprise sur un CSV v1 (49 colonnes) ajoutait des
    # lignes ordonnées v2 sous l'en-tête v1 : interrompu avant la réécriture
    # finale, le fichier mélangeait les deux, et le `--resume` suivant relisait
    # `count_in_body` comme `Weight`. Sinon on réécrit : `existing` est déjà
    # passé par `to_v2`, donc les lignes v1 relues ressortent en v2.
    first: List[str] = []
    if os.path.exists(out_path):
        with open(out_path, newline="", encoding="utf-8") as hf:
            first = next(csv.reader(hf), [])
    append = bool(existing) and first == header
    f = open(out_path, "a" if append else "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(f, fieldnames=header, quoting=csv.QUOTE_MINIMAL,
                            extrasaction="ignore")
    if not append:
        writer.writeheader()
        writer.writerows(existing)
        f.flush()
    written = 0

    def _emit(row):                                      # thread principal uniquement
        nonlocal written
        rows.append(row)
        writer.writerow(row)
        written += 1
        if written % 10 == 0:
            f.flush()
            print("[link_coding] %d/%d arêtes (%d appels, %d miss)"
                  % (written, total, budget.calls, misses), flush=True)

    def _task(e, ev):                                    # threads : HTTP pur, sans DB
        # Frein réel sur max_calls. Le plafond calculé d'avance ignore les
        # reprises : un fournisseur qui répond 429 une fois sur deux triple le
        # nombre d'appels facturés sous un plafond annoncé. On refuse de
        # COMMENCER une arête quand le budget est épuisé — jamais de couper au
        # milieu, une arête à demi codée perd des juges et fausse le panel.
        if budget.exhausted():
            return build_row(e, ev, [], [], _indet_aggregate(len(judges)))
        loc, cit, agg = code_one_edge(ev, judges, project_meta, budget, retries)
        return build_row(e, ev, loc, cit, agg)

    interrupted = False
    skipped = 0
    try:
        # INDET (incodables) : comptées dans manifest.misses_indet mais PAS écrites
        # dans la table livrée (nettoyage 10/07/2026 — table = liens codables seuls).
        if to_code:
            with ThreadPoolExecutor(max_workers=workers) as ex:
                futs = [ex.submit(_task, e, ev) for e, ev in to_code]
                try:
                    for fut in as_completed(futs):
                        row = fut.result()
                        if _row_is_coded(row):           # ≥1 verdict → on écrit la ligne
                            _emit(row)
                        else:
                            # Tous les juges vides (échec API) : la ligne n'est
                            # PAS écrite, elle sera re-codée au prochain --resume.
                            skipped += 1
                except KeyboardInterrupt:
                    # Sans cette annulation, sortir du `with` déclenche un
                    # shutdown(wait=True) qui laisse la file ENTIÈRE se vider :
                    # le processus paraît figé, continue de payer des appels
                    # pendant des heures, et jette les lignes obtenues.
                    ex.shutdown(wait=False, cancel_futures=True)
                    raise
    except KeyboardInterrupt:
        # Ctrl-C : on perd au plus les arêtes déjà en vol (≤ max_workers), pas la
        # file entière. Les lignes déjà codées sont flushées ci-dessous, puis tri +
        # manifeste + stats sont écrits pour le partiel. On reprend ensuite avec
        # --resume (les arêtes déjà codées sont sautées).
        interrupted = True
        print("\n[link_coding] interruption (Ctrl-C) — %d arêtes codées, sauvegarde du "
              "partiel…" % len(rows), flush=True)
    finally:
        f.flush()
        f.close()

    # Réécriture TRIÉE (Source,Target) en fin de run complet, atomique (tmp+replace).
    # L'append de Phase B est en ordre d'achèvement ; un run interrompu laisse ce
    # partiel valide (rechargé par --resume). Le tri final ne s'applique qu'à un run
    # mené à terme.
    try:
        rows.sort(key=lambda r: (str(r.get(STRATUM_COL, "")), int(r[SRC_COL]), int(r[TGT_COL])))
        tmp = out_path + ".tmp"
        with open(tmp, "w", newline="", encoding="utf-8") as f2:
            w2 = csv.DictWriter(f2, fieldnames=header, quoting=csv.QUOTE_MINIMAL)
            w2.writeheader()
            w2.writerows(rows)
        os.replace(tmp, out_path)
    except Exception as exc:
        print("[link_coding] tri final ignoré (%s) — CSV en ordre d'achèvement" % exc)

    manifest = {
        "sprint": "recode-links 2026-07-07",
        "schema": "v2-46col-2026-09-12",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "frame_csv": csv_path, "frame_sha256": _sha256(csv_path) if csv_path else "",
        "seed": seed, "n_elim": n_elim, "n_ret": n_ret, "minrel": minrel,
        "n_eliminated": sum(1 for e in sample if str(e["weightbody"]) == "0"),
        "n_retained": sum(1 for e in sample if str(e["weightbody"]) == "1"),
        "judges": judges, "n_judges": len(judges),
        "calls": budget.calls, "max_calls": max_calls, "budget_stopped": budget_stopped,
        "interrupted": interrupted, "complete": not interrupted and not budget_stopped,
        "rows": len(rows), "misses_indet": misses,
        "skipped_empty": skipped,   # arêtes non écrites (tous juges vides = échec API)
        "reviews": sum(1 for r in rows if str(r["contested_axes"]) != "0"),   # 0/1/2 axes contestés
    }
    with open(out_path + ".manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    with open(out_path + ".stats.txt", "w", encoding="utf-8") as f:
        f.write(_stats_report(rows, sample, manifest))

    print("[link_coding] %d lignes écrites (%d INDET, %d vides ignorées, %d appels) → %s"
          % (len(rows), misses, skipped, budget.calls, out_path))
    if interrupted:
        print("[link_coding] PARTIEL sauvegardé — relance la MÊME commande avec --resume "
              "pour continuer (les arêtes déjà codées seront sautées).", flush=True)
    return len(rows)


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _stats_report(rows: List[dict], sample: List[dict], manifest: dict) -> str:
    n = len(rows)
    out = ["Recode-links stats — %d arêtes (seed=%s, %d juges)"
           % (n, manifest["seed"], manifest["n_judges"]),
           "frame SHA-256 : %s" % manifest["frame_sha256"],
           "appels LLM : %d (plafond %s%s)"
           % (manifest["calls"], manifest["max_calls"],
              ", INTERROMPU" if manifest["budget_stopped"] else ""),
           ""]
    by_stratum = Counter(r[STRATUM_COL] for r in rows)
    out.append("== strates (body_extraction_mwi) ==")
    for k, v in by_stratum.most_common():
        out.append("  %-12s %5d" % (k, v))
    out.append("\n== evidence_source ==")
    for k, v in Counter(r["evidence_source"] for r in rows).most_common():
        out.append("  %-8s %5d  (%.1f%%)" % (k, v, 100 * v / n if n else 0))
    out.append("\n== anchor_tag (top 15) ==")
    for k, v in Counter(r["anchor_tag"] for r in rows).most_common(15):
        out.append("  %-10s %5d" % (k or "∅", v))
    out.append("\n== rule_place_code (pré-codeur déterministe) ==")
    for k, v in Counter(r["rule_place_code"] for r in rows).most_common():
        out.append("  %-14s %5d" % (k or "∅", v))
    out.append("\n== panel_place_group (MACRO consensus) ==")
    for k in MACRO_CODES + ("NOMAJ", ""):
        v = sum(1 for r in rows if r["panel_place_group"] == k)
        if v:
            out.append("  %-10s %5d" % (k or "∅", v))
    out.append("\n== panel_cites (acte de citation, consensus) ==")
    for k, v in Counter(str(r["panel_cites"]) for r in rows).most_common():
        out.append("  %-8s %5d" % (k, v))
    # tableau joint 6×2 MACRO × CIT_ACT, par strate (charge = hors-diagonale)
    for stratum in ("eliminated", "retained"):
        sub = [r for r in rows if r[STRATUM_COL] == stratum]
        if not sub:
            continue
        out.append("\n== 6×2 panel_place_group × panel_cites — strate %s (n=%d) =="
                   % (stratum, len(sub)))
        out.append("  %-10s %6s %6s %6s" % ("MACRO", "cit=1", "cit=0", "autre"))
        for mac in MACRO_CODES:
            c1 = sum(1 for r in sub if r["panel_place_group"] == mac
                     and str(r["panel_cites"]) == "1")
            c0 = sum(1 for r in sub if r["panel_place_group"] == mac
                     and str(r["panel_cites"]) == "0")
            ca = sum(1 for r in sub if r["panel_place_group"] == mac
                     and str(r["panel_cites"]) not in ("0", "1"))
            if c1 or c0 or ca:
                out.append("  %-10s %6d %6d %6d" % (mac, c1, c0, ca))
    rev = sum(1 for r in rows if str(r["contested_axes"]) != "0")
    out.append("\ncontested_axes >=1 (routage humain) : %d (%.1f%%)  [1 axe: %d, 2 axes: %d]"
               % (rev, 100 * rev / n if n else 0,
                  sum(1 for r in rows if str(r["contested_axes"]) == "1"),
                  sum(1 for r in rows if str(r["contested_axes"]) == "2")))
    out.append("miss INDET : %d ; NOMAJ loc : %d ; NOMAJ cit : %d"
               % (manifest["misses_indet"],
                  sum(1 for r in rows if r["panel_place_code"] == "NOMAJ"),
                  sum(1 for r in rows if str(r["panel_cites"]) == "NOMAJ")))
    return "\n".join(out) + "\n"
