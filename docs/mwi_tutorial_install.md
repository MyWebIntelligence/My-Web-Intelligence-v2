# Tutoriel pas à pas — Installer MyWebIntelligence (MWI)

> **Pour qui ?** Étudiantes et étudiants de licence (et toute personne curieuse) qui n'ont pas encore l'habitude d'installer un logiciel scientifique en ligne de commande.
>
> **Le contrat de ce tutoriel** : à la fin, vous aurez MWI installé et prêt à l'emploi, **et** vous comprendrez pourquoi chaque étape était nécessaire. On n'attend de vous **aucune connaissance préalable**. Toutes les commandes se copient-collent ; chacune est expliquée avant d'être tapée.
>
> **Combien de temps ?** Comptez 30 à 45 minutes la première fois. Les fois suivantes : 2 minutes pour démarrer.

---

## Table des matières

0. [Comprendre les concepts (avant de taper la moindre commande)](#0-comprendre-les-concepts-avant-de-taper-la-moindre-commande)
1. [Préparer son ordinateur](#1-préparer-son-ordinateur)
2. [Chemin A — Docker Compose (recommandé)](#2-chemin-a--docker-compose-recommandé)
3. [Chemin B — Installation locale Python](#3-chemin-b--installation-locale-python)
4. [Chemin C — Docker manuel (avancé)](#4-chemin-c--docker-manuel-avancé)
5. [Vérifier que tout fonctionne](#5-vérifier-que-tout-fonctionne)
6. [Options à activer plus tard](#6-options-à-activer-plus-tard)
7. [Dépannage : problèmes fréquents](#7-dépannage--problèmes-fréquents)
8. [Mettre à jour ou désinstaller](#8-mettre-à-jour-ou-désinstaller)

---

## 0. Comprendre les concepts (avant de taper la moindre commande)

Cette section est la plus importante. Si vous ne comprenez **pas** ce que vous tapez, vous serez incapable de débloquer la moindre erreur. Cinq concepts suffisent.

### 0.1 — Le terminal (ligne de commande)

Le **terminal** est une fenêtre où l'on parle à l'ordinateur en tapant du texte au lieu de cliquer sur des boutons. Une commande est une instruction : un verbe (`ls`, `cd`, `git`…) éventuellement suivi d'options (`--name=…`) et d'arguments (un chemin, un mot…).

Trois commandes à connaître **par cœur** avant de continuer :

```bash
pwd          # "print working directory" : affiche dans quel dossier vous êtes
ls           # "list" : liste les fichiers et dossiers du dossier courant
cd Recherche # "change directory" : entre dans le dossier "Recherche"
cd ..        # remonte d'un cran (vers le dossier parent)
```

> 💡 **Pourquoi ça compte ?** La quasi-totalité des erreurs de débutant vient de « je ne suis pas dans le bon dossier ». Tapez `pwd` à chaque fois que vous doutez.

### 0.2 — Git et GitHub

**Git** est un logiciel qui gère les versions du code source. **GitHub** est un site web qui héberge des dépôts Git. Pour récupérer le code de MWI, on va le **cloner** (copier en local) depuis GitHub avec :

```bash
git clone https://github.com/MyWebIntelligence/mwi.git
```

Cette commande dit : « Va chercher le dépôt à cette URL et fais-en une copie locale dans un dossier `mwi/` ».

### 0.3 — Python et l'environnement virtuel (`venv`)

**Python** est le langage dans lequel MWI est écrit. Pour faire tourner MWI, votre machine doit savoir exécuter Python (`python3 --version` doit fonctionner).

MWI a besoin de bibliothèques externes (peewee, aiohttp, beautifulsoup4…). Si on les installait directement sur le Python du système, elles entreraient en conflit avec d'autres projets Python que vous pourriez avoir. **Solution** : on crée un **environnement virtuel** — un mini-Python isolé, propre à ce projet :

```bash
python3 -m venv .venv      # crée un dossier .venv qui contient un Python isolé
source .venv/bin/activate  # "active" cet environnement : votre terminal utilise désormais ce Python
```

> 💡 **L'analogie** : un venv, c'est comme un atelier rangé pour un seul projet. Au lieu de mélanger les outils de tous vos chantiers dans la même boîte, vous avez une boîte par chantier.

### 0.4 — Docker et le « conteneur »

**Docker** prend une application + Python + toutes les bibliothèques + la version exacte de chaque dépendance, et emballe le tout dans un **conteneur** : une boîte qui tourne pareil sur n'importe quelle machine. Vous n'installez plus rien à la main : Docker construit la boîte d'après une recette (le `Dockerfile`) et la fait tourner.

> 💡 **L'analogie** : c'est un livre de cuisine + une boîte sous vide. Le `Dockerfile` est la recette ; l'image est le plat congelé ; le conteneur est ce plat décongelé qui tourne. Si ça marche chez vous, ça marchera chez votre encadrant·e — même OS, mêmes versions, mêmes résultats.

**Docker Compose** est une couche au-dessus qui orchestre plusieurs conteneurs avec un fichier `docker-compose.yml`. Pour MWI, ça permet une commande unique : `docker compose up`.

### 0.5 — Choisir son chemin

Trois manières d'installer MWI. Vous n'en suivez **qu'une seule**.

| Vous voulez… | Choisissez | Difficulté |
|---|---|---|
| Le plus simple, sans bricoler Python | **Chemin A — Docker Compose** | ⭐ |
| Apprendre Python en même temps | **Chemin B — Local** | ⭐⭐ |
| Vous savez déjà ce qu'est `docker run` | **Chemin C — Docker manuel** | ⭐⭐⭐ |

👉 **Si vous hésitez : Chemin A.**

---

## 1. Préparer son ordinateur

### 1.1 — Ouvrir un terminal

| Système | Comment ouvrir le terminal |
|---|---|
| **macOS** | Application *Terminal* (dossier *Applications → Utilitaires*). |
| **Windows** | Installer **Git Bash** depuis [git-scm.com](https://git-scm.com/download/win) puis ouvrir *Git Bash*. **Ne pas utiliser PowerShell** tant que vous débutez : la syntaxe diffère par endroits. |
| **Linux** | Application *Terminal* (`Ctrl + Alt + T` sur Ubuntu). |

> 💡 **Copier-coller dans un terminal** : `Cmd+C/V` (macOS), `Ctrl+Shift+C/V` (Linux), clic-droit → *Paste* (Git Bash).

### 1.2 — Vérifier que Git est installé

Git nous servira à récupérer le code. La commande suivante demande sa version :

```bash
git --version
```

- **Réponse `git version 2.x.y`** : parfait, passez à 1.3.
- **Réponse `command not found`** : Git n'est pas installé.
  - **macOS** : tapez juste `git` dans le terminal, macOS proposera d'installer les *Command Line Tools*.
  - **Windows** : déjà couvert si vous avez installé Git Bash.
  - **Linux** : `sudo apt-get install git` (Ubuntu/Debian).

### 1.3 — Installer ce qui manque selon votre chemin

| Chemin | À installer | Section |
|---|---|---|
| A — Docker Compose | Docker Desktop | 1.4 |
| B — Local | Python 3.10+ | 1.5 |
| C — Docker manuel | Docker Desktop | 1.4 |

### 1.4 — Installer Docker Desktop *(chemins A et C)*

1. Rendez-vous sur [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/) et téléchargez la version pour votre OS.
2. Installez-la avec l'assistant graphique.
3. **Démarrez Docker Desktop** (l'application). Dans la barre des tâches doit apparaître une **baleine** 🐋. Attendez qu'elle soit fixe : Docker n'est prêt que lorsque l'icône arrête de bouger.
4. Vérifiez :

```bash
docker --version           # doit afficher Docker version 24.x ou supérieur
docker compose version     # doit afficher Docker Compose version v2.x
```

> 💡 Si la deuxième commande dit *not found*, vous avez une vieille version. Mettez Docker Desktop à jour : **Compose v2** est intégré depuis 2022.

### 1.5 — Installer Python *(chemin B uniquement)*

1. Allez sur [python.org/downloads](https://www.python.org/downloads/).
2. Téléchargez **Python 3.10 ou plus récent** (3.11 ou 3.12 sont parfaits).
3. ⚠️ **Sur Windows**, pendant l'installation, **cochez la case « Add Python to PATH »** avant *Install*. Sans ça, le terminal ne trouvera pas Python.
4. Vérifiez :

```bash
python3 --version
# Si "command not found" sur Windows, essayez :
py -3 --version
```

Vous devez voir `Python 3.10.x` ou plus.

### 1.6 — Choisir un dossier de travail et cloner MWI

On va ranger MWI dans un dossier `Recherche` à la racine de votre dossier personnel.

```bash
cd ~                  # va dans votre dossier personnel ("home")
mkdir -p Recherche    # crée le dossier Recherche s'il n'existe pas (l'option -p évite l'erreur s'il existe déjà)
cd Recherche          # entre dedans
```

On télécharge maintenant le code source de MWI :

```bash
git clone https://github.com/MyWebIntelligence/mwi.git
cd mwi
```

> 💡 **Décodage de la commande `git clone`** : `git` est le programme, `clone` est le verbe (« copie en local »), l'URL est le dépôt distant. Résultat : un dossier `mwi/` apparaît avec tout le code dedans.

À partir de maintenant, **toutes les commandes de ce tutoriel sont à lancer depuis ce dossier `mwi/`**. Vérifiez avec `pwd` que vous y êtes bien.

---

## 2. Chemin A — Docker Compose (recommandé)

**Idée générale** : Docker Compose va construire un conteneur qui contient déjà Python, Mercury Parser, et toutes les dépendances. Vous n'installez plus rien sur votre machine.

### 2.1 — Le script tout-en-un

Le projet fournit un script qui automatise toute l'installation. Une seule commande :

```bash
./scripts/docker-compose-setup.sh basic
```

**Ce qui se passe sous le capot** :

1. Le script vous pose quelques questions (timezone, dossier de données…) et écrit un fichier `.env`.
2. Il **construit l'image Docker** (`docker compose build`) — long la première fois (~5 minutes), instantané ensuite.
3. Il **démarre le conteneur** en arrière-plan (`docker compose up -d`).
4. Il copie `settings-example.py` vers `settings.py` à l'intérieur du conteneur.
5. Il crée la base de données SQLite (`python mywi.py db setup`).

> ⚠️ **Sur Windows, lancez ce script depuis Git Bash, pas PowerShell.** Si vous êtes dans PowerShell, fermez-le et ouvrez Git Bash, puis refaites `cd` jusqu'au dossier `mwi/`.

### 2.2 — Choisir entre `basic`, `api`, `llm`

Le mot après le script précise les fonctionnalités à activer. Vous pouvez monter en gamme plus tard ; commencez par `basic`.

| Niveau | Inclut | À choisir si… |
|---|---|---|
| `basic` | Crawl, exports CSV/GEXF | Vous découvrez. |
| `api` | + SerpAPI (Google), SEO Rank, OpenRouter (LLM) | Vous avez des clés API. |
| `llm` | + bibliothèques de machine learning | Vous voulez les embeddings/NLI. |

### 2.3 — Si le script échoue : faire les étapes à la main

Pas de panique : on refait juste ce que le script faisait, mais visiblement.

```bash
# 1) Créer le fichier .env (assistant interactif — validez par défaut avec Entrée si vous n'êtes pas sûr·e)
python3 scripts/install-docker-compose.py
# Sur Windows si python3 n'est pas reconnu :
# py -3 scripts/install-docker-compose.py
```
**Ce que ça fait** : génère un fichier `.env` qui dit à Docker où ranger vos données, quelle timezone utiliser, etc. C'est une fiche de configuration.

```bash
# 2) Construire l'image et lancer le conteneur en arrière-plan
docker compose up -d --build
```
**Décodage** : `up` démarre les services, `-d` veut dire « *detached* » (en arrière-plan, votre terminal reste libre), `--build` (re)construit l'image avant de démarrer.

```bash
# 3) Créer settings.py À L'INTÉRIEUR du conteneur (étape obligatoire, à faire une fois)
docker compose exec mwi bash -lc "cp settings-example.py settings.py"
```
**Décodage** : `docker compose exec mwi …` exécute une commande à l'intérieur du conteneur nommé `mwi`. Ici on lance `bash -lc "cp …"` pour copier le fichier d'exemple vers le vrai fichier de configuration.

> ⚠️ Ce fichier `settings.py` n'est **jamais** créé automatiquement. Si vous oubliez cette étape, MWI plantera au démarrage.

```bash
# 4) Initialiser la base de données SQLite
docker compose exec mwi python mywi.py db setup
```
**Ce que ça fait** : crée le fichier `data/mwi.db` avec toutes les tables (Land, Expression, Word, Domain…).

```bash
# 5) Vérifier que tout fonctionne : la commande doit afficher "0 lands"
docker compose exec mwi python mywi.py land list
```

Si vous voyez `0 lands`, **bravo**, MWI est installé. Filez à la [section 5](#5-vérifier-que-tout-fonctionne).

### 2.4 — Utiliser MWI au quotidien

Vous avez deux manières de lancer une commande MWI.

**Manière 1 — Préfixer chaque commande** (rapide, pour une seule commande) :

```bash
docker compose exec mwi python mywi.py land list
```

**Manière 2 — Entrer dans le conteneur** (confortable, pour une session de travail) :

```bash
docker compose exec mwi bash
```
**Ce qui se passe** : votre invite change pour `root@a1b2c3:/app#`. Vous êtes maintenant **à l'intérieur du conteneur**, et vous pouvez taper directement :

```bash
python mywi.py land list
python mywi.py land create --name="MonProjet" --desc="Test"
exit          # ou Ctrl+D pour ressortir
```

### 2.5 — Où sont mes données ?

Le dossier `./data` (sur votre machine, dans le projet `mwi/`) est synchronisé en permanence avec `/app/data` à l'intérieur du conteneur. **Vos données restent même si vous supprimez le conteneur.**

```bash
ls -la data/    # voir le fichier mwi.db et les exports
```

### 2.6 — Démarrer/arrêter au quotidien

```bash
docker compose up -d        # démarrer en arrière-plan
docker compose down         # arrêter (les données restent dans ./data)
docker compose logs mwi     # voir les logs (Ctrl+C pour quitter le défilement)
docker compose ps           # vérifier que le conteneur tourne
```

> 💡 **À retenir** : `down` n'efface pas vos données. Il arrête juste le conteneur. Pour tout supprimer (image + volumes), voir la section 8.

---

## 3. Chemin B — Installation locale Python

**Idée générale** : on installe Python + les dépendances directement sur votre machine. Plus d'étapes qu'avec Docker, mais vous comprenez tout ce qui se passe.

### 3.1 — Créer un environnement virtuel

Rappel de la section 0.3 : un *venv* est un Python isolé, pour éviter d'écraser celui du système.

```bash
python3 -m venv .venv
# Sur Windows si python3 n'existe pas :
# py -3 -m venv .venv
```
**Décodage** : `python3 -m venv` exécute le module `venv` ; `.venv` est le nom du dossier à créer (le point devant le rend discret dans `ls`).

### 3.2 — Activer l'environnement virtuel

⚠️ **À refaire à chaque nouvelle session de terminal**, sinon vous utiliserez le Python du système et MWI ne trouvera pas ses bibliothèques.

| Système / Shell | Commande |
|---|---|
| macOS, Linux | `source .venv/bin/activate` |
| Windows — Git Bash | `source .venv/Scripts/activate` |
| Windows — PowerShell | `.\.venv\Scripts\Activate.ps1` |
| Windows — cmd.exe | `.\.venv\Scripts\activate.bat` |

**Comment savoir si c'est activé ?** Votre invite de commande affiche `(.venv)` au tout début. Sans ça, l'activation a échoué.

```bash
which python    # macOS/Linux : doit pointer vers .venv/bin/python
where python    # Windows : doit pointer vers .venv\Scripts\python.exe
```

> 💡 **Pour sortir** du venv : `deactivate`.

### 3.3 — Installer les dépendances

On commence par mettre à jour `pip` (le gestionnaire de paquets Python), puis on installe les bibliothèques listées dans `requirements.txt`.

```bash
python -m pip install -U pip setuptools wheel
python -m pip install -r requirements.txt
```
**Décodage** : `pip install -U` met à jour ; `-r requirements.txt` lit la liste des paquets depuis ce fichier (peewee, aiohttp, beautifulsoup4, nltk…). Comptez 2 à 5 minutes la première fois.

> 💡 **Sur la cascade fetch (sprint-403)** — `requirements.txt` inclut `curl_cffi>=0.7.0`. Cette bibliothèque imite l'empreinte TLS de Chrome 120 et permet à MWI de récupérer les pages bloquées par Cloudflare (codes `403`/`429`) sans lancer de navigateur. Aucune action supplémentaire requise : l'installation est automatique. Si `pip` se plaint sur macOS arm64, exécuter `pip install --upgrade pip` avant de relancer (testé OK avec Python 3.13 + arm64).

### 3.4 — Générer le fichier `settings.py`

```bash
python scripts/install-basic.py
```
**Ce qui se passe** : un assistant vous pose des questions (chemin de stockage, *user agent*, nombre de connexions parallèles…). Validez avec **Entrée** pour accepter les valeurs par défaut. Un fichier `settings.py` est créé à la racine.

> 💡 `settings.py` est **personnel** et **gitignoré** : il ne sera jamais envoyé sur GitHub. Vous pourrez l'éditer plus tard avec n'importe quel éditeur de texte.

**Les trois niveaux d'installation.** `install-basic.py` est le premier de **trois assistants** — c'est l'équivalent, pour le chemin B, des niveaux `basic` / `api` / `llm` du chemin A (§2.2). Les deux autres ne **créent** pas `settings.py` : ils le **complètent** (lancez donc toujours `install-basic.py` en premier).

| Assistant | Ce qu'il ajoute à `settings.py` | Prérequis |
|---|---|---|
| `python scripts/install-basic.py` | Configuration de base (stockage, réseau) — **suffisant pour démarrer** | — |
| `python scripts/install-api.py` | Clés d'API : SerpAPI (`land urlist`), SEO Rank (`land seorank`), OpenRouter (`land llm validate`) | Avoir des clés (détail en §6.1) |
| `python scripts/install-llm.py` | Installation complète LLM : provider d'embeddings (OpenAI, Mistral, Gemini, HuggingFace, Ollama…), modèles NLI, backend FAISS | `pip install -r requirements-ml.txt` (~2 Go — détail en §6.2) |

> 💡 **Vous pouvez monter en gamme plus tard** : les assistants `api` et `llm` se lancent à tout moment sur un `settings.py` existant (une sauvegarde est faite avant modification). Commencez par `basic`, finissez l'installation, puis revenez en §6 quand vous aurez l'usage des API ou de l'analyse sémantique.

### 3.5 — Initialiser la base de données

```bash
python mywi.py db setup
```
**Ce qui se passe** : MWI crée `data/mwi.db` (un fichier SQLite) et y crée toutes les tables.

> ⚠️ **`db setup` est destructif** : si vous le relancez plus tard, il efface toutes vos données. Pour appliquer de nouvelles colonnes à une base existante, utilisez `python mywi.py db migrate` (non destructif).

### 3.6 — Vérifier

```bash
python mywi.py land list
```

Si vous voyez `0 lands` (et pas une erreur), c'est gagné.

### 3.7 — Installer Mercury Parser (recommandé pour l'extraction propre)

Mercury Parser est l'outil qui transforme une page web bruitée (publicités, menus…) en texte propre. Il est requis pour la commande `land readable`. Il s'installe via **npm**, le gestionnaire de paquets de Node.js.

```bash
node --version    # vérifier si Node.js est déjà installé
npm --version
```

**Si Node.js manque** :

- **macOS** : `brew install node` (avec Homebrew) ou télécharger sur [nodejs.org](https://nodejs.org/).
- **Windows / Linux** : télécharger sur [nodejs.org](https://nodejs.org/).

Puis :

```bash
npm install -g @postlight/mercury-parser    # -g = installation globale (utilisable depuis n'importe où)
mercury-parser --version                    # vérifier
```

> 💡 **Sans Mercury**, la commande `land readable` ne fonctionnera pas, mais le crawl basique (`land crawl`) si.

---

## 4. Chemin C — Docker manuel (avancé)

Pour celles et ceux qui maîtrisent déjà Docker. On utilise les commandes `docker` directement, sans Compose.

```bash
# 1) Construire l'image
docker build -t mwi:latest .
```
**Décodage** : `-t mwi:latest` étiquette l'image avec le nom `mwi` et le tag `latest` ; le `.` final dit « utilise le Dockerfile du dossier courant ».

```bash
# 2) Lancer le conteneur (le -v monte un dossier de votre machine dans le conteneur)
docker run -dit --name mwi -v ~/mywi_data:/app/data mwi:latest
```
**Décodage** : `-d` = en arrière-plan, `-i` = interactif, `-t` = avec un terminal ; `--name mwi` nomme le conteneur ; `-v ~/mywi_data:/app/data` synchronise le dossier `~/mywi_data` (sur votre machine) avec `/app/data` (dans le conteneur).

```bash
# 3) Créer settings.py dans le conteneur
docker exec mwi bash -lc "cp settings-example.py settings.py"

# 4) Initialiser la base
docker exec -it mwi python mywi.py db setup

# 5) Tester
docker exec -it mwi python mywi.py land list
```

**Gestion :**

```bash
docker stop mwi      # arrêter
docker start mwi     # redémarrer
docker rm mwi        # supprimer (les données dans ~/mywi_data restent)
```

---

## 5. Vérifier que tout fonctionne

Petit test concret pour vous assurer que la chaîne complète marche : créer un Land, y mettre des termes, lister.

> ⚠️ Si **chemin A ou C** : préfixez chaque commande par `docker compose exec mwi` (ou `docker exec mwi`), ou bien entrez d'abord dans le conteneur (`docker compose exec mwi bash`).
>
> Si **chemin B** : assurez-vous que `(.venv)` apparaît dans votre invite. Sinon, réactivez (cf. 3.2).

### 5.1 — Créer un Land de test

```bash
python mywi.py land create --name="TestInstall" --desc="Mon premier essai"
```
**Décodage** : `land` est l'objet, `create` le verbe, `--name` et `--desc` sont les paramètres obligatoires. Sortie attendue : `Land "TestInstall" created (fullhtml=disabled)`.

### 5.2 — Ajouter des termes (mots-clés thématiques)

```bash
python mywi.py land addterm --land="TestInstall" --terms="climat, environnement, écologie"
```
**Ce qui se passe** : MWI lemmatise chaque terme (l'écologie devient « écologi », *etc.*) et l'enregistre dans le dictionnaire du Land.

### 5.3 — Vérifier dans la liste

```bash
python mywi.py land list
```

Vous voyez `TestInstall` avec ses termes : c'est gagné.

### 5.4 — Lancer la suite de tests automatiques *(facultatif mais rassurant)*

```bash
# Chemin B
pip install pytest pytest-cov
pytest tests/ -q

# Chemin A
docker compose exec mwi pytest tests/ -q
```

Vous devez voir quelque chose comme `98 passed in 7.5s`. Cela confirme que **toute** l'installation est saine.

### 5.5 — Faire le ménage

```bash
python mywi.py land delete --name="TestInstall"
```

🎉 **Installation complète.** Vous pouvez ouvrir `docs/mwi_tutorial_crawl.md` pour apprendre à constituer un vrai corpus.

---

## 6. Options à activer plus tard

Vous n'avez **pas besoin** de ces options pour utiliser MWI. Activez-les quand vous en aurez l'usage.

### 6.1 — Configurer les clés d'API

Trois services externes peuvent être branchés à MWI :

| Service | À quoi ça sert | Commande MWI concernée |
|---|---|---|
| **SerpAPI** | Amorcer un Land avec une recherche Google automatisée | `land urlist` |
| **SEO Rank** | Récupérer des métriques SEO par URL | `land seorank` |
| **OpenRouter** | Demander à un LLM si une page est pertinente | `land llm validate` |

Lancez l'assistant interactif :

```bash
# Chemin B
python scripts/install-api.py

# Chemin A
docker compose exec -it mwi python scripts/install-api.py
```

L'assistant vous demande chaque clé. Si vous n'en avez pas, validez avec **Entrée** pour passer cette ligne. Les clés sont sauvegardées dans `settings.py` (sur votre machine ou dans le conteneur) — elles ne sortent jamais de chez vous.

### 6.2 — Activer les embeddings et la NLI (analyse sémantique)

Cela installe **PyTorch** et **sentence-transformers** (~2 Go), pour calculer la similarité sémantique entre paragraphes.

```bash
# Chemin B
python -m pip install -r requirements-ml.txt
python scripts/install-llm.py

# Chemin A : reconstruire l'image avec le niveau llm
./scripts/docker-compose-setup.sh llm
```

Vérification :

```bash
python mywi.py embedding check
```

### 6.3 — Activer Playwright (extraction des médias dynamiques)

Playwright pilote un vrai navigateur Chrome pour analyser les pages dont les images sont chargées en JavaScript.

```bash
# Chemin B
python install_playwright.py

# Chemin A
docker compose exec mwi python install_playwright.py
```

Sur Linux/Docker, certaines bibliothèques système sont nécessaires. La commande ci-dessous les installe en une fois :

```bash
docker compose exec mwi bash -lc "apt-get update && apt-get install -y libnspr4 libnss3 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 libatspi2.0-0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libxkbcommon0 libasound2"
docker compose exec mwi python install_playwright.py
```

---

## 7. Dépannage : problèmes fréquents

### 7.1 — `command not found: python` ou `python3`

**Cause** : Python n'est pas installé, ou pas dans votre PATH.

- **Windows** : réinstallez Python depuis [python.org](https://www.python.org/downloads/) en cochant cette fois *Add Python to PATH*.
- **macOS** : essayez `python3` (le nom `python` a disparu sur macOS récents).
- **Linux** : `sudo apt-get install python3 python3-venv python3-pip`.

### 7.2 — `docker: command not found`

**Cause** : Docker Desktop n'est pas démarré (ou pas installé). Lancez l'application **Docker Desktop** et attendez que la baleine arrête de bouger.

### 7.3 — Erreur SSL au téléchargement des dépendances

```bash
python -m pip install --upgrade certifi
```

Sur macOS, lancez aussi `Install Certificates.command` situé dans `/Applications/Python 3.x/`.

### 7.4 — NLTK : `LookupError: Resource punkt not found`

```bash
python -m nltk.downloader punkt punkt_tab
```

### 7.5 — `(.venv)` n'apparaît pas devant l'invite

**Cause** : le venv n'est pas activé. Refaites la commande d'activation (3.2). Sur PowerShell, vous pouvez avoir besoin d'autoriser les scripts une seule fois :

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

### 7.6 — Le conteneur Docker se ferme tout de suite

Lisez les logs pour comprendre :

```bash
docker compose logs mwi
```

L'erreur la plus fréquente : `settings.py` manquant. Recréez-le :

```bash
docker compose exec mwi bash -lc "cp settings-example.py settings.py"
```

### 7.7 — `mercury-parser: command not found` lors d'un `land readable`

Mercury Parser n'est pas installé ou pas dans le PATH. Voir 3.7. Dans Docker (chemins A et C), il est déjà inclus dans l'image officielle.

### 7.8 — Permission refusée sur `./scripts/docker-compose-setup.sh`

```bash
chmod +x scripts/docker-compose-setup.sh
./scripts/docker-compose-setup.sh basic
```
**Décodage** : `chmod +x` rend le fichier exécutable.

### 7.9 — Base de données corrompue ou bloquée

Sauvegardez d'abord, **toujours** :

```bash
cp data/mwi.db data/mwi.db.bak
bash scripts/sqlite_recover.sh data/mwi.db data/mwi_repaired.db
```

### 7.10 — macOS : segfault au démarrage avec PyTorch

Sur Apple Silicon, certains conflits OpenMP causent des plantages. Avant de lancer Python :

```bash
export OMP_NUM_THREADS=1
export KMP_DUPLICATE_LIB_OK=TRUE
```

Pour rendre permanent : ajoutez ces deux lignes à la fin de votre `~/.zshrc`.

---

## 8. Mettre à jour ou désinstaller

### 8.1 — Mettre à jour MWI (récupérer la dernière version)

```bash
# Depuis le dossier mwi/
git pull
```
**Ce que ça fait** : récupère les nouveaux commits depuis GitHub. Puis selon votre chemin :

```bash
# Chemin A : reconstruire l'image, redémarrer, appliquer les nouvelles migrations DB
docker compose down
docker compose up -d --build
docker compose exec mwi python mywi.py db migrate

# Chemin B : mettre à jour les dépendances et appliquer les migrations
source .venv/bin/activate
python -m pip install -r requirements.txt --upgrade
python mywi.py db migrate
```

> ⚠️ Toujours `db migrate` (non destructif), **jamais** `db setup` sur une base existante.

### 8.2 — Désinstaller proprement

**Chemin A — Docker Compose** :

```bash
docker compose down --rmi all --volumes
# Supprime conteneurs + image + volumes Docker.
# Vos données restent dans ./data — supprimez-les manuellement si voulu :
rm -rf data/
```

**Chemin B — Local** :

```bash
deactivate          # sortir du venv
cd ..
rm -rf mwi/         # supprime tout le projet (code + venv + données)
```

**Chemin C — Docker manuel** :

```bash
docker stop mwi
docker rm mwi
docker rmi mwi:latest
rm -rf ~/mywi_data
```

---

## Récapitulatif final

| Étape | Commande clé |
|---|---|
| Cloner le code | `git clone https://github.com/MyWebIntelligence/mwi.git && cd mwi` |
| Installer (chemin A) | `./scripts/docker-compose-setup.sh basic` |
| Installer (chemin B) | `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && python scripts/install-basic.py && python mywi.py db setup` |
| Tester | `python mywi.py land list` |
| Premier land | `python mywi.py land create --name="X" --desc="Y"` |

📚 **Suite logique** : `docs/mwi_tutorial_crawl.md` pour apprendre à crawler votre premier corpus.

❓ **Vous bloquez ?** Ouvrez une *issue* sur [GitHub](https://github.com/MyWebIntelligence/mwi/issues) en précisant : votre OS (macOS/Windows/Linux), votre chemin (A/B/C), la commande tapée, et le message d'erreur **exact** (copier-coller du terminal complet).
