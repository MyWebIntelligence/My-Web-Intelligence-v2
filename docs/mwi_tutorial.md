# MyWebIntelligence — Un projet de recherche de A à Z

## Cartographier la controverse sur la régulation de l'intelligence artificielle

> **Pour qui ?** Chercheuses et chercheurs en SHS / SIC qui ont déjà installé MyWebIntelligence (MWI)
> et veulent dérouler **un vrai projet de recherche complet** : de la formulation de la requête
> jusqu'aux exports analysables dans Gephi, R ou Python.
>
> **Le contrat de ce tutoriel** : vous assistez à la production d'un corpus de A à Z — création du
> projet, vocabulaire, collecte des graines, crawl, normalisation, extraction du texte éditorial,
> qualification, nettoyage, enrichissements, et exports — avec **toutes les vérifications et tous
> les audits SQL** à chaque étape. Chaque commande de l'outil est couverte.
>
> **Ce que ce tutoriel n'est pas** : un tutoriel d'installation. MWI est supposé installé et
> fonctionnel (`settings.py` présent, base initialisée). Si ce n'est pas le cas, suivez d'abord
> `docs/mwi_tutorial_install.md`, puis revenez ici.
>
> **Combien de temps ?** Lecture : ~45 min. Exécution réelle du projet : de quelques heures
> (corpus pilote) à plusieurs jours (corpus complet, crawl profondeur 6).
>
> 📓 Ce document est la **version terminal** du notebook `docs/mwi_tutorial.ipynb` : même
> protocole, mêmes commandes, mêmes audits — tout se copie-colle dans un shell (bash ou zsh).

---

### Le fil rouge : l'étude « Does Extraction Level Matter? »

Ce tutoriel simule la phase empirique de l'article *Does Extraction Level Matter? A Comparative
Assessment of Page-Level and Body-Text-Level Hyperlink Networks for Controversy Mapping*
(`docs/Art1_Methods_v1.0.docx`, §4 Methods). Le design est un **corpus apparié** : un seul corpus
crawlé, traité par deux procédures d'extraction de liens — page entière (Procédure A) contre corps
de texte éditorial (Procédure B) — pour mesurer ce que change le niveau d'extraction dans la
cartographie d'une controverse.

Le terrain : **la controverse sur la régulation de l'IA dans le web anglophone** (AI Act européen,
Executive Order américain de 2023 et son abrogation, AI Action Summit de Paris 2025, code de
conduite GPAI, paquet Digital Omnibus…). Le corpus visé : **8 000 à 15 000 pages**, **400 à 800
entités web** après agrégation, crawl jusqu'à **profondeur 6**, à partir de **8 requêtes-graines**
organisées en 4 axes (2 requêtes par axe).

| Axe | Focalisation des requêtes | Acteurs attendus |
|---|---|---|
| 1. Régulation institutionnelle | Cadres statutaires et application (EU AI Act ; régulation fédérale et étatique US) | Institutions publiques, régulateurs, juristes |
| 2. Risques sociétaux | Sécurité, risque existentiel, discriminations algorithmiques | ONG, instituts de sécurité, académiques |
| 3. Gouvernance industrielle | Autorégulation, engagements volontaires, gouvernance des modèles de frontière | Entreprises, consortiums, fondations |
| 4. Propriété intellectuelle et droit | Contentieux copyright de l'IA générative, licences de données d'entraînement | Ayants droit, cabinets, tribunaux, éditeurs |

Ce tutoriel déroule **la première requête (Q1, axe 1 — EU AI Act)** de bout en bout. Les 7 autres
requêtes suivent exactement le même chemin (on montre comment les enchaîner en §4.6).

> ⚠️ Les chaînes de requêtes exactes de l'étude sont publiées dans les *supplementary materials*
> de l'article. Celles utilisées ici sont **illustratives** mais fidèles à l'axe visé.

---

### Table des matières

