# Recette — sprint `body-links` (septembre 2026)

Branche `feat/body-links-2026-09`. Jeu de vérité `benchmarks/body_links/gold_v1.csv`
(sha256 `ad8260b9…`), corpus de banc `bench_corpus_v1.sqlite`, land `airegulation`.

---

## 1. Résultat

| | avant | après | cible |
|---|---|---|---|
| Précision (pondérée) | 0,8800 | **0,9162** ± 0,024 | ≥ 0,95 ✗ |
| Rappel (pondéré) | 0,8463 | **0,9210** ± 0,016 | ≥ 0,88 ✓ |
| Vrais positifs | 528 | 592 | |
| Faux positifs | 72 | 55 | |
| dont sommaires (`TOC`) | 27 | **2** | < 5 ✓ |

**Le GATE de rappel est franchi avec 4 points de marge. Celui de précision ne
l'est pas, et la § 4 montre qu'il n'était pas atteignable.**

### Progression ticket par ticket

| étape | précision | rappel | TP / FP / FN |
|---|---|---|---|
| étiquettes gelées (référence) | 0,8800 | 0,8463 | 528 / 72 / 131 |
| T0 — extracteur rejoué | 0,8812 | 0,8557 | 536 / 72 / 123 |
| T2 — jambe HTML + `favor_recall` | 0,8792 | **0,9249** | 595 / 82 / 64 |
| T3 — classification structurelle | **0,9162** | 0,9210 | 592 / 55 / 67 |
| T4 — profils d'export | 0,9162 | 0,9210 | neutre |
| T1′ — identité des nœuds | 0,9162 | 0,9210 | **neutre, prouvé** |

L'écart entre les étiquettes gelées et l'extracteur rejoué (+8 vrais positifs)
est la dérive entre le crawl de juillet et le code d'aujourd'hui, pas un gain.

---

## 2. Vérifications

| contrôle | résultat |
|---|---|
| `make test-basic` | **832 passés, 3 skippés**, 0 échec |
| `flake8` sur les fichiers du sprint | propre ; dette préexistante inchangée, fichier par fichier |
| `make bench-determinism` | deux graines de hachage → sorties identiques au bit près |
| Budget d'analyses HTML | 2 parses + 2 appels Trafilatura par page ; test dédié |
| Volume d'arêtes (garde Goodhart) | 7 779 estimées contre 7 442 gelées → **×1,045**, dans la bande [0,95 ; 1,30] ✓ |
| Migration 014 | idempotente, découverte après 013, testée sur base ancienne |
| Aucun LLM dans l'extraction | `body_links` n'importe ni `core`, ni `model`, ni `llm_openrouter` (vérifié par AST) |
| Aucune règle lexicale | allowlist de jetons lue sur l'AST **et déclarée dans le test** ; même page rejouée en japonais, verdicts identiques |

### Profils d'export

| profil | précision | rappel |
|---|---|---|
| `citation` (défaut) | 0,9162 | 0,9210 |
| `citation+reco` | 0,9162 | 0,9210 |
| `all` | 0,8792 | 0,9249 |

`all` retombe exactement sur l'état pré-T3 : la classification est la seule
chose qui sépare les deux, ce qui vaut contrôle de cohérence.

---

## 3. Corrections apportées à la carte de sprint

Cinq prémisses chiffrées du plan de sprint interne (non publié) étaient
fausses. Elles ont été re-mesurées avant d'écrire du code.

1. **Le rappel affiché était biaisé.** L'échantillon de codage est stratifié
   (600 retenus sur 7 442 ; 943 éliminés sur 8 559), à des taux différents. Le
   rappel doit être estimé par Horvitz-Thompson : **0,846 et non 0,801**. La
   cible était à 3,4 points, pas 8.
2. **Les « trois juges » sont trois LLM** (qwen3.7-max, gemini-3.1-flash-lite,
   minimax-m3 ; 20 311 appels). 36 lignes routées vers arbitrage humain,
   **aucune arbitrée**. Le κ de 0,74 est un accord inter-modèles.
3. **T1 n'apportait aucun rappel** : 0 des 131 pertes récupérable par fusion de
   nœuds, aucune variante d'URL parmi elles. L'échelle de résolution absorbe
   déjà ces divergences au barreau relâché. T1 est devenu un ticket de qualité
   de graphe, déplacé en avant-dernier, et il se ferme en prouvant sa neutralité.
