# Changelog

All notable changes to MyWebIntelligence are documented in this file.
The format roughly follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added — Multi-API Search Router (sprint-searchrouter)

- New `mwi/search/` package — orchestrates URL collection across 5 providers:
  SearXNG (self-hosted, primary), Brave, Serper, SerpAPI, Tavily.
- Two orchestration strategies: `fallback` (preserve quotas) and `parallel`
  (triangulation — Rogers, *Doing Digital Methods*, 2019).
- New CLI verbs `python mywi.py search {run,list,usage,check}`.
  - `search run --land=… --query=…` — execute a search and seed Expressions.
  - `search list --land=…` — list past queries.
  - `search usage --land=…` — aggregate per-provider usage report.
  - `search check` — display configured/unconfigured providers.
- New tables `searchquery` and `searchresultlog` (migration `010_add_search_tables.py`).
  Reproducibility (JOSS): every collection persists query text, strategy,
  language, language, and per-provider usage report.
- Docker Compose stack for self-hosted SearXNG (`docker/searxng/`).
- Documentation: `docs/searxng_setup.md`, `docs/search_router.md`,
  `docs/search_router_architecture.md`.
- Settings: `SEARXNG_BASE_URL`, `BRAVE_API_KEY`, `SERPER_API_KEY`,
  `SERPAPI_API_KEY`, `TAVILY_API_KEY`, `SEARCH_DEFAULT_STRATEGY`,
  `SEARCH_PROVIDER_TIMEOUT`. All optional — adapters with no key are
  silently skipped.
- 64 new tests (`tests/test_17` → `tests/test_25`), 89 % coverage on
  `mwi/search/`.

### Changed

- `mwi/search.py` (the historical SerpAPI engine router for `land urlist`)
  was renamed to `mwi/serpapi_router.py` to free the `mwi/search/` package
  namespace. Public behaviour preserved — `core.SerpApiError` and
  `core.fetch_serpapi_url_list` aliases unchanged.
- `tests/test_16_search_router.py` renamed to `tests/test_16_serpapi_router.py`.

### Notes for users

- `land urlist` (single-engine SerpAPI) is **preserved** — both flows can
  coexist. New deployments should prefer `search run` (multi-provider,
  journaled, JOSS-compliant).
