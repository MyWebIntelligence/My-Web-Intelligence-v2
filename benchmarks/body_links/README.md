# Jeu de vérité `body_links` — v1

Référence de mesure du sprint `body-links`. Le fichier `gold_v1.csv` est **figé** :
un changement de la fonction d'étiquetage produit un `gold_v2.csv`, jamais une
modification en place.

## Ce que mesure ce jeu

Une arête du réseau « corps de texte » (`ExpressionLink`) doit être retenue si et
seulement si le lien est **situé dans la zone éditoriale** de la page source **et**
constitue un **acte de citation** :

```
gold = 1  ⟺  place_group == 'EDITORIAL'  ∧  cites == '1'
```

La colonne `gold` est **matérialisée** dans le CSV pour que la fonction d'étiquetage
ne puisse pas dériver silencieusement entre deux exécutions du banc.

## Provenance

| | |
|---|---|
| Land | `airegulation` (20 930 pages `relevance ≥ 1`, 164 731 expressions) |
| Cadre d'échantillonnage | `export_land_airegulation_nodelinkcsv_20260706134804_pageslinksfullhtml.csv` |
| sha256 du cadre | `3f3879dbeabd343c36ee6ef22ff367a634f4f46c67e5ecb8bc00e5d94e359f64` |
| Export du cadre | 6 juillet 2026, `minrel=1`, réseau fermé (les deux extrémités sont des expressions du land) |
| Campagne de codage | `codage_3juges_minLinkedin.csv`, sha256 `945b9513d0dd3fa8f3a74841195b811ffafbfcb812344a8fab63db32f1999850` |
| Graine de tirage | 42 |
| sha256 de `gold_v1.csv` | `ad8260b930591aba498c0e52984b8a701de77b551e6b6949f688f112c27c4574` |
| Projection | `python scripts/build_gold_v1.py --coding CODING.csv --frame FRAME.csv` |

## Les juges sont trois modèles de langue

Le codage a été produit par **trois LLM** interrogés via OpenRouter, et non par des
juges humains :

- `qwen/qwen3.7-max`
- `google/gemini-3.1-flash-lite:nitro`
- `minimax/minimax-m3`

20 311 appels. Le κ de Fleiss de 0,74 sur l'axe citation est donc un **accord
inter-modèles**, pas un accord inter-annotateurs humains. 36 lignes ont été routées
vers un arbitrage humain ; **aucune n'a été arbitrée** — les colonnes `human_*` de la
campagne sont vides sur les 1 543 lignes. Le script de projection les honore malgré
tout, afin qu'une passe d'arbitrage ultérieure soit prise en compte sans changer le code.

> **Ces juges sont un instrument de mesure hors ligne.** Ils n'entrent jamais dans la
> chaîne d'extraction de MWI, ni au crawl, ni en consolidation, ni à l'export. Le banc
> lit ce CSV ; il n'appelle aucun modèle.

## Plan de sondage — indispensable au calcul du rappel

L'échantillon est **stratifié** sur la décision de MWI au moment du gel du cadre
(`weightbody` : 1 = arête retenue par l'extraction du corps, 0 = lien présent seulement
dans le HTML brut). Les deux strates ont été tirées à des **taux différents** :

| strate | échantillon | population du cadre | taux de sondage | poids `N_h / n_h` |
|---|---|---|---|---|
| `retained` | 600 | 7 442 | 0,0806 | 12,403333 |
| `eliminated` | 943 | 8 559 | 0,1102 | 9,076352 |

Conséquences, à respecter par tout consommateur :

- La **précision** ne mêle que la strate `retained` tant que l'extracteur ne prédit
  rien hors d'elle : les poids se simplifient et le comptage brut est non biaisé.
  Dès qu'un extracteur modifié retient des arêtes de la strate `eliminated`, elle doit
  être calculée comme un **ratio de totaux pondérés**.
- Le **rappel** mêle toujours les deux strates : il **doit** être pondéré. Le comptage
  brut (0,801 à la ligne de base) sous-estime le rappel réel (**0,846**).
- La strate est une propriété du **plan de sondage**, figée au 6 juillet 2026. Elle reste
  valide quand l'extracteur change : changer l'extracteur change la prédiction, jamais la
  strate. En revanche, **retirer un nouvel échantillon depuis l'ensemble retenu par un
  extracteur modifié annulerait tous les poids** et rendrait les mesures incomparables.

Les colonnes `stratum`, `stratum_sample_n` et `stratum_population_n` rendent le fichier
auto-suffisant : aucun consommateur n'a besoin de relire ce README ni le cadre pour
calculer les poids.

## Ligne de base (extracteur du commit `cd850ea`)