4. **La cible de T4 n'existait pas.** Les 89 lignes `REF_BIB` sont toutes
   étiquetées `EDITORIAL ∧ cites=1` : les expulser aurait converti 64 citations
   authentiques en pertes et fait tomber le rappel de 0,92 à 0,76. T4 a été
   re-cadré, et les bibliographies restent dans le profil par défaut.
5. **Le levier de rappel n'était pas l'union markdown + HTML** (sur les pertes,
   l'ensemble markdown est inclus dans l'ensemble HTML : l'union n'apporte rien)
   mais **`favor_recall` sur la seule jambe HTML**.

Deux corrections mineures : le « bug `--limit` » n'existait pas (l'arithmétique
était juste, la sémantique fautive) ; et la base de référence était le mauvais
instantané (466 pages sources résolues sur 1 109, contre 1 109 sur 1 109 pour
celle du clone de recherche).

---

## 4. Pourquoi la précision plafonne

Trois passes de mesure indépendantes convergent.

| exclusion **parfaite** de… | précision atteinte |
|---|---|
| rien (état livré) | 0,9162 |
| recommandation | 0,9462 |
| recommandation + outils de référence + listings | 0,9610 |

**Même une règle de recommandation parfaite reste sous 0,95.** Et aucune règle
structurelle trouvée ne sépare utilement : le ratio de prose du conteneur
distingue bien en médiane (0,93 pour une citation contre 0,48 pour un bloc de
recommandation) mais les distributions se recouvrent, et sur toute la grille de
seuils **chaque faux positif retiré coûte environ une vraie citation**. La
meilleure combinaison (répétition de motif entre frères + ratio de prose +
nombre d'ancres) gagne 1,0 point de précision pour 0,5 de rappel, sous le seuil
d'admission de 2 points de F1 que le sprint s'était fixé. **Aucune règle `reco`
n'a donc été livrée.**

Enfin, sur les 55 faux positifs restants, **13 sont du bruit du jeu de vérité**
(9 indéterminés, 2 sans majorité, 2 éditoriaux jugés non-citants). Avec un gold
parfait, le plafond des cas nets serait 0,934. Le κ de 0,74 mord exactement où
la carte l'avait prévu : « au-delà de 0,95, l'écart mesuré est celui des juges
autant que celui de l'extracteur ».

**Recommandation.** Acter 0,916 avec les listes nominatives
(`bench_false_kept.csv`, `bench_missed.csv`), et renvoyer le durcissement des
seuils au **second jeu de vérité sur un land d'un autre genre** (décision D5) —
seul moyen honnête de distinguer une règle transférable d'un réglage sur
`airegulation`.

---

## 5. Deux échecs de règle instructifs

Le banc a invalidé mes deux premières formulations, et les deux corrections sont
gelées en tests.

1. **« N'importe quel ancêtre sectionnant »** exilait 10 citations authentiques :
   sur ces pages, tout l'article est enveloppé dans un `<header>` (gabarit qui
   s'en sert comme bandeau). Correctif : *un élément de sectionnement
   majoritairement fait de prose n'est pas une annexe*. 9 des 10 récupérées.
2. **La grille d'ancres mesurée sur le bloc** ne voyait rien : un sommaire
   enveloppe chaque entrée dans son propre `<p>`, donc le bloc porte une seule
   ancre pendant que le conteneur en porte 7 à 49. Mesurée sur le **conteneur**,
   les sommaires tombent de 27 à 2.

---

## 6. Ce qui reste à faire côté opérateur

Ces gestes touchent des données de production ; ils n'ont pas été exécutés.

1. **Sauvegarder la base** avant toute application :
   `cp data/mwi.db data/mwi.db.bak_$(date +%Y%m%d_%H%M%S)`.
   `_merge_one` supprime des `Expression` et le CASCADE emporte médias,
   paragraphes et contenus tagués, sans annulation possible.
2. **Trois dry-runs de décision** (D1 `path_casefold`, D2 trackers), qui
   produisent le mapping sans rien modifier — voir `--mapping-out` dans le
   README.
3. **`python mywi.py db migrate`** sur les bases existantes (migration 014).
4. **`land consolidate`** pour rétro-remplir `kind` sur un land déjà crawlé,
   puis réexporter.
5. Les consommateurs qui référencent des identifiants internes doivent
   **remapper** à partir du fichier `--mapping-out`.
