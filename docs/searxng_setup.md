# SearXNG — Setup, démarrage et dépannage

SearXNG est l'instance auto-hébergée utilisée par le routeur de recherche
multi-API de MyWebIntelligence (`mywi.py search`). C'est la source primaire
gratuite, compatible avec ~250 moteurs (Google, DuckDuckGo, Qwant, Brave,
Mojeek, Startpage…).

## 1. Pré-requis

- Docker Engine ≥ 20.10
- Docker Compose v2 (commande `docker compose`)
- Port `8888` libre côté hôte

## 2. Démarrage

```bash
cd docker/searxng
docker compose up -d
```

Vérification :

```bash
curl -s "http://localhost:8888/search?q=test&format=json&language=fr" \
  | python3 -c "import sys, json; d = json.load(sys.stdin); \
                assert 'results' in d; print(f'{len(d[\"results\"])} OK')"
```

La réponse doit afficher `<N> OK` avec N > 0.

## 3. Arrêt et nettoyage

```bash
docker compose down            # arrêt
docker compose down -v         # arrêt + suppression des volumes
```

## 4. Configuration

| Fichier | Rôle |
|---|---|
| `docker-compose.yml` | Service, ports, montage de la config |
| `settings.yml` | Moteurs activés, formats, locale par défaut |
| `limiter.toml` | Bypass du rate-limiter pour `127.0.0.0/8` |

Les moteurs activés par défaut : `google`, `duckduckgo`, `qwant`, `brave`,
`mojeek`, `startpage`. Les moteurs Image / Vidéo / Torrent sont désactivés.

## 5. Variables d'environnement (côté MWI)

```bash
export SEARXNG_BASE_URL="http://localhost:8888"
```

`SEARXNG_BASE_URL` est lue par `mwi/search/providers/searxng.py`. Si non
définie, l'adaptateur tombe sur `settings.SEARXNG_BASE_URL` puis sur
`http://localhost:8888`.

## 6. Dépannage

### `docker compose up -d` échoue immédiatement

- Vérifier que le port `8888` n'est pas déjà occupé (`lsof -i :8888`).
- Inspecter les logs : `docker compose logs searxng`.

### `curl` retourne `429 Too Many Requests`

Le limiter SearXNG s'active après plusieurs requêtes rapides. Le fichier
`limiter.toml` bypass déjà `127.0.0.0/8` ; si le problème persiste, vérifier
que SearXNG lit bien le fichier (`docker compose exec searxng cat
/etc/searxng/limiter.toml`).

### `curl` retourne du HTML au lieu de JSON

`format=json` n'est pas dans la liste autorisée. Vérifier la section
`search.formats` dans `settings.yml` (doit contenir `json`).

### Aucun résultat retourné par certains moteurs

Certains moteurs (Google, Bing) appliquent une détection anti-bot agressive.
SearXNG peut être temporairement banni — patienter quelques minutes ou
basculer sur `qwant` / `mojeek` qui sont plus tolérants.

## 7. Mise à jour

```bash
cd docker/searxng
docker compose pull
docker compose up -d
```

## 8. Production

Pour un usage production (recherche académique en accès réseau ouvert) :

1. Régénérer `server.secret_key` dans `settings.yml`.
2. Mettre l'instance derrière un reverse-proxy avec HTTPS (Caddy, Traefik).
3. Activer un load-balancer Docker si plusieurs instances (cf. extensions
   futures du sprint search router).
