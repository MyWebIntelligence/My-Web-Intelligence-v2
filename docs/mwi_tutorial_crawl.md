# Tutoriel pas à pas — Constituer son premier corpus avec MWI

> **Prérequis** : MWI installé (voir `mwi_tutorial_install.md`). Vous savez ouvrir un terminal, entrer dans le dossier `mwi/`, et lancer `python mywi.py …`.
>
> **Le contrat** : on va construire un corpus thématique de A à Z, en s'appuyant sur **un vrai exemple** — le corpus *Mélenchon* (169 199 pages crawlées entre 2024 et 2025). Chaque commande est suivie de la sortie réelle qu'elle a produite, pour que vous sachiez à quoi vous attendre.
>
> **Combien de temps ?** Lecture : 30 min. Reproduction sur un petit corpus de test : 2 h (la majorité étant l'attente du crawl).

---

## Table des matières

0. [Le concept de *Land* (avant de coder)](#0-le-concept-de-land-avant-de-coder)
1. [Étape 1 — Créer son Land](#1-étape-1--créer-son-land)
2. [Étape 2 — Définir le vocabulaire (`addterm`)](#2-étape-2--définir-le-vocabulaire-addterm)
3. [Étape 3 — Donner des points de départ](#3-étape-3--donner-des-points-de-départ)
4. [Étape 4 — Crawler les URLs](#4-étape-4--crawler-les-urls)
5. [Étape 5 — Extraire le texte propre (Mercury Parser)](#5-étape-5--extraire-le-texte-propre-mercury-parser)
6. [Étape 6 — Enrichir le corpus (SEO Rank, médias)](#6-étape-6--enrichir-le-corpus-seo-rank-médias)
7. [Étape 7 — Exporter pour analyser ailleurs](#7-étape-7--exporter-pour-analyser-ailleurs)
8. [Étape 8 (avancé) — Liens sémantiques entre paragraphes](#8-étape-8-avancé--liens-sémantiques-entre-paragraphes)
9. [Inspecter sa base avec SQL](#9-inspecter-sa-base-avec-sql)
10. [Patterns récurrents et conseils de production](#10-patterns-récurrents-et-conseils-de-production)
11. [Récapitulatif](#11-récapitulatif)

---

## 0. Le concept de *Land* (avant de coder)

Avant tout, **comprenez le modèle mental**. Une fois qu'il est clair, les commandes deviennent évidentes.

### 0.1 — Qu'est-ce qu'un Land ?

Un **Land** est un *projet de recherche thématique*. C'est l'équivalent numérique d'un dossier d'enquête : il regroupe vos termes, vos URLs de départ, les pages collectées, les liens découverts, et les exports. Tout est rangé là.

> 💡 **Analogie** : un Land, c'est comme un classeur. Sur la couverture vous écrivez le sujet (`melenchon`), à l'intérieur vous mettez votre dictionnaire de mots-clés (les *termes*), des fiches (les *expressions*, c'est-à-dire les pages web), et un schéma des liens entre fiches. Vous pouvez avoir plusieurs classeurs en parallèle.

### 0.2 — Cycle de vie d'un Land

Un Land suit toujours les mêmes étapes :

```
1. land create   ──▶ créer le classeur vide
2. land addterm  ──▶ écrire le dictionnaire (mots-clés thématiques)
3. land addurl   ──▶ déposer les premières fiches (URLs de départ, dites "seeds")
   ou land urlist (si vous utilisez SerpAPI pour interroger Google)
4. land crawl    ──▶ aspirer le contenu de chaque page web référencée
5. land readable ──▶ nettoyer le texte (avec Mercury Parser)
6. land seorank  ──▶ enrichir avec des métriques externes (optionnel)
7. land export   ──▶ produire les fichiers d'analyse (CSV, GEXF…)
```

### 0.3 — Notre exemple fil rouge : le Land *Mélenchon*

Tout au long de ce tutoriel, on va dérouler le cycle de vie en s'appuyant sur **un vrai Land déjà constitué**, le corpus *Mélenchon*. Voici sa fiche signalétique :

| Champ | Valeur |
|---|---|
| `name` | `melenchon` |
| `lang` | `fr` |
| `description` | « analyse socio, politique sur le Web des pages qui abordent Jean-Luc Mélenchon, comme objet principal ou comme objet annexe du propos » |
| Nombre d'expressions | **169 199** |
| Profondeur de crawl | **0 → 3** |
| Pages avec HTTP 200 | 81 221 |
| Pages avec contenu lisible | 86 313 |
| Liens découverts | 205 265 |
| Médias référencés | 409 348 (408 927 images, 255 vidéos, 166 audios) |
| Domaines uniques | 7 868 |

À chaque étape on indiquera la commande utilisée, la sortie qu'elle a produite, et ce qu'on aurait pu faire autrement.

> 💡 Tous les chiffres sont vérifiables : à la fin du tutoriel (§9), on apprend à les requêter soi-même avec `sqlite3`.

---

## 1. Étape 1 — Créer son Land

**Pourquoi** : MWI a besoin d'un identifiant unique pour ranger les données. C'est aussi le moment de fixer la **langue** du corpus, car elle influence la lemmatisation des termes (voir §2.2).

### 1.1 — Commande générique

```bash
python mywi.py land create --name="MonLand" --desc="Description courte" [--lang=fr] [--fullhtml=TRUE]
```

| Paramètre | Rôle |
|---|---|
| `--name` | Identifiant unique. Évitez espaces et caractères exotiques. |
| `--desc` | Description en français lisible (apparaîtra dans `land list`). |
| `--lang` | Langue dominante du corpus. Défaut `fr`. |
| `--fullhtml` | Si `TRUE`, MWI archivera le HTML brut de chaque page (utile pour la reproductibilité, mais alourdit la base). |

### 1.2 — Notre exemple

```bash
python mywi.py land create \
  --name="melenchon" \
  --lang=fr \
  --desc="analyse socio, politique sur le Web des pages qui abordent Jean-Luc Mélenchon, comme objet principal ou comme objet annexe du propos"
```

**Sortie attendue** :

```
Land "melenchon" created (fullhtml=disabled)
```

> 💡 **Décodage du nom** : ASCII pur, sans accents (« melenchon » et non « mélenchon »). Avantage : la commande reste tapable sans clavier français, et toutes les futures références — `--name=melenchon` — fonctionnent partout.

### 1.3 — Vérifier

```bash
python mywi.py land list
```

Vous devez voir votre Land apparaître avec ses champs.

---

## 2. Étape 2 — Définir le vocabulaire (`addterm`)

**Pourquoi** : sans vocabulaire, MWI ne saurait pas évaluer la **pertinence** de chaque page crawlée. Il compare le texte de la page aux termes du Land et calcule un score.

### 2.1 — Comment se calcule la pertinence ?

> 💡 **Formule** (simplifiée) : `relevance = 10 × (occurrences dans le titre) + 1 × (occurrences dans le contenu)`. Le titre pèse 10 fois plus que le contenu, ce qui privilégie les pages dont le sujet principal est notre thème.

Une page sans aucun terme aura `relevance = 0`. Une page dont le titre cite 3 fois le terme et le contenu 100 fois aura `relevance = 130`.

### 2.2 — La lemmatisation : un automatisme important

Quand vous ajoutez un terme, MWI applique un **stemmer** (un découpeur de mot français) qui réduit chaque terme à sa racine :

```
"écologie", "écologique", "écologiste"   →   stem = "écologi"
"manifeste", "manifeste",  "manifestation" → stem = "manifest"
```

Conséquence : ajouter le mot « écologie » suffit pour reconnaître toutes ses formes dérivées dans les pages. Inutile de lister chaque flexion.

> ⚠️ **Le stemmer NE NEUTRALISE PAS les accents**. « melenchon » et « mélenchon » sont vus comme deux formes différentes. Pour les sujets francophones, il vaut souvent mieux **ajouter les deux variantes**.

### 2.3 — Commande générique

```bash
python mywi.py land addterm --land="MonLand" --terms="terme1, terme2, expression composée"
```

### 2.4 — Notre exemple

Le Land *Mélenchon* contient seulement **2 termes** :

```bash
python mywi.py land addterm --land="melenchon" --terms="melenchon, mélenchon"
```

**Vérification dans la base** (anticipons §9) :

```sql
SELECT w.id, w.term, w.lemma
FROM word w
JOIN landdictionary ld ON ld.word_id = w.id
WHERE ld.land_id = 1;
-- 1|melenchon|melenchon
-- 2|mélenchon|mélenchon
```

> 💡 **Leçon de cet exemple** : pour un sujet « personnage public », un dictionnaire minimal (2 variantes orthographiques d'un nom propre) suffit, car le nom de la personne apparaît rarement dans des pages qui ne lui sont pas dédiées. Pour un sujet plus diffus (« écologie urbaine »), il faut un dictionnaire plus riche : 5 à 15 termes pour calibrer la pertinence.

### 2.5 — Effet immédiat sur les expressions déjà présentes

Si vous ajoutez des termes **après** un crawl, MWI **recalcule automatiquement** la pertinence de toutes les expressions du Land. C'est instantané pour quelques milliers de pages, plus long pour quelques centaines de milliers.

---

## 3. Étape 3 — Donner des points de départ

Le Land est créé, le vocabulaire fixé. Il faut maintenant lui donner les premières URLs à explorer. Trois options :

| Option | Quand l'utiliser | Commande |
|---|---|---|
| Liste manuelle | Vous avez vous-même sélectionné des sources | `land addurl` |
| Fichier texte | Vous avez une longue liste préparée ailleurs | `land addurl --path=…` |
| Recherche Google automatisée | Vous voulez un démarrage par mot-clé large | `land urlist` (SerpAPI) |

### 3.1 — Option A : ajouter des URLs à la main (`land addurl`)

```bash
python mywi.py land addurl \
  --land="melenchon" \
  --urls="https://fr.wikipedia.org/wiki/Jean-Luc_Mélenchon, https://www.lemonde.fr/jean-luc-melenchon/"
```

> 💡 **Décodage** : les URLs sont séparées par des virgules. Chaque URL est insérée comme une expression à `depth=0` (un *seed*, c'est-à-dire un point de départ).

### 3.2 — Option B : ajouter depuis un fichier texte

Préparez un fichier `seeds.txt` avec une URL par ligne :

```
https://fr.wikipedia.org/wiki/Jean-Luc_Mélenchon
https://www.lemonde.fr/jean-luc-melenchon/
https://www.liberation.fr/checknews/?s=Mélenchon
```

Puis :

```bash
python mywi.py land addurl --land="melenchon" --path=seeds.txt
```

> ⚠️ **Avec Docker** : le fichier doit être à l'intérieur du conteneur, ou dans le dossier `data/` partagé.

### 3.3 — Option C : amorcer via SerpAPI (notre cas)

C'est la méthode utilisée pour le corpus *Mélenchon*. SerpAPI est un service qui interroge Google à votre place et renvoie les résultats sous forme structurée (JSON).

**Prérequis** : une clé API SerpAPI (`settings.serpapi_api_key` ou variable d'environnement `MWI_SERPAPI_API_KEY`).

**Commande typique** :

```bash
python mywi.py land urlist \
  --name="melenchon" \
  --query="(Jean-Luc Mélenchon) OR (France insoumise)" \
  --datestart=2022-04-01 \
  --dateend=2024-12-31 \
  --timestep=month
```

> 💡 **Décodage des paramètres** :
> - `--query` : requête Google (booléens `OR` et `AND` autorisés).
> - `--datestart`/`--dateend` : fenêtre temporelle. Indispensable pour un *monitoring* longitudinal.
> - `--timestep=month` : SerpAPI fera **une requête par mois** dans la fenêtre, ce qui multiplie les résultats sans dépasser la limite Google de ~100 résultats par requête.
> - Délai par défaut entre requêtes : 1 seconde (`--sleep=1.0`) pour respecter le *rate limit*.

**Résultat dans notre Land Mélenchon** : 12 978 URLs insérées comme seeds (à `depth=0`). Elles sont la racine de l'arbre de crawl.

```
=== Distribution finale par profondeur ===
depth=0  → 12 978 (seeds — issus de SerpAPI)
depth=1  → 68 845 (liens trouvés sur les seeds)
depth=2  → 41 866 (liens trouvés sur les pages depth=1)
depth=3  → 45 510 (liens trouvés sur les pages depth=2)
```

### 3.4 — Combien de seeds faut-il ?

| Taille du sujet | Seeds recommandés |
|---|---|
| Personnage public, événement précis | 50 à 500 |
| Thème journalistique large | 500 à 5 000 |
| Surveillance longitudinale | 5 000 à 20 000 (SerpAPI multi-fenêtres) |

Le corpus Mélenchon (~13 000 seeds) correspond à une surveillance longitudinale sur 30 mois.

---

## 4. Étape 4 — Crawler les URLs

**Pourquoi** : on a une liste d'URLs. Il faut maintenant aller chercher leur contenu (HTML), en extraire le titre, le texte, les liens et les médias, et calculer la pertinence.

### 4.1 — Ce qui se passe sous le capot

Pour chaque URL, MWI :

1. envoie une requête HTTP avec `aiohttp` (asynchrone, plusieurs URLs en parallèle) ;
2. si la requête échoue (404, timeout…), retente sur **archive.org** ;
3. nettoie le HTML pour en extraire le titre, le texte, et la liste des liens et médias ;
4. enregistre tout dans la base : `expression.title`, `expression.readable`, `expression.relevance`, plus une ligne par lien dans `expressionlink`, plus une ligne par média dans `media` ;
5. les URLs trouvées dans les pages sont insérées comme nouvelles expressions à `depth+1`, prêtes pour le prochain `crawl`.

### 4.2 — Commande générique

```bash
python mywi.py land crawl --name="MonLand" [--limit=N] [--depth=D] [--http=CODE] [--fullhtml=TRUE|FALSE]
```

| Paramètre | Effet |
|---|---|
| `--limit` | Nombre maximum d'URLs traitées dans cette session (utile pour des batches courts). |
| `--depth` | Ne traiter que les URLs **déjà connues** à cette profondeur. Sans `--depth`, toutes profondeurs sont mélangées. |
| `--http` | Re-crawler les pages qui avaient échoué avec ce code (ex. `--http=503`). |
| `--fullhtml` | Surcharge la politique d'archivage du Land pour cette session. |

### 4.3 — Notre exemple : le crawl du Land Mélenchon

Le crawl Mélenchon a probablement été lancé en **plusieurs vagues**, en bouclant sur la commande pour absorber les ~13 000 seeds par batches de quelques centaines :

```bash
# Vague 1 : crawler les seeds (depth=0) par paquets de 500
for i in {1..30}; do
  python mywi.py land crawl --name="melenchon" --depth=0 --limit=500
done
```

> 💡 **Pourquoi ce pattern boucle ?** Les très gros crawls sont fragiles : une coupure réseau ou un timeout peut interrompre la session. Lancer beaucoup de petits batches est plus résilient et permet de **suivre l'avancée** au fur et à mesure.

```bash
# Vague 2 : crawler les nouvelles URLs apparues à depth=1
for i in {1..150}; do
  python mywi.py land crawl --name="melenchon" --depth=1 --limit=500
done

# Vague 3 : depth=2, etc.
```

### 4.4 — Statistiques réelles du crawl Mélenchon

Une fois toutes les vagues terminées :

```
total expressions     : 169 199
expressions fetched   : 121 833 (72 %)
HTTP 200              :  81 221 (66 % des fetched)
HTTP 403 (interdit)   :  13 308
HTTP 404 (introuvable):   8 695
HTTP 429 (rate limit) :   3 487
HTTP 000 (échec réseau):  9 215
HTTP ERR              :   3 647
```

> 💡 **Ce qu'on apprend de ces chiffres** : sur un grand crawl de presse française, on perd ~30 % des pages à cause des *paywalls* (403), des suppressions (404), et de la lutte anti-bot (429). C'est normal. Le ratio 200/fetched = 66 % est **plutôt bon** — au-dessous de 50 %, il faut envisager `archive.org` comme source secondaire.

### 4.5 — Top 5 des domaines présents dans le corpus

Ce que le crawl a accumulé (top par nombre de pages) :

| Domaine | Pages |
|---|---|
| `fr-wikipedia-org.translate.goog` | 17 069 |
| `en.wikipedia.org` | 10 865 |
| `translate.google.com` | 9 954 |
| `fr.wikipedia.org` | 9 558 |
| `www.lefigaro.fr` | 5 666 |
| `www.lemonde.fr` | 5 622 |
| `argoul.com` | 3 242 |
| `www.liberation.fr` | 3 016 |

> 💡 **Lecture critique** : Wikipedia domine massivement (Fr + En + traductions = ~47 000 pages, soit 28 % du corpus). Pour une étude sociologique, c'est à la fois une force (riche en biographie et événements) et un biais (homogénéité éditoriale). Mentionnez-le dans la méthode.

### 4.6 — Re-crawler ce qui a échoué

Plus tard, vous voudrez peut-être re-tenter les pages qui ont échoué temporairement (429, timeouts) :

```bash
# Re-crawler ce qui était en 429 (rate limit dépassé)
python mywi.py land crawl --name="melenchon" --http=429 --limit=1000
```

---

## 5. Étape 5 — Extraire le texte propre (Mercury Parser)

Le crawl a sauvegardé un `readable` basique pour chaque page (extrait via BeautifulSoup, qui garde encore beaucoup de bruit). Pour des analyses textuelles sérieuses, il faut **Mercury Parser**, un extracteur spécialisé qui élimine les menus, publicités, *footers*, *etc.*

### 5.1 — Prérequis

Mercury Parser est un outil Node.js. Si vous êtes sur Docker, il est déjà inclus dans l'image. Sinon :

```bash
sudo npm install -g @postlight/mercury-parser
mercury-parser --version    # vérifier
```

### 5.2 — Commande générique

```bash
python mywi.py land readable --name="MonLand" [--limit=N] [--depth=D] [--merge=STRATEGY]
```

| Paramètre `--merge` | Comportement quand des données existent déjà |
|---|---|
| `smart_merge` *(défaut)* | Fusion intelligente : Mercury prioritaire pour le contenu, plus long pour le titre. |
| `mercury_priority` | Mercury écrase tout. À utiliser pour rebuilder un corpus. |
| `preserve_existing` | Mercury ne remplit que les champs vides. Conservateur. |

### 5.3 — Notre exemple

Pour Mélenchon, l'utilisateur a probablement procédé en deux temps : d'abord les *seeds*, puis les profondeurs supérieures.

```bash
# Mercury sur les seeds (depth=0)
python mywi.py land readable --name="melenchon" --depth=0 --limit=2000

# Puis depth=1, depth=2…
python mywi.py land readable --name="melenchon" --depth=1 --limit=10000
```

**Résultat** : `86 313` expressions ont reçu un `readable` propre (51 % du total — les pages restantes sont soit non-fetched, soit non-200, soit ont reçu un readable basique mais pas Mercury).

### 5.4 — Anatomie d'un `readable`

Un extrait de la page Wikipedia *Jean-Luc Mélenchon* (`expression.id=727`, longueur 735 136 caractères) :

```markdown
[![Page d'aide sur l'homonymie](.../Logo_disambig.svg)](https://fr.wikipedia.org/wiki/Aide:Homonymie)

Pour les articles homonymes, voir [Mélenchon](https://fr.wikipedia.org/wiki/M%C3%A9lenchon)
et [JLM](https://fr.wikipedia.org/wiki/JLM).

![Illustration.](https://upload.wikimedia.org/wikipedia/commons/thumb/e/e7/Jea…
```

Le format est du **Markdown** : titres en `#`, liens en `[texte](url)`, images en `![alt](url)`. C'est ce format qui permet à MWI :

- d'extraire les liens sortants → `expressionlink` ;
- d'extraire les médias → `media` ;
- de calculer la pertinence sur le texte propre.

### 5.5 — Le score de pertinence appliqué

Sur cette page Wikipedia, après extraction :

```
expression.relevance = 1729
```

C'est le **score le plus élevé du Land**. Ce qui est attendu : le titre contient « Jean-Luc Mélenchon » et le texte ~170 fois (cf. la formule §2.1).

### 5.6 — Statistiques typiques après readable

```
expressions avec readable_at non-NULL : 86 313
caractère moyen par readable          : ~12 000
ratio relevance>0 / readable          : ~50 %
```

Les pages avec `relevance=0` malgré `readable` complet sont souvent des **pages connexes** (ex. articles juridiques en rapport avec un événement, sans citer le nom). On les **garde** pour l'analyse de réseau (elles ont des liens utiles), mais on les **filtre** pour l'analyse textuelle.

---

## 6. Étape 6 — Enrichir le corpus (SEO Rank, médias)

Cette étape est **optionnelle**. Elle ajoute des couches d'information utiles pour l'analyse, sans modifier le contenu textuel.

### 6.1 — SEO Rank : métriques d'autorité

SEO Rank est un service externe ([seo-rank.my-addr.com](https://seo-rank.my-addr.com/)) qui retourne, pour chaque URL :

- `sr_rank` : score d'autorité globale (plus bas = plus autoritaire) ;
- `sr_traffic` : trafic mensuel estimé ;
- `sr_dlinks`, `sr_hlinks` : *backlinks* ;
- `fb_shares`, `fb_comments`, `fb_reac` : engagement Facebook.

**Prérequis** : `settings.seorank_api_key` ou `MWI_SEORANK_API_KEY`.

**Commande** :

```bash
python mywi.py land seorank --name="melenchon" --depth=0 --limit=100
```

**Sur Mélenchon** : 13 972 expressions ont reçu un payload SEO Rank. Exemple de ce qui est stocké dans `expression.seorank` (champ JSON brut) :

```json
{
  "sr_domain": "unknown", "sr_rank": "unknown", "sr_kwords": "unknown",
  "sr_traffic": "unknown", "sr_costs": "unknown",
  "sr_ulinks": "unknown", "sr_hlinks": "unknown", "sr_dlinks": "unknown",
  "fb_comments": 726, "fb_shares": 172, "fb_reac": 867
}
```

> 💡 **Lecture** : ici les champs SEO sont `unknown` (limite du plan API utilisé), mais les métriques Facebook fonctionnent. C'est typique : tous les enrichissements ne réussissent pas — gardez ce qui est utile, ignorez le reste.

### 6.2 — Analyse des médias

Le crawl a déjà recensé 409 348 médias (URLs et types) sans les analyser. Pour télécharger chaque image et calculer ses dimensions, hash perceptuel, couleurs dominantes :

```bash
python mywi.py land medianalyse --name="melenchon" --depth=2 --minrel=1
```

> ⚠️ **Lourd** : chaque média est téléchargé et analysé (Pillow + EXIF). Compter ~0,5 s par image, plus la bande passante. Sur Mélenchon (~410 000 médias), une analyse complète prendrait des dizaines d'heures. Filtrez avec `--minrel` et `--depth`.

Sur le Land Mélenchon, l'étape `medianalyse` n'a pas été lancée (`media.analyzed_at` est NULL pour les 409 348 lignes). Les médias sont donc connus comme URLs mais pas encore analysés en profondeur.

### 6.3 — Validation LLM (optionnel)

Pour un filtre de pertinence plus fin que le score d'occurrence, on peut demander à un LLM (via OpenRouter) si la page est *vraiment* pertinente :

```bash
python mywi.py land llm validate --name="melenchon" --limit=100
```

Cela écrit `expression.validllm = "oui"|"non"` et `expression.validmodel = "<slug du modèle>"`. Sur Mélenchon, cette étape n'a pas été lancée non plus.

---

## 7. Étape 7 — Exporter pour analyser ailleurs

MWI n'est pas un outil d'analyse statistique : c'est un outil de **collecte et de structuration**. L'analyse se fait dans R, Python (pandas), Gephi, *etc.*, sur des fichiers exportés.

### 7.1 — Les formats d'export

| Format | À quoi ça sert | Outil cible |
|---|---|---|
| `pagecsv` | Une ligne par page, avec métadonnées et SEO Rank | Excel, R, pandas |
| `fullpagecsv` | Idem mais avec le `readable` complet | Analyse textuelle |
| `pagegexf` | Graphe de pages (nœuds = pages, arêtes = liens) | Gephi |
| `nodegexf` | Graphe de domaines (nœuds = domaines) | Gephi |
| `nodelinkcsv` | 4 CSV : `pagesnodes`, `pageslinks`, `domainnodes`, `domainlinks` | Cytoscape, R/igraph |
| `mediacsv` | Une ligne par média | Analyse iconographique |
| `corpus` | ZIP de fichiers `.txt` (un par page) | Pré-traitement NLP, scikit-learn |

### 7.2 — Exporter notre corpus *Mélenchon*

```bash
# Toutes les pages, format CSV léger
python mywi.py land export --name="melenchon" --type=pagecsv --minrel=1

# Graphe complet (4 CSV) pour analyse réseau
python mywi.py land export --name="melenchon" --type=nodelinkcsv --minrel=1

# Corpus textuel (ZIP)
python mywi.py land export --name="melenchon" --type=corpus --minrel=1
```

> 💡 **Décodage de `--minrel=1`** : on filtre à `relevance ≥ 1` pour n'exporter que les pages réellement liées au sujet. Sur Mélenchon, ça réduit le corpus de 169 199 → environ 50 000 pages exportables — beaucoup plus maniable et thématiquement homogène.

### 7.3 — Où atterrissent les fichiers ?

Les exports sont écrits dans `data/lands/<land_id>/` avec un nom horodaté :

```
data/lands/1/export_land_melenchon_pagecsv_20251023_140530.csv
data/lands/1/export_land_melenchon_pagesnodes_20251023_140612.csv
data/lands/1/export_land_melenchon_pageslinks_20251023_140612.csv
data/lands/1/export_land_melenchon_domainnodes_20251023_140612.csv
data/lands/1/export_land_melenchon_domainlinks_20251023_140612.csv
```

> 💡 **Astuce reproductibilité** : versionnez ces exports (Git LFS, Zenodo) en accompagnement de votre publication. Le DOI rendra votre corpus citable.

### 7.4 — Aperçu d'un `pagecsv`

Les colonnes typiques :

```
id, url, title, description, lang, relevance, depth, http_status,
created_at, fetched_at, readable_at, validllm,
sr_rank, sr_traffic, fb_shares, fb_comments, fb_reac
```

Une ligne représente exactement une page web. Vous pouvez l'ouvrir dans Excel pour un coup d'œil, ou la charger dans R/pandas.

---

## 8. Étape 8 (avancé) — Liens sémantiques entre paragraphes

Cette section présente le pipeline le plus puissant de MWI : trouver des **paragraphes qui se ressemblent sémantiquement**, à travers tout le corpus. C'est avancé et coûteux ; passez-la si vous débutez.

### 8.1 — Le concept de pseudolink

Deux paragraphes peuvent dire la même chose avec des mots différents :

> Page A : « Mélenchon a obtenu 22% au premier tour. »  
> Page B : « Le candidat de la France insoumise réalise un score de 22 pour cent. »

Un humain voit qu'ils énoncent le même fait. MWI le mesure avec :

1. un **embedding** : chaque paragraphe → vecteur de 768 dimensions ;
2. une **similarité cosinus** ou un **modèle NLI** : compare les vecteurs et tranche.

Le résultat : un *pseudolink* entre les deux paragraphes, exporté en CSV.

### 8.2 — Pré-requis ML

```bash
python -m pip install -r requirements-ml.txt
python mywi.py embedding check
```

### 8.3 — Le pipeline complet

```bash
# 1) Vectoriser tous les paragraphes du Land
python mywi.py embedding generate --name="melenchon"

# 2) Calculer les similarités (méthode adaptée au volume)
python mywi.py embedding similarity \
  --name="melenchon" \
  --method=cosine_lsh \
  --threshold=0.88 \
  --lshbits=20 --topk=15 \
  --minrel=1 --maxpairs=5000000

# 3) Exporter
python mywi.py land export --name="melenchon" --type=pseudolinks
```

### 8.4 — Status sur le Land Mélenchon

Sur notre Land exemple, l'étape *embeddings* **n'a pas été lancée** : les tables `paragraph` et `paragraph_similarity` sont vides. C'est cohérent avec un corpus de 169 000 pages dont l'analyse sémantique fine demanderait plusieurs jours de calcul. Pour un corpus pilote de quelques milliers de pages, le pipeline tourne en moins d'une heure.

---

## 9. Inspecter sa base avec SQL

Tout est dans `data/mwi.db` (ou le nom que vous avez choisi). C'est un fichier SQLite que vous pouvez interroger directement avec `sqlite3` ou un client graphique (DB Browser for SQLite, TablePlus…).

### 9.1 — Ouvrir la base

```bash
sqlite3 data/mwi_melenchon.db
# Une fois dans le prompt :
# .tables           pour lister les tables
# .schema land      pour voir le schéma de la table land
# .quit             pour sortir
```

### 9.2 — Quelques requêtes utiles (testées sur le Land Mélenchon)

**Combien de pages par profondeur ?**

```sql
SELECT depth, COUNT(*) AS pages FROM expression GROUP BY depth ORDER BY depth;
-- 0 | 12 978
-- 1 | 68 845
-- 2 | 41 866
-- 3 | 45 510
```

**Top 10 des domaines les plus riches ?**

```sql
SELECT d.name, COUNT(e.id) AS pages
FROM expression e JOIN domain d ON d.id=e.domain_id
GROUP BY d.name ORDER BY pages DESC LIMIT 10;
```

**Distribution des HTTP status** (pour repérer un crawl en bonne santé) :

```sql
SELECT http_status, COUNT(*) FROM expression
WHERE fetched_at IS NOT NULL
GROUP BY http_status ORDER BY 2 DESC LIMIT 10;
```

**Page la plus pertinente du Land** :

```sql
SELECT id, url, title, relevance
FROM expression WHERE relevance > 0
ORDER BY relevance DESC LIMIT 5;
-- 727 | https://fr.wikipedia.org/wiki/Jean-Luc_M%C3%A9lenchon | Jean-Luc Mélenchon — Wikipédia | 1729
```

**Ego-réseau d'une page** (les liens sortants de la page Wikipedia FR) :

```sql
SELECT s.url AS source, t.url AS cible
FROM expressionlink el
JOIN expression s ON s.id = el.source_id
JOIN expression t ON t.id = el.target_id
WHERE el.source_id = 727
LIMIT 10;
```

**Champs JSON SEO Rank** (extraction d'une clé spécifique) :

```sql
SELECT id, url, json_extract(seorank, '$.fb_shares') AS shares
FROM expression WHERE seorank IS NOT NULL
ORDER BY shares DESC LIMIT 10;
```

> 💡 **Astuce** : tout le SQL ici est portable vers PostgreSQL si vous migrez votre base un jour (le projet a une feuille de route PostgreSQL — voir `.claude/project/POSTGREFeature.md`).

---

## 10. Patterns récurrents et conseils de production

### 10.1 — Crawler par batches plutôt qu'en une fois

```bash
# Ne pas faire :
python mywi.py land crawl --name="big" --limit=100000   # un seul gros batch fragile

# Préférer :
for i in {1..200}; do
  python mywi.py land crawl --name="big" --limit=500
done
```

### 10.2 — Toujours sauvegarder avant `db setup`

```bash
cp data/mwi.db data/mwi.db.bak_$(date +%Y%m%d_%H%M%S)
```

### 10.3 — Utiliser `db migrate` (et jamais `db setup`) sur une base existante

`db setup` est destructif. `db migrate` est idempotent et n'altère que le schéma.

```bash
python mywi.py db migrate
```

### 10.4 — Filtrer agressivement avant un export ou une analyse ML

```bash
# pagecsv allégé : seulement les pages pertinentes
python mywi.py land export --name="melenchon" --type=pagecsv --minrel=1

# Embeddings : limiter aux pages pertinentes pour ne pas vectoriser le bruit
python mywi.py embedding similarity --name="melenchon" --method=cosine_lsh --minrel=2
```

### 10.5 — Documenter ses paramètres dans un README de corpus

Pour la reproductibilité scientifique, écrivez **toujours** un fichier `README_corpus.md` qui mentionne :

- la version de MWI utilisée (`git rev-parse HEAD`) ;
- les commandes exactes lancées (avec dates) ;
- la requête SerpAPI le cas échéant ;
- les filtres et seuils appliqués (`--minrel`, `--threshold`…).

C'est ce que demanderont les *reviewers* JOSS, et c'est ce qui rendra votre travail citable.

---

## 11. Récapitulatif

Le cycle complet, vu d'en haut, sur un corpus minimal :

```bash
# 1. Créer
python mywi.py land create --name="MonSujet" --desc="Ma question de recherche" --lang=fr

# 2. Vocabulaire
python mywi.py land addterm --land="MonSujet" --terms="motA, motB, expression composée"

# 3. Seeds (au choix)
python mywi.py land addurl --land="MonSujet" --path=seeds.txt
# OU
python mywi.py land urlist --name="MonSujet" --query="..." --datestart=2024-01-01 --dateend=2024-12-31

# 4. Crawler par vagues
for i in {1..50}; do
  python mywi.py land crawl --name="MonSujet" --limit=200
done

# 5. Mercury (texte propre)
python mywi.py land readable --name="MonSujet"

# 6. Enrichir (optionnel)
python mywi.py land seorank --name="MonSujet" --minrel=1
python mywi.py land medianalyse --name="MonSujet" --minrel=1

# 7. Exporter
python mywi.py land export --name="MonSujet" --type=pagecsv --minrel=1
python mywi.py land export --name="MonSujet" --type=nodelinkcsv --minrel=1
python mywi.py land export --name="MonSujet" --type=corpus --minrel=1
```

### 11.1 — Les chiffres-clés du Land Mélenchon (référence)

| Métrique | Valeur |
|---|---|
| Land | `melenchon` (lang=`fr`) |
| Termes | 2 (`melenchon`, `mélenchon`) |
| Seeds (depth=0) | 12 978 |
| Profondeur max | 3 |
| Total expressions | 169 199 |
| HTTP 200 | 81 221 |
| Pages avec `readable` | 86 313 |
| Pages avec `seorank` | 13 972 |
| Liens (`expressionlink`) | 205 265 |
| Médias (`media`) | 409 348 |
| Domaines uniques | 7 868 |
| Page la plus pertinente | id 727, fr.wikipedia.org (relevance = 1729) |

### 11.2 — Que faire ensuite ?

- 📖 Approfondir les pipelines : voir `.claude/rules/Pipelines.md`.
- 🔬 Analyser dans R : utiliser `mwiR` ([github.com/MyWebIntelligence/mwiR](https://github.com/MyWebIntelligence/mwiR)).
- 🎨 Visualiser un graphe : importer le GEXF dans **Gephi**.
- 🤖 Embeddings : reprendre §8 sur un corpus pilote de quelques milliers de pages.

❓ **Vous bloquez ?** Ouvrez une *issue* sur [GitHub](https://github.com/MyWebIntelligence/mwi/issues) en précisant : votre OS, l'étape concernée, la commande tapée, la sortie complète (terminal + erreur), et la requête SQL si vous interrogez la base.