- [§0 — Conventions du tutoriel et amorçage du shell](#sec0)
- [§1 — Vérifications préalables](#sec1)
- [§2 — Créer le Land](#sec2)
- [§3 — Le dictionnaire du Land](#sec3)
- [§4 — Collecter les graines (requête Q1)](#sec4)
- [§5 — Le crawl](#sec5)
- [§6 — Normaliser les URLs](#sec6)
- [§7 — Extraire le texte éditorial (readable)](#sec7)
- [§8 — Qualifier et nettoyer le corpus](#sec8)
- [§9 — Domaines et heuristiques](#sec9)
- [§10 — Enrichissement SEO Rank](#sec10)
- [§11 — Analyse des médias](#sec11)
- [§12 — Consolidation](#sec12)
- [§13 — Embeddings et pseudolinks](#sec13)
- [§14 — Tags](#sec14)
- [§15 — Exporter le corpus](#sec15)
- [§16 — Bilan chiffré et reproductibilité](#sec16)
- [§17 — Récapitulatif A→Z et pièges connus](#sec17)

<a id="sec0"></a>
## §0 — Conventions du tutoriel et amorçage du shell

Trois types de blocs cohabitent ici :

1. **Blocs `bash` de commandes** — ils exécutent le CLI MyWebIntelligence (`python mywi.py …`).
   C'est la voie officielle : tout ce que fait MWI passe par là. Copiez-collez-les tels quels
   dans votre terminal.
2. **Blocs `bash` d'audit SQL** — après chaque étape du pipeline, on **vérifie** ce qui a été
   écrit en base avec le client `sqlite3` en ligne de commande (lecture seule, sortie en colonnes).
3. **Blocs « Sortie indicative »** — les volumes affichés correspondent aux ordres de grandeur
   attendus pour ce projet ; vos chiffres varieront selon la date d'exécution, les clés API
   configurées et l'état du web.

> 💡 **Décodage** : MWI stocke tout dans une base SQLite unique (`data/mwi.db` par défaut, mode
> WAL). L'auditer en SQL n'est pas un luxe : c'est la pratique qui distingue un corpus *décrit* d'un
> corpus *vérifié*. Chaque section de ce tutoriel se termine par un audit.

> ⚠️ **Prérequis du tutoriel** : le client `sqlite3` doit être disponible dans votre terminal
> (préinstallé sur macOS et la plupart des distributions Linux ; sinon `apt install sqlite3` /
> `brew install sqlite`). Aucune dépendance Python supplémentaire n'est requise.

Le bloc suivant se place à la racine du dépôt, lit `settings.py`, et définit les variables shell
utilisées par tous les autres blocs. **Exécutez-le en premier — et ré-exécutez-le dans chaque
nouvelle session de terminal** : toutes les autres commandes dépendent de `$LAND`, `$DATA` et
`$DB`.

```bash
# Sous zsh (défaut macOS) : autoriser les commentaires '#' en fin de ligne, comme bash
setopt interactive_comments 2>/dev/null || true

# Se placer à la racine du dépôt MWI (adaptez le chemin) et activer l'environnement virtuel
cd /chemin/vers/MyWebIntelligencePython
source .venv/bin/activate   # ou venv/bin/activate selon votre installation

# Le projet de recherche (fil rouge Art.1)
LAND="airegulation"

# Lire l'emplacement des données depuis settings.py (override possible via MYWI_DATA_DIR)
DATA=$(python -c "import os, settings; print(os.path.abspath(os.path.expanduser(os.environ.get('MYWI_DATA_DIR', settings.data_location))))")
DB="$DATA/mwi.db"

echo "Racine du dépôt : $(pwd)"
echo "Dossier données : $DATA"
echo "Base SQLite     : $DB $([ -f "$DB" ] && echo '(existe)' || echo '(absente — voir §1)')"
echo "Land du projet  : $LAND"
```

<a id="sec1"></a>
## §1 — Vérifications préalables

Avant de toucher au projet, on vérifie l'instrument. Quatre contrôles :

| Contrôle | Commande | Ce qu'on vérifie |
|---|---|---|
| Schéma de base à jour | `db migrate` | Les migrations 001…011 sont appliquées (idempotent) |
| Fournisseurs de recherche | `search check` | Quels moteurs sont configurés pour la collecte des graines |
| Chaîne embeddings | `embedding check` | Provider, FAISS, sentence-transformers, tables DB |
| Mercury Parser | `mercury-parser --version` | Requis par `land readable` (§7) |

> ⚠️ **Jamais `db setup` sur une base existante.** `db setup` est **destructif** : il supprime et
> recrée toutes les tables (il demande d'ailleurs de confirmer en tapant exactement `Y`
> majuscule). Sur une base qui contient déjà des corpus, la seule commande légitime est
> `db migrate`, idempotente et non destructive. Si vous partez d'une base vierge, exécutez une
> seule fois `python mywi.py db setup` dans un terminal, puis revenez ici.

```bash
# Mettre le schéma à niveau (idempotent — ne détruit rien)
python mywi.py db migrate
```

```bash
# Quels fournisseurs de recherche sont configurés ? (clé absente = fournisseur ignoré silencieusement)
python mywi.py search check
```

**Sortie indicative** :

```text
Provider          Configured
--------------------------------
searxng           yes
brave             yes
serper            no
serpapi           yes
tavily            no
```

> 💡 **Décodage** : le routeur multi-API n'exige aucune clé — une clé absente désactive
> silencieusement le fournisseur, sans jamais lever d'erreur. Pour ce projet, l'idéal
> méthodologique est d'avoir au moins **SearXNG** (auto-hébergé, gratuit, illimité) plus un
> fournisseur commercial pour la triangulation. Pour démarrer SearXNG :
> `cd docker/searxng && docker compose up -d` (instance locale sur le port 8888, voir
> `docs/searxng_setup.md`). On y revient en §4.

```bash
# La chaîne embeddings est-elle prête ? (provider, FAISS, sentence-transformers, tables)
python mywi.py embedding check
```

```bash
# Mercury Parser (npm) est requis par le pipeline readable (§7)
mercury-parser --version || echo "⚠️ mercury-parser introuvable — installez-le : sudo npm install -g @postlight/mercury-parser"
```

<a id="sec2"></a>
## §2 — Créer le Land

Le **Land** est l'unité de recherche centrale de MWI : une collection thématique d'URLs, de termes,
de pages crawlées et d'analyses, isolée des autres projets de la base. Trois décisions se prennent
**à la création**, et elles découlent directement du design de l'étude :

| Paramètre | Valeur ici | Justification méthodologique |
|---|---|---|
| `--name` | `airegulation` | Identifiant stable, sans espaces (réutilisé dans toutes les commandes) |
| `--lang` | `en` | Le terrain est le web **anglophone** : la langue du Land pilote le stemmer et le tokeniseur du score de pertinence (15 langues Snowball), et les pages détectées dans une autre langue verront leur pertinence forcée à 0 |
| `--fullhtml` | `TRUE` | **Non négociable pour ce design** : le corpus apparié exige de conserver le HTML brut de chaque page pour rejouer les deux procédures d'extraction *offline* sur les mêmes documents |

> 💡 **Décodage `--fullhtml`** : avec `--fullhtml=TRUE`, le HTML brut est stocké dans
> `expression.html` **avant toute extraction** — même si le parsing échoue, l'archive est
> conservée. C'est ce qui rendra possible (i) la Procédure A (extraction page entière, rejouée sur
> le HTML stocké), (ii) la Procédure B (extraction corps de texte), et (iii) l'export `htmldump`
> pour le dépôt de réplication. Coût : ~100 Ko par page, soit ~1 à 1,5 Go pour 12 000 pages
> (plafond par page : `settings.fullhtml_max_size_kb`, 5 Mo par défaut).

> ⚠️ Si un Land du même nom existe déjà (re-exécution du tutoriel), `land create` échouera sur la
> contrainte d'unicité — c'est normal, passez à la suite.

```bash
DESC="Controverse sur la régulation de l'IA dans le web anglophone (2023-2026) — corpus apparié pour la comparaison page-level vs body-text-level (Art.1, SSCR). Axes : régulation institutionnelle, risques sociétaux, gouvernance industrielle, propriété intellectuelle."

python mywi.py land create --name=$LAND --desc="$DESC" --lang=en --fullhtml=TRUE
```

**Sortie attendue** :

```text
Land "airegulation" created (fullhtml=enabled)
```

On vérifie immédiatement la fiche du Land :

```bash
python mywi.py land list --name=$LAND
```

```bash
# Audit SQL : la politique fullhtml est bien stockée au niveau du Land (1 = activée)
sqlite3 -header -column "$DB" "
SELECT id, name, lang, fullhtml, description
FROM land WHERE name = '$LAND';
"
```

<a id="sec3"></a>
## §3 — Le dictionnaire du Land

Le dictionnaire est le **vocabulaire de pertinence** du projet. À chaque page crawlée, MWI calcule :

```text
relevance = 10 × (occurrences des lemmes dans le titre) + 1 × (occurrences dans le texte)
```

La pertinence est forcée à **0** si la langue détectée de la page ne correspond pas à celle du Land
(`en` ici), ou si la gate LLM (§8) répond « non ». Ce score servira de filtre de qualification tout
au long du pipeline (`--minrel`).

> 💡 **Lemmatisation multilingue.** MWI lemmatise avec le stemmer Snowball **de la langue du
> Land** (15 langues : en, fr, de, es, it, pt, ru, ar…). Sur ce Land `en`, `regulation` et
> `regulations` se replient sur le même lemme (`regul`) — inutile d'énumérer les pluriels. Les
> variantes **dérivationnelles** restent en revanche distinctes (`regulatory` → `regulatori`) :
> listez-les explicitement. Pour un Land multilingue (`--lang=en,fr`), chaque terme est lemmatisé
> une fois **par langue** (colonne `word.lang`, migration 011) et le score utilise l'union des
> lemmes.
>
> ⚠️ **Land non francophone créé avant juin 2026 ?** Ses lemmes ont été calculés avec l'ancien
> stemmer français. Rattrapage en deux commandes : `python mywi.py db migrate` puis
> `python mywi.py land relemm --name=<land>` — idempotent, re-stemme le dictionnaire dans la
> bonne langue et recalcule la pertinence de tout le corpus.

Le vocabulaire ci-dessous opérationnalise la controverse telle que cadrée en §4.2 du document de
méthode : régulation institutionnelle, conformité, gouvernance, législation.

```bash
python mywi.py land addterm --land=$LAND --terms="artificial intelligence, AI act, AI regulation, regulation, regulations, regulatory, governance, compliance, enforcement, legislation, AI policy, AI safety"
```

```bash
# Audit SQL : termes et lemmes effectivement enregistrés dans le dictionnaire du Land
sqlite3 -header -column "$DB" "
SELECT w.id, w.term, w.lemma, w.lang
FROM word w
JOIN landdictionary ld ON ld.word_id = w.id
JOIN land l ON l.id = ld.land_id
WHERE l.name = '$LAND'
ORDER BY w.id;
"
```

> 💡 **Décodage** : `land addterm` recalcule **immédiatement** la pertinence de toutes les
> expressions existantes du Land. Maintenant (0 page), c'est instantané. Si vous ajoutez un terme
> après le crawl de 12 000 pages, attendez-vous à un recalcul de plusieurs minutes — c'est le prix
> de la cohérence du score sur tout le corpus. Lisez la colonne `lemma` : le stemmer
> **anglais** replie `regulation` et `regulations` sur le même lemme `regul` (les deux lignes sont
> donc redondantes — sans danger), tandis que `regulatory` garde son propre lemme `regulatori`.
> La colonne `lang` trace la langue de lemmatisation — c'est la clé logique `(term, lang)`
> introduite par la migration 011, qui permet les Lands multilingues.

<a id="sec4"></a>
## §4 — Collecter les graines (requête Q1)

Le document de méthode prévoit que les graines soient récupérées via plusieurs moteurs, **en
journalisant le moteur source de chaque URL** pour pouvoir tester les effets de sélection propres à
chaque index (les moteurs sont des *infomédiaires* dont le classement est lui-même un filtre
biaisé — Marres & Moats, 2015). MWI v2 offre trois voies complémentaires :

| Voie | Commande | Quand l'utiliser |
|---|---|---|
| **Routeur multi-API** (recommandé) | `search run` | Triangulation multi-moteurs, journalisation complète (`searchquery` + `searchresultlog`) |
| **SerpAPI legacy** | `land urlist` | Balayage temporel Google avec fenêtres datées (`--datestart`/`--dateend`) |
| **Graines manuelles** | `land addurl` | Sources de référence connues a priori |

### 4.1 — La requête Q1

Axe 1 (régulation institutionnelle), requête 1 : cadres statutaires et application de l'**EU AI
Act**. Version illustrative utilisée ici :

```text
"EU AI Act" enforcement implementation
```

### 4.2 — Démarrer SearXNG (fournisseur primaire, gratuit)

Si `search check` (§1) a montré `searxng : not configured`, démarrez l'instance locale :

```bash
# Instance SearXNG locale (Docker) — fournisseur primaire sans clé ni quota
( cd docker/searxng && docker compose up -d )
# Laisser quelques secondes au conteneur, puis re-vérifier
sleep 5 && python mywi.py search check
```

### 4.3 — Lancer la collecte multi-moteurs

`--strategy=parallel` interroge **tous** les fournisseurs configurés simultanément, fusionne et
déduplique par URL canonique : c'est la triangulation méthodologique du design. (`fallback`, la
stratégie par défaut, s'arrête au premier moteur qui répond — elle préserve les quotas mais ne
triangule pas.)

> 💡 `--limit=50` s'entend **par fournisseur** : avec 3 fournisseurs actifs en parallèle, on peut
> collecter jusqu'à ~150 URLs avant déduplication.
>
> 💡 Sans `--language`, `search run` hérite de la langue **primaire du Land** (`en` ici) — on le
> garde explicite dans ce tutoriel pour la lisibilité du protocole.

```bash
Q1='"EU AI Act" enforcement implementation'   # requête Q1 — axe 1, version illustrative

python mywi.py search run --land=$LAND --query="$Q1" --limit=50 --strategy=parallel --language=en
```

**Sortie indicative** :

```text
[search run] strategy=parallel providers=[searxng, brave, serpapi] language=en limit=50
[search run] 112 URLs from providers — 108 new in Land, 4 already present.
[search run] usage report:
  - searxng    calls=1 errors=0 status=ok quota=None
  - brave      calls=1 errors=0 status=ok quota=1000
  - serpapi    calls=1 errors=0 status=ok quota=100
```

### 4.4 — Vérifier ce qui a été journalisé

Chaque exécution de `search run` écrit une ligne `searchquery` (requête, stratégie, rapport d'usage
JSON par fournisseur) et une ligne `searchresultlog` par URL distincte (fournisseurs l'ayant
retournée, meilleur rang). C'est la matérialisation du principe « journaliser le moteur source de
chaque URL ».

```bash
# Vue CLI : requêtes passées et usage agrégé par fournisseur
python mywi.py search list --land=$LAND
python mywi.py search usage --land=$LAND
```

```bash
# Audit SQL 1 : les exécutions de recherche et leur rapport d'usage (reproductibilité)
sqlite3 -header -column "$DB" "
SELECT sq.id, sq.query, sq.strategy, sq.language,
       sq.num_requested, sq.num_collected, sq.created_at, sq.usage_report
FROM searchquery sq
JOIN land l ON l.id = sq.land_id
WHERE l.name = '$LAND'
ORDER BY sq.created_at;
"
```

```bash
# Audit SQL 2 : distribution des fournisseurs ayant retourné chaque URL
# ('searxng+brave' = URL retournée par les deux moteurs → recoupement inter-index)
sqlite3 -header -column "$DB" "
SELECT srl.providers, COUNT(*) AS urls, MIN(srl.rank_min) AS meilleur_rang
FROM searchresultlog srl
JOIN searchquery sq ON sq.id = srl.search_query_id
JOIN land l ON l.id = sq.land_id
WHERE l.name = '$LAND'
GROUP BY srl.providers
ORDER BY urls DESC;
"
```

> 💡 **Lecture critique** : les URLs retournées par **plusieurs** moteurs (`searxng+brave+serpapi`)
> sont les plus robustes au biais d'index ; celles retournées par un seul moteur documentent la
> singularité de cet index. Cette table est l'argument empirique qui répond à l'objection
> « votre corpus est un artefact de Google ».

### 4.5 — Variante datée : `land urlist` (SerpAPI legacy)

Pour un **monitoring temporel** (la séquence législative 2023-2026 est au cœur du terrain), la voie
legacy SerpAPI permet de balayer Google par fenêtres datées. Nécessite une clé SerpAPI —
cascade de résolution unifiée avec le routeur : env `SERPAPI_API_KEY` →
`settings.SERPAPI_API_KEY` → `settings.serpapi_api_key` (legacy) → env `MWI_SERPAPI_API_KEY`.
Sans `--lang`, la commande hérite de la langue primaire du Land.

> ⚠️ Le filtre temporel n'existe que pour `google` et `duckduckgo` (pas `bing`). La progression
> s'affiche automatiquement quand `--datestart` et `--dateend` sont fournis.

```bash
Q1_DATED='("EU AI Act" OR "Artificial Intelligence Act") (enforcement OR implementation)'

python mywi.py land urlist --name=$LAND --query="$Q1_DATED" --engine=google --lang=en --datestart=2023-06-01 --dateend=2026-05-31 --timestep=month --sleep=1.0
```

### 4.6 — Graines manuelles et montée en charge

Les sources de référence évidentes du terrain (le texte officiel de l'AI Act, la page de la
Commission européenne) méritent d'être ajoutées explicitement — elles ancrent le crawl :

```bash
SEEDS="https://artificialintelligenceact.eu/,https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai"

python mywi.py land addurl --land=$LAND --urls="$SEEDS"
# Variante fichier : une URL par ligne dans seeds_q1.txt, puis :
#   python mywi.py land addurl --land=airegulation --path=seeds_q1.txt
```

**Les 7 autres requêtes** suivent le même schéma — chacune produira sa propre ligne
`searchquery`, donc sa propre trace de provenance :

```bash
QUERIES=(
  '"AI Act" "general-purpose AI" code of practice obligations'   # Q2 — axe 1
  '"AI safety" existential risk regulation policy'               # Q3 — axe 2
  'algorithmic discrimination AI harms accountability'           # Q4 — axe 2
  'frontier model governance voluntary commitments'              # Q5 — axe 3
  'AI self-regulation industry standards governance'             # Q6 — axe 3
  'generative AI copyright lawsuit training data'                # Q7 — axe 4
  'AI training data licensing publishers rights'                 # Q8 — axe 4
)
for q in "${QUERIES[@]}"; do
  python mywi.py search run --land=$LAND --query="$q" --limit=50 --strategy=parallel --language=en
done
```

### 4.7 — Audit final de la couche de graines

```bash
# Combien de graines (depth=0), et d'où viennent-elles ?
sqlite3 -header -column "$DB" "
SELECT COUNT(*)                                            AS graines_depth0,
       COUNT(DISTINCT e.domain_id)                         AS domaines_distincts,
       SUM(CASE WHEN e.original_url IS NOT NULL THEN 1 ELSE 0 END) AS urls_normalisees_a_l_insertion
FROM expression e
JOIN land l ON l.id = e.land_id
WHERE l.name = '$LAND' AND e.depth = 0;
"
```

> 💡 **Décodage** : toute URL entrant dans MWI passe par le pipeline de **canonicalisation**
> (`mwi.url_normalizer`) dès l'insertion : suppression des ancres, déballage des liens Wayback,
> retrait des trackers (`utm_*`, `fbclid`, `gclid`…), tri des paramètres. Quand la transformation
> modifie l'URL, l'original est archivé dans `expression.original_url` — la provenance est
> auditable sans re-crawler. La normalisation *rétrospective* (sur les liens découverts pendant le
> crawl) arrive en §6.

<a id="sec5"></a>
## §5 — Le crawl

Le crawl télécharge chaque page, extrait métadonnées, liens (qui deviennent des expressions de
profondeur +1) et médias, calcule la pertinence, et — politique `fullhtml` oblige — archive le HTML
brut. MWI embarque une **cascade anti-blocage** : quand `aiohttp` se voit refuser la page
(`403`, `406`, `429`, `503`, `520`, `521`, `523`, `526`, erreur réseau — liste réglable via `settings.crawl_retry_status_codes`), il bascule automatiquement sur
`curl_cffi` (empreinte TLS Chrome, activé par défaut), puis `playwright` (navigateur réel,
opt-in via `settings.crawl_fallback_playwright`), puis l'archive Wayback.

Deux colonnes tracent cette mécanique, et il faut les lire **ensemble** :

| Colonne | Sémantique |
|---|---|
| `expression.http_status` | Le statut de la stratégie **qui a livré le HTML** (un 403 sauvé par curl_cffi devient `200`) |
| `expression.fetch_method` | La stratégie qui a livré : `aiohttp`, `curl_cffi`, `playwright`, `archive_org` |

Le signal « le serveur d'origine m'a bloqué » se retrouve donc avec `fetch_method != 'aiohttp'`.

### 5.1 — Crawl pilote

Toujours commencer par un pilote : 20 pages suffisent à vérifier que la chaîne complète
(réseau → extraction → scoring → stockage HTML) fonctionne avant d'engager des heures de crawl.

```bash
python mywi.py land crawl --name=$LAND --limit=20
```

**Sortie indicative** (le nombre d'erreurs dépend de l'état du web ; la première ligne, elle,
est déterministe) :

```text
Full HTML storage: ON (source: land default)
20 expressions processed (2 errors)
```

> 💡 **Décodage** : la première ligne confirme la politique HTML effective et sa source. Le Land a
> été créé avec `--fullhtml=TRUE`, le crawl en hérite (`source: land default`). Un
> `--fullhtml=FALSE` sur la ligne de commande aurait priorité (`source: CLI`). Quelques erreurs
> sont normales (sites morts, timeouts) — le crawl ne s'arrête jamais sur une page qui échoue.

### 5.2 — Crawl complet, par vagues de profondeur

Le design fixe une profondeur maximale de **6**. La boucle ci-dessous crawle vague par vague : la
vague `d` télécharge les pages de profondeur `d` et *crée* les expressions de profondeur `d+1`
(les liens découverts). S'arrêter après la vague 6 laisse les expressions de profondeur 7 non
crawlées — c'est le bornage voulu.

> ⚠️ **Durée** : sur un corpus qui atteint 8 000-15 000 pages, comptez plusieurs heures (réglage
> `settings.parallel_connections`). Lancez cette boucle en connaissance de cause — ou exécutez-la
> avec `nohup … | tee crawl.log` pour survivre à une déconnexion.

```bash
for d in 0 1 2 3 4 5 6; do          # profondeurs 0 à 6 incluses (design Art.1)
  echo ""
  echo "=== Vague de profondeur $d ==="
  python mywi.py land crawl --name=$LAND --depth=$d
done
```

### 5.3 — Audit de la collecte

`land list` donne la photographie d'ensemble — y compris la distribution des codes HTTP, des
méthodes de fetch et le volume de HTML archivé :

```bash
python mywi.py land list --name=$LAND
```

**Sortie indicative** (corpus complet, 8 requêtes, profondeur 6) :

```text
airegulation - (Jun 10 2026 14:30)
    Controverse sur la régulation de l'IA dans le web anglophone (2023-2026)...
    12 terms in land dictionary [artificial intelligence, ai act, ...]
    14620 expressions in land (1820 remaining to crawl)
    Status codes: 200: 10980 - 403: 820 - 404: 540 - ERR: 460
    Fetch methods: aiohttp: 9870 - curl_cffi: 980 - archive_org: 130
    Full HTML: policy=ON — 10920 expressions stored (1145.3 MB)
```

On passe aux audits SQL fins :

```bash
# Audit SQL 1 : distribution par profondeur — la morphologie du crawl
sqlite3 -header -column "$DB" "
SELECT e.depth,
       COUNT(*)                                              AS expressions,
       SUM(CASE WHEN e.fetched_at IS NOT NULL THEN 1 ELSE 0 END) AS crawlees,
       SUM(CASE WHEN e.http_status = '200'   THEN 1 ELSE 0 END)  AS http_200
FROM expression e
JOIN land l ON l.id = e.land_id
WHERE l.name = '$LAND'
GROUP BY e.depth
ORDER BY e.depth;
"
```

```bash
# Audit SQL 2 : croisement fetch_method × http_status — efficacité de la cascade
# (http_status est un VARCHAR : toujours comparer à des chaînes, '200' et non 200)
sqlite3 -header -column "$DB" "
SELECT e.fetch_method, e.http_status, COUNT(*) AS pages
FROM expression e
JOIN land l ON l.id = e.land_id
WHERE l.name = '$LAND' AND e.fetched_at IS NOT NULL
GROUP BY e.fetch_method, e.http_status
ORDER BY pages DESC;
"
```

```bash
# Audit SQL 3 : l'archive HTML brute — couverture et volume (exigence du corpus apparié)
sqlite3 -header -column "$DB" "
SELECT COUNT(*)                                                   AS pages_crawlees,
       SUM(CASE WHEN e.html IS NOT NULL THEN 1 ELSE 0 END)        AS html_archive,
       ROUND(COALESCE(SUM(LENGTH(e.html)), 0) / 1048576.0, 1)     AS volume_mb
FROM expression e
JOIN land l ON l.id = e.land_id
WHERE l.name = '$LAND' AND e.fetched_at IS NOT NULL;
"
```

> 💡 **Lecture critique** : les pages crawlées **sans** HTML archivé sont celles où toute la
> cascade a échoué (`raw_html=None`) — typiquement du Cloudflare Enterprise. Elles resteront dans
> le corpus avec leur statut d'origine (403…), mais ne pourront pas alimenter la comparaison
> appariée. Leur proportion est une statistique de validité à reporter dans l'article.

### 5.4 — Rattrapage ciblé : `--retry-status`

Les pages en `403`/`429` au premier passage méritent une seconde chance : `--retry-status` rejoue
la cascade complète sur ces statuts précis, **en ignorant** le filtre habituel « jamais crawlé »
(`fetched_at IS NULL`). Sur des corpus réels, curl_cffi récupère une large part des 403 initiaux.

```bash
python mywi.py land crawl --name=$LAND --retry-status=403,429
```

```bash
# Audit SQL 4 : qui reste réellement bloqué après rattrapage ?
# (fetch_method='aiohttp' + statut d'erreur = aucune stratégie de secours n'a livré)
sqlite3 -header -column "$DB" "
SELECT e.http_status, COUNT(*) AS pages_bloquees
FROM expression e
JOIN land l ON l.id = e.land_id
WHERE l.name = '$LAND' AND e.fetch_method = 'aiohttp'
  AND e.http_status IN ('403', '406', '429', '503')
GROUP BY e.http_status
ORDER BY pages_bloquees DESC;
"
```

> ⚠️ **Limite connue** : les sites sous Cloudflare Enterprise (NYT…) résistent à `curl_cffi`
> comme à Playwright (détection `navigator.webdriver`, réputation IP). C'est une limite
> d'instrument à documenter, pas à contourner. Si un site est crucial pour le corpus, l'option
> propre est le fournisseur Brave en §4 (`--providers=brave`) ou l'archive Wayback.

<a id="sec6"></a>
## §6 — Normaliser les URLs

Le crawl a inséré des milliers d'URLs découvertes dans les pages. Même avec la canonicalisation à
l'insertion, un corpus réel accumule des doublons : trackers, liens Wayback imbriqués, casse de
l'hôte — voire `http://` vs `https://` et `www.` vs nu, **si** vous activez les règles
correspondantes (`force_https`, `strip_www` : OFF par défaut dans `settings.url_normalization`,
car risquées sur un Land existant). Or le design compte des **entités web** : deux URLs pour la même
page faussent les comptes de nœuds et d'arêtes.

`land normalize` applique rétrospectivement les règles de `settings.url_normalization` et gère
deux cas pour chaque URL transformée :

- **Rename** : la forme canonique n'existe pas encore → mise à jour en place, original archivé
  dans `original_url` ;
- **Merge** : la forme canonique existe déjà → les liens (`expressionlink`) du doublon sont
  remappés vers l'expression canonique (déduplication des arêtes, suppression des boucles), puis
  le doublon est **supprimé** (cascade sur ses médias, paragraphes, tags).

> ⚠️ **Sauvegarde obligatoire avant toute opération qui supprime.** Le merge détruit des lignes.
> Règle d'or : on ne lance jamais `normalize` sans backup ni sans `--dry-run` préalable.

```bash
# 1) Sauvegarde de la base (horodatée)
cp "$DB" "$DB.bak_$(date +%Y%m%d_%H%M%S)"
ls -lh "$DB".bak_*
```

```bash
# 2) Aperçu sans modification — que ferait la normalisation ?
python mywi.py land normalize --name=$LAND --dry-run --verbose
```

**Sortie indicative** :

```text
Would renamed: 212, merged: 87
  Links remapped (incoming): 0
  Links dropped  (incoming): 0
  Links remapped (outgoing): 0
  Links dropped  (outgoing): 0
  Cascade-deleted Media: 0
  Cascade-deleted Paragraph: 0
  Cascade-deleted TaggedContent: 0
Run again without --dry-run to apply.
```

> 💡 En `--dry-run`, seuls `renamed`/`merged` sont estimés ; les compteurs de remapping et de
> cascade restent **structurellement à 0** — ils ne sont calculés que lors de l'application
> réelle, qui imprime alors les volumes effectifs. `--verbose` liste chaque RENAME/MERGE prévu.

Si l'aperçu est cohérent (pas de fusion aberrante), on applique :

```bash
# 3) Application réelle
python mywi.py land normalize --name=$LAND
# Variante : --reset-status remet http_status/fetched_at à NULL pour re-crawler les URLs renommées
```

```bash
# Audit SQL : provenance — combien d'URLs portent la trace d'une transformation ?
sqlite3 -header -column "$DB" "
SELECT COUNT(*)                                                  AS expressions,
       SUM(CASE WHEN e.original_url IS NOT NULL THEN 1 ELSE 0 END) AS avec_original_url
FROM expression e
JOIN land l ON l.id = e.land_id
WHERE l.name = '$LAND';
"
```

### 6.1 — Cas particulier : les domaines `web.archive.org`

Les pages sauvées par la stratégie Wayback peuvent s'être retrouvées rattachées au domaine
`web.archive.org` au lieu de leur domaine d'origine — ce qui fausserait l'agrégation par entité
web (§4.4 du document de méthode). `db fix_archive_domains` corrige ce rattachement (idempotent) :

```bash
# Aperçu d'abord (--dryrun est un vrai flag booléen ici), puis application
python mywi.py db fix_archive_domains --dryrun
python mywi.py db fix_archive_domains
```

<a id="sec7"></a>
## §7 — Extraire le texte éditorial (`readable`)

C'est **le cœur méthodologique de l'étude** : la Procédure B repose sur la séparation entre le
corps de texte éditorial et l'appareillage de la page (navigation, pieds de page, encarts,
publicité). Le pipeline `readable` de MWI :

1. si le HTML brut est archivé (`expression.html`, notre cas grâce à `--fullhtml`), extrait
   **localement** avec Trafilatura — pas de re-téléchargement, reproductibilité garantie (le même
   HTML donnera toujours le même texte) ;
2. sinon, appelle Mercury Parser (CLI npm) sur l'URL, avec retry et backoff ;
3. fusionne le résultat avec l'existant selon la stratégie `--merge` ;
4. extrait du markdown obtenu les **liens éditoriaux** (créés en `expressionlink`) et les médias ;
5. recalcule la pertinence.

| Stratégie `--merge` | Comportement |
|---|---|
| `smart_merge` (défaut) | Champ par champ : titre le plus informatif, contenu Mercury prioritaire, description la plus détaillée |
| `mercury_priority` | Mercury écrase systématiquement |
| `preserve_existing` | Ne touche jamais aux données existantes (strictement additif) |

```bash
python mywi.py land readable --name=$LAND --merge=smart_merge
```

**Sortie indicative** :

```text
🚀 Starting readable pipeline for land: airegulation
🔧 Merge strategy: smart_merge
🔄 Processing URL: https://artificialintelligenceact.eu/
...
✅ Completed processing 10980 expressions
✔️ Updated: 10410, Errors: 570, Skipped: 0
```

> 💡 Le recours au HTML stocké est **silencieux en console** (le message « Used stored HTML » part
> dans le logger au niveau INFO, invisible par défaut). Vérifiez-le plutôt indirectement : absence
> de trafic réseau pendant le traitement, et audit de couverture ci-dessous.

### 7.1 — Audit de couverture

```bash
# Audit SQL 1 : couverture readable et longueur moyenne du texte éditorial
sqlite3 -header -column "$DB" "
SELECT COUNT(*)                                                    AS pages_crawlees,
       SUM(CASE WHEN e.readable_at IS NOT NULL THEN 1 ELSE 0 END)  AS readable_ok,
       ROUND(AVG(LENGTH(e.readable)), 0)                           AS longueur_moyenne,
       SUM(CASE WHEN e.readable IS NULL OR LENGTH(e.readable) < 100 THEN 1 ELSE 0 END) AS vides_ou_quasi_vides
FROM expression e
JOIN land l ON l.id = e.land_id
WHERE l.name = '$LAND' AND e.fetched_at IS NOT NULL;
"
```

```bash
# Audit SQL 2 : le graphe de liens éditoriaux créé par l'extraction
sqlite3 -header -column "$DB" "
SELECT COUNT(*)                       AS liens_diriges,
       COUNT(DISTINCT el.source_id)   AS pages_citantes,
       COUNT(DISTINCT el.target_id)   AS pages_citees
FROM expressionlink el
JOIN expression s ON s.id = el.source_id
JOIN land l ON l.id = s.land_id
WHERE l.name = '$LAND';
"
```

### 7.2 — Le critère d'arrêt du design

Le document de méthode fixe une règle **documentée à l'avance** : *si moins de 3 000 pages portent
au moins un lien dans le corps de texte, les requêtes sont élargies et le crawl est rejoué.* C'est
maintenant qu'on la teste :

```bash
# Critère d'arrêt (§4.2 du document de méthode) : ≥ 3000 pages avec ≥ 1 lien sortant éditorial
n=$(sqlite3 "$DB" "
SELECT COUNT(DISTINCT el.source_id) AS pages_avec_lien_editorial
FROM expressionlink el
JOIN expression s ON s.id = el.source_id
JOIN land l ON l.id = s.land_id
WHERE l.name = '$LAND';
")
seuil=3000
echo "Pages avec au moins un lien éditorial : $n  (seuil : $seuil)"
if [ "$n" -ge "$seuil" ]; then
  echo "✅ critère SATISFAIT — la collecte peut être close"
else
  echo "❌ critère NON satisfait — élargir les requêtes (§4) et rejouer le crawl (§5)"
fi
```

> 💡 **Pourquoi ce critère est important** : il transforme une décision discrétionnaire (« le
> corpus est-il assez riche ? ») en règle falsifiable, annoncée avant la collecte. C'est ce genre
> de pré-engagement qui rend le protocole publiable et le corpus réutilisable.

<a id="sec8"></a>
## §8 — Qualifier et nettoyer le corpus

Le crawl ramène inévitablement du bruit : pages hors sujet aspirées par les liens, pages dans une
autre langue, pages vides. La qualification s'appuie sur trois instruments, du moins cher au plus
cher :

1. **Le score de pertinence lexical** (déjà calculé) — gratuit, transparent, mais grossier ;
2. **La gate LLM** (`land llm validate`, OpenRouter) — un verdict `oui`/`non` par page sur la base
   du texte éditorial ;
3. **La suppression contrôlée** (`land delete --maxrel`) — irréversible, donc en dernier.

### 8.1 — La photographie avant nettoyage

```bash
# Audit SQL 1 : distribution de la pertinence (pages crawlées)
sqlite3 -header -column "$DB" "
SELECT CASE
         WHEN e.relevance IS NULL THEN 'NULL (non scorée)'
         WHEN e.relevance = 0  THEN '0 (hors sujet / hors langue)'
         WHEN e.relevance BETWEEN 1 AND 9   THEN '1-9'
         WHEN e.relevance BETWEEN 10 AND 49 THEN '10-49'
         ELSE '50+'
       END                            AS tranche_pertinence,
       COUNT(*)                       AS pages
FROM expression e
JOIN land l ON l.id = e.land_id
WHERE l.name = '$LAND' AND e.fetched_at IS NOT NULL
GROUP BY tranche_pertinence
ORDER BY pages DESC;
"
```

```bash
# Audit SQL 2 : langues détectées — le corpus est-il bien anglophone ?
sqlite3 -header -column "$DB" "
SELECT COALESCE(e.lang, '(non détectée)') AS langue, COUNT(*) AS pages
FROM expression e
JOIN land l ON l.id = e.land_id
WHERE l.name = '$LAND' AND e.fetched_at IS NOT NULL
GROUP BY e.lang
ORDER BY pages DESC
LIMIT 10;
"
```

> 💡 **Rappel** : une page dont la langue détectée diffère de celle du Land (`en`) a sa
> pertinence **forcée à 0** — le filtre linguistique du design est donc déjà appliqué par
> construction dans le score.

### 8.2 — La gate LLM (optionnelle mais recommandée)

`land llm validate` envoie le texte éditorial à un modèle via OpenRouter qui répond « cette page
parle-t-elle réellement de la régulation de l'IA ? ». Le verdict est stocké dans
`expression.validllm` (`oui`/`non`) avec le modèle utilisé (`validmodel`) ; un `non` force la
pertinence à 0.

Prérequis dans `settings.py` : `openrouter_enabled=True`, `openrouter_api_key`,
`openrouter_model`. Seules les pages avec un `readable` d'au moins
`openrouter_readable_min_chars` caractères et sans verdict antérieur sont traitées
(`--force` re-soumet aussi les `non`, jamais les `oui`). Pour un Land non francophone comme
celui-ci, le prompt est rédigé **en anglais** (le verdict stocké reste `oui`/`non`).

```bash
# Pilote sur 200 pages d'abord — vérifier le verdict et le coût avant le passage complet
python mywi.py land llm validate --name=$LAND --limit=200
```

```bash
# Audit SQL : distribution des verdicts LLM
sqlite3 -header -column "$DB" "
SELECT COALESCE(e.validllm, '(non soumis)') AS verdict,
       e.validmodel                          AS modele,
       COUNT(*)                              AS pages
FROM expression e
JOIN land l ON l.id = e.land_id
WHERE l.name = '$LAND' AND e.fetched_at IS NOT NULL
GROUP BY e.validllm, e.validmodel
ORDER BY pages DESC;
"
```

### 8.3 — Le nettoyage contrôlé

`land delete --maxrel=1` supprime les expressions **crawlées** dont la pertinence est
**strictement inférieure à 1** — c'est-à-dire le bruit à pertinence 0 (hors sujet, hors langue,
verdict LLM négatif). Les pages jamais crawlées ne sont pas touchées.

> ⚠️ **Triple garde-fou avant de supprimer** :
> 1. la sauvegarde de §6 existe (sinon, refaites-en une) ;
> 2. l'aperçu SQL ci-dessous donne le périmètre exact de la suppression ;
> 3. la commande demande une confirmation : tapez exactement `Y` majuscule (tout le reste annule).
>    Ci-dessous, on pipe la confirmation — ne le faites qu'après avoir validé l'aperçu.

```bash
# Aperçu : combien de pages seraient supprimées ?
sqlite3 -header -column "$DB" "
SELECT COUNT(*) AS pages_a_supprimer
FROM expression e
JOIN land l ON l.id = e.land_id
WHERE l.name = '$LAND' AND e.fetched_at IS NOT NULL AND e.relevance < 1;
"
```

```bash
# Suppression effective (la confirmation 'Y' est pipée — exécution consciente uniquement !)
echo "Y" | python mywi.py land delete --name=$LAND --maxrel=1
```

```bash
# Contrôle post-suppression : il ne doit plus rester de pages crawlées à pertinence 0
sqlite3 -header -column "$DB" "
SELECT COUNT(*) AS pages_relevance_zero_restantes
FROM expression e
JOIN land l ON l.id = e.land_id
WHERE l.name = '$LAND' AND e.fetched_at IS NOT NULL AND e.relevance < 1;
"
```

> 💡 **Note de design** : dans l'étude Art.1, le corpus apparié doit rester *constant* entre les
> deux procédures d'extraction — le nettoyage définit donc le **corpus qualifié** une fois pour
> toutes, *avant* la construction des deux réseaux. Toute suppression ultérieure invaliderait la
> comparaison (les deux réseaux ne partageraient plus le même ensemble de nœuds).

<a id="sec9"></a>
## §9 — Domaines et heuristiques

L'agrégation au niveau **entité web** (§4.4 du document de méthode) repose sur la table `domain`.
Deux commandes l'entretiennent :

- `domain crawl` visite la page d'accueil de chaque domaine et en extrait titre, description,
  mots-clés (chaîne de secours : Trafilatura → Wayback → requests) ;
- `heuristic update` réapplique les règles `settings.heuristics` (regex de domaine) au
  rattachement expression → domaine.

> 💡 `domain crawl` est **global** (tous les domaines de la base, pas seulement ce Land) — c'est
> voulu : un domaine est une entité partagée entre projets.

```bash
python mywi.py domain crawl --limit=500
# Re-lancer avec --http=ERR pour rejouer TOUS les domaines en échec
# (matche ERR_TRAFI, ERR_ARCHIVE*, ERR_ALL_FAILED, ERR_PROCESS… + ARC_NO_HTML, REQ_NO_HTML, 000) ;
# un code précis reste possible en égalité stricte : --http=ERR_ALL_FAILED
```

```bash
# heuristic update affiche le nombre de réattributions (« 0 domain(s) updated » si rien à corriger)
python mywi.py heuristic update
```

```bash
# Audit SQL : les entités web du corpus — le « M » de l'article (cible : 400-800)
sqlite3 -header -column "$DB" "
SELECT d.name                                   AS domaine,
       COUNT(*)                                 AS pages,
       ROUND(AVG(e.relevance), 1)               AS pertinence_moyenne,
       MAX(d.title IS NOT NULL)                 AS metadonnees_ok
FROM expression e
JOIN domain d ON d.id = e.domain_id
JOIN land l ON l.id = e.land_id
WHERE l.name = '$LAND' AND e.fetched_at IS NOT NULL
GROUP BY d.name
ORDER BY pages DESC
LIMIT 20;
"
```

> 💡 **Lecture critique** : repérez ici les concentrations suspectes. Si un seul domaine
> (Wikipedia, un agrégateur) représente une part démesurée du corpus, c'est un biais de structure
> à documenter dans l'article — voire un candidat à l'exclusion motivée. Le nombre total de
> domaines distincts est l'estimation brute du **[M]** du papier (avant agrégation fine en
> entités web).

<a id="sec10"></a>
## §10 — Enrichissement SEO Rank

`land seorank` interroge l'API seo-rank.my-addr.com et stocke le JSON brut dans
`expression.seorank` : rang Moz, trafic estimé, backlinks, métriques Facebook. Ces variables
serviront d'attributs de nœuds dans les exports (colonnes `sr_*` ajoutées automatiquement) — utile
pour pondérer la visibilité des acteurs de la controverse.

Prérequis : `settings.seorank_api_key` ou `MWI_SEORANK_API_KEY` (sans clé, la commande s'arrête
immédiatement).

> 💡 **Filtres par défaut** : seules les pages `http_status=200`, de pertinence ≥ 1 et sans
> données `seorank` existantes sont traitées. Élargir avec `--http=all`, `--minrel=0`, `--force`.

```bash
# Pilote : les graines d'abord (depth=0), 100 pages
python mywi.py land seorank --name=$LAND --depth=0 --limit=100
```

```bash
# Passage complet (1 seconde par appel par défaut — compter ~3h pour 10 000 pages)
python mywi.py land seorank --name=$LAND
```

```bash
# Audit SQL : couverture et premier aperçu des métriques (JSON interrogé via json_extract)
sqlite3 -header -column "$DB" "
SELECT COUNT(*)                                                AS pages_eligibles,
       SUM(CASE WHEN e.seorank IS NOT NULL THEN 1 ELSE 0 END)  AS enrichies,
       ROUND(AVG(json_extract(e.seorank, '$.sr_rank')), 0)     AS sr_rank_moyen,
       ROUND(AVG(json_extract(e.seorank, '$.fb_shares')), 0)   AS fb_shares_moyen
FROM expression e
JOIN land l ON l.id = e.land_id
WHERE l.name = '$LAND' AND e.http_status = '200' AND e.relevance >= 1;
"
```

<a id="sec11"></a>
## §11 — Analyse des médias

Le crawl et le pipeline readable ont déjà **recensé** les médias (table `media` : URL + type).
`land medianalyse` les **télécharge et analyse** : dimensions, poids, format, couleurs dominantes,
EXIF, hash perceptuel (détection de doublons visuels).

> ⚠️ **Durée et volume** : l'analyse télécharge chaque fichier. Sur un corpus de 10 000 pages, le
> recensement peut dépasser 100 000 images — auditez le volume *avant* de lancer.
>
> 💡 **Filtres** : `--depth` et `--minrel` sont honorés — on peut restreindre l'analyse aux
> pages peu profondes et pertinentes, là où se joue la controverse. Les critères de conformité
> (dimensions, poids) viennent de `settings.py` (`media_min_width`, `media_min_height`,
> `media_max_file_size`) et sont surchargeables dans les verbes de maintenance (§11.1).

```bash
# Recensement avant analyse : combien de médias, de quels types ?
sqlite3 -header -column "$DB" "
SELECT m.type, COUNT(*) AS medias,
       SUM(CASE WHEN m.analyzed_at IS NOT NULL THEN 1 ELSE 0 END) AS deja_analyses
FROM media m
JOIN expression e ON e.id = m.expression_id
JOIN land l ON l.id = e.land_id
WHERE l.name = '$LAND'
GROUP BY m.type
ORDER BY medias DESC;
"
```

```bash
# --depth / --minrel restreignent le périmètre (ici : pages pertinentes uniquement)
python mywi.py land medianalyse --name=$LAND --minrel=1
```

```bash
# Audit SQL : résultats d'analyse — formats, dimensions, doublons visuels
sqlite3 -header -column "$DB" "
SELECT m.format,
       COUNT(*)                          AS images,
       ROUND(AVG(m.width), 0)            AS largeur_moy,
       ROUND(AVG(m.height), 0)           AS hauteur_moy,
       COUNT(*) - COUNT(DISTINCT m.image_hash) AS doublons_visuels
FROM media m
JOIN expression e ON e.id = m.expression_id
JOIN land l ON l.id = e.land_id
WHERE l.name = '$LAND' AND m.analyzed_at IS NOT NULL AND m.type = 'img'
GROUP BY m.format
ORDER BY images DESC;
"
```

### 11.1 — Maintenance du corpus média

Trois verbes outillent le contrôle qualité après l'analyse :

| Verbe | Effet | Garde-fou |
|---|---|---|
| `land media_stats` | Statistiques agrégées : formats, dimensions, tailles, doublons par hash perceptuel | Lecture seule |
| `land preview_deletion` | **Dry-run pur** : compte + 20 exemples de médias non conformes | Ne supprime jamais rien |
| `land reanalyze` | Re-analyse (jamais analysés / en erreur d'abord) ; `--suppress` supprime les non-conformes | Confirmation `Y` avant toute suppression |

Les seuils `--minwidth` / `--minheight` (pixels) et `--maxsize` (Mo) ont pour défauts les valeurs
de `settings.py` (`media_min_width`, `media_min_height`, `media_max_file_size`). Le flux
recommandé : `media_stats` (photographie) → `preview_deletion` (périmètre exact) → `reanalyze
--suppress` (action) — chaque étape valide la suivante.

```bash
# Statistiques agrégées du corpus média (lecture seule)
python mywi.py land media_stats --name=$LAND
```

```bash
# Dry-run pur : que supprimerait un filtre 200×200 px / 5 Mo ? (rien n'est supprimé)
python mywi.py land preview_deletion --name=$LAND --minwidth=200 --minheight=200 --maxsize=5
```

```bash
# Re-analyse des médias jamais analysés ou en erreur (sans suppression)
python mywi.py land reanalyze --name=$LAND --limit=500
# Variante destructive — supprime les non-conformes APRÈS confirmation pipée (périmètre validé en
# preview_deletion d'abord !) :
#   echo "Y" | python mywi.py land reanalyze --name=airegulation --suppress --minwidth=200 --minheight=200
```

<a id="sec12"></a>
## §12 — Consolidation

`land consolidate` reconstruit liens (`expressionlink`) et médias à partir du contenu stocké, et
recalcule la pertinence des pages déjà crawlées. À utiliser **après toute modification externe de
la base** — typiquement après une session de tagging dans MyWebClient, un import, ou une
suppression manuelle — pour garantir que le graphe reflète bien le contenu.

> 💡 Inutile de le lancer en routine : le pipeline normal (crawl → readable) maintient déjà ces
> structures. C'est un outil de réparation et de mise en cohérence.

```bash
python mywi.py land consolidate --name=$LAND --depth=0
# --depth limite aux pages de cette profondeur ; --limit borne le nombre de pages traitées
```

<a id="sec13"></a>
## §13 — Embeddings et pseudolinks

Au-delà du graphe hypertexte, MWI peut construire un **graphe sémantique** : chaque paragraphe du
texte éditorial est vectorisé, puis les paires de paragraphes proches (entre pages différentes)
deviennent des **pseudolinks**. Pour l'étude de la controverse, c'est la couche qui révèle les
proximités d'argumentaires que les hyperliens ne matérialisent pas (deux think tanks qui tiennent
le même discours sans jamais se citer).

Trois méthodes de similarité :

| Méthode | Usage | Paramètres clés |
|---|---|---|
| `cosine` | Exact, O(n²) — corpus ≤ ~50 000 paragraphes | `--threshold` |
| `cosine_lsh` | Approximation LSH — gros corpus | `--lshbits`, `--topk`, `--maxpairs` |
| `nli` | Relations logiques (implication +1 / neutre 0 / contradiction −1) via Cross-Encoder | `--backend=faiss\|bruteforce`, `--topk`, `--maxpairs` ; nécessite `requirements-ml.txt` |

Le provider d'embeddings se règle dans `settings.py` (`embed_provider` : `openai`, `mistral`,
`gemini`, `huggingface`, `ollama`, `http`… — et `fake` pour tester la chaîne hors ligne).

> ⚠️ Sans les extras ML installés, la méthode `nli` retombe sur un prédicteur **neutre**
> (`score=0`, `score_raw=0.5`) : les chiffres sortent mais ne veulent rien dire. Vérifiez avec
> `embedding check` (§1) avant d'interpréter.

```bash
# 1) Vectoriser les paragraphes du corpus qualifié
python mywi.py embedding generate --name=$LAND
```

```bash
# Audit SQL : paragraphes découpés et vecteurs générés
sqlite3 -header -column "$DB" "
SELECT COUNT(DISTINCT p.id)  AS paragraphes,
       COUNT(pe.id)          AS vecteurs,
       MAX(pe.model_name)    AS modele
FROM paragraph p
JOIN expression e ON e.id = p.expression_id
JOIN land l ON l.id = e.land_id
LEFT JOIN paragraph_embedding pe ON pe.paragraph_id = p.id
WHERE l.name = '$LAND';
"
```

```bash
# 2) Calcul des pseudolinks — cosinus exact (adapté à un corpus de cette taille)
python mywi.py embedding similarity --name=$LAND --method=cosine --threshold=0.85 --minrel=1
```

**Variantes**, selon la volumétrie et la question de recherche :

```bash
# Gros corpus (> 50 000 paragraphes) : LSH approché, plafonné
python mywi.py embedding similarity --name=airegulation --method=cosine_lsh \
    --threshold=0.85 --lshbits=20 --topk=15 --minrel=1 --maxpairs=5000000

# Relations logiques (accord/désaccord entre argumentaires) : NLI
python mywi.py embedding similarity --name=airegulation --method=nli \
    --backend=faiss --topk=50 --minrel=1 --maxpairs=2000000

# Tout remettre à zéro pour ce Land (paragraphes + embeddings + similarités)
# Demande de taper 'Y' avant suppression ; --force la saute (pour les scripts)
python mywi.py embedding reset --name=airegulation
```

```bash
# Audit SQL : pseudolinks par méthode et distribution des scores
sqlite3 -header -column "$DB" "
SELECT ps.method,
       COUNT(*)                   AS paires,
       ROUND(MIN(ps.score), 3)    AS score_min,
       ROUND(AVG(ps.score), 3)    AS score_moyen,
       ROUND(MAX(ps.score), 3)    AS score_max
FROM paragraph_similarity ps
JOIN paragraph p ON p.id = ps.source_paragraph_id
JOIN expression e ON e.id = p.expression_id
JOIN land l ON l.id = e.land_id
WHERE l.name = '$LAND'
GROUP BY ps.method;
"
```

<a id="sec14"></a>
## §14 — Tags

La couche de **codage qualitatif** : des tags hiérarchiques posés sur des extraits précis du texte
éditorial (table `taggedcontent`, ancrage au caractère près sur `expression.readable`). Dans le
protocole Art.1, c'est par cette couche que passe l'annotation des entités en 10 catégories
d'acteurs et en positions discursives (pro-régulation / pro-innovation / mixte / neutre) — réalisée
en double codage aveugle dans l'interface graphique **MyWebClient**, puis exportée ici.

MWI exporte deux vues :

- `matrix` — matrice de co-occurrence des tags (quels codes apparaissent ensemble) ;
- `content` — les extraits taggés eux-mêmes, un par ligne.

```bash
python mywi.py tag export --name=$LAND --type=matrix --minrel=1
python mywi.py tag export --name=$LAND --type=content --minrel=1
```

> 💡 Si aucun tag n'a encore été posé, la commande sort proprement : le CSV est écrit avec sa
> seule ligne d'en-tête et la console affiche `Successfully exported …` — ce n'est pas une
> erreur. Notez le motif de nommage distinct : `export_tags_<land>_<type>_<horodatage>.csv`
> (et non `export_land_*`). Le filtre `--minrel` s'applique aux
> **expressions porteuses** des extraits taggés, pas aux tags eux-mêmes.

<a id="sec15"></a>
## §15 — Exporter le corpus

L'export est l'interface entre MWI et l'écosystème d'analyse (Gephi, R, Python, NVivo). Tous les
fichiers sont écrits dans `settings.data_location` avec le motif
`export_land_<land>_<type>_<horodatage>.<ext>`.

| Type | Produit | Usage |
|---|---|---|
| `pagecsv` | CSV des pages (+ colonnes `sr_*` si SEO Rank) | Analyse tabulaire R/pandas |
| `fullpagecsv` | Idem + texte readable complet | Analyse textuelle |
| `pagegexf` | Graphe **pages** (GEXF) | Gephi — réseau de citations fin |
| `nodegexf` | Graphe **domaines** (GEXF) | Gephi — réseau d'entités web (le réseau B de l'étude !) |
| `nodecsv` | Nœuds domaines (CSV) | Tables d'entités |
| `nodelinkcsv` | 4 CSV : `*_pagesnodes`, `*_pageslinks`, `*_domainnodes`, `*_domainlinks` | Import igraph/networkx |
| `mediacsv` | Médias + attributs d'analyse | Études visuelles |
| `corpus` | Zip de fichiers texte (un par page, en-tête YAML) — lots de 1 000 | Réplication, archives |
| `htmldump` | Zip du HTML brut (`<id>.html` + `manifest.csv`) | **Le matériau de la Procédure A** |
| `pseudolinks` | Paires de paragraphes similaires | Graphe sémantique |
| `pseudolinkspage` | Pseudolinks agrégés page↔page | Graphe sémantique (pages) |
| `pseudolinksdomain` | Pseudolinks agrégés domaine↔domaine | Graphe sémantique (entités) |

> ⚠️ **Deux pièges d'export** : (1) le filtre de pertinence par défaut est `--minrel=1` — les
> pages à pertinence 0 sont silencieusement exclues ; passez `--minrel=0` pour tout exporter.
> (2) Les exports `pseudolinks*` produisent un fichier au contenu CSV **sans extension** — c'est
> le comportement actuel, le chemin exact est affiché par la commande.

```bash
# Les quatre exports pivots de l'étude
python mywi.py land export --name=$LAND --type=pagecsv  --minrel=1
python mywi.py land export --name=$LAND --type=nodegexf --minrel=1
python mywi.py land export --name=$LAND --type=corpus   --minrel=1
python mywi.py land export --name=$LAND --type=htmldump --minrel=1
```

```bash
# Le reste de la panoplie, en boucle
for t in fullpagecsv nodecsv pagegexf mediacsv nodelinkcsv pseudolinks pseudolinkspage pseudolinksdomain; do
  python mywi.py land export --name=$LAND --type=$t --minrel=1
done
```

```bash
# Inventaire des fichiers produits
ls -lh "$DATA"/export_land_${LAND}_*
```

```bash
# Aperçu du pagecsv le plus récent — premier contact avec les données exportées
last=$(ls -t "$DATA"/export_land_${LAND}_pagecsv_*.csv 2>/dev/null | head -1)
if [ -n "$last" ]; then
  echo "$last : $(($(wc -l < "$last") - 1)) pages"
  head -3 "$last"
else
  echo "Aucun pagecsv trouvé — l'export a-t-il tourné ?"
fi
```

> 💡 **Vers la suite de l'étude** : `htmldump` fournit le HTML brut sur lequel la **Procédure A**
> (extraction page entière, type `LxmlLinkExtractor`) sera rejouée hors MWI ; les
> `expressionlink` exportés via `nodelinkcsv`/`nodegexf` matérialisent la **Procédure B**
> (liens du corps de texte). Les deux réseaux, projetés sur le même ensemble d'entités, sont
> exactement le dispositif apparié décrit en §4.3-4.4 du document de méthode.

<a id="sec16"></a>
## §16 — Bilan chiffré et reproductibilité

Dernière étape : produire **les chiffres qui rempliront les crochets `[N]`, `[M]`, `[dates]`** du
document de méthode, et vérifier que toutes les traces de reproductibilité sont en place.

```bash
# La fiche d'identité chiffrée du corpus — les valeurs de l'article
# (-line affiche une ligne par indicateur, façon fiche)
sqlite3 -line "$DB" "
SELECT
  (SELECT COUNT(*) FROM expression e JOIN land l ON l.id=e.land_id
    WHERE l.name = '$LAND' AND e.fetched_at IS NOT NULL)                          AS N_pages_crawlees,
  (SELECT COUNT(*) FROM expression e JOIN land l ON l.id=e.land_id
    WHERE l.name = '$LAND' AND e.http_status = '200' AND e.relevance >= 1)        AS N_pages_qualifiees,
  (SELECT COUNT(DISTINCT e.domain_id) FROM expression e JOIN land l ON l.id=e.land_id
    WHERE l.name = '$LAND' AND e.fetched_at IS NOT NULL)                          AS M_domaines,
  (SELECT MIN(DATE(e.fetched_at)) FROM expression e JOIN land l ON l.id=e.land_id
    WHERE l.name = '$LAND')                                                       AS date_debut_crawl,
  (SELECT MAX(DATE(e.fetched_at)) FROM expression e JOIN land l ON l.id=e.land_id
    WHERE l.name = '$LAND')                                                       AS date_fin_crawl,
  (SELECT COUNT(DISTINCT el.source_id) FROM expressionlink el
    JOIN expression s ON s.id = el.source_id JOIN land l ON l.id = s.land_id
    WHERE l.name = '$LAND')                                                       AS pages_avec_lien_editorial,
  (SELECT COUNT(*) FROM expressionlink el
    JOIN expression s ON s.id = el.source_id JOIN land l ON l.id = s.land_id
    WHERE l.name = '$LAND')                                                       AS liens_editoriaux,
  (SELECT SUM(CASE WHEN e.html IS NOT NULL THEN 1 ELSE 0 END)
    FROM expression e JOIN land l ON l.id=e.land_id
    WHERE l.name = '$LAND' AND e.fetched_at IS NOT NULL)                          AS pages_html_archive,
  (SELECT COUNT(*) FROM searchquery sq JOIN land l ON l.id=sq.land_id
    WHERE l.name = '$LAND')                                                       AS requetes_journalisees;
"
```

### La checklist de reproductibilité

| Exigence du protocole | Trace dans la base | Vérifiée en |
|---|---|---|
| Moteur source de chaque URL de graine | `searchquery.usage_report` + `searchresultlog.providers` | §4.4 |
| Paramètres et dates de chaque collecte | `searchquery` (requête, stratégie, langue, dates) | §4.4 |
| URL d'origine avant canonicalisation | `expression.original_url` | §4.7, §6 |
| Stratégie réseau ayant livré chaque page | `expression.fetch_method` (+ `http_status`) | §5.3 |
| HTML brut pour rejouer les extractions | `expression.html` (+ export `htmldump`) | §5.3, §15 |
| Critère d'arrêt documenté à l'avance | requête SQL §7.2 (≥ 3 000 pages avec lien éditorial) | §7.2 |
| Verdicts de qualification | `expression.relevance`, `validllm`, `validmodel` | §8 |
| Exports horodatés pour dépôt | `data/export_land_airegulation_*` → Zenodo (DOI réservé) | §15 |

Le corpus est prêt pour la phase d'analyse de l'article : construction des deux réseaux
(Procédures A et B), annotation des entités en double codage, puis les tests H1/H2/H3 (QAP,
MRQAP, tau de Kendall) — hors périmètre de MWI, dans R ou Python, sur les exports produits ici.

<a id="sec17"></a>
## §17 — Récapitulatif A→Z et pièges connus

### Le pipeline complet en une page

```bash
# §1 — Instrument
python mywi.py db migrate
python mywi.py search check
python mywi.py embedding check

# §2-3 — Projet
python mywi.py land create --name=airegulation --desc="..." --lang=en --fullhtml=TRUE
python mywi.py land addterm --land=airegulation --terms="artificial intelligence, AI act, ..."
python mywi.py land relemm --name=airegulation   # rattrapage : Land non-fr créé avant juin 2026

# §4 — Graines (×8 requêtes)
python mywi.py search run --land=airegulation --query='"EU AI Act" enforcement implementation' \
    --limit=50 --strategy=parallel --language=en
python mywi.py land urlist --name=airegulation --query='...' --engine=google --lang=en \
    --datestart=2023-06-01 --dateend=2026-05-31 --timestep=month
python mywi.py land addurl --land=airegulation --urls="https://...,https://..."
python mywi.py search list  --land=airegulation
python mywi.py search usage --land=airegulation

# §5 — Crawl (profondeur bornée à 6, puis rattrapage)
python mywi.py land crawl --name=airegulation --depth=0      # … répéter jusqu'à --depth=6
python mywi.py land crawl --name=airegulation --retry-status=403,429
python mywi.py land list  --name=airegulation

# §6 — Normalisation (backup + dry-run d'abord !)
python mywi.py land normalize --name=airegulation --dry-run --verbose
python mywi.py land normalize --name=airegulation
python mywi.py db fix_archive_domains

# §7 — Texte éditorial
python mywi.py land readable --name=airegulation --merge=smart_merge

# §8 — Qualification et nettoyage
python mywi.py land llm validate --name=airegulation --limit=200
python mywi.py land delete --name=airegulation --maxrel=1     # confirmation 'Y'

# §9-11 — Enrichissements
python mywi.py domain crawl --limit=500
python mywi.py heuristic update
python mywi.py land seorank --name=airegulation
python mywi.py land medianalyse --name=airegulation --minrel=1
python mywi.py land media_stats --name=airegulation
python mywi.py land preview_deletion --name=airegulation --minwidth=200 --minheight=200

# §12-13 — Consolidation et sémantique
python mywi.py land consolidate --name=airegulation --depth=0
python mywi.py embedding generate --name=airegulation
python mywi.py embedding similarity --name=airegulation --method=cosine --threshold=0.85 --minrel=1

# §14-15 — Exports
python mywi.py tag export --name=airegulation --type=matrix --minrel=1
python mywi.py land export --name=airegulation --type=pagecsv  --minrel=1
python mywi.py land export --name=airegulation --type=nodegexf --minrel=1
python mywi.py land export --name=airegulation --type=corpus   --minrel=1
python mywi.py land export --name=airegulation --type=htmldump --minrel=1
# (+ fullpagecsv, nodecsv, pagegexf, mediacsv, nodelinkcsv, pseudolinks, pseudolinkspage, pseudolinksdomain)
```

### Les pièges qui coûtent cher

| Piège | Parade |
|---|---|
| `db setup` sur une base existante | **Destructif.** Toujours `db migrate` |
| Confirmations interactives (`db setup`, `land delete`, `embedding reset`, `reanalyze --suppress`) | Taper exactement `Y` majuscule (`y`, `yes`, Entrée = annulation) — `--force` disponible sur `embedding reset` |
| `addterm`/`addurl` et `search *` utilisent `--land`, les autres verbes `--name` | Vérifier le flag avant de copier-coller |
| Pertinence forcée à 0 hors langue | Choisir `--lang` à la création, l'auditer en §8.1 |
| Land non-fr créé avant le stemming multilingue (juin 2026) | `db migrate` puis `land relemm --name=…` (§3) |
| Exports avec `--minrel=1` par défaut | Passer `--minrel=0` pour le corpus intégral |
| `land normalize` supprime des doublons | Backup + `--dry-run` systématiques |
| `mercury-parser` hors PATH | `land readable` échoue silencieusement page à page — tester en §1 |
| Extras ML absents | `nli` rend des scores neutres (0.5) sans erreur — `embedding check` |
| `--limit` de `search run` est *par fournisseur* | En `parallel`, le total peut atteindre n_fournisseurs × limit |

### Pour aller plus loin

- `docs/mwi_tutorial.ipynb` — la version Jupyter de ce tutoriel (mêmes étapes, audits en pandas) ;
- `docs/mwi_tutorial_install.md` — installation pas à pas (si un poste doit être monté) ;
- `docs/mwi_tutorial_crawl.md` — tutoriel corpus sur un terrain francophone (fil rouge « melenchon ») ;
- `docs/search_router.md` et `docs/searxng_setup.md` — le routeur multi-API en détail ;
- `.claude/rules/Pipelines.md` — référence interne de tous les pipelines ;
- `docs/Art1_Methods_v1.0.docx` — le document de méthode dont ce tutoriel est la phase empirique.

---

> ❓ **Vous bloquez ?** Ouvrez une issue sur le dépôt GitHub du projet en précisant : votre OS,
> la section du tutoriel, la commande exacte exécutée et la sortie complète (copier-coller).
