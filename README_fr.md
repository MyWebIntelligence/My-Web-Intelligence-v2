# My Web Intelligence (MyWI)

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.18376428.svg)](https://doi.org/10.5281/zenodo.18376428)

DÉPÔT PRINCIPAL (VITRINE)

Ceci est le point d'entrée principal de My Web Intelligence.
Page d'accueil de l'organisation : https://github.com/MyWebIntelligence

MyWebIntelligence (MWI) est un outil de recherche reproductible pour les méthodes numériques en sciences sociales et en sciences de la communication. Il couvre : la collecte de corpus, la qualification (assistée par le TAL/LLM, mais auditable), l'analyse socio-sémantique et de réseau, et les exports pour la réplication (CSV/JSON/GEXF). MWI est un outil écrit en Python qui stocke ses informations dans une base de données SQLite.

Pour parcourir la base de données, un outil comme [SQLiteBrowser](https://sqlitebrowser.org/) peut être très utile.

Version anglaise : [README.md](README.md)

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
    - [1. Créer un nouveau land](#1-créer-un-nouveau-land)
    - [2. Lister les lands créés](#2-lister-les-lands-créés)
    - [3. Ajouter des termes à un land](#3-ajouter-des-termes-à-un-land)
    - [4. Ajouter des URLs à un land](#4-ajouter-des-urls-à-un-land)
    - [5. Récupérer des URLs via SerpAPI (Google)](#5-récupérer-des-urls-via-serpapi-google)
    - [6. Routeur de recherche multi-API](#6-routeur-de-recherche-multi-api)
    - [7. Supprimer un land ou des expressions](#7-supprimer-un-land-ou-des-expressions)
  - [Lands multilingues](#lands-multilingues)
  - [Collecte de données](#collecte-de-données)
    - [1. Crawler les URLs du land](#1-crawler-les-urls-du-land)
    - [2. Récupérer le contenu lisible (pipeline Mercury Parser)](#2-récupérer-le-contenu-lisible-pipeline-mercury-parser)
    - [3. Capturer les métriques SEO Rank](#3-capturer-les-métriques-seo-rank)
    - [4. Analyse des médias](#4-analyse-des-médias)
    - [5. Crawler les domaines](#5-crawler-les-domaines)
  - [Exporter les données](#exporter-les-données)
    - [1. Exporter les données d'un land](#1-exporter-les-données-dun-land)
    - [2. Exporter les données des tags](#2-exporter-les-données-des-tags)
  - [Mettre à jour les domaines depuis les réglages d'heuristiques](#mettre-à-jour-les-domaines-depuis-les-réglages-dheuristiques)
  - [Pipeline de consolidation des lands](#pipeline-de-consolidation-des-lands)
  - [Pipeline de normalisation des URLs](#pipeline-de-normalisation-des-urls)
  - [Tests](#tests)
- [Embeddings & pseudolinks (guide utilisateur)](#embeddings--pseudolinks-guide-utilisateur)
  - [Objectif](#objectif)
  - [Pré-requis & installation](#pré-requis--installation)
  - [Modèles](#modèles)
  - [Réglages (référence des clés)](#réglages-référence-des-clés)
  - [Commandes & paramètres](#commandes--paramètres)
  - [Dépannage & précautions](#dépannage--précautions)
  - [Bonnes pratiques — performance](#bonnes-pratiques--performance)
  - [Choix du modèle et replis](#choix-du-modèle-et-replis)
  - [Progression & logs](#progression--logs)
  - [Méthodes de similarité](#méthodes-de-similarité)
  - [Choisir le backend ANN (FAISS)](#choisir-le-backend-ann-faiss)
  - [Similarité à grande échelle (lands volumineux)](#similarité-à-grande-échelle-lands-volumineux)
  - [Relations NLI (ANN + cross-encoder)](#relations-nli-ann--cross-encoder)
- [Dépannage & réparation](#dépannage--réparation)
  - [Garder le schéma de base à jour](#garder-le-schéma-de-base-à-jour)
  - [Réparer l'attribution des domaines archive.org](#réparer-lattribution-des-domaines-archiveorg)
  - [Récupération SQLite](#récupération-sqlite)
- [Pour les développeurs](#pour-les-développeurs)
  - [Architecture & fonctionnement interne](#architecture--fonctionnement-interne)
    - [Structure des fichiers & flux](#structure-des-fichiers--flux)
    - [Schéma de données (SQLite, via Peewee)](#schéma-de-données-sqlite-via-peewee)
    - [Workflows principaux](#workflows-principaux)
    - [Notes d'implémentation](#notes-dimplémentation)
    - [Réglages](#réglages)
    - [Tests (vue développeur)](#tests-vue-développeur)
    - [Extension](#extension)
- [Licence](#licence)

## Fonctionnalités

*   **Création et gestion des lands** : organisez votre recherche en « lands », des collections thématiques de termes et d'URLs.
*   **Routeur de recherche multi-API** : collectez des URLs de départ auprès de cinq fournisseurs au plus (SearXNG auto-hébergé, Brave, Serper, SerpAPI, Tavily) avec les stratégies `fallback` ou `parallel`, et un journal complet par requête pour la reproductibilité (JOSS). Voir [`docs/search_router.md`](docs/search_router.md).
*   **Crawl web** : crawlez les URLs associées à vos lands pour recueillir le contenu des pages web.
*   **Extraction de contenu** : traitez les pages crawlées pour en extraire le contenu lisible.
*   **Enrichissement SEO Rank** : interrogez l'API SEO Rank pour chaque expression et conservez la réponse JSON brute à côté de l'URL.
*   **Embeddings & pseudolinks** : embeddings au niveau du paragraphe, similarité sémantique et export CSV de « pseudolinks » entre paragraphes sémantiquement proches d'une page à l'autre.
*   **Analyse et filtrage des médias** : extraction et analyse automatiques des images, des vidéos et de l'audio. Extrait les métadonnées (dimensions, taille, format, couleurs dominantes, EXIF), permet un filtrage et une suppression intelligents, la détection des doublons et un traitement asynchrone par lots.
*   **Détection améliorée des médias** : détecte les fichiers médias dont l'extension est en majuscules comme en minuscules (.JPG, .jpg, .PNG, .png, etc.).
*   **Extraction dynamique des médias** : extraction optionnelle par navigateur headless pour les médias générés en JavaScript ou chargés en différé (lazy loading).
*   **Analyse des domaines** : recueillez des informations sur les domaines rencontrés pendant le crawl.
*   **Export des données** : exportez les données collectées dans divers formats (CSV, GEXF, corpus brut) pour une analyse ultérieure.
*   **Analyse par tags** : exportez des matrices de tags et leur contenu pour approfondir l'analyse.

## Tutoriels

*   [`docs/mwi_tutorial.ipynb`](docs/mwi_tutorial.ipynb) — un projet de recherche complet de A à Z (création du land, amorçage multi-moteurs, crawl borné en profondeur, normalisation d'URL, extraction du contenu lisible, qualification, enrichissements, exports), avec un audit SQL après chaque étape. Ouvrez-le avec `uv run --with jupyter --with pandas jupyter lab docs/mwi_tutorial.ipynb` (dépendances propres au notebook, non installées par `uv sync`).
*   [`docs/mwi_tutorial_install.md`](docs/mwi_tutorial_install.md) — installation pas à pas.
*   [`docs/mwi_tutorial_crawl.md`](docs/mwi_tutorial_crawl.md) — tutoriel de constitution d'un corpus sur une étude de cas francophone.

---

# Installation

**Trois options d'installation :** Docker Compose (recommandé), Docker manuel ou Python en local.  
Sauf mention contraire, lancez chaque commande depuis la racine du dépôt. Sous Windows, utilisez un terminal compatible Bash (Git Bash ou WSL) pour les scripts shell ; pour les commandes Python, utilisez `python` ou `py -3`.

> 📘 **Guide détaillé :** voir [docs/mwi_tutorial_install.md](docs/mwi_tutorial_install.md) pour des instructions d'installation complètes, avec des scripts de configuration interactifs.

## Démarrage rapide : Docker Compose (recommandé)

**Installation automatisée en une seule commande :**
```bash
./scripts/docker-compose-setup.sh [basic|api|llm]
```
Si vous omettez l'argument, le script utilise `basic`. Choisissez `api` pour configurer SerpAPI/SEO Rank/OpenRouter, ou `llm` pour préparer en plus les dépendances embeddings/NLI.

Sous Windows, lancez le script depuis un shell compatible Bash :
- Git Bash : `./scripts/docker-compose-setup.sh`
- PowerShell : `& "C:\Program Files\Git\bin\bash.exe" ./scripts/docker-compose-setup.sh`
- WSL : `wsl bash ./scripts/docker-compose-setup.sh`
Un double-clic sur le fichier `.sh` ne l'exécute pas.

**Ou pas à pas (terminal de la machine hôte) :**

1. Cloner le projet :
   ```bash
   git clone https://github.com/MyWebIntelligence/mwi.git
   cd mwi
   ```
2. Générer `.env` pour Docker Compose (assistant interactif) :
   ```bash
   python scripts/install-docker-compose.py
   ```
   Sous Windows, vous pouvez aussi utiliser `py -3 scripts/install-docker-compose.py`.
3. Construire et démarrer le conteneur :
   ```bash
   docker compose up -d --build
   ```
4. Créer `settings.py` **dans** le conteneur (une seule fois par environnement) :
   ```bash
   docker compose exec mwi bash -lc "cp settings-example.py settings.py"
   ```
   Pour personnaliser plutôt les réglages de façon interactive, lancez :
   ```bash
   docker compose exec -it mwi python scripts/install-basic.py --output settings.py
   ```
5. Initialiser puis vérifier la base de données :
   ```bash
   docker compose exec mwi python mywi.py db setup
   docker compose exec mwi python mywi.py land list
   ```

> ⚠️ `settings.py` n'est **pas** créé automatiquement dans le conteneur.  
> Créez-le depuis le conteneur (copiez `settings-example.py` ou lancez `python scripts/install-basic.py`) avant d'exécuter les commandes MyWI ; ce fichier contient les chemins et les clés propres à l'environnement, et il est volontairement exclu du contrôle de version et des couches Docker.

**Où sont mes données ?**

- Ordinateur : `./data` (par défaut) ou le chemin défini dans `.env`
- Conteneur : `/app/data` (correspondance automatique)

**Gestion :**
```bash
docker compose up -d       # Démarrer
docker compose down        # Arrêter
docker compose logs mwi    # Voir les logs
docker compose exec mwi bash  # Entrer dans le conteneur
```

---

## Docker manuel (avancé)

Pour des tests rapides, ou quand Compose n'est pas disponible :
```bash
# Construction
docker build -t mwi:latest .

# Exécution
docker run -dit --name mwi -v ~/mywi_data:/app/data mwi:latest

# Création de settings.py dans le conteneur (premier lancement)
docker exec mwi bash -lc "cp settings-example.py settings.py"
# Ou, pour personnaliser :
# docker exec -it mwi python scripts/install-basic.py --output settings.py

# Initialisation
docker exec -it mwi python mywi.py db setup

# Utilisation
docker exec -it mwi python mywi.py land list
```

> ⚠️ Avant de lancer des commandes dans le conteneur, assurez-vous que `settings.py` existe (copiez `settings-example.py` ou lancez `python scripts/install-basic.py`). Le projet ne génère jamais ce fichier automatiquement.

**Gestion :** `docker stop mwi` · `docker start mwi` · `docker rm mwi`

---

## Installation locale

**Pré-requis :** [uv](https://docs.astral.sh/uv/) et git. uv provisionne
l'interpréteur Python (3.10+) et l'environnement virtuel pour vous — aucune
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
#    uv lit .python-version (3.11) et télécharge cet interpréteur s'il est absent.
uv sync

# 3. Configurer (assistant interactif)
uv run python scripts/install-basic.py

# 4. Initialiser la base de données
uv run python mywi.py db setup

# 5. Vérifier
uv run python mywi.py land list
```

`uv run <cmd>` s'exécute dans le venv du projet et le re-synchronise à la volée —
pas besoin de `source .venv/bin/activate` (vous pouvez toujours activer `.venv`
manuellement si vous préférez). Vous modifiez les dépendances ? Changez
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

**Étapes optionnelles :**

- **Configuration des API :** `uv run python scripts/install-api.py`
- **LLM/embeddings (extras ML) :** `uv sync --extra ml && uv run python scripts/install-llm.py`
- **Médias dynamiques (Playwright) :**
  - Navigateurs : `uv run python install_playwright.py`
  - Bibliothèques Debian/Ubuntu : `sudo apt-get install libnspr4 libnss3 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 libatspi2.0-0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libxkbcommon0 libasound2`
  - Docker : `docker compose exec mwi bash -lc "apt-get update && apt-get install -y <libs>"` puis `docker compose exec mwi python install_playwright.py`
  - **Note (sprint-403)** : Playwright est désormais aussi mis à profit par la
    cascade de fetch (`crawl_fallback_playwright=True` dans `settings.py`) et par
    `extract_dynamic_medias`. Les deux partagent le même singleton `BrowserPool`,
    si bien qu'une seule instance Chromium est lancée par crawl, quel que soit le
    nombre de pages qui l'utilisent.

**Dépendance de la cascade de fetch (sprint-403) :** `requirements.txt` inclut
désormais `curl_cffi>=0.7.0`. Elle permet l'imitation TLS (Chrome 120), afin que
les pages qui renvoient `403`/`429` à un simple `aiohttp` à cause de l'empreinte
Cloudflare puissent tout de même être récupérées sans lancer un navigateur complet.
Activée par défaut ; peut être désactivée avec `crawl_fallback_curl_cffi = False`
dans `settings.py`.

**Dépannage NLTK (Windows/macOS) :**
```bash
uv run python -m nltk.downloader punkt punkt_tab
# En cas d'erreur SSL : uv pip install certifi
```

---

## Scripts utiles

**Démarrages rapides**
- `scripts/docker-compose-setup.sh` — amorçage Docker de bout en bout (crée `.env` ou le sauvegarde, lance l'assistant, construit l'image, démarre le conteneur, initialise la base et peut lancer un test sommaire (smoke test) des API/du ML). Lancez `./scripts/docker-compose-setup.sh [basic|api|llm]`.

**Assistants de configuration interactifs**
- `scripts/install-docker-compose.py` — écrit `.env` pour Compose (fuseau horaire, chemin des données sur l'hôte ↔ `/app/data`, options de build Playwright/ML, clés SerpAPI/SEO Rank/OpenRouter, valeurs par défaut des embeddings/NLI). Lancez `python scripts/install-docker-compose.py [--level basic|api|llm] [--output .env]`.
- `scripts/install-basic.py` — génère un `settings.py` minimal (chemin de stockage, timeouts réseau, concurrence, user agent, médias dynamiques, analyse des médias, heuristiques par défaut). Lancez `uv run python scripts/install-basic.py [--output settings.py]`.
- `scripts/install-api.py` — enregistre les identifiants SerpAPI, SEO Rank et OpenRouter dans `settings.py` (avec repli sur les variables d'environnement). Lancez `uv run python scripts/install-api.py [--output settings.py]`.
- `scripts/install-llm.py` — configure le fournisseur d'embeddings, les modèles/backends NLI et les paramètres de relance et de traitement par lots, après avoir vérifié les dépendances ML. Lancez `uv run python scripts/install-llm.py [--output settings.py]`.

**Diagnostics & récupération**
- `scripts/test-apis.py` — valide les clés d'API configurées ; accepte `--serpapi`, `--seorank`, `--openrouter` ou `--all` (ajoutez `-v` pour une sortie détaillée). Lancez `uv run python scripts/test-apis.py ...`.
- `scripts/sqlite_recover.sh` — outil de réparation SQLite non destructif (voir [Récupération SQLite](#récupération-sqlite)). Lancez `scripts/sqlite_recover.sh [INPUT_DB] [OUTPUT_DB]`.

**Utilitaires**
- `scripts/install-nltk.py` — télécharge les tokenizers `punkt` et `punkt_tab` requis par NLTK. Lancez `uv run python scripts/install-nltk.py`.
- `scripts/crawl_robuste.sh` — exemple de boucle de relance autour de `land crawl` ; modifiez le nom du land et les limites avant de le lancer. Exécutez-le avec `bash scripts/crawl_robuste.sh`.
- `scripts/install_utils.py` — bibliothèque d'utilitaires partagée par les assistants d'installation interactifs (non exécutable seule).

---

# Utilisation

## Notes générales

*   **Codes de sortie.** `0` succès ; `1` échec métier (land introuvable,
    rien à faire, confirmation annulée ou exception non rattrapée) ;
    `2` erreur d'usage argparse. Jusqu'en 2026-09, toute exécution sortait en `0`,
    si bien qu'un enchaînement comme `mywi.py land crawl ... && mywi.py land export ...`
    continuait après une étape qui avait échoué. Si un de vos scripts comptait
    là-dessus, il s'arrêtera désormais là où il aurait toujours dû s'arrêter.
*   **Toutes les commandes ci-dessous sont écrites pour l'installation locale avec uv**
    (celle qui est recommandée) : `uv run python mywi.py ...`, lancée depuis la racine
    du dépôt. `uv run` s'exécute dans le `.venv` du projet — rien à activer, et
    l'environnement est resynchronisé à la volée.
*   **Dans le conteneur Docker, retirez le préfixe `uv run `** et tapez
    `python mywi.py ...` : l'image place déjà son environnement dans le `PATH`.
    Il en va de même pour un venv activé à la main (repli pip).
*   Si vous utilisez Docker, exécutez d'abord `docker exec -it mwi bash` pour entrer dans le conteneur. L'invite peut ressembler à `root@<container_id>:/app#` ou à une forme voisine.

```bash
# Vérifier que le service tourne
docker compose up -d
# Entrer dans le conteneur
docker compose exec mwi bash
# ou
docker exec -it mwi bash
#  >>> L'invite ressemble généralement à root@<container_id>:/app#

# Puis lancer n'importe quelle commande de l'application — sans `uv run`
python mywi.py land list
```

*   Les arguments comme `LAND_NAME` ou `TERMS` sont des marqueurs génériques ; remplacez-les par vos valeurs réelles.
*   Le notebook tutoriel (`docs/mwi_tutorial.ipynb`) requiert en plus `jupyter` et `pandas` — volontairement **absents** des dépendances du projet (réservés au notebook). Laissez uv les fournir pour la seule durée de la session : `uv run --with jupyter --with pandas jupyter lab docs/mwi_tutorial.ipynb`.

Si vous préférez un venv activé au préfixe `uv run` :

```bash
# macOS / Linux
source .venv/bin/activate

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# Invite de commandes Windows (cmd.exe)
.\.venv\Scripts\activate.bat

# Puis lancer n'importe quelle commande de l'application, sans `uv run`
python mywi.py land list
```

## Gestion des lands

Un « Land » est un concept central de MyWI : il représente un domaine ou un sujet de recherche précis.

---

### 1. Créer un nouveau land

Créer un nouveau land (sujet/projet de recherche).

```bash
uv run python mywi.py land create --name="MyResearchTopic" --desc="A description of this research topic"
```

| Option      | Type   | Requis | Défaut  | Description                                 |
|-------------|--------|--------|---------|---------------------------------------------|
| --name      | str    | Oui    |         | Nom du land (identifiant unique)            |
| --desc      | str    | Non    |         | Description du land                         |
| --lang      | str    | Non    | fr      | Code de langue du land (défaut : fr)        |
| --fullhtml  | str    | Non    | FALSE   | Si `TRUE`, les crawls de ce land stockent par défaut le HTML brut dans `expression.html` |

**Exemple :**
```bash
uv run python mywi.py land create --name="AsthmaResearch" --desc="Research on asthma and air quality" --lang="en"

# Land qui stocke par défaut le HTML complet de chaque page crawlée
uv run python mywi.py land create --name="AsthmaArchive" --desc="HTML archive" --fullhtml=TRUE
```

---

### 2. Lister les lands créés

Lister tous les lands ou afficher les propriétés d'un land précis.

- Lister tous les lands :
  ```bash
  uv run python mywi.py land list
  ```
- Afficher le détail d'un land précis :
  ```bash
  uv run python mywi.py land list --name="MyResearchTopic"
  ```

| Option   | Type | Requis | Défaut | Description                          |
|----------|------|--------|--------|--------------------------------------|
| --name   | str  | Non    |        | Nom du land dont afficher le détail  |

La vue détaillée affiche, pour chaque land :
- Le nombre de termes du dictionnaire.
- Le nombre total d'expressions (et combien restent à crawler).
- La répartition des statuts HTTP.
- La **répartition des méthodes de récupération** (sprint-403) : la stratégie qui
  a fourni le HTML de chaque page crawlée — `aiohttp`, `curl_cffi`, `playwright`,
  `archive_org`, ou `unknown` pour les pages crawlées avant la migration.
- Le **stockage du HTML complet** (sprint-html) : la politique `ON|OFF`, ainsi que
  le nombre et la taille cumulée des expressions dont le HTML brut est archivé dans
  `expression.html`. Affiché seulement quand la politique est active ou que des
  données anciennes existent. Exemple :
  `Full HTML: policy=ON — 156544 expressions stored (3812.7 MB)`.
- Le résumé du pipeline d'embeddings (paragraphes / embeddings / pseudolinks).

---

### 3. Ajouter des termes à un land

Ajouter des mots-clés ou des locutions à un land.

```bash
uv run python mywi.py land addterm --land="MyResearchTopic" --terms="keyword1, keyword2, related phrase"
```

| Option   | Type | Requis | Défaut | Description                                        |
|----------|------|--------|--------|----------------------------------------------------|
| --land   | str  | Oui    |        | Nom du land auquel ajouter les termes              |
| --terms  | str  | Oui    |        | Liste de termes/mots-clés séparés par des virgules |

---

### 4. Ajouter des URLs à un land

Ajouter des URLs à un land, directement ou depuis un fichier.

- Directement :
  ```bash
  uv run python mywi.py land addurl --land="MyResearchTopic" --urls="https://example.com/page1, https://anothersite.org/article"
  ```
- Depuis un fichier (une URL par ligne) :
  ```bash
  uv run python mywi.py land addurl --land="MyResearchTopic" --path="/path/to/your/url_list.txt"
  ```
  *(Si vous utilisez Docker, assurez-vous que ce fichier est accessible depuis le conteneur, par exemple dans votre volume de données monté.)*

| Option   | Type | Requis | Défaut | Description                                          |
|----------|------|--------|--------|------------------------------------------------------|
| --land   | str  | Oui    |        | Nom du land auquel ajouter les URLs                  |
| --urls   | str  | Non    |        | Liste d'URLs à ajouter, séparées par des virgules    |
| --path   | str  | Non    |        | Chemin d'un fichier contenant les URLs (une par ligne) |

---

### 5. Récupérer des URLs via SerpAPI (Google)

Amorcer un land avec des URLs issues des résultats de recherche Google, via
SerpAPI. Seules les nouvelles URLs sont insérées ; les entrées existantes
conservent leurs données mais reçoivent un titre si l'API en a renvoyé un.

```bash
uv run python mywi.py land urlist --name="MyResearchTopic" --query="(gilets jaunes) OR (manifestation)" \
  --datestart=2023-01-01 --dateend=2023-03-31 --timestep=week
```

| Option      | Type  | Requis | Défaut  | Description |
|-------------|-------|--------|---------|-------------|
| --name      | str   | Oui    |         | Land qui reçoit les URLs |
| --query     | str   | Oui    |         | Requête de recherche (toute chaîne booléenne valide) |
| --engine    | str   | Non    | google  | Moteur SerpAPI : `google`, `bing` ou `duckduckgo`. Les filtres de date exigent `google` ou `duckduckgo`. |
| --datestart | str   | Non    |         | Début du filtre de date (`YYYY-MM-DD`) |
| --dateend   | str   | Non    |         | Fin du filtre de date (`YYYY-MM-DD`) |
| --timestep  | str   | Non    | week    | Taille de la fenêtre lors du parcours entre les deux dates (`day`, `week`, `month`) |
| --sleep     | float | Non    | 1.0     | Délai de base (en secondes) entre deux pages, pour respecter les limites de débit |
| --lang      | str   | Non    | fr      | Liste de langues séparées par des virgules ; la première valeur est utilisée pour SerpAPI |
| --progress  | flag  | Non    | off     | Affiche une ligne de progression par fenêtre de dates (activé automatiquement quand une plage de dates est fixée) |

> **Clé d'API** — renseignez `settings.serpapi_api_key` ou exportez
> `MWI_SERPAPI_API_KEY` avant de lancer la commande.

> **Voir aussi** : le nouveau **Routeur de recherche multi-API** (section suivante)
> est la voie recommandée pour amorcer les Lands en MWI v2. `land urlist` est
> conservé pour la compatibilité et pour les collectes Google ponctuelles filtrées
> par date.

---

### 6. Routeur de recherche multi-API

Collecter des URLs de départ auprès de **cinq fournisseurs** au plus, en une seule
commande — SearXNG (auto-hébergé), Brave, Serper, SerpAPI, Tavily — avec deux
stratégies d'orchestration (`fallback` pour préserver les quotas, `parallel` pour
la triangulation). Chaque collecte est journalisée dans les tables `searchquery`
et `searchresultlog` pour la reproductibilité (JOSS).

#### Démarrage rapide (SearXNG seul — aucune clé d'API requise)

```bash
# 1. Démarrer une instance SearXNG locale.
cd docker/searxng && docker compose up -d
cd ../..

# 2. Vérifier les fournisseurs configurés.
uv run python mywi.py search check
# searxng yes / brave no / serper no / serpapi no / tavily no

# 3. Exécuter une recherche et amorcer un Land.
uv run python mywi.py land create --name=DemoSearch --desc="search router demo"
uv run python mywi.py search run --land=DemoSearch \
                          --query="humanités numériques" \
                          --limit=20 --strategy=fallback
```

#### Commandes

| Commande | Description |
|---------|-------------|
| `uv run python mywi.py search check` | Tableau configuré / non configuré par fournisseur |
| `uv run python mywi.py search run --land=X --query=… [--limit=20] [--strategy=fallback\|parallel] [--language=fr] [--providers=searxng,brave]` | Exécute la recherche, dédoublonne les URLs **après normalisation d'URL** (les variantes d'une même page — trackers, ordre des paramètres, Wayback — sont fusionnées en un seul résultat : fournisseurs concaténés, meilleur rang conservé, titre et extrait complétés s'ils manquaient), insère les Expressions dans le Land. **`--limit` plafonne les résultats PAR FOURNISSEUR**, et non au total : avec `--strategy=parallel` et deux fournisseurs, vous pouvez obtenir jusqu'à `limit x providers` URLs distinctes (la liste fusionnée n'est jamais tronquée — la tronquer jetterait la triangulation pour laquelle `parallel` existe). Avec `fallback`, vous en obtenez au plus `limit`, fournies par le premier fournisseur qui répond. `SearchQuery.num_requested` stocke donc un chiffre par fournisseur. |
| `uv run python mywi.py search list --land=X` | Liste les lignes `SearchQuery` passées d'un Land |
| `uv run python mywi.py search usage --land=X` | Rapport d'usage agrégé par fournisseur (appels, erreurs, statut, quota) |

#### Configuration

Ajoutez à `settings.py` les clés dont vous disposez. Le fichier dot-env n'est lu que par **Docker Compose** — il n'y a pas de chargeur dotenv dans `mwi/`, donc une clé placée là est invisible pour une exécution locale `uv run python mywi.py` :

```bash
SEARXNG_BASE_URL=http://localhost:8888  # défaut
BRAVE_API_KEY=...                       # optionnel
SERPER_API_KEY=...                      # optionnel
SERPAPI_API_KEY=...                     # optionnel (repli sur l'ancien serpapi_api_key)
TAVILY_API_KEY=...                      # optionnel
SEARCH_DEFAULT_STRATEGY=fallback        # ou "parallel"
SEARCH_PROVIDER_TIMEOUT=30              # secondes
```

Une clé manquante désactive silencieusement le fournisseur correspondant — le
routeur ne lève jamais d'erreur sur un fournisseur non configuré.

> 📘 **Documentation complète** :
> - Guide utilisateur : [`docs/search_router.md`](docs/search_router.md) (commandes, cadre légal, reproductibilité JOSS).
> - Guide développeur : [`docs/search_router_architecture.md`](docs/search_router_architecture.md) (diagramme de séquence, recette pour ajouter un nouveau fournisseur).
> - Mise en place de SearXNG : [`docs/searxng_setup.md`](docs/searxng_setup.md).

---

### 7. Supprimer un land ou des expressions

Supprimer un land entier, ou seulement les expressions situées sous un seuil de pertinence.

- Supprimer un land entier :
  ```bash
  uv run python mywi.py land delete --name="MyResearchTopic"
  ```
- Supprimer les expressions dont la pertinence est inférieure à une valeur donnée :
  ```bash
  uv run python mywi.py land delete --name="MyResearchTopic" --maxrel=MAXIMUM_RELEVANCE
  # p. ex., --maxrel=1 supprime les pages de pertinence 0
  ```
  `--maxrel` est un **entier** et la comparaison est **stricte**
  (`relevance < maxrel`) : la plus petite valeur utile est donc `1`. Une valeur
  inférieure à 1 est **refusée** : la pertinence est soit NULL, soit un entier
  positif ou nul, donc `relevance < 0` ne correspondrait à rien, et un `--maxrel`
  nu (qu'argparse lit comme `0`) était autrefois pris pour « aucun seuil » et
  supprimait le land entier. Omettez complètement l'option si c'est ce que vous
  voulez.

  Avant de supprimer, la commande annonce exactement ce qu'elle s'apprête à
  retirer et attend un `Y` :

  ```text
  the ENTIRE land "MyResearchTopic" and all its data (1843 expression(s)) will be deleted, type 'Y' to proceed :
  12 crawled expression(s) with relevance < 1 in land "MyResearchTopic" will be deleted, type 'Y' to proceed :
  ```
- Supprimer les pages peu pertinentes **et** les liens non crawlés qu'elles ont laissés orphelins :
  ```bash
  # Prévisualiser d'abord (compte les orphelins, ne supprime rien)
  uv run python mywi.py land delete --name="MyResearchTopic" --maxrel=1 --prune-orphans --dry-run
  # Puis appliquer
  uv run python mywi.py land delete --name="MyResearchTopic" --maxrel=1 --prune-orphans
  ```
  Supprimer les pages de pertinence 0 retire leurs liens sortants ; les URLs non
  crawlées qu'elles avaient découvertes peuvent alors se retrouver sans aucun lien
  entrant. `--prune-orphans` supprime ces expressions inatteignables et toujours non
  crawlées (`depth > 0`, jamais récupérées, aucun lien entrant). Les URLs de départ
  (`depth 0`), les pages crawlées et les liens encore atteignables depuis une page
  conservée sont toujours gardés.

| Option         | Type | Requis | Défaut | Description                                         |
|----------------|------|--------|--------|-----------------------------------------------------|
| --name         | str  | Oui    |        | Nom du land à supprimer                             |
| --maxrel       | int  | Non    |        | Ne supprime que les expressions crawlées dont `relevance < maxrel`. Doit être **>= 1** ; une valeur inférieure ou nue est refusée. Omettez-la pour supprimer le land entier. |
| --prune-orphans| flag | Non    | False  | Après la suppression par --maxrel, supprime aussi les expressions non crawlées restées sans lien entrant (depth>0, fetched_at IS NULL). Sans --maxrel, n'élague que les URLs non crawlées actuellement orphelines (ne supprime jamais le land entier). |
| --dry-run      | flag | Non    | False  | Aperçu seulement : indique combien d'expressions/orphelins seraient supprimés, sans rien supprimer |
| --vacuum       | flag | Non    |        | Lance VACUUM après la suppression pour récupérer l'espace disque (lent sur les grosses bases) |


## Lands multilingues

Le calcul de la pertinence tient compte de la langue : la tokenisation et le
stemming utilisent la ou les langues déclarées sur le land (`--lang`), et pas
seulement le français.

```bash
# Land monolingue anglais
uv run python mywi.py land create --name="EnglishTopic" --desc="..." --lang=en

# Land multilingue : un lemme par langue pour chaque terme (correspondance par union)
uv run python mywi.py land create --name="BilingualTopic" --desc="..." --lang=fr,en
uv run python mywi.py land addterm --land="BilingualTopic" --terms="work, policy"
```

Points clés :

- **Langues de stemming prises en charge** (Snowball, ISO 639-1) : `ar`, `da`, `de`,
  `en`, `es`, `fi`, `fr`, `hu`, `it`, `nl`, `no`, `pt`, `ro`, `ru`, `sv`.
  Une langue non prise en charge se replie sur l'identité en minuscules (pas de stemming).
- La **tokenisation** utilise le modèle punkt NLTK propre à chaque langue quand il
  existe ; `ar`, `hu` et `ro` n'ont pas de modèle punkt et utilisent un tokenizer
  de repli compatible unicode (les écritures cyrillique, arabe et grecque sont
  entièrement prises en charge).
- Chaque page est tokenisée et stemmée dans **sa propre langue** quand elle
  appartient aux langues du land, sinon dans la langue primaire du land.
- `search run` et `land urlist` héritent de la langue primaire du land quand
  `--language` / `--lang` n'est pas fourni.
- Les **lands non francophones existants**, créés avant cette fonctionnalité, ont
  été lemmatisés avec le stemmer français. Corrigez-les avec :

  ```bash
  uv run python mywi.py db migrate                      # ajoute word.lang (migration 011)
  uv run python mywi.py land relemm --name="EnglishTopic"  # re-stemme les termes + recalcule la pertinence
  ```

## Collecte de données

### 1. Crawler les URLs du land

Crawler les URLs ajoutées à un land pour en récupérer le contenu.

```bash
uv run python mywi.py land crawl --name="MyResearchTopic" [--limit=NUMBER] [--http=HTTP_STATUS_CODE] [--retry-status=CSV]
```

| Option         | Type   | Requis | Défaut           | Description                                                                 |
|----------------|--------|--------|------------------|-----------------------------------------------------------------------------|
| --name         | str    | Oui    |                  | Nom du land dont les URLs sont à crawler                                    |
| --limit        | int    | Non    |                  | Nombre maximal d'URLs à crawler lors de cette exécution                     |
| --http         | str    | Non    |                  | Re-crawler uniquement les pages qui ont précédemment abouti à cette erreur HTTP (ex. 503) |
| --retry-status | str    | Non    |                  | Codes à relancer, séparés par des virgules, en ignorant `fetched_at` (ex. `403,429`) |
| --depth        | int    | Non    |                  | Ne crawler que les URLs restant à crawler à la profondeur indiquée          |
| --fullhtml     | str    | Non    | (défaut du land) | Surcharger la politique de stockage HTML du land (`TRUE`/`FALSE`) pour ce crawl |
| --issuecrawl   | flag   | Non    | désactivé        | Forcer la gate OpenRouter en mode analyse de controverse pour cette exécution (voir ci-dessous) ; en son absence, la gate applique la valeur par défaut du réglage `openrouter_issue_mode` |

**Exemples :**
```bash
uv run python mywi.py land crawl --name="AsthmaResearch"
uv run python mywi.py land crawl --name="AsthmaResearch" --limit=10
uv run python mywi.py land crawl --name="AsthmaResearch" --http=503
uv run python mywi.py land crawl --name="AsthmaResearch" --depth=2
uv run python mywi.py land crawl --name="AsthmaResearch" --depth=1 --limit=5
uv run python mywi.py land crawl --name="AsthmaResearch" --fullhtml=TRUE   # archiver le HTML brut
uv run python mywi.py land crawl --name="AsthmaResearch" --retry-status=403,429   # rattrapage par la cascade
uv run python mywi.py land crawl --name="AsthmaResearch" --issuecrawl     # gate en mode analyse de controverse
```

> **Mode analyse de controverse (`--issuecrawl`)** — quand la gate OpenRouter
> est activée, `--issuecrawl` la force en *mode issue* pour cette exécution, en
> remplaçant la valeur par défaut du réglage `openrouter_issue_mode`. En mode
> issue, la gate ne conserve que les pages éditoriales / de prise de position
> qui engagent l'enjeu du projet (une position, un argument, une opinion, une
> analyse ou une information substantielle) et rejette les pages
> d'index/sommaire/navigation ainsi que les pages génériques de présentation
> d'entreprise. Voir
> [Gate de pertinence OpenRouter](#optionnel--gate-de-pertinence-openrouter-filtre-ia-ouinon)
> pour plus de détails.

> **Cascade anti-Cloudflare** — quand `aiohttp` renvoie un statut « rattrapable »
> (`403`, `406`, `429`, `503`, `520`, `521`, `523`, `526`, `ERR`), MWI bascule
> automatiquement sur `curl_cffi` (imitation de l'empreinte TLS, activé par
> défaut), puis, en option, sur Playwright (`crawl_fallback_playwright=True`
> pour l'activer, ~3-5 s/page), puis sur archive.org. La stratégie qui a
> finalement fourni le HTML est enregistrée dans `expression.fetch_method`
> (visible dans `uv run python mywi.py land list`).
> Utilisez `--retry-status=403,429` pour rejouer la cascade sur des URLs déjà
> crawlées sans réinitialiser leur `fetched_at`. Bloc de configuration :
> clés `crawl_fallback_*` dans `settings-example.py`.
>
> **Les certificats TLS ne sont pas vérifiés pendant `land crawl`.** C'est un
> arbitrage assumé, pas un oubli : les sites institutionnels à certificat expiré
> ou mal configuré sont fréquents dans les corpus anciens, et les écarter
> biaiserait silencieusement l'échantillon. Conséquence : sur ce seul chemin de
> code, le serveur d'origine n'est pas authentifié cryptographiquement — une
> page stockée pourrait en principe provenir d'un intermédiaire non authentifié.
> Tous les autres chemins réseau (`land readable`, `land medianalyse`,
> `land reanalyze`, `domain crawl`, `heuristic update --fetch-missing`, et
> le repli `curl_cffi`) vérifient bien les certificats. Réactivez la
> vérification si vous collectez un jour depuis un réseau que vous ne maîtrisez pas.

> **Archivage du HTML brut (`--fullhtml`, sprint-html)** — quand l'option est
> active, le HTML brut renvoyé par la cascade est persisté dans `expression.html`
> **avant** toute étape d'extraction. Ainsi, une page téléchargée avec succès
> mais dont l'analyse par Trafilatura/BeautifulSoup a échoué (interstitiels
> Cloudflare, sites JS-only, markup cassé) est quand même archivée —
> exactement les cas pour lesquels on active généralement l'option.
> La taille stockée est plafonnée à `settings.fullhtml_max_size_kb`
> (défaut 5 MB par page) pour protéger le cache WAL de SQLite contre les
> pages pathologiques ; mettez le plafond à `0` pour le désactiver. Contrôlez
> à tout moment la taille de l'archive avec `uv run python mywi.py land list --name=X`
> (ligne `Full HTML: policy=ON — N stored (X.Y MB)`) ou directement
> en SQL :
> ```sql
> SELECT fetch_method,
>        SUM(CASE WHEN html IS NOT NULL THEN 1 ELSE 0 END) AS with_html,
>        COUNT(*) AS total
>   FROM expression WHERE land_id=?
>   GROUP BY fetch_method;
> ```

> **Astuce (Bash)** — Lancer plusieurs petits lots peut être plus rapide qu'un seul crawl géant. Sous macOS/Linux, vous pouvez boucler le crawler en une ligne :
> ```bash
> for i in {1..100}; do uv run python mywi.py land crawl --name="melenchon" --depth=0 --limit=100; done
> ```
> La boucle est une option de **débit**, pas d'exhaustivité. Jusqu'en
> 2026-09, elle était silencieusement indispensable : le découpage en lots
> utilisait `OFFSET` sur une sélection que le crawler rétrécit lui-même, si bien
> qu'une seule exécution n'atteignait qu'environ la moitié des URLs en attente
> et qu'il fallait la relancer. C'est corrigé — un seul `land crawl` visite
> désormais chaque expression en attente. Si un ancien land signale encore
> « remaining to crawl » après une exécution menée à son terme, crawlez-le
> simplement une fois de plus.

---

### 2. Récupérer le contenu lisible (pipeline Mercury Parser)

Extraire un contenu lisible de haute qualité avec le **pipeline autonome Mercury Parser**. Ce système moderne offre une extraction de contenu intelligente, avec des stratégies de fusion configurables et un enrichissement automatique des médias et des liens.

**Prérequis :** nécessite l'outil en ligne de commande `mercury-parser` — sauf pour
les pages dont le HTML brut est déjà stocké (`--fullhtml`), qui sont extraites
localement et n'atteignent jamais Mercury :
```bash
sudo npm install -g @postlight/mercury-parser
```

> **Chemin du HTML stocké.** Quand `expression.html` est disponible, le pipeline
> en extrait le contenu avec exactement le même appel Trafilatura que le crawl :
> les deux chemins ne peuvent donc pas diverger, et relancer `land readable` sur
> un land `--fullhtml` ne réécrit pas inutilement chaque page (ce qui rejouerait
> aussi la gate LLM). Jusqu'en 2026-09, ce chemin remplissait un champ interne
> que le pipeline ne lisait jamais : les pages ressortaient datées comme « lues »
> avec un corps vide. Par ailleurs, un `readable` non vide n'est jamais remplacé
> par un contenu **plus court** — le HTML stocké est plafonné par
> `settings.fullhtml_max_size_kb`, si bien que ré-extraire depuis une archive
> tronquée ne pourrait que perdre du texte.
>
> Si un land a été touché, réinitialisez le marqueur sur les pages vides et
> relancez (sauvegardez d'abord, voir [Garder le schéma de base à jour](#garder-le-schéma-de-base-à-jour)) :
> ```sql
> UPDATE expression SET readable_at = NULL
>  WHERE land_id = <id> AND html IS NOT NULL
>    AND (readable IS NULL OR readable = '');
> ```
> puis `land readable`, puis `land consolidate`.

**Commande :**
```bash
uv run python mywi.py land readable --name="MyResearchTopic" [--limit=NUMBER] [--depth=NUMBER] [--merge=STRATEGY] [--llm=true|false] [--issuecrawl]
```

| Option   | Type   | Requis | Défaut  | Description                                         |
|----------|--------|--------|---------|-----------------------------------------------------|
| --name   | str    | Oui    |         | Nom du land à traiter                               |
| --limit  | int    | Non    |         | Nombre maximal de pages à traiter lors de cette exécution |
| --depth  | int    | Non    |         | Profondeur de crawl maximale à traiter (ex. 2 = URLs de départ + 2 niveaux) |
| --merge  | str    | Non    | smart_merge | Stratégie de fusion du contenu (voir ci-dessous) |
| --llm    | bool   | Non    | false   | Activer la vérification de pertinence OpenRouter (`true` pour l'activer) |
| --issuecrawl | flag | Non  | désactivé | Forcer la gate OpenRouter en mode analyse de controverse pour cette exécution (remplace la valeur par défaut du réglage `openrouter_issue_mode`) |

**Stratégies de fusion :**

- **`smart_merge`** (défaut) : fusion intelligente selon le type de champ
  - Titres : préfère les titres les plus longs et les plus informatifs
  - Contenu : Mercury Parser est prioritaire (extraction plus propre)
  - Descriptions : conserve la version la plus détaillée
  
- **`mercury_priority`** : Mercury écrase toujours les données existantes
  - À utiliser pour une migration de données ou quand on préfère l'extraction Mercury
  
- **`preserve_existing`** : ne remplit que les champs vides, n'écrase jamais rien
  - Option sûre pour enrichir sans perte de données

**Fonctionnalités du pipeline :**

- **Extraction de haute qualité** : Mercury Parser assure un excellent nettoyage du contenu
- **Logique bidirectionnelle** : 
  - Base vide + contenu Mercury → remplit depuis Mercury
  - Base pleine + Mercury vide → préserve la base (s'abstient)
  - Base pleine + Mercury plein → applique la stratégie de fusion
- **Enrichissement automatique** : 
  - Extrait et rattache les fichiers médias (images, vidéos)
  - Crée des liens entre expressions à partir des URLs découvertes
  - Met à jour les métadonnées (auteur, date de publication, langue)
  - Recalcule les scores de pertinence

**Exemples :**
```bash
# Extraction de base avec fusion intelligente (défaut)
uv run python mywi.py land readable --name="AsthmaResearch"

# Ne traiter que les 50 premières pages, avec une limite de profondeur
uv run python mywi.py land readable --name="AsthmaResearch" --limit=50 --depth=2

# Stratégie Mercury prioritaire (écrase les données existantes)
uv run python mywi.py land readable --name="AsthmaResearch" --merge=mercury_priority

# Stratégie conservatrice (ne remplit que les champs vides)
uv run python mywi.py land readable --name="AsthmaResearch" --merge=preserve_existing

# Avancé : traitement limité avec une stratégie précise
uv run python mywi.py land readable --name="AsthmaResearch" --limit=100 --depth=1 --merge=smart_merge

# Déclencher la validation OpenRouter (nécessite une configuration OpenRouter)
uv run python mywi.py land readable --name="AsthmaResearch" --llm=true

# Valider en mode analyse de controverse (mode issue) pour cette exécution
uv run python mywi.py land readable --name="AsthmaResearch" --llm=true --issuecrawl
```

**Sortie :** le pipeline fournit des statistiques détaillées, notamment :
- Nombre d'expressions traitées
- Taux de succès/d'erreur
- Nombre de mises à jour par type de champ
- Indicateurs de performance

**Remarque :** ce pipeline remplace l'ancienne fonctionnalité readable et apporte une meilleure qualité de contenu, davantage de robustesse et des stratégies de fusion souples selon les cas d'usage.

---

### 3. Capturer les métriques SEO Rank

Récupérer les métriques SEO Rank de chaque expression et stocker le JSON brut de la réponse dans la base de données.

**Prérequis :**

- Renseignez `seorank_api_key` dans `settings.py` ou exportez `MWI_SEORANK_API_KEY` avant de lancer la commande.
- Ajustez éventuellement `seorank_request_delay` pour respecter la politique de limitation de débit du fournisseur (défaut : une seconde entre deux appels).

**Commande :**
```bash
uv run python mywi.py land seorank --name="MyResearchTopic" [--limit=NUMBER] [--depth=NUMBER] [--force]
```

| Option   | Type    | Requis | Défaut  | Description |
|----------|---------|--------|---------|-------------|
| --name   | str     | Oui    |         | Land dont les expressions seront enrichies |
| --limit  | int     | Non    |         | Nombre maximal d'expressions à interroger lors de cette exécution |
| --depth  | int     | Non    |         | Restreindre aux expressions d'une profondeur de crawl donnée |
| --http   | str     | Non    | 200     | Filtrer par statut HTTP (`all` pour désactiver le filtre) |
| --minrel | int     | Non    | 1       | Ne traiter que les expressions dont la `relevance` est ≥ à cette valeur |
| --force  | boolean | Non    | False   | Récupérer à nouveau même si `expression.seorank` contient déjà des données |

**Comportement :**

- Par défaut, seules les expressions sans données SEO Rank sont sélectionnées. Utilisez `--force` pour rafraîchir les entrées existantes.
- `--http` vaut `200` par défaut ; passez `--http=all` (ou `any`) pour inclure tous les codes de statut.
- `--minrel` (entier) vaut `1` par défaut ; mettez `0` pour inclure les pages de pertinence `0`.
- `--limit` s'applique après le filtrage ; fixez-le pour garder une exécution courte pendant les tests.
- Chaque appel réussi stocke la réponse JSON telle quelle dans la colonne `expression.seorank` (champ texte).
- Les erreurs et les réponses HTTP autres que 200 sont journalisées, et la commande passe à l'URL suivante.

**Exemple :**
```bash
# Enrichir les 100 premières URLs de départ (profondeur 0) du land "AsthmaResearch"
uv run python mywi.py land seorank --name="AsthmaResearch" --depth=0 --limit=100

# Rafraîchir toutes les réponses stockées, quelles que soient les valeurs actuelles
uv run python mywi.py land seorank --name="AsthmaResearch" --force
```

**Astuce :** une fois les données stockées, vous pouvez les inspecter directement via SQLite (`SELECT seorank FROM expression WHERE id=…`) ou les charger en Python avec `json.loads` pour vos analyses en aval.

**Champs de la réponse (API SEO Rank) :**
- `sr_domain` – domaine auquel se rapportent les métriques.
- `sr_rank` – score SEO Rank global du fournisseur (plus la valeur est basse, plus l'autorité est forte).
- `sr_kwords` – nombre de mots-clés suivis pour lesquels le domaine est actuellement classé.
- `sr_traffic` – estimation des visites organiques mensuelles attribuées au domaine.
- `sr_costs` – coût estimé (en USD) du trafic organique, en équivalent publicitaire.
- `sr_ulinks` – nombre de liens sortants trouvés sur l'URL analysée.
- `sr_hlinks` – nombre total de liens entrants pointant vers l'URL (tous les liens HTTP).
- `sr_dlinks` – nombre de domaines référents uniques qui pointent vers l'URL.
- `fb_comments` – commentaires Facebook enregistrés pour l'URL.
- `fb_shares` – partages Facebook enregistrés pour l'URL.
- `fb_reac` – réactions Facebook (j'aime, etc.) enregistrées pour l'URL.


### 4. Analyse des médias

Analyser les fichiers médias (images, vidéos, audio) associés aux expressions d'un land. Cette commande récupère les médias, analyse leurs propriétés et stocke les résultats dans la base de données.

```bash
uv run python mywi.py land medianalyse --name=LAND_NAME [--depth=DEPTH] [--minrel=MIN_RELEVANCE]
```

| Option | Type | Requis | Défaut | Description |
|---|---|---|---|---|
| `--name` | str | Oui | | Nom du land dont les médias sont à analyser. |
| `--depth` | int | Non | 0 | N'analyser que les médias des expressions jusqu'à cette profondeur de crawl. |
| `--minrel` | int | Non | 0 | N'analyser que les médias des expressions dont la pertinence est supérieure ou égale à cette valeur. |

**Exemple :**
```bash
uv run python mywi.py land medianalyse --name="AsthmaResearch" --depth=2 --minrel=1
```

**Remarques :**
- Ce traitement télécharge les fichiers médias pour en faire une analyse détaillée.
- La configuration de l'analyse des médias (ex. `media_min_width`, `media_max_file_size`) se trouve dans `settings.py`.
- Les résultats — dimensions, taille de fichier, format, couleurs dominantes, données EXIF et empreintes — sont stockés dans la base de données.
- **Deux empreintes, deux questions.** `image_hash` est un SHA-256 des octets téléchargés et répond à la question *« est-ce le même FICHIER ? »* — réencodez un PNG à un autre niveau de compression et l'empreinte n'a plus aucun rapport. `perceptual_hash` est un dHash de 64 bits et répond à la question *« est-ce la même IMAGE ? »* — une photo reprise par un autre média après une recompression ou un redimensionnement garde une empreinte proche, ce qui permet de mesurer la circulation des images dans un corpus. Jusqu'en 2026-09, seule la première existait, sous un commentaire et une documentation qui la qualifiaient de « perceptuelle ».
- **`perceptual_hash` est NULL sur tout ce qui a été analysé avant la migration 016.** Cette empreinte ne peut pas être remplie rétroactivement depuis la base de données — les octets ne sont pas stockés. Lancez `uv run python mywi.py db migrate`, puis `uv run python mywi.py land reanalyze --name=LAND` pour la remplir. Cela retélécharge un fichier par média : sur un gros land, procédez par étapes avec `--limit`.
- **Vos mesures survivent à `land consolidate`.** Depuis 2026-09, la consolidation réconcilie les lignes de médias par URL au lieu de les supprimer puis de les recréer : les médias analysés conservent donc leur `id` et leurs colonnes d'enrichissement.
- `land readable` (Mercury) ne voit que **les images markdown**. Les médias vidéo, audio et `<img>` HTML découverts par le crawl sont toujours supprimés sur ce chemin — c'est antérieur au travail de réconciliation et inchangé. Lancez `land consolidate` après `land readable` si vous devez les récupérer.

**Verbes de maintenance des médias :**

```bash
# Statistiques agrégées : totaux, formats, tranches de dimensions/tailles, doublons par hash
uv run python mywi.py land media_stats --name=LAND_NAME [--near=5]

# Dry-run pur : compte + jusqu'à 20 URLs d'exemple de médias non conformes (rien n'est supprimé)
uv run python mywi.py land preview_deletion --name=LAND_NAME [--minwidth=N] [--minheight=N] [--maxsize=MB]

# Re-analyse des médias (jamais analysés / en erreur d'abord) ;
# --suppress supprime les médias non conformes APRÈS confirmation
uv run python mywi.py land reanalyze --name=LAND_NAME [--limit=N] [--minwidth=N] [--minheight=N] [--maxsize=MB] [--suppress]
```

Les critères par défaut viennent de `settings.media_min_width`, `media_min_height`
et `media_max_file_size`.

---

### 5. Crawler les domaines

Récupérer des informations sur les domaines identifiés à partir des expressions ajoutées aux lands.

```bash
uv run python mywi.py domain crawl [--limit=NUMBER] [--http=HTTP_STATUS_CODE]
```

| Option   | Type   | Requis | Défaut  | Description                                                                 |
|----------|--------|--------|---------|-----------------------------------------------------------------------------|
| --limit  | int    | Non    |         | Nombre maximal de domaines à crawler lors de cette exécution                |
| --http   | str    | Non    |         | Re-crawler uniquement les domaines qui ont précédemment abouti à cette erreur HTTP (ex. 503). `ERR` correspond à **tous** les statuts d'échec (`ERR_*`, `ARC_NO_HTML`, `REQ_NO_HTML`, `000`) |

**Exemples :**
```bash
uv run python mywi.py domain crawl
uv run python mywi.py domain crawl --limit=5
uv run python mywi.py domain crawl --http=404
uv run python mywi.py domain crawl --http=ERR   # relancer tous les domaines en échec
```

---

## Exporter les données

Exportez les données de vos lands ou de vos tags pour les analyser dans d'autres outils.

### 1. Exporter les données d'un land

Exportez les données d'un land dans différents formats.

`pagecsv` et `pagegexf` incluent tous les champs SEO Rank stockés dans `expression.seorank` ; les valeurs manquantes ou `unknown` sont exportées sous la forme `na`.


```bash
uv run python mywi.py land export --name="MyResearchTopic" --type=EXPORT_TYPE [--minrel=MINIMUM_RELEVANCE]
```

| Option   | Type   | Requis | Défaut | Description                                                                 |
|----------|--------|--------|--------|-----------------------------------------------------------------------------|
| --name   | str    | Oui    |        | Nom du land à exporter                                                      |
| --type   | str    | Oui    |        | Type d'export (voir ci-dessous)                                             |
| --minrel | int    | Non    |        | Pertinence minimale des expressions incluses dans l'export                  |

**Valeurs d'EXPORT_TYPE :**
- `pagecsv` : CSV des pages
- `pagegexf` : graphe GEXF des pages — **arêtes inter-domaines uniquement**. Une arête entre deux pages du même site est écartée, alors que `nodelinkcsv` (`*_pageslinks.csv`) et `pagesjson` la conservent. C'est délibéré (une carte de pages dans Gephi se lit en général pour la circulation entre sites), mais cela signifie que le GEXF et le CSV d'un même land ne portent pas le même nombre d'arêtes : utilisez `nodelinkcsv` ou `pagesjson` pour le graphe de pages complet.
- `fullpagecsv` : CSV avec le contenu complet des pages
- `nodecsv` : CSV des nœuds
- `nodegexf` : graphe GEXF des nœuds
- `mediacsv` : CSV des liens de médias
- `corpus` : corpus de texte brut
- `pseudolinks` : CSV des paires sémantiques de paragraphes (expression source/cible, domaine, indices de paragraphe, score de relation, confiance, extraits)
- `pseudolinkspage` : CSV des pseudolinks agrégés au niveau des pages (expression↔expression). Colonnes : Source_ExpressionID, Target_ExpressionID, Source_DomainID, Target_DomainID, PairCount, EntailCount, NeutralCount, ContradictCount, AvgRelationScore, AvgConfidence.
- `pseudolinksdomain` : CSV des pseudolinks agrégés au niveau des domaines (domaine↔domaine). Colonnes : Source_DomainID, Source_Domain, Target_DomainID, Target_Domain, PairCount, EntailCount, NeutralCount, ContradictCount, AvgRelationScore, AvgConfidence. Les paires intra-domaine (self-loops dans le graphe de domaines) sont exclues.
- `nodelinkcsv` : produit 4 fichiers CSV pour une analyse de réseau complète :
  - `*_pagesnodes.csv` : nœuds expressions avec tous les champs (id, url, domain_id, domain_name, title, description, keywords, lang, relevance, depth, http_status, created_at, published_at, fetched_at, approved_at, readable_at, validllm, validmodel) + colonnes SEO Rank dynamiques (sr_rank, sr_traffic, fb_shares, etc.)
  - `*_pageslinks.csv` : tous les liens entre expressions (source_id, source_url, source_domain_id, target_id, target_url, target_domain_id, context, dom, **kind**). Les self-loops (source = cible) ne sont jamais exportés. `kind` est la zone structurelle du lien (`body`, `nav`, `toc`, `reco`, `ref`) — voir **Profils de liens** ci-dessous ; les lignes écrites avant la migration 014 n'ont pas de kind et sont exportées comme `body`.
  - `*_domainnodes.csv` : nœuds domaines avec agrégations (id, name, title, description, http_status, nbexpressions, average_relevance, first_expression_date, last_expression_date)
  - `*_domainlinks.csv` : liens inter-domaines agrégés (source_domain_id, source_domain_name, target_domain_id, target_domain_name, link_count)
  - Avec `--fullhtml=TRUE` (nécessite un land crawlé avec `--fullhtml`), émet les 4 fichiers `*fullhtml.csv` **à la place** des 4 de base — le flag *bascule* le réseau exporté (il ne s'ajoute pas) : lancez donc un export séparé sans lui pour obtenir aussi le réseau MyWI. Ces fichiers forment le **réseau de liens brut**, reconstruit à partir de *tous* les `<a href>` de `expression.html` (réseau fermé — cibles restreintes aux pages du corpus qualifiées par `--minrel`). `*_pageslinksfullhtml.csv` utilise les colonnes Gephi `Source,Target,Weight` (Weight laissé vide), plus `weightbody` (`1` si l'arête existe dans `ExpressionLink`), `weighthtml` (multiplicité des ancres brutes pour les arêtes trouvées seulement dans le HTML stocké) et `citation` (`1` si le lien apparaît dans le markdown `readable` de la page source — une citation écrite dans le texte par l'auteur ; `0` pour les liens de navigation, de pied de page ou raw-only, ou quand le readable est absent) ; `*_domainlinksfullhtml.csv` utilise `in_mwi` + `out_mwi`. Cela permet de comparer le réseau de liens de *citation* de MyWI (`ExpressionLink`, issu du contenu lisible) au réseau *toute la page* d'un crawler classique. L'export affiche un rapport de couverture en trois volets (raw∩mywi / raw\mywi / mywi\raw). Sans HTML stocké, les fichiers sont émis vides (en-tête seul) avec un avertissement.
- `nodesjson` : graphe de **domaines** sous forme de fichier JSON force-graph `{nodes, links}` (pour `react-force-graph`, D3, Sigma). Un nœud par domaine portant au moins une expression de `relevance >= minrel`, avec 9 champs analytiques (`id, name, title, description, keywords, nbexpressions, average_relevance, first_expression_date, last_expression_date`) **plus** `corpus` — un tableau trié des expressions de ce domaine, chacune un objet imbriqué `{title, urlarticle, description, published_at}`. Les liens sont des arêtes inter-domaines orientées, avec `value` = nombre de liens page à page. La sortie est déterministe. Conforme à `docs/graph.schema.json`.
- `pagesjson` : graphe de **pages** sous forme de fichier JSON force-graph `{nodes, links}`. Un nœud par `Expression` avec les champs de `pagecsv` (moins `depth`/`readable`), `tags` en tableau trié et `seorank` en objet imbriqué (`{}` s'il est absent). Les valeurs absentes sont des `null` JSON (et non la sentinelle `na` du CSV). Les liens sont les arêtes page à page du réseau fermé `minrel` (intra-domaine conservé, pas d'agrégation, self-loops exclus). La sortie est déterministe. Conforme à `docs/graph.schema.json`.
- `htmldump` (sprint-html E) : archive zip du HTML brut stocké via
  `--fullhtml`. Contient un `{expression_id}.html` par expression dont
  `html IS NOT NULL`, plus un `manifest.csv` listant
  `id, url, http_status, fetch_method, fetched_at, relevance, size_bytes`
  pour les outils de réplication en aval. Ignore les expressions sans HTML stocké ;
  respecte `--minrel` comme les autres exports.

**Exemples :**
```bash
uv run python mywi.py land export --name="AsthmaResearch" --type=pagecsv
uv run python mywi.py land export --name="AsthmaResearch" --type=corpus --minrel=0.7
uv run python mywi.py land export --name="AsthmaResearch" --type=pseudolinks
uv run python mywi.py land export --name="AsthmaResearch" --type=pseudolinkspage
uv run python mywi.py land export --name="AsthmaResearch" --type=pseudolinksdomain
uv run python mywi.py land export --name="AsthmaResearch" --type=nodelinkcsv --minrel=1
uv run python mywi.py land export --name="AsthmaResearch" --type=nodelinkcsv --fullhtml=TRUE --minrel=1  # réseau brut seul (omettre le flag pour les 4 de base)
uv run python mywi.py land export --name="AsthmaResearch" --type=nodelinkcsv --link-profile=all  # conserve tous les kinds de liens
uv run python mywi.py land export --name="AsthmaResearch" --type=nodelinkcsv --minrel=1 --resolve-twins=TRUE  # rattache les liens enregistrés sur des jumelles d'URL
```

#### Profils de liens (`--link-profile`)

Chaque lien porte un **kind structurel** qui indique où il se situe dans la page
source : `body` (le fil principal du texte), `nav` (menus, en-têtes, pieds de
page), `toc` (sommaires et grilles d'ancres), `reco` (blocs de recommandation),
`ref` (blocs de références). Le kind est décidé uniquement par des règles
**structurelles** déterministes — position DOM, ancêtres de sectionnement,
densité d'ancres, part de prose —, jamais par les mots de la page : elles valent
donc pour toutes les langues.

| profil | kinds exportés |
|---|---|
| `citation` (défaut) | `body`, `ref` |
| `citation+reco` | `body`, `ref`, `reco` |
| `all` | tous les kinds |

Les blocs de références sont **conservés** par défaut : ce sont des citations,
et les exclure coûte bien plus en citations perdues qu'il ne rapporte en bruit
retiré.

Deux choses ne changent jamais avec le profil : les lignes sans kind (écrites
avant la migration 014) sont toujours traitées comme `body`, et le **réseau
toute la page** (`*pageslinksfullhtml.csv`) n'est **jamais filtré** — c'est le
comparateur qui sert à juger le réseau body ; le filtrer supprimerait donc la
mesure.

Redéfinissez les profils dans `settings.py` via `link_profiles`.

#### Rattachement des jumelles d'URL (`--resolve-twins`)

Le crawl rattache un lien à une fiche par égalité **exacte** de l'URL
normalisée, et la normalisation conserve le slash final par défaut
(`trailing_slash = "preserve"`). Un lien de corps de texte écrit
`https://site.org/page/` alors que la page du corpus est `https://site.org/page`
est donc enregistré vers une seconde fiche, une **jumelle** d'URL jamais crawlée
(pertinence NULL). Le réseau fermé de l'export écarte cette arête, tandis que la
passe HTML brute de `--fullhtml`, qui résout les liens par une correspondance
tolérante à trois clés (URL normalisée ; URL en minuscules sans slash final ;
hôte sans `www` plus chemin), retrouve le même lien et le classe comme lien du
seul HTML brut (`weightbody = 0`, `citation = 1`).

`--resolve-twins=TRUE` (`nodelinkcsv` seulement) applique cette même
correspondance aux liens de corps de texte, sur le même périmètre :

- toute ligne d'`ExpressionLink` dont la source passe `--minrel` mais pas la
  cible est rattachée à la page du corpus que désigne son URL (variante de slash
  final, de `www`, de `http`/`https` ou de casse du chemin) ;
- une cible que la correspondance ne sait pas placer (aucune correspondance, ou
  clé partagée par deux pages du corpus) reste dehors ; un rattachement qui
  retombe sur la page source est écarté comme boucle ;
- quand une arête directe et une ou plusieurs jumelles aboutissent à la même
  paire (source, cible), **une seule** arête est conservée : le meilleur kind
  d'abord (`body` > `ref` > `reco` > `toc` > `nav`), la ligne directe avant la
  jumelle en cas d'égalité ; la ligne retenue fournit `context` et `dom` ;
- `--link-profile` filtre le kind **retenu** dans `*_pageslinks.csv` et
  `*_domainlinks.csv` ; `*_pageslinksfullhtml.csv` n'est toujours jamais filtré ;
- les fichiers de nœuds ne changent pas : le périmètre du réseau fermé est le
  même.

L'option lit la base et n'y écrit jamais. Sans elle (défaut `FALSE`), la sortie
est la sortie historique, octet pour octet. L'export affiche le nombre d'arêtes
rattachées. Sur un export `--fullhtml`, une arête `weightbody = 0` portant
`citation = 1` signale une jumelle non résolue ; avec l'option, il ne doit plus
y en avoir.

```bash
uv run python mywi.py land export --name="AsthmaResearch" --type=nodelinkcsv --minrel=1 --resolve-twins=TRUE
uv run python mywi.py land export --name="AsthmaResearch" --type=nodelinkcsv --minrel=1 --fullhtml=TRUE --resolve-twins=TRUE
```

```bash
uv run python mywi.py land export --name="AsthmaResearch" --type=nodesjson --minrel=1  # graphe de domaines JSON force-graph
uv run python mywi.py land export --name="AsthmaResearch" --type=pagesjson --minrel=1  # graphe de pages JSON force-graph
uv run python mywi.py land export --name="AsthmaArchive"  --type=htmldump --minrel=1
```

---

### 2. Exporter les données des tags

Exportez les données fondées sur les tags d'un land.

```bash
uv run python mywi.py tag export --name="MyResearchTopic" --type=EXPORT_TYPE [--minrel=MINIMUM_RELEVANCE]
```

| Option   | Type   | Requis | Défaut | Description                                                                 |
|----------|--------|--------|--------|-----------------------------------------------------------------------------|
| --name   | str    | Oui    |        | Nom du land dont on exporte les tags                                        |
| --type   | str    | Oui    |        | Type d'export (voir ci-dessous)                                             |
| --minrel | int    | Non    |        | Pertinence minimale du contenu tagué inclus dans l'export                   |

**Valeurs d'EXPORT_TYPE :**
- `matrix` : matrice de co-occurrence des tags
- `content` : contenu associé aux tags

**Exemples :**
```bash
uv run python mywi.py tag export --name="AsthmaResearch" --type=matrix
uv run python mywi.py tag export --name="AsthmaResearch" --type=content --minrel=1
```

---

## Mettre à jour les domaines depuis les réglages d'heuristiques

Regroupe le domaine de chaque expression à l'aide de la **table unifiée des
heuristiques de plateformes** (`mwi/platform_heuristics.py`, 144 entrées
**hébergeurs** — éditeurs exclus ; `{host: {"url", "html"}}` ;
surcharge via `settings.platform_heuristics`). Elle remplace le dictionnaire plat
`settings.heuristics`. **Seules les plateformes listées sont regroupées** ; tout
autre hôte garde son netloc nu.

```bash
# Règles URL sur les plateformes listées (sûr — jamais de re-baseline global)
uv run python mywi.py heuristic update --land=LAND

# Aperçu sans écrire
uv run python mywi.py heuristic update --land=LAND --dry-run

# Résout les plateformes listées depuis le HTML de la page (signal déclaratif par plateforme)
uv run python mywi.py heuristic update --land=LAND --html

# Land sans fullhtml : récupère le HTML manquant à la volée (--limit est obligatoire)
uv run python mywi.py heuristic update --land=LAND --html --fetch-missing --limit=500
```

Options :

- `--land=LAND` — restreint à un land. `--limit=N` — plafonne le nombre d'expressions
  traitées (ou de récupérations avec `--fetch-missing`). `--dry-run` — aperçu, n'écrit rien.
- `--html` — résout l'entité éditoriale d'une plateforme listée depuis le HTML de la
  page, via son signal déclaratif (`ldjson_author` / `canonical` / `og_url` /
  `rel_author` / `ldjson_publisher`), au lieu de l'URL.
- `--fetch-missing` — avec `--html`, récupère à la volée le HTML des pages d'hôtes
  listés qui n'ont pas de HTML stocké. **Exige un `--limit` explicite** ; le HTML est
  utilisé, pas persisté.

Aucune migration de base n'est nécessaire.

### Reconstruction complète du corpus (récupération / re-baseline)

`heuristic update` ne touche que les plateformes listées. Pour recalculer le
domaine de **toutes** les expressions depuis leur URL (par ex. pour nettoyer les
résidus de chemins de section laissés par un ancien état des heuristiques),
utilisez l'outil de reconstruction autonome — dry-run par défaut, `--apply` pour
écrire, par lots et à partir de l'URL seule (sans réseau) :

```bash
uv run python scripts/reconstruct_domains.py --name=LAND --db=data/mwi_x.db
uv run python scripts/reconstruct_domains.py --name=LAND --db=data/mwi_x.db --apply
```

## Pipeline de consolidation des lands

Le pipeline `land consolidate` sert à recalculer et à réparer la structure interne d'un land après que la base a été modifiée par des applications tierces (comme MyWebClient) ou par des scripts externes.

**Objectif :**  
- Recalcule le score de pertinence de chaque page crawlée (expressions dont `fetched_at` n'est pas nul).
- Ré-extrait et reconstruit tous les liens sortants (ExpressionLink) de ces pages.
- **Réconcilie** les médias (Media) par URL au lieu de les reconstruire : un média encore référencé par la page garde sa ligne — même `id`, mêmes mesures (dimensions, EXIF, empreintes, couleurs dominantes) —, un média disparu du contenu est supprimé, et un nouveau est ajouté. Avant 2026-09, chaque consolidation effaçait puis recréait ces lignes : les douze colonnes d'enrichissement revenaient à NULL et l'`id` changeait, ce qui cassait silencieusement les jointures externes sur `mediacsv.id` (mwiR). Si vos mesures ont été perdues ainsi, `land medianalyse` (ou `land reanalyze`) les recalcule.
- Ajoute les documents manquants référencés par des liens.
- Reconstruit le graphe de liens, en remplaçant toute donnée périmée ou incohérente.
- **Respecte les verdicts LLM stockés** : après le recalcul lexical, toute expression avec `validllm='non'` garde `relevance=0` — la consolidation ne ressuscite jamais une page que le LLM a rejetée auparavant (`validllm='oui'` ou NULL applique le score lexical comme avant).

**Quand l'utiliser :**  
- Après avoir importé ou modifié des données dans la base avec des outils externes (par ex. MyWebClient).
- Pour rétablir la cohérence si les liens ou les médias ne correspondent plus au contenu réel des pages.

**Commande :**
```bash
uv run python mywi.py land consolidate --name=LAND_NAME [--limit=LIMIT] [--depth=NbDEEP] [--minrel=MIN_RELEVANCE] [--llm=true|false] [--issuecrawl]
```
- `--name` (obligatoire) : nom du land à consolider.
- `--limit` (facultatif) : nombre maximal de pages à traiter.
- `--depth` (facultatif) : ne traite que les pages à la profondeur de crawl indiquée.
- `--minrel` (facultatif) : ne traite que les pages dont la pertinence est ≥ cette valeur.
- `--llm` (facultatif, défaut `false`) : si `true`, relance la gate de pertinence OpenRouter par expression (même idiome que `land readable --llm=true`), rafraîchit `validllm`/`validmodel`, puis applique la règle de verdict ci-dessus. Si OpenRouter n'est pas configuré, le flag est ignoré avec un avertissement et la consolidation continue sans LLM (en respectant toujours les verdicts stockés). Utilisez `--limit`/`--depth`/`--minrel` pour borner les appels au LLM.
- `--issuecrawl` (facultatif) : avec `--llm=true`, force la gate en mode « analyse de controverse » pour cette exécution (prend le pas sur la valeur par défaut du réglage `openrouter_issue_mode`).

**Exemple :**
```bash
uv run python mywi.py land consolidate --name="AsthmaResearch" --depth=0

# Revalider avec la gate LLM pendant la consolidation
uv run python mywi.py land consolidate --name="AsthmaResearch" --llm=true --limit=200

# Idem, en mode analyse de controverse
uv run python mywi.py land consolidate --name="AsthmaResearch" --llm=true --issuecrawl
```

**Remarques :**
- Seules les pages déjà crawlées (`fetched_at` renseigné) sont concernées.
- **Tout ou rien, page par page.** Chaque expression est d'abord entièrement préparée (pertinence, extraction des liens, gate LLM facultative), et seulement ensuite réécrite dans une transaction unique et courte. Si quoi que ce soit échoue en cours de route — base verrouillée, incident disque, Ctrl-C —, la page garde ses liens, médias et métadonnées précédents au lieu d'en être dépouillée. La consolidation est aussi désormais exhaustive en une seule passe, y compris avec `--minrel` (elle sautait auparavant environ un quart des pages sur lesquelles elle filtrait).
- La consolidation n'appelle **pas** le LLM par défaut ; elle se contente de respecter les verdicts déjà stockés, sauf si `--llm=true` est passé.
- Pour chaque page, le nombre de liens et de médias extraits est affiché.
- Ce pipeline est particulièrement utile après des imports massifs, des migrations, ou avec des clients tiers qui ne maintiennent pas forcément tous les invariants de MyWI.

---

## Pipeline de normalisation des URLs

Toute URL ingérée par MWI (URLs de départ, résultats SerpAPI, liens extraits au
moment du crawl, liens issus de Mercury Parser) passe par `mwi.url_normalizer.normalize_url`
**avant** d'être insérée en base. Cela garantit une forme canonique unique par
page logique et évite les Expressions en double dues aux variantes d'URL
(snapshots Wayback, paramètres de pistage, ancres, casse de l'hôte).

**Configuration** — voir `settings.url_normalization` (et `settings-example.py`).
Défauts conservateurs : `unwrap_archive`, `lowercase_host`, `strip_trackers`,
`normalize_query_order` sont à ON ; `force_https`, `strip_www`,
`strip_mobile_subdomain` sont à OFF (activation explicite requise via les
variables d'environnement `MWI_URL_FORCE_HTTPS=true`, `MWI_URL_STRIP_WWW=true`,
`MWI_URL_STRIP_MOBILE=true`).

**Provenance** — quand la normalisation modifie l'URL, la forme d'origine est
conservée dans `Expression.original_url` (NULL sinon). Permet l'audit
rétrospectif sans relancer le crawl.

**Normalisation rétroactive** — les Lands créés avant ce pipeline peuvent être
mis à jour avec :

```bash
# Toujours sauvegarder d'abord !
# Sauvegarde compatible WAL. Un simple `cp data/mwi.db` NE suffit PAS : la base
# tourne en mode WAL, les transactions validées vivent donc dans data/mwi.db-wal
# jusqu'à un checkpoint — copier le seul fichier principal peut les perdre.
sqlite3 data/mwi.db ".backup data/mwi.db.bak_$(date +%Y%m%d_%H%M%S)"

# Aperçu (aucune écriture en base)
uv run python mywi.py land normalize --name=LAND_NAME --dry-run --verbose

# Application
uv run python mywi.py land normalize --name=LAND_NAME

# Application + remise à zéro de http_status pour que les URLs renommées soient recrawlées la fois suivante
uv run python mywi.py land normalize --name=LAND_NAME --reset-status

# Exporte la correspondance old_id -> new_id (produite aussi en --dry-run)
uv run python mywi.py land normalize --name=LAND_NAME --dry-run --mapping-out=plan.csv
```

**Ce que fait `land normalize`** — les Expressions sont planifiées par groupe
d'URL canonique (toutes les variantes qui convergent vers la même cible
appartiennent à un même groupe) :

- Si la forme canonique n'est présente sur **aucune** ligne : la **variante la
  plus riche est promue** (html > readable > relevance > fetched_at >
  plus petit id) — UPDATE en place, `original_url` rempli — et les autres
  variantes du groupe y sont fusionnées. Cela traite les variantes http/https,
  www et slash final lorsque les règles correspondantes viennent d'être
  activées (deux lignes ne finissent jamais par partager la même URL).
- Si la forme canonique **est** déjà une Expression : chaque variante y est
  fusionnée — remappage de tous les `ExpressionLink` (entrants et sortants)
  vers la canonique, suppression des self-loops et des doublons préexistants,
  **remplissage des champs de contenu vides de la canonique** (`html`,
  `readable`, `title`, métadonnées, verdict LLM sous forme de paire
  `(validllm, validmodel)` ; `depth` prend le minimum ; `relevance` n'est pas
  touchée — lancez `land consolidate` ensuite pour la recalculer) à partir du
  doublon, sans jamais écraser un champ non vide, puis DELETE de l'Expression
  redondante (la CASCADE supprime ses Media, Paragraph et TaggedContent).
- **Ce que la cascade détruit, et ce qui le rétablit.** `Media` revient avec
  `land consolidate` (et `land medianalyse` pour les mesures) ; `Paragraph` /
  embeddings / similarités reviennent avec `embedding generate` puis
  `embedding similarity` ; **`TaggedContent` ne revient pas du tout**. Les
  extraits tagués sont des annotations manuelles — rien ne peut les recalculer.
  **Exportez-les avant de normaliser** : `uv run python mywi.py tag export --name=LAND
  --type=content`. (Cette page affirmait jusqu'en 2026-09 que la consolidation
  reconstruisait les trois ; elle n'a jamais touché à Paragraph ni à TaggedContent.)
- Les chaînes Wayback-de-Wayback sont résolues transitivement en une seule passe.
- Le bilan compte `renamed`, `promoted`, `merged`, `collision groups` et les
  champs `backfilled`. En `--dry-run`, les volumes de remappage de liens et de
  cascade restent à 0 (ils ne sont calculés qu'à l'application).

**Runbook de dédoublonnage** (doublons de variantes : http/https, www, slash
final) — pour résorber un corpus existant pollué par des lignes qui sont des
variantes d'une même URL :

```bash
# 1. Sauvegarde (checkpoint du WAL d'abord)
sqlite3 data/mwi.db "PRAGMA wal_checkpoint(TRUNCATE);"
# Sauvegarde compatible WAL. Un simple `cp data/mwi.db` NE suffit PAS : la base
# tourne en mode WAL, les transactions validées vivent donc dans data/mwi.db-wal
# jusqu'à un checkpoint — copier le seul fichier principal peut les perdre.
sqlite3 data/mwi.db ".backup data/mwi.db.bak_$(date +%Y%m%d_%H%M%S)"

# 2. Activer les règles strictes (les fixer aussi dans settings.py pour que les
#    crawls futurs continuent de les appliquer — sinon les variantes réapparaissent)
export MWI_URL_FORCE_HTTPS=true
export MWI_URL_STRIP_WWW=true
# et modifier settings.py : "trailing_slash": "strip"  (pas de surcharge par variable d'environnement)

# 3. Auditer, puis appliquer (interruptible, relançable, converge)
uv run python mywi.py land normalize --name=LAND_NAME --dry-run --verbose
uv run python mywi.py land normalize --name=LAND_NAME

# 4. Vérifier : un second dry-run signale 0 changement, et
#    SELECT url, COUNT(*) FROM expression WHERE land_id=? GROUP BY url
#    HAVING COUNT(*)>1;  ne renvoie aucune ligne

# 5. Recalculer la pertinence et reconstruire liens/médias depuis les readables fusionnés
uv run python mywi.py land consolidate --name=LAND_NAME
```

Les doublons exacts hérités (plusieurs lignes partageant déjà la même URL
canonique) sont aussi résorbés : la ligne la plus riche survit, ses sœurs y sont
fusionnées. Limites connues : `https://site.com` et `https://site.com/` ne
convergent que sous la politique `strip` (le défaut `preserve` en garde deux nœuds) ;
`--limit` plafonne les groupes de collision, et un groupe n'est jamais coupé (les relances convergent). Sur de très grosses bases,
préférez travailler sur une copie locale (les E/S SQLite sur un disque synchronisé
dans le cloud sont lentes), puis remettez le fichier en place.

**Circuit breaker archive.org** — quand archive.org est injoignable (ce qui
arrive fréquemment depuis 2024), le repli Wayback du pipeline readable ouvre un
breaker valable pour tout le processus après 5 échecs consécutifs et saute le
repli pendant 5 minutes. Économise jusqu'à ~10 s par expression pendant les pannes.

**Travailler sur une autre base que `data/mwi.db`** — chaque commande CLI
accepte un flag global `--db PATH` qui remplace l'emplacement du fichier SQLite.
Utile pour des projets menés en parallèle, des sauvegardes, ou des fichiers reçus
de collaborateurs qui ne s'appellent pas `mwi.db` :

```bash
uv run python mywi.py land normalize --name=foo --db /path/to/projectA.db --dry-run
uv run python mywi.py db migrate --db ./backups/melenchon_v2.db
uv run python mywi.py land export --name=bar --db /tmp/incoming.db --type=pagecsv
```

Alternative sans modification du code : `MYWI_DATA_DIR=/some/dir uv run python mywi.py …`
(le fichier doit alors s'appeler `mwi.db` dans ce dossier).

---

## Tests

MyWI inclut une suite de tests aux standards JOSS. Lancez `make test` : sa dernière ligne
donne les chiffres du jour. Attendez-vous à **2 skips** — les deux tests réseau réels
(curl_cffi, Playwright), ignorés par construction — et à quelques tests
**désélectionnés** : ceux qui exigent une clé d'API (`make test-apis`) ou une instance
SearXNG active (`make test-integration`). Couverture ~87 % à la dernière mesure
(10 juin 2026).

### Démarrage rapide

```bash
# Installer les dépendances de test (uv installe automatiquement le groupe dev — pytest,
# pytest-asyncio, aioresponses, pytest-cov). Repli pip : pip install -r requirements.txt
uv sync

# Tests de base, sans clés API, sans réseau (environ une minute). Les cibles Make appellent `uv run` en interne.
make test

# Idem, avec rapport de couverture (ouvrir htmlcov/index.html)
make test-cov
```

### Structure des tests

La suite est à plat et numérotée, `tests/test_NN_*.py`, un fichier par domaine de
comportement. `make list-tests` affiche chaque test ; les comptes par fichier bougent
trop souvent pour valoir la peine d'être recopiés ici.

| Fichiers | Domaine |
|-------|------|
| `test_01` – `test_08` | Socle : installation et migrations, gestion des lands, crawl et extraction, exports, analyse des médias, embeddings, workflows de bout en bout, stockage du HTML brut (`--fullhtml`) |
| `test_09` | Normalisation des URLs |
| `test_10` – `test_15` | Cascade de récupération (aiohttp → curl_cffi → Playwright → archive.org), `fetch_method`, `--retry-status`, pool de navigateurs partagé |
| `test_16` | Routeur SerpAPI (`land urlist`) |
| `test_17` – `test_25` | Routeur de recherche multi-API : modèles, les cinq fournisseurs, routeur, contrôleur, intégration |
| `test_26` | Lands multilingues |
| `test_27` | Correctifs de la CLI (confirmations, `--http=ERR`, troncature, dry-run) |
| `test_28` – `test_31` | Contexte des liens, réseau de liens du HTML brut, parseur de liens markdown, consolidation des liens |
| `test_32` | Verdicts LLM respectés par `consolidate`, mode controverse |
| `test_33` | Heuristiques de domaine |
| `test_34` – `test_38` | Liens du corps : banc hors ligne, extraction, classification `kind`, export `--link-profile`, pipeline de normalisation |
| `test_39` – `test_50` | Robustesse et reproductibilité : sous-processus Mercury, empreinte perceptuelle, pagination keyset, consolidate atomique, gardes de dry-run, lots du readable, codes de sortie, occurrences de paragraphes, workflow CI, gate LLM asynchrone, déterminisme des exports, liens des README |
| `test_51` | Statistiques du planificateur SQLite et pragmas |
| `test_52` | Codage des liens par quatre juges LLM |
| `test_53` | Rattachement des jumelles d'URL à l'export (`--resolve-twins`) |

Les anciens smoke tests (`test_cli.py`, `test_core.py`, etc.) se trouvent dans `tests/legacy/` et sont conservés à titre de référence ; `make test` les exécute aussi.

### Toutes les cibles Make

| Commande | Rôle |
|---------|---------|
| `make test` (alias `make test-basic`) | Suite par défaut, sans clés API |
| `make test-quick` | N'exécute que `test_01_installation.py` (smoke test) |
| `make test-all` | Exécute *tous* les tests, y compris ceux qui nécessitent des clés API |
| `make test-cov` / `make test-cov-open` | Rapport de couverture (ouvert dans le navigateur) |
| `make test-apis` | Tests conditionnés par `MWI_SERPAPI_API_KEY`, `MWI_SEORANK_API_KEY`, `MWI_OPENROUTER_API_KEY` |
| `make test-integration` | Tests de bout en bout lents (réseau) |
| `make lint` / `make lint-all` / `make typecheck` | flake8 classe bugs / flake8 complet / mypy — les trois bloquent la CI |
| `make bench-cache` / `make bench-links` / `make bench-determinism` | Banc hors ligne des liens du corps (voir [`benchmarks/body_links/README.md`](benchmarks/body_links/README.md)) |
| `make test-01` … `make test-05` | Raccourcis par fichier |
| `make check` | `test-quick` + `test-cov` (recommandé pour la CI) |
| `make joss-test` | Rejoue le flux d'évaluation JOSS |
| `make list-tests` / `make list-markers` | Aides à la découverte |
| `make clean` | Supprime `.pytest_cache`, `htmlcov`, `__pycache__` |

### Tests d'API

Les tests qui appellent des API externes sont automatiquement ignorés en l'absence de clés :

```bash
export MWI_SERPAPI_API_KEY="your_key"
export MWI_SEORANK_API_KEY="your_key"
export MWI_OPENROUTER_API_KEY="your_key"
make test-apis
```

### Pour aller plus loin

**`--db PATH`** redirige le fichier SQLite et **rien d'autre** : le fichier doit déjà exister, et les exports ainsi que `lands/<id>/` vont toujours dans `settings.data_location`. Pointer `--db` vers la base d'un autre projet écrit donc les exports de ce projet dans le dossier de données *courant*.

Pour la définition des marqueurs pytest, voir `pytest.ini`. Pour la configuration de la CI, voir `.github/workflows/ci.yml`.

La CI bloque sur trois contrôles : `make lint` (la classe bugs de flake8 : erreurs de
syntaxe, noms non définis, comparaisons impossibles), `make lint-all` (flake8 complet) et
`make typecheck` (mypy). Les trois sont à zéro : un seul message fait échouer le build.
La CI exécute flake8 sous Python 3.12, qui inspecte aussi les champs des f-strings : un
environnement local en 3.11 peut remonter moins de messages. Pour reproduire le verdict
de la CI : `uv run --locked --python 3.12 flake8 mwi/ --count` (ce qui reconstruit le
`.venv` sous Python 3.12).

# Embeddings & pseudolinks (guide utilisateur)

## Objectif
- Construire des vecteurs au niveau du paragraphe (embeddings) à partir des pages, puis relier les paragraphes similaires d'une page à l'autre (« pseudolinks »).
- En option, classer chaque paire avec un modèle NLI (entailment/neutral/contradiction).
- Exporter les liens entre paragraphes, ainsi que des liens agrégés au niveau des pages et des domaines.

Flux type
1) Crawl + extraction du texte lisible
2) Génération des embeddings (vecteurs de paragraphes)
3) Calcul des similarités (cosinus ou ANN+NLI)
4) Export en CSV (paragraphe/page/domaine)

## Pré-requis & installation
- Base de données initialisée et pages dotées d'un texte lisible.
- Installer les dépendances (uv — recommandé) :
  ```bash
  uv sync                # base
  uv sync --extra ml     # + NLI + accélération FAISS
  ```
- Repli pip (sans uv) :
  ```bash
  python3 -m venv .venv && source .venv/bin/activate
  python -m pip install -U pip
  python -m pip install -r requirements.txt          # base
  python -m pip install -r requirements-ml.txt       # + NLI + accélération FAISS
  ```
- Vérification rapide de l'environnement :
  ```bash
  uv run python mywi.py embedding check
  ```


## Modèles
- Multilingue (recommandé) :
  - MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7
- Repli léger (anglais) :
  - typeform/distilbert-base-uncased-mnli
- À définir dans `settings.py:nli_model_name` (les deux exemples y sont documentés).

## Réglages (référence des clés)
- Embeddings (bi-encodeur) :
  - `embed_provider` : 'fake' | 'http' | 'openai' | 'mistral' | 'gemini' | 'huggingface' | 'ollama'
  - `embed_model_name`, `embed_batch_size`, `embed_min_paragraph_chars`, `embed_max_paragraph_chars`
  - `embed_similarity_method` : 'cosine' | 'cosine_lsh'
  - `embed_similarity_threshold` (pour les méthodes fondées sur le cosinus)
- Rappel ANN et NLI :
  - `similarity_backend` : 'faiss' | 'bruteforce'
  - `similarity_top_k` : nombre de voisins par paragraphe pour le rappel ANN
  - `nli_model_name`, `nli_fallback_model_name`
  - `nli_backend_preference` : 'auto' | 'transformers' | 'crossencoder' | 'fallback'
  - `nli_batch_size`, `nli_max_tokens`
  - `nli_torch_num_threads` : threads Torch (définir aussi `OMP_NUM_THREADS` à l'exécution)
  - `nli_progress_every_pairs`, `nli_show_throughput`
- Variables d'environnement CPU (à exporter dans votre shell) :
  - `OMP_NUM_THREADS=N` (threads OpenMP de FAISS/Torch/NumPy)
  - Optionnel : `MKL_NUM_THREADS=N`, `OPENBLAS_NUM_THREADS=N`, `TOKENIZERS_PARALLELISM=false`

## Commandes & paramètres
- Générer les embeddings :
  ```bash
  uv run python mywi.py embedding generate --name=LAND [--limit N]
  ```
- Calculer les similarités (au choix) :
  - Cosinus (exact) :
    ```bash
    uv run python mywi.py embedding similarity --name=LAND --method=cosine \
      --threshold=0.85 [--minrel R]
    ```
  - Cosinus LSH (approché) :
    ```bash
    uv run python mywi.py embedding similarity --name=LAND --method=cosine_lsh \
      --lshbits=20 --topk=15 --threshold=0.85 [--minrel R] [--maxpairs M]
    ```
  - ANN + NLI :
    ```bash
    uv run python mywi.py embedding similarity --name=LAND --method=nli \
      --backend=faiss|bruteforce --topk=10 [--minrel R] [--maxpairs M]
    ```
- Exporter les CSV :
  - Paires de paragraphes :
    ```bash
    uv run python mywi.py land export --name=LAND --type=pseudolinks
    ```
  - Agrégation au niveau des pages :
    ```bash
    uv run python mywi.py land export --name=LAND --type=pseudolinkspage
    ```
  - Agrégation au niveau des domaines :
    ```bash
    uv run python mywi.py land export --name=LAND --type=pseudolinksdomain
    ```
- Utilitaires :
  - Vérifier l'environnement : `uv run python mywi.py embedding check`
  - Réinitialiser les embeddings d'un land : `uv run python mywi.py embedding reset --name=LAND` (demande une confirmation `Y` ; `--force` la contourne)

## Dépannage & précautions
- « Partout `score_raw=0.5` et `score=0` » → repli neutre ; installer les extras ML ou passer au modèle EN sûr.
- « Pas de colonne `score_raw` » → lancer une fois `uv run python mywi.py db migrate`.
- Segfaults sous macOS (OpenMP/Torch) : venv pip-only ; essayer `OMP_NUM_THREADS=1`, puis augmenter ; en option `KMP_DUPLICATE_LIB_OK=TRUE`.
- Calcul des scores trop lent : diminuer `nli_batch_size`, augmenter modérément les threads, filtrer avec `--minrel`, plafonner avec `--maxpairs`.
- Trop de paires : relever `threshold`, augmenter `lshbits`, réduire `topk`, ou utiliser `--minrel`.

## Bonnes pratiques — performance

Repères rapides pour arbitrer entre vitesse et qualité :

- Taille petite/moyenne (≤ ~50k paragraphes)
  - Méthode simple et rapide : `cosine` avec `--threshold=0.85` et `--minrel=1`.
  - Exemple :
    ```bash
    uv run python mywi.py embedding similarity --name=LAND --method=cosine \
      --threshold=0.85 --minrel=1
    ```

- Grande taille (≥ ~100k paragraphes)
  - Préférer `cosine_lsh` (approché) et borner l'éventail des voisins (fan-out) ainsi que la sortie :
    - `--lshbits=18–22` (20 par défaut)
    - `--topk=10–20`
    - `--threshold=0.85–0.90`
    - `--minrel=1–2`
    - `--maxpairs` pour plafonner le nombre total de paires (par ex. 5–10M)
  - Exemple :
    ```bash
    uv run python mywi.py embedding similarity --name=LAND --method=cosine_lsh \
      --lshbits=20 --topk=15 --threshold=0.88 --minrel=1 --maxpairs=8000000
    ```

- NLI (ANN + cross-encoder)
  - Utiliser FAISS pour le rappel s'il est disponible : `--backend=faiss`.
  - Commencer petit : `--topk=6–10`, `--minrel=1–2`, `--maxpairs=20k–200k`.
  - Choisir le modèle :
    - Smoke test / passage rapide sur CPU : DistilBERT MNLI (EN) → `typeform/distilbert-base-uncased-mnli`.
    - Qualité multilingue : DeBERTa XNLI → `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7` (nécessite `sentencepiece`).
  - Régler :
    - `nli_batch_size=32–96` selon la RAM.
    - `nli_max_tokens=384–512` si vous voulez tronquer un peu plus pour gagner en vitesse.
  - Exemple :
    ```bash
    uv run python mywi.py embedding similarity --name=LAND --method=nli \
      --backend=faiss --topk=8 --minrel=2 --maxpairs=20000
    ```

- CPU & threads (dans votre venv)
  - Définir les threads : `export OMP_NUM_THREADS=N` (FAISS/Torch/NumPy),
    et `settings.py:nli_torch_num_threads = N` (intra-op Torch).
  - Règle empirique : N = (cœurs disponibles − 1) pour garder de la marge au système.
  - Garder `TOKENIZERS_PARALLELISM=false` pour éviter un surcoût inutile.

- Débit & logs
  - Suivre la progression toutes les `nli_progress_every_pairs` paires, avec le débit (paires/s) et l'ETA.
  - Si le débit est faible, diminuer `nli_max_tokens` ou `nli_batch_size`, et/ou relever `--minrel`.

## Choix du modèle et replis

- Le modèle NLI par défaut peut être multilingue (basé sur DeBERTa) et nécessiter `sentencepiece`.
- Alternative sûre (anglais) : `typeform/distilbert-base-uncased-mnli`.
- À configurer dans `settings.py:nli_model_name`.
- Si des dépendances manquent, le code peut se replier sur un prédicteur neutre (`score=0`, `score_raw=0.5`).

## Progression & logs

- Le rappel journalise toutes les quelques centaines de paragraphes (nombre de paires candidates).
- Le calcul des scores NLI journalise la progression toutes les `settings.nli_progress_every_pairs` paires, avec le débit et l'ETA.
- Le résumé final affiche le nombre total de paires, le temps écoulé et les paires/s.

## Méthodes de similarité

Choisissez une méthode avec `--method` lorsque vous lancez `embedding similarity` :

- `cosine` : cosinus exact paire par paire (O(n²)) sur les embeddings.
  - Adapté aux ensembles petits/moyens. Utilise `--threshold` et, en option, `--minrel`.
  - N'utilise pas FAISS.
- `cosine_lsh` : approché, répartition en buckets par hyperplans LSH + force brute locale.
  - Passe bien à l'échelle sans bibliothèque externe. Utilise `--lshbits`, `--topk`, `--threshold`, `--minrel`, `--maxpairs`.
  - N'utilise pas FAISS.
- `nli` (alias : `ann+nli`, `semantic`) : ANN + cross-encoder NLI, en deux étapes.
  - Étape 1 (rappel) : top-k ANN par paragraphe, via FAISS s'il est disponible, sinon en force brute.
  - Étape 2 (précision) : le cross-encoder NLI renvoie RelationScore ∈ {-1, 0, 1} et ConfidenceScore.
  - Utilise `--backend`, `--topk`, `--minrel`, `--maxpairs`. Voir plus bas pour FAISS.

## Choisir le backend ANN (FAISS)

- Installer FAISS (optionnel) : `uv sync --extra ml` (repli pip : `python -m pip install -r requirements-ml.txt`).
- Surcharge en CLI : `--backend=faiss` pour forcer le rappel FAISS avec `--method=nli`.
- Défaut dans les réglages : `similarity_backend = 'faiss'` pour préférer FAISS quand aucun `--backend` n'est précisé.
- Repli : si FAISS n'est pas installé ou si son import échoue, le rappel utilise automatiquement `bruteforce`.
- Vérifier : `uv run python mywi.py embedding check` affiche `FAISS: available` quand il est détecté.

## Similarité à grande échelle (lands volumineux)

Pour les grandes collections (de centaines de milliers à des millions de paragraphes), préférez la méthode fondée sur LSH et contraignez la recherche et la sortie :

```bash
# Buckets LSH + top-k par paragraphe + plafond strict du nombre total de paires
uv run python mywi.py embedding similarity \
  --name=MyResearchTopic \
  --method=cosine_lsh \
  --threshold=0.85 \
  --lshbits=20 \
  --topk=15 \
  --minrel=1 \
  --maxpairs=5000000
```

- `--method=cosine_lsh` : recherche approchée par hyperplans aléatoires ; réduit drastiquement le nombre de paires candidates.
- `--lshbits` : nombre d'hyperplans/bits (plus élevé → buckets plus fins, par ex. 18–22).
- `--topk` : ne garder que les K meilleurs voisins par paragraphe (limite l'éventail des voisins par source).
- `--threshold` : seuil de cosinus ; le relever réduit le nombre de paires.
- `--minrel` : filtre les paragraphes selon la pertinence de l'expression (écarte le contenu de faible valeur).
- `--maxpairs` : plafond strict du nombre de paires écrites en base.

Suggestions de réglage :
- Commencer avec `--lshbits=20`, `--topk=10–20`, `--threshold=0.85`, `--minrel=1`.
- S'il y a trop de paires, augmenter `lshbits`, relever `threshold` ou réduire `topk`.

## Relations NLI (ANN + cross-encoder)

Classer les relations logiques entre paragraphes (entailment/paraphrase = 1, neutral = 0, contradiction = -1) au moyen d'un pipeline en deux étapes : rappel ANN, puis cross-encoder NLI.

Pré-requis (optionnels, à installer seulement si vous avez besoin de NLI ou d'un rappel ANN plus rapide) :
```bash
uv sync --extra ml   # Cross-encoder NLI (sentence-transformers, transformers) + FAISS pour un rappel ANN plus rapide
# Repli pip : python -m pip install -r requirements-ml.txt
```

Exemple de commande :
```bash
# --backend : bruteforce, ou faiss s'il est installé · --topk : candidats par paragraphe issus du rappel ANN
# --minrel : filtre de pertinence optionnel · --maxpairs : plafond de sécurité optionnel
uv run python mywi.py embedding similarity --name=MyResearchTopic --method=nli --backend=bruteforce --topk=50 --minrel=1 --maxpairs=2000000
```

Réglages concernés :
- `nli_model_name` (par défaut : MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7)
- `nli_batch_size` (par défaut : 64)
- `similarity_backend` ('bruteforce' | 'faiss')
- `similarity_top_k` (par défaut : 50)

Recettes rapides :
- Cosinus exact (petit ensemble) :
  ```bash
  uv run python mywi.py embedding similarity --name=MyResearchTopic --method=cosine --threshold=0.85 --minrel=1
  ```
- Cosinus approché (grand ensemble, sans dépendances) :
  ```bash
  uv run python mywi.py embedding similarity --name=MyResearchTopic --method=cosine_lsh --lshbits=20 --topk=15 --threshold=0.85 --minrel=1 --maxpairs=5000000
  ```
- ANN + NLI avec FAISS :
  ```bash
  uv sync --extra ml
  uv run python mywi.py embedding similarity --name=MyResearchTopic --method=nli --backend=faiss --topk=50 --minrel=1 --maxpairs=2000000
  ```

Export CSV (pseudolinks) :
- `uv run python mywi.py land export --name=MyResearchTopic --type=pseudolinks`
- Colonnes : `Source_ParagraphID, Target_ParagraphID, RelationScore, ConfidenceScore, Source_Text, Target_Text, Source_ExpressionID, Target_ExpressionID`

Vérification rapide de l'environnement :
```bash
uv run python mywi.py embedding check
```

Affiche la configuration du fournisseur, les bibliothèques optionnelles (faiss/sentence-transformers/transformers) et la disponibilité des tables de la base.

# Dépannage & réparation

## Garder le schéma de base à jour

Lorsque vous récupérez une version plus récente de MyWI, assurez-vous que votre base existante dispose des dernières colonnes et des derniers index.

```bash
uv run python mywi.py db migrate
```

Cette commande est idempotente : elle inspecte `data/mwi.db` (ou l'emplacement indiqué par `MYWI_DATA_DIR`) et ajoute les champs manquants. Lancez-la après chaque mise à jour ou avant de partager une base. Par précaution, sauvegardez d'abord le fichier :

```bash
# Sauvegarde compatible WAL. Un simple `cp data/mwi.db` ne suffit PAS : la base
# tourne en mode WAL, donc les transactions validées vivent dans data/mwi.db-wal
# jusqu'à un checkpoint — copier le seul fichier principal peut les perdre.
sqlite3 data/mwi.db ".backup data/mwi.db.bak_$(date +%Y%m%d_%H%M%S)"
```

## Réparer l'attribution des domaines archive.org

D'anciens crawls ont parfois rattaché `archive.org` (ou `web.archive.org`) comme `domain` d'une `Expression` alors que le contenu réel provenait d'un autre hôte (repli sur la Wayback Machine). Lancez la commande de maintenance ci-dessous pour réattribuer ces expressions au bon domaine, en réanalysant l'URL archivée :

```bash
# Aperçu seulement — liste les expressions concernées, n'écrit rien
uv run python mywi.py db fix_archive_domains --dry-run

# Appliquer la réattribution
uv run python mywi.py db fix_archive_domains
```

La commande est non destructive — elle se contente de mettre à jour la clé étrangère `expression.domain` et de créer les lignes `Domain` manquantes. Utilisez d'abord `--dry-run` pour examiner ce qui changerait (rien n'est écrit, et aucune ligne `Domain` n'est créée). Lancez-la après un `db migrate` si vous soupçonnez qu'archive.org est surreprésenté dans vos statistiques de domaines.

## Récupération SQLite

Si votre base SQLite est corrompue (par ex. « database disk image is malformed »), vous pouvez tenter une récupération non destructive avec le script utilitaire fourni. Il sauvegarde la base d'origine, essaie `sqlite3 .recover` (puis `.dump` en repli), reconstruit une nouvelle base et vérifie son intégrité.

Prérequis :
- `sqlite3` disponible dans votre shell.

Étapes :
```bash
chmod +x scripts/sqlite_recover.sh
# Utilisation : scripts/sqlite_recover.sh [INPUT_DB] [OUTPUT_DB]
scripts/sqlite_recover.sh data/mwi.db data/mwi_repaired.db
```

Ce que fait le script :
- Sauvegarde `data/mwi.db` (+ `-wal` / `-shm` s'ils existent) dans `data/sqlite_repair_<timestamp>/backup/`
- Tente d'abord `.recover`, se replie sur `.dump` dans `data/sqlite_repair_<timestamp>/dump/`
- Reconstruit `data/mwi_repaired.db`, exécute `PRAGMA integrity_check;` et liste les tables sous `data/sqlite_repair_<timestamp>/logs/`

Validez la base réparée avec MyWI sans remplacer l'originale :
```bash
mkdir -p data/test-repaired
cp data/mwi_repaired.db data/test-repaired/mwi.db
MYWI_DATA_DIR="$PWD/data/test-repaired" uv run python mywi.py land list
```

Si tout semble correct, adoptez la base réparée (après une sauvegarde manuelle) :
```bash
# Sauvegarde compatible WAL. Un simple `cp data/mwi.db` ne suffit PAS : la base
# tourne en mode WAL, donc les transactions validées vivent dans data/mwi.db-wal
# jusqu'à un checkpoint — copier le seul fichier principal peut les perdre.
sqlite3 data/mwi.db ".backup data/mwi.db.bak_$(date +%Y%m%d_%H%M%S)"
mv data/mwi_repaired.db data/mwi.db
```

Remarque : vous pouvez faire pointer temporairement l'application vers un autre répertoire de données grâce à la variable d'environnement `MYWI_DATA_DIR` ; elle remplace `settings.py:data_location` pour cette session.

# Pour les développeurs

## Architecture & fonctionnement interne

### Structure des fichiers & flux

```
mywi.py  →  mwi/cli.py  →  mwi/controller.py  →  mwi/core.py & mwi/export.py
                                     ↘︎ mwi/model.py (Peewee ORM)
                                     ↘︎ mwi/embedding_pipeline.py (paragraph embeddings)
```

- **mywi.py** : point d'entrée console, lance la CLI.
- **mwi/cli.py** : analyse les arguments de la CLI, distribue les commandes aux contrôleurs.
- **mwi/controller.py** : associe les verbes à la logique métier de core/export/model.
- **mwi/core.py** : algorithmes principaux (crawl, parsing, pipelines, calcul des scores, etc.).
- **mwi/export.py** : exporteurs (CSV, GEXF, corpus).
- **mwi/model.py** : schéma de la base de données (ORM Peewee).

### Schéma de données (SQLite, via Peewee)

- **Land** : projet ou sujet de recherche. Colonne notable : `fullhtml` (INTEGER, défaut `0`) — quand elle vaut `1` (via `land create --fullhtml=TRUE`), les crawls de ce Land stockent par défaut le HTML brut de chaque page dans `Expression.html`.
- **Word** : vocabulaire normalisé.
- **LandDictionary** : relation plusieurs-à-plusieurs Land/Word.
- **Domain** : site web / domaine unique.
- **Expression** : URL / page individuelle. Colonnes supplémentaires ajoutées par des migrations récentes :
  - `html` (TEXT, nullable) — HTML brut conservé quand `--fullhtml=TRUE` est en vigueur (migration `007`).
  - `seorank` (TEXT, nullable) — charge utile JSON brute de l'API SEO Rank (migration `006`).
  - `validllm` (`oui`/`non`/null) et `validmodel` (slug du modèle OpenRouter) — verdict LLM en masse (migration `005`).
- **ExpressionLink** : lien orienté entre Expressions.
- **Media** : images, vidéos, audio contenus dans les Expressions.
- **Paragraph / ParagraphEmbedding / ParagraphSimilarity** : stockage des paragraphes, embeddings et liens sémantiques (pseudolinks).
- **Tag** : tags hiérarchiques.
- **TaggedContent** : extraits tagués dans les Expressions.

### Workflows principaux

- **Initialisation du projet** : `uv run python mywi.py db setup`
- **Analyse des médias** : `uv run python mywi.py land medianalyse --name=LAND_NAME [--depth=DEPTH] [--minrel=MIN_RELEVANCE]`
- **Cycle de vie d'un Land** : créer, ajouter des termes, ajouter des URL, crawler, extraire le contenu lisible, exporter, nettoyer/supprimer.
- **Enrichissement SEO Rank** : `uv run python mywi.py land seorank --name=LAND [--limit N] [--depth D] [--force]`
- **Traitement des domaines** : `uv run python mywi.py domain crawl`
- **Export des tags** : `uv run python mywi.py tag export`
- **Mise à jour des heuristiques** : `uv run python mywi.py heuristic update [--land=X] [--html] [--fetch-missing --limit=N]`
- **Embeddings & similarité** :
  - Génération : `uv run python mywi.py embedding generate --name=LAND [--limit N]`
  - Similarité : `uv run python mywi.py embedding similarity --name=LAND [--threshold 0.85] [--method cosine]`

### Notes d'implémentation

- **Score de pertinence** : somme pondérée des occurrences de lemmes dans le titre / le contenu.
- **Lots asynchrones** : concurrence polie pour le crawl.
- **Extraction des médias** : les URL d'images (`.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`, `.bmp`, `.svg`, quelle que soit la casse), de vidéos et de sons sont enregistrées dans `Media` ; leur mesure (dimensions, EXIF, empreintes, couleurs) est une étape distincte, `land medianalyse`.
- **Export** : formats multiples, SQL dynamique, GEXF avec attributs.

### Réglages

Variables clés de `settings.py` :
- `data_location`, `user_agent`, `parallel_connections`, `default_timeout`, `archive`, `heuristics`.

#### Configuration des embeddings
- `embed_provider` : 'fake' (local, déterministe) ou 'http'
- Fournisseurs pris en charge : `fake`, `http`, `openai`, `mistral`, `gemini`, `huggingface`, `ollama`
- `embed_api_url` : URL du fournisseur HTTP générique (POST {"model": name, "input": [texts...]})
- `embed_model_name` : libellé du modèle stocké avec les vecteurs
- `embed_batch_size` : taille des lots lors des appels au fournisseur
- `embed_min_paragraph_chars` / `embed_max_paragraph_chars` : bornes de longueur des paragraphes
- `embed_similarity_threshold` / `embed_similarity_method` : seuil de filtrage et méthode de similarité
  
Clés propres à chaque fournisseur :
- OpenAI : `embed_openai_base_url` (défaut `https://api.openai.com/v1`), `embed_openai_api_key`
- Mistral : `embed_mistral_base_url` (défaut `https://api.mistral.ai/v1`), `embed_mistral_api_key`
- Gemini : `embed_gemini_base_url` (défaut `https://generativelanguage.googleapis.com/v1beta`), `embed_gemini_api_key` (paramètre de requête)
- Hugging Face : `embed_hf_base_url` (défaut `https://api-inference.huggingface.co/models`), `embed_hf_api_key`
- Ollama : `embed_ollama_base_url` (défaut `http://localhost:11434`)
  
Remarques :
- OpenAI/Mistral attendent la charge utile `{ "model": name, "input": [texts...] }` et renvoient `{ "data": [{"embedding": [...]}, ...] }`.
- Gemini utilise `:batchEmbedContents` et renvoie `{ "embeddings": [{"values": [...]}, ...] }`.
- Hugging Face accepte `{ "inputs": [texts...] }` et renvoie généralement une liste de vecteurs.
- Ollama (local) ne traite pas par lots : appels séquentiels à `/api/embeddings` avec `{ "model": name, "prompt": text }`.

#### Optionnel : gate de pertinence OpenRouter (filtre IA oui/non)

Si elle est activée, les pages sont d'abord jugées par un LLM (via OpenRouter) comme pertinentes (oui) ou non (non). Un « non » fixe `relevance=0` et interrompt la suite du traitement ; sinon, la pertinence pondérée classique est calculée. Cela s'applique pendant crawl/readable/`llm validate`, mais pas lors du recalcul en masse (`land addterm`). `land consolidate` n'appelle pas le LLM par défaut mais **respecte** tout verdict `validllm='non'` stocké (et peut relancer la gate avec `--llm=true`).

Les prompts sont **en anglais partout** et énoncent explicitement la langue de
travail du projet (par ex. *« The project's working language is French (fr) »*),
en demandant au modèle de raisonner dans le contexte culturel et linguistique du
projet. Le parseur oui/non accepte à la fois `oui`/`non` et `yes`/`no`.

**Mode analyse de controverse (issue mode)** — quand il est actif, la gate ne
retient que les pages éditoriales / de prise de position qui engagent la
problématique du projet (une position, un argument, une opinion, une analyse ou
une information substantielle) et rejette les pages d'index / de sommaire / de
navigation ainsi que les pages de présentation d'entreprise génériques qui ne
débattent pas de la problématique (tradition de la cartographie des controverses,
Venturini/Latour). Même sémantique de verdict oui/non ; un `non` force toujours
`relevance=0`. Activez-le globalement via le réglage `openrouter_issue_mode`
(variable d'environnement `MWI_OPENROUTER_ISSUE_MODE`), ou pour un run donné avec
le flag `--issuecrawl` sur `land crawl`, `land readable`,
`land consolidate --llm=true` et `land llm validate` (le flag remplace la valeur
par défaut du réglage pour ce run).

Variables configurables par l'environnement :
- `MWI_OPENROUTER_ENABLED` (défaut `false`)
- `MWI_OPENROUTER_API_KEY`
- `MWI_OPENROUTER_MODEL` (par ex. `openai/gpt-4o-mini`, `anthropic/claude-3-haiku`)
- `MWI_OPENROUTER_TIMEOUT` (défaut `15` secondes)
- `MWI_OPENROUTER_MAX_CHARS` (défaut `12000`)
- `MWI_OPENROUTER_MAX_CALLS` (défaut `500`)
- `MWI_OPENROUTER_ISSUE_MODE` (défaut `false`) — mode analyse de controverse global, pour chaque appel à la gate (`openrouter_issue_mode` dans `settings.py`)

Remarque : désactivé ou non configuré, le système se comporte exactement comme avant.

#### Validation LLM en masse (oui/non)
Valide la pertinence en masse via OpenRouter et enregistre le verdict en base (`expression.validllm`, `expression.validmodel`).

Commande :
```bash
uv run python mywi.py land llm validate --name=LAND [--limit N] [--force] [--issuecrawl]
```

Prérequis :
- Dans `settings.py` : réglez `openrouter_enabled=True` et renseignez `openrouter_api_key` et `openrouter_model`.
- Si votre base est ancienne : `uv run python mywi.py db migrate` (ajoute les colonnes manquantes).

Option `--issuecrawl` :
- Force la gate en mode analyse de controverse pour ce run (remplace la valeur par défaut du réglage `openrouter_issue_mode`). Voir [Gate de pertinence OpenRouter](#optionnel--gate-de-pertinence-openrouter-filtre-ia-ouinon).

Comportement :
- Pour chaque expression sans verdict, appelle le LLM pour obtenir une réponse oui/non.
- Enregistre `validllm` = `"oui"|"non"` (en français) et `validmodel` = slug du modèle.
  - Filtrage : ne traite que les expressions sans verdict « oui/non » dont `readable` n'est pas NULL et a une longueur ≥ `openrouter_readable_min_chars`.
  - Respecte `openrouter_readable_min_chars`, `openrouter_readable_max_chars` et `openrouter_max_calls_per_run`.
  - Si le verdict est `"non"`, la `relevance` de l'expression est fixée à `0`.

Option `--force` :
- Inclut aussi dans la sélection les expressions ayant déjà un verdict `"non"` (n'inclut pas les `"oui"`).

#### Enrichissement SEO Rank

La commande `land seorank` enrichit chaque expression avec la charge utile brute de l'API SEO Rank. Configurez ces clés dans `settings.py` (ou via des variables d'environnement) :

- `seorank_api_base_url` : point d'accès de base (par défaut `https://seo-rank.my-addr.com/api2/moz+sr+fb`).
- `seorank_api_key` : clé API requise (`MWI_SEORANK_API_KEY` remplace la valeur par défaut).
- `seorank_timeout` : délai d'expiration des requêtes, en secondes.
- `seorank_request_delay` : pause entre les appels, pour rester poli envers le fournisseur.

Par défaut, la commande ne cible que les expressions avec `http_status = 200` et `relevance ≥ 1` ; passez `--http=all` ou `--minrel=0` pour élargir la sélection.

Sans clé API valide, la commande s'arrête immédiatement. Utilisez `--force` pour rafraîchir les entrées qui contiennent déjà des données dans `expression.seorank`.

#### Amorçage SerpAPI (`land urlist`)

La commande `land urlist` interroge un moteur de recherche SerpAPI (Google par défaut ;
à remplacer avec `--engine=bing|duckduckgo`) et ajoute les nouvelles URL à un land.
Configurez les valeurs suivantes dans `settings.py` ou via des variables
d'environnement :

- `serpapi_api_key` : clé API requise (`MWI_SERPAPI_API_KEY` remplace la valeur par défaut).
- `serpapi_base_url` : point d'accès de base (par défaut `https://serpapi.com/search`).
- `serpapi_timeout` : délai d'expiration HTTP, en secondes.

Les filtres de date (`--datestart`, `--dateend`, `--timestep`) sont optionnels mais,
quand ils sont utilisés, doivent être fournis sous forme de chaînes `YYYY-MM-DD`
valides, et ils exigent `--engine=google` ou `--engine=duckduckgo`. La commande
marque une pause entre les pages (`--sleep`) pour éviter les limites de débit ; ne
la mettez à `0` que pour des tests/mocks. Quand une plage de dates est fournie (ou
quand vous ajoutez `--progress`), la CLI affiche une ligne par fenêtre indiquant
les dates couvertes et le nombre d'URL renvoyées par SerpAPI.

### Tests (vue développeur)

- Suite active : les fichiers numérotés `tests/test_NN_*.py` (inventaire dans [Structure des tests](#structure-des-tests)).
- Les anciens smokes (`test_cli.py`, `test_core.py`, etc.) vivent sous `tests/legacy/`. Ils **sont** exécutés par `make test` : `pytest.ini` fixe `testpaths = tests` et pytest parcourt les sous-dossiers récursivement. (Cette ligne affirmait le contraire jusqu'en 2026-09.)
- Le conftest de `tests/conftest.py` met en place une base SQLite isolée par test, dans des répertoires temporaires.
- Voir le tableau complet des cibles Make dans la section [Tests](#tests) ci-dessus pour les points d'entrée.

### Extension

- Ajouter un export : implémenter `Export.write_<type>`, mettre à jour le contrôleur.
- Changer de langue : passer `--lang` à la création du land.
- Ajouter des en-têtes / un proxy : modifier `settings` ou patcher la logique de session.
- Tags personnalisés : utiliser la hiérarchie de tags ; l'export l'aplatit en chemins.

---

# Licence

Ce projet est distribué sous licence MIT — voir [LICENSE](LICENSE).
