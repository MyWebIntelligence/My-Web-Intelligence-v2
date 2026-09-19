# Multi-API Search Router — User Guide

**Sprint** : `sprint-searchrouter`
**CLI surface** : `python mywi.py search {run,list,usage,check}`

This document describes the multi-API search router shipped in MWI v2.
The router is **independent** from the historical `land urlist` SerpAPI
flow — both can coexist. `search run` is the recommended way to seed a
Land in MWI v2.

## 1. What it does

For one user query, the router queries **up to five backends** in
parallel or in fallback, deduplicates the URLs by canonical form, and
inserts new `Expression` rows into the target Land.

| Provider | Index | Free quota | Notes |
|----------|-------|-----------|-------|
| SearXNG  | aggregates ~250 engines | unlimited (self-hosted) | Primary, recommended |
| Brave    | proprietary (30 B pages) | ~1k req/month | Paid tier since 2026 |
| Serper   | Google SERP | 2.5k credits one-time | Google de facto |
| SerpAPI  | multi-engine | 100 req/month | Access to Scholar |
| Tavily   | LLM-tailored | 1k credits/month | Extracted content |

Two strategies:

- `fallback` — try providers in priority order, stop at the first hit.
  Preserves quotas. **Default**.
- `parallel` — query every configured provider concurrently, merge and
  dedup. Use for triangulation.

## 2. Minimum setup (SearXNG only, no API key)

```bash
# 1. Start SearXNG locally (Docker required).
cd docker/searxng
docker compose up -d

# 2. Verify the routing layer sees it.
python mywi.py search check
# Expected:
#   Provider          Configured
#   --------------------------------
#   searxng           yes
#   brave             no
#   ...

# 3. Create a Land and run a search.
python mywi.py land create --name=DemoSearch --desc="search router demo"
python mywi.py search run --land=DemoSearch \
                          --query="humanités numériques" \
                          --limit=20
```

## 3. Full setup (SearXNG + commercial APIs)

Copy `.env.example` to `.env` and fill in the keys you have :

```bash
SEARXNG_BASE_URL=http://localhost:8888
BRAVE_API_KEY=brv-xxx
SERPER_API_KEY=srp-xxx
SERPAPI_API_KEY=spa-xxx
TAVILY_API_KEY=tvl-xxx

SEARCH_DEFAULT_STRATEGY=parallel
```

Then:

```bash
python mywi.py search check
# All five providers should now be 'yes'.

python mywi.py search run --land=DemoSearch \
                          --query="humanités numériques" \
                          --limit=50 --strategy=parallel
```

## 4. Commands

### 4.1 `search run`

```bash
python mywi.py search run --land=NAME --query="..." \
                          [--limit=N] [--strategy=fallback|parallel] \
                          [--language=fr] [--providers=searxng,brave]
```

| Flag | Description | Default |
|------|-------------|---------|
| `--land`     | Target Land (must exist) | required |
| `--query`    | Search query | required |
| `--limit`    | Max results per provider | 20 |
| `--strategy` | `fallback` or `parallel` | settings.SEARCH_DEFAULT_STRATEGY |
| `--language` | ISO 639-1 language hint | `fr` |
| `--providers`| CSV whitelist | all configured |

The command writes:
- 1 `SearchQuery` row in `searchquery`.
- 1 `SearchResultLog` row per unique URL in `searchresultlog`.
- 1 `Expression` row per new URL in `expression` (deduped by Land).

### 4.2 `search list`

```bash
python mywi.py search list --land=NAME
```

Lists every search query executed for a Land, most recent first.

### 4.3 `search usage`

```bash
python mywi.py search usage --land=NAME
```

Aggregates the JSON `usage_report` columns of past queries, per provider:
total calls, total errors, last status, monthly quota.

### 4.4 `search check`

```bash
python mywi.py search check
```

Per-provider configured/unconfigured table. Use it to confirm your `.env`
or `settings.py` is wired correctly.

## 5. Configuration reference

All values are read from environment variables, then `settings.py`,
then a sensible default. Putting them in `.env` is the cleanest path.

| Variable | Description |
|----------|-------------|
| `SEARXNG_BASE_URL` | Default `http://localhost:8888` |
| `BRAVE_API_KEY`    | `X-Subscription-Token` header |
| `SERPER_API_KEY`   | `X-API-KEY` header |
| `SERPAPI_API_KEY`  | URL `api_key` query string. Falls back to historical `settings.serpapi_api_key` (snake-case). |
| `TAVILY_API_KEY`   | JSON body `api_key` field |
| `SEARCH_DEFAULT_STRATEGY` | `fallback` (default) or `parallel` |
| `SEARCH_PROVIDER_TIMEOUT` | Seconds — default `30` |

A missing or empty key silently disables the corresponding provider —
the router never errors on missing credentials.

## 6. Difference vs `land urlist`

`land urlist` (historical) and `search run` (new) both insert URLs into
a Land. They have **different scopes**:

|  | `land urlist` | `search run` |
|---|---------------|--------------|
| Backend | SerpAPI single engine | 1 to 5 providers |
| Date filter | yes (`--datestart/--dateend`) | no (planned) |
| Triangulation | no | yes (`--strategy=parallel`) |
| Trace | nothing persisted | `SearchQuery` + `SearchResultLog` |
| Quota report | no | yes (`search usage`) |

For a one-shot Google date-filtered seeding: keep `land urlist`.
For reproducible multi-engine collection: use `search run`.

## 7. Cadre légal

Le scraping des SERP via SearXNG opère, en contexte européen, dans le
cadre de l'**exception de Text and Data Mining** prévue par l'article 4
de la **directive 2019/790/UE** pour la recherche scientifique. MWI
étant un outil de recherche académique porté par un laboratoire public,
cette exception s'applique. Les fournisseurs commerciaux (Brave,
Serper, SerpAPI, Tavily) imposent leurs propres conditions d'utilisation
contractuelles ; respectez-les en conservant les clés API personnelles
et les volumes définis par chaque tier.

Référence : Margoni, T. & Kretschmer, M. (2022). *A Deeper Look into
the EU Text and Data Mining Exceptions*. **GRUR International**.

## 8. Reproductibilité (JOSS)

Chaque `SearchQuery` stocke la requête, la stratégie, la langue, la date,
et le rapport d'usage par fournisseur. Pour reproduire une collecte :

```sql
-- Récupérer les paramètres exacts d'une recherche passée
SELECT id, query, strategy, language, num_requested,
       created_at, completed_at, usage_report
FROM searchquery
WHERE land_id = ?
ORDER BY created_at;

-- Lister les URLs effectivement collectées
SELECT srl.url, srl.providers, srl.rank_min
FROM searchresultlog srl
WHERE srl.search_query_id = ?
ORDER BY srl.rank_min;
```

## 9. Limitations connues

- Cloudflare Enterprise (NYT, Cultura.com, etc.) bloque la plupart des
  scrapers — SearXNG inclus. Fallback : changer de moteur via
  `--providers=brave` quand cela vaut le coup.
- Les fournisseurs commerciaux peuvent renvoyer `429` après quelques
  appels rapides. Le routeur logge `quota_exceeded` et continue avec
  les autres providers.
- Pas de pagination cross-page : le routeur récupère `--limit` URLs
  d'une seule passe par fournisseur.

## 10. Architecture (pointer)

Pour les détails de conception (extension à un nouveau provider,
diagramme de séquence) : voir [`docs/search_router_architecture.md`](
search_router_architecture.md).