| | valeur |
|---|---|
| TP / FP / FN | 528 / 72 / 131 |
| Précision | **0,8800** (± 0,025 à 95 %) |
| Rappel brut | 0,8012 — *biaisé, pour référence seulement* |
| Rappel pondéré | **0,8463** |
| Population estimée | ~6 549 citations captées · ~1 189 manquées · ~893 faux retenus |

## Schéma — 13 colonnes

| colonne | contenu |
|---|---|
| `source_url`, `target_url` | clé de la ligne ; URL gelées au 6 juillet 2026. Les 1 543 couples sont uniques. |
| `place_group` | zone, consensus macro : `EDITORIAL` 662 · `NAV` 525 · `RECO` 292 · `OTHER` 36 · `ADS` 21 · vide 7 |
| `place_code` | code fin du panel (16 valeurs). Sans lui, les critères de fermeture des tickets de classification ne sont pas vérifiables. |
| `cites` | acte de citation, `0`/`1` |
| `gold` | dérivé, matérialisé (voir plus haut) |
| `place_agreement` | `3/3` 1210 · `2/3` 301 · `1/3` 31 · `2/2` 1 |
| `cites_agreement` | `3/3` 1301 · `2/3` 242 |
| `stratum`, `stratum_sample_n`, `stratum_population_n` | plan de sondage |
| `anchor_tag` | balise de l'ancre — permet la ventilation des pertes sans rouvrir le corpus |
| `external_target` | cible hors domaine source, **gelée à la date du codage** (les heuristiques de domaine ont bougé depuis le sprint heuristique : la recalculer donnerait un autre résultat) |

### Colonnes volontairement exclues

- `rule_place_*` — sortie d'un **pré-codeur déterministe**, c'est-à-dire une *prédiction*,
  pas une étiquette. La conserver inviterait à optimiser MWI pour ressembler à une autre
  heuristique plutôt qu'aux juges.
- `anchor_text` — seul champ qui permettrait d'écrire une règle **lexicale**, interdite par
  la contrainte de généralisation du sprint.
- `source_page_id`, `target_page_id` — identifiants internes, périmés dès la première fusion
  de nœuds.
- `judge{1,2,3}_*` — les votes bruts. Les garder inviterait à redériver un autre consensus,
  c'est-à-dire à changer le jeu de vérité sans changer le fichier.
- `in_body_mwi`, `count_in_body`, `count_in_page`, `evidence_source` — `evidence_source` est
  redondante avec la strate (1:1). **`in_body_mwi` contredit `body_extraction_mwi` sur 8
  lignes** (toutes `in_body_mwi=1`, `eliminated`, `count_in_body=0`) : garder les deux serait
  un piège permanent. La strate fait foi ; c'est elle qui définit le plan de sondage.
- `dom_path`, `context_text` — recalculables à volonté depuis le HTML du corpus de banc.
- `human_place_group`, `human_cites` — toujours vides (voir plus haut).

### Lignes conservées malgré leur ambiguïté

- **7 lignes à `place_group` vide** (toutes `place_code = NOMAJ`, toutes `cites = 1`) :
  conservées avec `gold = 0` — une zone indéterminée n'est pas une zone éditoriale démontrée.
  Les retirer changerait `stratum_sample_n` et donc **tous** les poids, pour 0,45 % de
  l'échantillon.
- **31 lignes `NOMAJ`** (pas de majorité sur le code fin, parfois une majorité sur le groupe) :
  conservées. Le banc les compte normalement mais affiche une ligne « contested = 31 (2,0 %) »,
  pour qu'aucun mouvement de métrique inférieur à 2 points ne soit lu comme un effet réel.

## Format

UTF-8 sans BOM · fins de ligne `LF` · `QUOTE_ALL` · trié par `(source_url, target_url)` en
points de code Unicode. Le tri est vérifiable sans outil :

```
LC_ALL=C sort -c <(tail -n +2 benchmarks/body_links/gold_v1.csv) && echo OK
```

## Limites de validité

1. **Rappel intra-cadre.** Le cadre est un réseau fermé : une citation vers une page que MWI
   n'a jamais ajoutée au corpus n'existe dans aucune strate. Le rappel mesuré n'est pas un
   rappel absolu.
2. **Hors échantillon.** Une arête prédite qui appartient au cadre sans avoir été tirée n'est
   ni vraie ni fausse : elle est non étiquetée. Le banc la compte à part.
3. **Erreur du jeu de vérité.** κ = 0,74, inter-modèles. Au-delà d'environ 0,95 de précision,
   l'écart mesuré est celui des juges autant que celui de l'extracteur : on lit alors les
   listes nominatives, pas les décimales.
4. **Un seul land, une seule thématique.** Les seuils calibrés ici doivent être confrontés à
   un second jeu de vérité sur un land d'un autre genre avant d'être figés.
