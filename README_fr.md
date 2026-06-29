# My Web Intelligence (MyWI)

Version anglaise : [README.md](README.md)

MyWebIntelligence (MyWI) est un outil Python destiné aux équipes de recherche numérique. Il aide à constituer et analyser des corpus web, organisés par « lands » (projets thématiques). L’application collecte, nettoie et enrichit les pages, puis les stocke dans une base SQLite (mode WAL) facile à inspecter avec des outils comme [DB Browser for SQLite](https://sqlitebrowser.org/).

## Table des matières

- [Fonctionnalités](#fonctionnalités)
- [Tutoriels](#tutoriels)
- [Installation](#installation)
  - [Démarrage rapide : Docker Compose (recommandé)](#démarrage-rapide--docker-compose-recommandé)
  - [Docker manuel (avancé)](#docker-manuel-avancé)
  - [Installation locale](#installation-locale)
- [Scripts utiles](#scripts-utiles)
- [Utilisation](#utilisation)
  - [Notes générales](#notes-générales)
- [Gestion des lands](#gestion-des-lands)
  - [1. Créer un land](#1-créer-un-land)
  - [2. Lister les lands](#2-lister-les-lands)
  - [3. Ajouter des termes](#3-ajouter-des-termes)
  - [4. Ajouter des URLs](#4-ajouter-des-urls)
  - [5. Récupérer des URLs via SerpAPI](#5-récupérer-des-urls-via-serpapi)
  - [6. Routeur de recherche multi-API](#6-routeur-de-recherche-multi-api)
  - [7. Supprimer un land ou des expressions](#7-supprimer-un-land-ou-des-expressions)
- [Collecte de données](#collecte-de-données)
  - [1. Crawler les URLs du land](#1-crawler-les-urls-du-land)
  - [2. Extraire un contenu lisible (pipeline Mercury)](#2-extraire-un-contenu-lisible-pipeline-mercury)
  - [3. Capturer les métriques SEO Rank](#3-capturer-les-métriques-seo-rank)
  - [4. Analyse médias](#4-analyse-médias)
  - [5. Crawl des domaines](#5-crawl-des-domaines)
- [Exports](#exports)
  - [1. Exporter un land](#1-exporter-un-land)
  - [2. Exporter les tags](#2-exporter-les-tags)
- [Mettre à jour les domaines depuis les heuristiques](#mettre-à-jour-les-domaines-depuis-les-heuristiques)
- [Pipeline de consolidation des lands](#pipeline-de-consolidation-des-lands)
- [Tests](#tests)
- [Embeddings & pseudolinks (guide utilisateur)](#embeddings--pseudolinks-guide-utilisateur)
  - [Objectif](#objectif)
  - [Pré-requis & installation](#pré-requis--installation)
  - [Modèles](#modèles)
  - [Paramètres (référence)](#paramètres-référence)
  - [Commandes & paramètres](#commandes--paramètres)
  - [Dépannage & précautions](#dépannage--précautions)
  - [Bonnes pratiques — performance](#bonnes-pratiques--performance)
  - [Choix des modèles et recours](#choix-des-modèles-et-recours)
  - [Progression & logs](#progression--logs)
  - [Méthodes de similarité](#méthodes-de-similarité)
  - [Choisir le backend ANN (FAISS)](#choisir-le-backend-ann-faiss)
  - [Similarité scalable (lands volumineux)](#similarité-scalable-lands-volumineux)
  - [Relations NLI (ANN + cross-encoder)](#relations-nli-ann--cross-encoder)
- [Dépannage & réparation](#dépannage--réparation)
  - [Garder le schéma de base à jour](#garder-le-schéma-de-base-à-jour)
  - [Récupération SQLite](#récupération-sqlite)
- [Pour les développeurs](#pour-les-développeurs)
  - [Architecture & flux internes](#architecture--flux-internes)
  - [Schéma de données (SQLite/Peewee)](#schéma-de-données-sqlitepeewee)
  - [Workflows principaux](#workflows-principaux)
  - [Notes d’implémentation](#notes-dimplémentation)
  - [Paramètres](#paramètres)
  - [Tests](#tests-1)
  - [Extension](#extension)
- [Licence](#licence)

## Fonctionnalités

- **Lands thématiques** : organisez URLs, lexiques et exports par projet.
- **Crawl résilient** : parallélisme contrôlé, retries, filtres HTTP, profondeur maîtrisée.
- **Extraction Mercury** : contenu lisible propre avec fusion configurable, enrichissement des métadonnées, recalcul de la pertinence.
- **Analyse médias** : dimensions, formats, couleurs dominantes, EXIF, hash perceptuel, score NSFW, erreurs traçables.
- **Routeur de recherche multi-API** : collecte de seeds depuis 5 fournisseurs (SearXNG auto-hébergé, Brave, Serper, SerpAPI, Tavily) avec stratégies `fallback` ou `parallel`, journal complet par requête pour la reproductibilité (JOSS). Voir [`docs/search_router.md`](docs/search_router.md).
- **Enrichissements** : SerpAPI pour préremplir les lands, SEO Rank pour les métriques, validation LLM (OpenRouter) en option.
- **Embeddings & pseudolinks** : vecteurs par paragraphe, similarité cosine (exacte ou LSH), pipeline NLI pour qualifier les relations logiques.
- **Exports multiples** : CSV, GEXF (pages/nœuds), corpus brut, médias, tags, pseudolinks.
- **Configuration centralisée** : `settings.py` + variables d’environnement pour adapter timeouts, clés API, heuristiques, providers ML.

## Tutoriels

- [`docs/mwi_tutorial.ipynb`](docs/mwi_tutorial.ipynb) — un projet de recherche complet de A à Z (création du Land, graines multi-moteurs, crawl borné en profondeur, normalisation d'URL, extraction readable, qualification, enrichissements, exports), avec un audit SQL après chaque étape. Nécessite `pip install jupyter pandas`.
- [`docs/mwi_tutorial_install.md`](docs/mwi_tutorial_install.md) — installation pas à pas.
- [`docs/mwi_tutorial_crawl.md`](docs/mwi_tutorial_crawl.md) — tutoriel corpus sur un terrain francophone.

---

# Installation

## Démarrage rapide : Docker Compose (recommandé)

**Commande unique**

```bash
./scripts/docker-compose-setup.sh [basic|api|llm]
```
Si vous omettez l’argument, le script utilise `basic`. Choisissez `api` pour configurer SerpAPI / SEO Rank / OpenRouter, ou `llm` pour inclure en plus les dépendances embeddings & NLI.

Sous Windows, exécutez ce script dans un terminal compatible Bash :
- Git Bash : `./scripts/docker-compose-setup.sh`
- PowerShell : `& "C:\Program Files\Git\bin\bash.exe" ./scripts/docker-compose-setup.sh`
- WSL : `wsl bash ./scripts/docker-compose-setup.sh`
Un double-clic sur le fichier `.sh` ne lance rien.

**Approche pas-à-pas**

1. Cloner le dépôt :
   ```bash
   git clone https://github.com/MyWebIntelligence/mwi.git
   cd mwi
   ```
2. Générer `.env` avec l’assistant interactif :
   ```bash
   python scripts/install-docker-compose.py
   ```
   (Sous Windows, `py -3 scripts/install-docker-compose.py` fonctionne aussi.)
3. Construire et démarrer le conteneur :
   ```bash
   docker compose up -d --build
   ```
4. Créer `settings.py` **depuis le conteneur** (à faire une seule fois par environnement) :
   ```bash
   docker compose exec mwi bash -lc "cp settings-example.py settings.py"
   ```
   Pour personnaliser la configuration, lancez plutôt :
   ```bash
   docker compose exec -it mwi python scripts/install-basic.py --output settings.py
   ```
5. Initialiser puis vérifier la base :
   ```bash
   docker compose exec mwi python mywi.py db setup
   docker compose exec mwi python mywi.py land list
   ```

> ⚠️ `settings.py` n’est jamais créé automatiquement dans le conteneur. Copiez `settings-example.py` (ou exécutez `python scripts/install-basic.py`) avant de lancer les commandes MyWI pour y renseigner chemins, clés API et options spécifiques.

**Où sont vos données ?**

- Machine hôte : `./data` (ou `HOST_DATA_DIR` défini dans `.env`).
- Conteneur : `/app/data` (via `MYWI_DATA_DIR`).

**Commandes de gestion**

```bash
docker compose up -d        # Démarrer
docker compose down         # Arrêter
docker compose logs mwi     # Voir les logs
docker compose exec mwi bash  # Entrer dans le conteneur
```

## Docker manuel (avancé)

```bash
# Construction
docker build -t mwi:latest .

# Exécution
docker run -dit --name mwi -v ~/mywi_data:/app/data mwi:latest

# Création de settings.py dans le conteneur (premier lancement)
docker exec mwi bash -lc "cp settings-example.py settings.py"
# Variante interactive :
# docker exec -it mwi python scripts/install-basic.py --output settings.py

# Initialisation
docker exec -it mwi python mywi.py db setup

# Utilisation
docker exec -it mwi python mywi.py land list
```

Gestion : `docker stop mwi` · `docker start mwi` · `docker rm mwi`.

## Installation locale

**Pré-requis** : [uv](https://docs.astral.sh/uv/) et git. uv provisionne
l'interpréteur Python (3.9+) et l'environnement virtuel pour vous — aucune
installation séparée de `python`/`pip`/`venv` n'est nécessaire.

Installer uv une seule fois :
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh        # macOS / Linux
# Windows (PowerShell) : powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
# ou : brew install uv   /   pipx install uv
```

**Mise en place rapide :**
```bash
# 1. Cloner
git clone https://github.com/MyWebIntelligence/mwi.git
cd mwi

# 2. Créer l'environnement depuis le lockfile (base + outils de dev).
#    uv lit .python-version (3.11) et télécharge cet interpréteur si absent.
uv sync

# 3. Configurer (assistant interactif)
uv run python scripts/install-basic.py

# 4. Initialiser la base
uv run python mywi.py db setup

# 5. Vérifier
uv run python mywi.py land list
```

`uv run <cmd>` s'exécute dans le venv du projet et le re-synchronise à la volée —
pas besoin de `source .venv/bin/activate` (vous pouvez toujours activer `.venv`
manuellement si vous préférez). Vous éditez les dépendances ? Modifiez
`pyproject.toml`, puis lancez `make lock` (ou `uv lock`) pour rafraîchir
`uv.lock` et le `requirements.txt` généré.

**Repli pip (sans uv).** Un `requirements.txt` épinglé, aligné sur le lockfile,
est toujours généré, donc le flux classique continue de fonctionner :
```bash
python3 -m venv .venv && source .venv/bin/activate   # Windows : .\.venv\Scripts\activate
python -m pip install -U pip
python -m pip install -r requirements.txt            # base (ajouter -r requirements-ml.txt pour le ML)
python scripts/install-basic.py
python mywi.py db setup
```

**Étapes optionnelles**

- APIs : `uv run python scripts/install-api.py`
- Embeddings/LLM : `uv sync --extra ml && uv run python scripts/install-llm.py`
- Médias dynamiques (Playwright) :
  - Navigateurs : `uv run python install_playwright.py`
  - Dépendances Debian/Ubuntu : `sudo apt-get install libnspr4 libnss3 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 libatspi2.0-0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libxkbcommon0 libasound2`
  - Docker : `docker compose exec mwi bash -lc "apt-get update && apt-get install -y <libs>"` puis `docker compose exec mwi python install_playwright.py`
  - **Note (sprint-403)** : Playwright est désormais aussi utilisé par la cascade
    fetch (`crawl_fallback_playwright=True` dans `settings.py`) et par
    `extract_dynamic_medias`. Les deux partagent un `BrowserPool` singleton —
    une seule instance Chromium par crawl quel que soit le nombre d'usages.

**Cascade fetch (sprint-403)** : `requirements.txt` inclut `curl_cffi>=0.7.0`.
Cette dépendance permet l'imitation TLS (Chrome 120) pour récupérer les pages
qui retournent `403`/`429` à `aiohttp` à cause de l'empreinte Cloudflare, sans
lancer de navigateur. Activée par défaut ; désactiver avec
`crawl_fallback_curl_cffi = False` dans `settings.py`.

**Problèmes NLTK (Windows/macOS)**

```bash
uv run python -m nltk.downloader punkt punkt_tab
# En cas d’erreur SSL : uv pip install certifi
```

## Scripts utiles

**Démarrage express**
- `scripts/docker-compose-setup.sh` — bootstrap complet Docker (crée/backup `.env`, lance l’assistant, build, démarre, initialise la base, tests optionnels). `./scripts/docker-compose-setup.sh [basic|api|llm]`.

**Assistants interactifs**
- `scripts/install-docker-compose.py` — génère `.env` pour Compose (fuseau horaire, mapping dossier hôte ↔ `/app/data`, flags Playwright/ML, clés SerpAPI/SEO Rank/OpenRouter, paramètres embeddings/NLI). `python scripts/install-docker-compose.py [--level basic|api|llm] [--output .env]`.
- `scripts/install-basic.py` — produit un `settings.py` minimal (stockage, timeouts, parallélisme, user agent, médias dynamiques, analyse médias, heuristiques). `python scripts/install-basic.py [--output settings.py]`.
- `scripts/install-api.py` — enregistre les clés SerpAPI / SEO Rank / OpenRouter dans `settings.py` (avec fallback via variables d’environnement). `python scripts/install-api.py [--output settings.py]`.
- `scripts/install-llm.py` — configure provider d’embeddings, modèles/backends NLI, paramètres de retry/batching (vérifie les dépendances ML). `python scripts/install-llm.py [--output settings.py]`.

**Diagnostics & reprise**
- `scripts/test-apis.py` — teste SerpAPI, SEO Rank, OpenRouter (`--serpapi`, `--seorank`, `--openrouter`, `--all`, `-v` pour le détail). `python scripts/test-apis.py ...`.
- `scripts/sqlite_recover.sh` — réparation SQLite non destructive (voir [Récupération SQLite](#récupération-sqlite)). `scripts/sqlite_recover.sh [INPUT_DB] [OUTPUT_DB]`.

**Utilitaires**
- `scripts/install-nltk.py` — télécharge `punkt` et `punkt_tab` pour NLTK. `python scripts/install-nltk.py`.
- `scripts/crawl_robuste.sh` — exemple de boucle `land crawl` avec retries (éditer nom du land et paramètres). `bash scripts/crawl_robuste.sh`.
- `scripts/install_utils.py` — helpers communs aux assistants (non exécutable seul).

# Utilisation

## Notes générales

- Toutes les commandes passent par `python mywi.py ...`.
- En Docker :

```bash
# Vérifier que le service tourne
docker compose up -d
# Shell dans le conteneur
docker compose exec mwi bash
# ou
docker exec -it mwi bash
# >>> prompt ≈ root@<container_id>:/app#

# Exemple de commande applicative
python mywi.py land list
```

- En local : activez votre environnement virtuel avant d’appeler la CLI.

```bash
# macOS / Linux
source .venv/bin/activate

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# Windows Command Prompt
.\.venv\Scripts\activate.bat

python mywi.py land list
```

- Remplacez les placeholders (`LAND`, `TERMS`, `https://…`) par vos valeurs.
- Le notebook tutoriel (`docs/mwi_tutorial.ipynb`) requiert en plus
  `pip install pandas jupyter` — volontairement hors `requirements.txt`
  (dépendances réservées au notebook).

---

## Gestion des lands

### 1. Créer un land

```bash
python mywi.py land create --name="MonProjet" --desc="Description" --lang=fr
```

| Option       | Type | Requis | Défaut | Description |
|--------------|------|--------|--------|-------------|
| `--name`     | str  | Oui    |        | Nom du land (identifiant unique) |
| `--desc`     | str  | Non    |        | Description |
| `--lang`     | str  | Non    | fr     | Code langue |
| `--fullhtml` | str  | Non    | FALSE  | Si `TRUE`, les crawls de ce land stockent le HTML brut dans `expression.html` par défaut |

**Exemples**

```bash
python mywi.py land create --name="AsthmaResearch" --desc="Recherche asthme & qualité de l'air" --lang="en"

# Land qui archive le HTML brut de chaque page crawlée par défaut
python mywi.py land create --name="AsthmaArchive" --desc="Archive HTML" --fullhtml=TRUE
```

### 2. Lister les lands

```bash
python mywi.py land list
python mywi.py land list --name="MonProjet"
```

### 3. Ajouter des termes

```bash
python mywi.py land addterm --land="MonProjet" --terms="mot1, mot2"
```

### 4. Ajouter des URLs

```bash
# Directement
python mywi.py land addurl --land="MonProjet" --urls="https://exemple.org,https://exemple.net"

# Depuis un fichier
python mywi.py land addurl --land="MonProjet" --path=urls.txt
```

### 5. Récupérer des URLs via SerpAPI

```bash
python mywi.py land urlist --name="MonProjet" --query="(mot clé)" \
  --datestart=2023-01-01 --dateend=2023-03-31 --timestep=week --lang=fr
```

- Nécessite `settings.serpapi_api_key` ou `MWI_SERPAPI_API_KEY`.
- `--sleep` contrôle la pause (défaut : 1 s).

> **Voir aussi** : le **Routeur de recherche multi-API** ci-dessous est la voie
> recommandée pour amorcer un Land en MWI v2. `land urlist` reste préservé pour
> les besoins ciblés Google + filtre de date.

### 6. Routeur de recherche multi-API

Collecte des seeds depuis **5 fournisseurs** en une seule commande — SearXNG
(auto-hébergé), Brave, Serper, SerpAPI, Tavily — avec deux stratégies
d'orchestration (`fallback` pour préserver les quotas, `parallel` pour la
triangulation). Chaque collecte est journalisée dans les tables `searchquery`
et `searchresultlog` pour la reproductibilité (JOSS).

#### Démarrage rapide (SearXNG seul, sans clé API)

```bash
# 1. Démarrer une instance SearXNG locale.
cd docker/searxng && docker compose up -d
cd ../..

# 2. Vérifier les fournisseurs configurés.
python mywi.py search check

# 3. Exécuter une recherche et amorcer un Land.
python mywi.py land create --name=DemoSearch --desc="démo routeur de recherche"
python mywi.py search run --land=DemoSearch \
                          --query="humanités numériques" \
                          --limit=20 --strategy=fallback
```

#### Commandes

| Commande | Description |
|----------|-------------|
| `python mywi.py search check` | État configuré / non configuré pour les 5 fournisseurs |
| `python mywi.py search run --land=X --query=… [--limit=20] [--strategy=fallback\|parallel] [--language=fr] [--providers=searxng,brave]` | Exécute la requête, dédoublonne et insère les Expressions dans le Land |
| `python mywi.py search list --land=X` | Liste les `SearchQuery` passées pour un Land |
| `python mywi.py search usage --land=X` | Agrège le rapport d'usage par fournisseur (calls, errors, status, quota) |

#### Configuration

Renseigner les clés disponibles dans `settings.py` ou `.env` (cf. `.env.example`) :

```bash
SEARXNG_BASE_URL=http://localhost:8888  # défaut
BRAVE_API_KEY=...                       # optionnel
SERPER_API_KEY=...                      # optionnel
SERPAPI_API_KEY=...                     # optionnel (fallback vers serpapi_api_key legacy)
TAVILY_API_KEY=...                      # optionnel
SEARCH_DEFAULT_STRATEGY=fallback        # ou "parallel"
SEARCH_PROVIDER_TIMEOUT=30              # secondes
```

Une clé manquante désactive silencieusement le fournisseur correspondant — le
routeur ne lève jamais d'erreur sur une absence de clé.

> 📘 **Documentation complète** :
> - Guide utilisateur : [`docs/search_router.md`](docs/search_router.md) (commandes, cadre légal TDM, reproductibilité JOSS).
> - Guide développeur : [`docs/search_router_architecture.md`](docs/search_router_architecture.md) (diagramme de séquence, recette d'ajout d'un nouveau provider).
> - Mise en place SearXNG : [`docs/searxng_setup.md`](docs/searxng_setup.md).

### 7. Supprimer un land ou des expressions

```bash
python mywi.py land delete --name="MonProjet"
python mywi.py land delete --name="MonProjet" --maxrel=0.5
```

---

## Lands multilingues

Le scoring de pertinence est paramétré par la **langue du Land** :
tokenisation et stemming ne sont plus limités au français.

```bash
# Land anglophone
python mywi.py land create --name="SujetAnglais" --desc="..." --lang=en

# Land bilingue : un lemme par langue pour chaque terme (matching par union)
python mywi.py land create --name="SujetBilingue" --desc="..." --lang=fr,en
python mywi.py land addterm --land="SujetBilingue" --terms="travail, work"
```

Points clés :

- **15 langues de stemming** (Snowball, ISO 639-1) : `ar`, `da`, `de`, `en`,
  `es`, `fi`, `fr`, `hu`, `it`, `nl`, `no`, `pt`, `ro`, `ru`, `sv`.
  Langue non supportée → identité minuscule (pas de stemming).
- **Tokenisation** : modèle punkt NLTK par langue quand il existe ;
  `ar`, `hu` et `ro` n'ont pas de modèle punkt et utilisent un tokenizer
  unicode (cyrillique, arabe, grec pris en charge).
- Chaque page est tokenisée/stemmée dans **sa propre langue** si elle
  appartient aux langues du Land, sinon dans la langue primaire du Land.
- `search run` et `land urlist` héritent de la langue primaire du Land
  quand `--language` / `--lang` n'est pas fourni.
- **Lands non francophones créés avant cette fonctionnalité** : leurs lemmes
  ont été calculés avec le stemmer français. Pour les corriger :

  ```bash
  python mywi.py db migrate                        # ajoute word.lang (migration 011)
  python mywi.py land relemm --name="SujetAnglais" # re-stemme + recalcule la pertinence
  ```

---

## Collecte de données

### 1. Crawler les URLs du land

```bash
python mywi.py land crawl --name="MonProjet" [--limit N] [--http CODE] [--retry-status CSV] [--depth D] [--fullhtml=TRUE|FALSE] [--issuecrawl]
```

- `--limit` : plafond d’URLs par run.
- `--http` : relancer uniquement les codes spécifiés (`--http 503`).
- `--retry-status` : codes séparés par virgule à relancer, en ignorant `fetched_at` (`--retry-status=403,429`). Mode backfill cascade.
- `--depth` : limite la profondeur.
- `--fullhtml` : surcharge ponctuelle de la politique de stockage HTML (sinon hérite de `land.fullhtml`).
- `--issuecrawl` : force le mode « analyse de controverse » de la gate LLM (OpenRouter) pour ce run (cf. [Pipeline de consolidation des lands](#pipeline-de-consolidation-des-lands)).

> Astuce shell :
> `for i in {1..100}; do python mywi.py land crawl --name="MonProjet" --depth=0 --limit=100; done`

> **Cascade anti-Cloudflare (sprint-403)** — quand `aiohttp` reçoit un code
> "rattrapable" (`403`, `406`, `429`, `503`, `520`, `521`, `523`, `526`, `ERR`), MWI bascule
> automatiquement sur `curl_cffi` (TLS chrome120, ON par défaut), puis
> Playwright optionnel (`crawl_fallback_playwright=True`, ~3-5 s/page),
> puis archive.org. La stratégie utilisée est enregistrée dans
> `expression.fetch_method` (visible dans `python mywi.py land list`).
> Utiliser `--retry-status=403,429` pour rejouer la cascade sur les URLs
> déjà crawlées sans réinitialiser leur `fetched_at`. Config détaillée :
> `settings-example.py` (bloc `crawl_fallback_*`) et
> `.claude/rules/Pipelines.md` §3.5.

> **Archivage HTML brut (`--fullhtml`, sprint-html)** — quand l'option est
> active, le HTML retourné par la cascade est persisté dans
> `expression.html` **avant** toute extraction. Une page téléchargée mais
> dont Trafilatura/BeautifulSoup ne peuvent rien extraire (interstitiels
> Cloudflare, sites JS-only, markup cassé) est **archivée quand même** —
> exactement les cas pour lesquels on active généralement l'option.
> Le stockage est plafonné à `settings.fullhtml_max_size_kb` (défaut 5 MB
> par page) ; mettre à `0` pour désactiver le plafond. La commande
> `python mywi.py land list --name=X` affiche la politique active et le
> volume cumulé via la ligne `Full HTML: policy=ON — N stored (X.Y MB)`.
> Audit SQL :
> ```sql
> SELECT fetch_method,
>        SUM(CASE WHEN html IS NOT NULL THEN 1 ELSE 0 END) AS with_html,
>        COUNT(*) AS total
>   FROM expression WHERE land_id=?
>   GROUP BY fetch_method;
> ```
> Voir `.claude/rules/Pipelines.md` §3.6 pour le détail.
> Export dédié : `--type=htmldump` (zip + manifest CSV).

### 2. Extraire un contenu lisible (pipeline Mercury)

**Pré-requis** : `npm install -g @postlight/mercury-parser`

```bash
python mywi.py land readable --name="MonProjet" [--limit N] [--depth D] [--merge stratégie] [--llm=true|false] [--issuecrawl]
```

- `smart_merge` (défaut) : fusion intelligente.
- `mercury_priority` : Mercury écrase tout.
- `preserve_existing` : complète uniquement les champs vides.
- `--llm=true` : filtre OpenRouter (si configuré).
- `--issuecrawl` : force le mode « analyse de controverse » de la gate LLM pour ce run (cf. [Pipeline de consolidation des lands](#pipeline-de-consolidation-des-lands)).

### 3. Capturer les métriques SEO Rank

```bash
python mywi.py land seorank --name="MonProjet" [--limit N] [--depth D] [--force]
```

- Clé API : `settings.seorank_api_key` ou `MWI_SEORANK_API_KEY`.
- Par défaut : HTTP 200 et `relevance ≥ 1`.
- `--force` : rafraîchit même les entrées existantes.

### 4. Analyse médias

```bash
python mywi.py land medianalyse --name="MonProjet" [--depth D] [--minrel R]
```

Télécharge, mesure (dimensions/taille), extrait couleurs & EXIF, calcule hash, NSFW, consigne les erreurs.

Verbes de maintenance média :

```bash
# Statistiques agrégées : totaux, formats, dimensions, tailles, doublons par hash
python mywi.py land media_stats --name="MonProjet"

# Dry-run pur : compte + 20 exemples de médias non conformes (rien n'est supprimé)
python mywi.py land preview_deletion --name="MonProjet" [--minwidth N] [--minheight N] [--maxsize MB]

# Re-analyse (médias jamais analysés / en erreur d'abord) ;
# --suppress supprime les non-conformes APRÈS confirmation
python mywi.py land reanalyze --name="MonProjet" [--limit N] [--minwidth N] [--minheight N] [--maxsize MB] [--suppress]
```

Les critères par défaut viennent de `settings.media_min_width`,
`media_min_height` et `media_max_file_size`.

### 5. Crawl des domaines

```bash
python mywi.py domain crawl [--limit N] [--http CODE]
```

`--http=ERR` matche **tous** les statuts d'échec (`ERR_*`, `ARC_NO_HTML`,
`REQ_NO_HTML`, `000`) — pratique pour relancer tous les domaines en erreur.

---

## Exports

### 1. Exporter un land

```bash
python mywi.py land export --name="MonProjet" --type=pagecsv
python mywi.py land export --name="MonProjet" --type=nodegexf
python mywi.py land export --name="MonProjet" --type=mediacsv
python mywi.py land export --name="MonProjet" --type=corpus
python mywi.py land export --name="MonProjet" --type=pseudolinks
python mywi.py land export --name="MonProjet" --type=nodelinkcsv --minrel=1
python mywi.py land export --name="MonProjet" --type=nodelinkcsv --fullhtml=TRUE --minrel=1  # réseau brut SEUL (sans le flag = 4 de base)
python mywi.py land export --name="MonProjet" --type=nodesjson --minrel=1  # graphe de domaines JSON force-graph
python mywi.py land export --name="MonProjet" --type=pagesjson --minrel=1  # graphe de pages JSON force-graph
```

Types : `pagecsv`, `fullpagecsv`, `nodecsv`, `pagegexf`, `nodegexf`, `mediacsv`, `corpus`, `pseudolinks`, `pseudolinkspage`, `pseudolinksdomain`, `nodelinkcsv`, `nodesjson`, `pagesjson`, `htmldump`.

> **Exports JSON force-graph (`nodesjson` / `pagesjson`)** — format `{nodes, links}`
> directement consommable par un visualiseur React/JS (`react-force-graph`, D3,
> Sigma). `nodesjson` = graphe de **domaines** (9 variables analytiques + `corpus`,
> le tableau trié des URL du domaine) ; `pagesjson` = graphe de **pages** (`tags`
> en tableau trié, `seorank` en objet imbriqué, `null` pour les valeurs absentes).
> Exports **déterministes**. Contrat : `docs/graph.schema.json`.

> **Réseau de liens brut (`nodelinkcsv --fullhtml=TRUE`, sprint
> fullhtml-linknetwork)** — émet **uniquement** les 4 fichiers `*fullhtml.csv`
> **à la place** des 4 classiques (interrupteur, pas additif : relancer **sans**
> le flag pour le réseau MyWI) : le réseau de liens reconstruit depuis **tous** les
> `<a href>` du HTML brut (`expression.html`), réseau fermé (cibles ∈ corpus
> qualifié par `--minrel`). Colonnes `weight` (multiplicité des ancres) et
> `in_mywi` (1 si l'arête existe aussi dans `ExpressionLink`). Permet de comparer
> le réseau de liens **éditoriaux** de MyWI au réseau « toute la page » d'un
> crawler classique. **Prérequis** : Land crawlé avec `--fullhtml`. Un rapport de
> couverture (raw∩mywi / raw\mywi / mywi\raw) s'affiche en fin d'export.

### 2. Exporter les tags

```bash
python mywi.py tag export --name="MonProjet" --type=matrix
python mywi.py tag export --name="MonProjet" --type=content
```

---

## Mettre à jour les domaines depuis les heuristiques

```bash
python mywi.py heuristic update
```

## Pipeline de consolidation des lands

```bash
python mywi.py land consolidate --name="MonProjet" [--limit N] [--depth D] [--minrel R] [--llm=true] [--issuecrawl]
```

Reconstruit les liens et médias et recalcule la pertinence lexicale. La
consolidation **respecte les verdicts LLM déjà stockés** : après le recalcul
lexical, si `expression.validllm = 'non'`, la pertinence est forcée à `0` (la
page rejetée n'est jamais ressuscitée). `validllm = 'oui'` ou `NULL` → le score
lexical s'applique normalement. Par défaut, `land consolidate` n'appelle pas le
LLM.

- `--llm=true` : relance la gate de pertinence OpenRouter par expression
  (en respectant `openrouter_readable_min_chars`), rafraîchit
  `validllm`/`validmodel`, puis applique la règle ci-dessus. Si OpenRouter n'est
  pas configuré, le flag est ignoré avec un avertissement et la consolidation
  continue sans LLM (en respectant toujours les verdicts stockés). Bornez les
  appels avec `--limit` / `--depth` / `--minrel`.
- `--issuecrawl` : avec `--llm=true`, force le mode « analyse de controverse »
  pour ce run (voir ci-dessous).

**Mode analyse de controverse** — activable globalement via le paramètre
`openrouter_issue_mode` (variable d'environnement `MWI_OPENROUTER_ISSUE_MODE`,
défaut `false`) ou ponctuellement via le flag `--issuecrawl` (sur `land crawl`,
`land readable`, `land consolidate --llm=true` et `land llm validate`). Dans ce
mode, la gate LLM ne retient que les pages éditoriales / de prise de position
qui engagent la problématique du projet (argument, opinion, analyse ou
information substantielle) et rejette les pages d'index, de sommaire, de
navigation et les pages de présentation d'entreprise génériques qui ne débattent
pas la question (tradition de la cartographie des controverses,
Venturini/Latour). La sémantique du verdict oui/non est inchangée :
`validllm = 'non'` force toujours la pertinence à `0`. Les prompts LLM
(pertinence standard et controverse) sont rédigés en anglais et énoncent
explicitement la langue de travail du projet, en demandant au modèle de
raisonner dans cette langue.

## Normalisation des URLs

Toute URL entrant dans MWI (seeds, résultats SerpAPI, liens extraits par
le crawl ou Mercury) passe par `mwi.url_normalizer.normalize_url`
**avant** insertion en base. Cette canonicalisation garantit une seule
forme par page logique et évite les doublons d'`Expression` causés par
des variantes d'URL (snapshots Wayback, paramètres de tracking, ancres,
casse du host).

**Configuration** — voir `settings.url_normalization` dans
`settings-example.py`. Défauts conservateurs :

| Règle | Défaut | Effet |
|---|---|---|
| `unwrap_archive` | ON | `web.archive.org/.../X` → `X`, récursivement |
| `lowercase_host` | ON | `EXAMPLE.com` → `example.com` (path préservé) |
| `strip_trackers` | ON | Retire `utm_*`, `fbclid`, `gclid`, etc. |
| `normalize_query_order` | ON | Tri alphabétique des params restants |
| `force_https` | OFF | `http://X` → `https://X` (à activer manuellement) |
| `strip_www` | OFF | `www.X.com` → `X.com` (à activer manuellement) |
| `strip_mobile_subdomain` | OFF | `m.X.com` → `X.com` (à activer manuellement) |
| `trailing_slash` | `preserve` | `preserve` \| `strip` \| `add` |

Override par variables d'environnement :
`MWI_URL_FORCE_HTTPS=true`, `MWI_URL_STRIP_WWW=true`,
`MWI_URL_STRIP_MOBILE=true`.

**Provenance** — quand la normalisation modifie l'URL, l'original est
sauvegardé dans `Expression.original_url` (NULL sinon). Permet l'audit
rétrospectif sans relancer le crawl.

**Rattrapage rétrospectif** — pour appliquer les règles à un Land créé
avant ce pipeline :

```bash
# Backup obligatoire
cp data/mwi.db data/mwi.db.bak_$(date +%Y%m%d_%H%M%S)

# Applique la migration 008 (ajoute la colonne original_url)
python mywi.py db migrate

# Aperçu (n'écrit rien)
python mywi.py land normalize --name=MonProjet --dry-run --verbose

# Application
python mywi.py land normalize --name=MonProjet

# Variante : remet http_status=NULL pour re-crawler les URLs renommées
python mywi.py land normalize --name=MonProjet --reset-status
```

**Ce que fait `land normalize`** pour chaque `Expression` du Land :

- Si la forme canonique **n'existe pas** déjà comme autre Expression :
  UPDATE en place + `original_url` rempli.
- Si la forme canonique **existe** : tous les `ExpressionLink`
  (entrants ET sortants) sont remappés vers le canonique, les self-loops
  et arêtes en double sont supprimés, puis l'Expression doublon est
  supprimée (CASCADE sur `Media`, `Paragraph`, `TaggedContent`).
- Les chaînes Wayback-de-Wayback sont résolues en une seule passe.

**Circuit breaker archive.org** — quand archive.org est en panne (ce qui
arrive régulièrement depuis 2024), le fallback Wayback du flux readable
ouvre un breaker après 5 échecs consécutifs et skippe le fallback
pendant 5 min. Économise jusqu'à ~10s par expression pendant les
incidents. Reset automatique au cooldown ou au premier succès.

> **Garde « pas d'archive d'archive »** — quand l'URL est déjà une
> `web.archive.org/...`, le fallback ne se déclenche jamais.

**Travailler sur une autre base que `data/mwi.db`** — le flag `--db`
accepte n'importe quel chemin de fichier SQLite, indépendamment du nom :

```bash
python mywi.py land normalize --name=foo --db ./backups/projet_A.db --dry-run
python mywi.py db migrate --db /chemin/vers/melenchon_v2.db
```

Le flag s'applique à **toutes** les commandes MWI. Alternative sans
modification : `MYWI_DATA_DIR=/dossier python mywi.py …` (le fichier
doit alors s'appeler `mwi.db` dans ce dossier).

## Tests

MyWI inclut une suite de tests aux standards JOSS (≈98 tests répartis sur 8 fichiers, ~87% de couverture).

### Démarrage rapide

```bash
# Installer les dépendances de test (uv synchronise depuis uv.lock)
uv sync
# Repli pip : python -m pip install -r requirements.txt

# Exécuter les tests de base (sans clés API, ~7 secondes)
make test

# Avec rapport de couverture (ouvre htmlcov/index.html)
make test-cov
```

### Structure des tests

| Fichier | Tests | Couverture |
|---------|------:|------------|
| `tests/test_01_installation.py`     | 12 | Setup base, idempotence des migrations |
| `tests/test_02_land_management.py`  | 19 | CRUD land/termes/URLs, dictionnaire |
| `tests/test_03_data_collection.py`  | 12 | Pipeline crawl, extraction de contenu |
| `tests/test_04_export.py`           | 12 | Exports CSV / GEXF / corpus / pseudolinks |
| `tests/test_05_media_analysis.py`   |  9 | Pillow / EXIF / hash / couleurs |
| `tests/test_06_embeddings.py`       | 12 | Découpage paragraphes, providers, similarité |
| `tests/test_07_integration.py`      | 11 | Workflows end-to-end |
| `tests/test_08_expression_html.py`  | 11 | Stockage `--fullhtml`, défaut `Land.fullhtml`, migration 007 |

Les anciens smokes (`test_cli.py`, `test_core.py`, etc.) vivent dans `tests/legacy/` à titre de référence ; la suite active est `tests/test_0?_*.py`.

### Cibles Make

| Commande | Rôle |
|----------|------|
| `make test` (alias `make test-basic`) | Suite par défaut, sans clés API |
| `make test-quick` | Smoke test (`test_01_installation.py`) |
| `make test-all` | Toute la suite, y compris les tests API |
| `make test-cov` / `make test-cov-open` | Couverture (ouvre le rapport) |
| `make test-apis` | Tests gated par `MWI_SERPAPI_API_KEY`, `MWI_SEORANK_API_KEY`, `MWI_OPENROUTER_API_KEY` |
| `make test-integration` | Tests end-to-end (réseau) |
| `make joss-test` | Rejoue le flux d'évaluation JOSS |
| `make clean` | Purge `.pytest_cache`, `htmlcov`, `__pycache__` |

### Tests API optionnels

Les tests qui appellent des APIs externes sont automatiquement ignorés sans clé :

```bash
export MWI_SERPAPI_API_KEY="votre_clé"
export MWI_SEORANK_API_KEY="votre_clé"
export MWI_OPENROUTER_API_KEY="votre_clé"
make test-apis
```

---

# Embeddings & pseudolinks (guide utilisateur)

## Objectif

- Générer des embeddings par paragraphe.
- Relier les paragraphes proches (pseudolinks) et, si besoin, qualifier la relation via NLI (entailment / neutral / contradiction).
- Exporter les relations au niveau paragraphe, page ou domaine.

## Pré-requis & installation

```bash
# uv synchronise base + outils de dev depuis uv.lock (provisionne Python 3.11)
uv sync
```

Repli pip (sans uv) :

```bash
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
```

Option ML :

```bash
uv sync --extra ml
# Repli pip : python -m pip install -r requirements-ml.txt
```

Vérification : `uv run python mywi.py embedding check`

## Modèles

- NLI recommandé : `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7`.
- Fallback léger (EN) : `typeform/distilbert-base-uncased-mnli`.

## Paramètres (référence)

- Embeddings : `embed_provider`, `embed_model_name`, `embed_batch_size`, `embed_min_paragraph_chars`, `embed_max_paragraph_chars`, `embed_similarity_method`, `embed_similarity_threshold`.
- Rappel ANN / NLI : `similarity_backend`, `similarity_top_k`, `nli_model_name`, `nli_fallback_model_name`, `nli_backend_preference`, `nli_batch_size`, `nli_max_tokens`, `nli_torch_num_threads`, `nli_progress_every_pairs`, `nli_show_throughput`.
- Variables CPU : `OMP_NUM_THREADS`, `MKL_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, `TOKENIZERS_PARALLELISM=false`.

## Commandes & paramètres

```bash
python mywi.py embedding generate --name=LAND [--limit N]

python mywi.py embedding similarity --name=LAND --method=cosine \
  --threshold=0.85 [--minrel R]

python mywi.py embedding similarity --name=LAND --method=cosine_lsh \
  --lshbits=20 --topk=15 --threshold=0.85 [--minrel R] [--maxpairs M]

python mywi.py embedding similarity --name=LAND --method=nli \
  --backend=faiss|bruteforce --topk=10 [--minrel R] [--maxpairs M]

python mywi.py land export --name=LAND --type=pseudolinks
python mywi.py land export --name=LAND --type=pseudolinkspage
python mywi.py land export --name=LAND --type=pseudolinksdomain
```

## Dépannage & précautions

- `score_raw=0.5` + `score=0` : fallback neutre → installer les dépendances ML ou choisir un autre modèle.
- Colonne `score_raw` absente : `python mywi.py db migrate`.
- Segfault macOS (OpenMP/Torch) : venv pip-only, commencer avec `OMP_NUM_THREADS=1`, augmenter ensuite.
- Lenteur : diminuer `nli_batch_size`, filtrer `--minrel`, plafonner `--maxpairs`, ajuster les threads.
- Trop de paires : augmenter `--threshold`, `--lshbits`, réduire `--topk`, utiliser `--minrel`.

## Bonnes pratiques — performance

- ≤ 50k paragraphes : `--method=cosine --threshold=0.85 --minrel=1`.
- ≥ 100k paragraphes : `--method=cosine_lsh`, `--lshbits=18–22`, `--topk=10–20`, `--threshold≥0.85`, `--maxpairs` pour plafonner.
- Pipeline NLI : FAISS recommandé, départ `--topk=6–10`, `--minrel=1–2`, `--maxpairs=20k–200k`, ajuster `nli_batch_size` (32–96) et `nli_max_tokens` (384–512).

## Choix des modèles et recours

- Par défaut : DeBERTa multilingue (`sentencepiece` requis).
- Alternative sûre (EN) : DistilBERT MNLI.
- Sans dépendances ML : fallback neutre (`score=0`).

## Progression & logs

- Rappel ANN : journalise les candidats.
- NLI : affiche `pairs/s`, ETA, cumul.
- Résumé final : temps total et volume traité.

## Méthodes de similarité

- `cosine` : comparaison exacte O(n²).
- `cosine_lsh` : approximation scalable via LSH.
- `nli` : ANN + cross-encoder, scores ∈ {-1,0,1}.

## Choisir le backend ANN (FAISS)

- Installer FAISS : `pip install faiss-cpu`.
- Forcer `--backend=faiss` ou `--backend=bruteforce`.
- Paramètre global : `similarity_backend = 'faiss'` dans `settings.py`.
- Sans FAISS : fallback bruteforce.

## Similarité scalable (lands volumineux)

```bash
python mywi.py embedding similarity \
  --name=LAND \
  --method=cosine_lsh \
  --threshold=0.85 \
  --lshbits=20 \
  --topk=15 \
  --minrel=1 \
  --maxpairs=5000000
```

- `--lshbits` : plus élevé → buckets plus fins.
- `--topk` : voisins conservés.
- `--threshold` : seuil minimal.
- `--minrel` : filtre pertinence.
- `--maxpairs` : limite globale.

## Relations NLI (ANN + cross-encoder)

```bash
pip install sentence-transformers transformers
pip install faiss-cpu

python mywi.py embedding similarity \
  --name=LAND \
  --method=nli \
  --backend=bruteforce \
  --topk=50 \
  --minrel=1 \
  --maxpairs=2000000
```

Paramètres clés : `nli_model_name`, `nli_batch_size`, `similarity_backend`, `similarity_top_k`.

---

# Dépannage & réparation

## Garder le schéma de base à jour

```bash
python mywi.py db migrate
cp data/mwi.db data/mwi.db.bak_$(date +%Y%m%d_%H%M%S)
```

## Récupération SQLite

```bash
chmod +x scripts/sqlite_recover.sh
scripts/sqlite_recover.sh data/mwi.db data/mwi_repaired.db
```

- Sauvegarde la base et les fichiers `-wal`/`-shm`.
- Tente `.recover`, fallback `.dump`.
- Reconstruit `data/mwi_repaired.db`, éxécute `PRAGMA integrity_check;` et liste les tables.
- Tester avant remplacement :

```bash
mkdir -p data/test-repaired
cp data/mwi_repaired.db data/test-repaired/mwi.db
MYWI_DATA_DIR="$PWD/data/test-repaired" python mywi.py land list
```

---

# Pour les développeurs

## Architecture & flux internes

```
mywi.py  →  mwi/cli.py  →  mwi/controller.py  →  mwi/core.py & mwi/export.py
                                     ↘ mwi/model.py (Peewee)
                                     ↘ mwi/readable_pipeline.py
                                     ↘ mwi/media_analyzer.py
                                     ↘ mwi/embedding_pipeline.py
```

- `mywi.py` : point d’entrée CLI.
- `mwi/cli.py` : parsing (`argparse`), expose `command_run()`.
- `mwi/controller.py` : façade, renvoie 1 (succès) ou 0 (échec).
- `mwi/core.py` : crawl, pipeline Mercury, heuristiques, consolidation, médias.
- `mwi/export.py` : exports CSV/GEXF/corpus.
- `mwi/model.py` : schéma Peewee, pragmas SQLite.

## Schéma de données (SQLite/Peewee)

- `Land`, `Word`, `LandDictionary`, `Domain`, `Expression`, `ExpressionLink`, `Media`, `Paragraph`, `ParagraphEmbedding`, `ParagraphSimilarity`, `Tag`, `TaggedContent`.

## Workflows principaux

- Initialisation : `python mywi.py db setup`
- Cycle land : créer → ajouter termes/URLs → `land crawl` → `land readable` → exports
- Médias : `python mywi.py land medianalyse ...`
- SEO Rank : `python mywi.py land seorank ...`
- Domaines : `python mywi.py domain crawl`
- Tags : `python mywi.py tag export`
- Embeddings : `python mywi.py embedding generate`, `python mywi.py embedding similarity`

## Notes d’implémentation

- Pertinence basée sur les lemmes (titre + contenu).
- Crawl asynchrone avec contrôle du parallélisme, timeouts, retries, archivage HTML optionnel.
- Médias : association automatique, filtrage configurable, hash, erreurs persistées.
- Exports : requêtes Peewee/SQL ciblées, génération CSV/GEXF enrichie.

## Paramètres

- `data_location`, `archive`, `dynamic_media_extraction`, `parallel_connections`, `default_timeout`, `user_agent`, `heuristics`.
- Embeddings : `embed_provider`, `embed_model_name`, `embed_api_url`, `embed_batch_size`, `embed_min_paragraph_chars`, `embed_max_paragraph_chars`, `embed_similarity_method`, `embed_similarity_threshold`, retrys.
- OpenRouter : `openrouter_enabled`, `openrouter_api_key`, `openrouter_model`, `openrouter_timeout`, `openrouter_readable_min_chars`, `openrouter_readable_max_chars`, `openrouter_max_calls_per_run`, `openrouter_issue_mode`.
- SEO Rank : `seorank_api_base_url`, `seorank_api_key`, `seorank_timeout`, `seorank_request_delay`.
- SerpAPI : `serpapi_api_key`, `serpapi_base_url`, `serpapi_timeout`.
- NLI : `nli_model_name`, `nli_fallback_model_name`, `nli_backend_preference`, `nli_batch_size`, `nli_max_tokens`, `nli_torch_num_threads`, `nli_progress_every_pairs`, `nli_show_throughput`, `nli_entailment_threshold`, `nli_contradiction_threshold`.
- Similarité : `similarity_backend`, `similarity_top_k`.

## Tests

- `pytest tests/`
- `pytest tests/test_cli.py`

## Extension

- Nouvel export : étendre `mwi/export.py`, raccorder dans `controller.py`.
- Provider embeddings : implémenter dans `embedding_pipeline.py`, déclarer dans `settings.py`.
- Enrichissement API : ajouter un contrôleur, la configuration `settings.py` et les scripts d’installation.

---

# Licence

Projet distribué sous licence MIT — voir [LICENSE](LICENSE).
