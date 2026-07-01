# Changelog

All notable changes to MyWebIntelligence are documented in this file.
The format roughly follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added — HTML-aware Domain Resolution (sprint-heuristique)

- `heuristic update` gains `--html`: for **opaque platforms** whose editorial
  entity is not derivable from the URL path (video channels, social accounts,
  hosted blogs, participatory press...), the domain is resolved from the page
  HTML instead of the URL. A generic signal cascade recovers a better URL
  (JSON-LD `author` → `rel="author"` → `<link canonical>` → `og:url`, **author
  first**) and feeds it back through the existing URL heuristic — one source of
  truth, two entry doors. Hosts outside the opaque set keep URL resolution and
  are never fetched.
- New `--fetch-missing` flag (requires `--html` **and** an explicit `--limit`):
  volatile async fetch (aiohttp → curl_cffi → archive.org cascade) of the HTML
  for opaque-host expressions with no stored HTML. The HTML is used, not stored.
- `heuristic update` also gains `--land` (scope to one land) and honors `--limit`.
  The command now batches domain reassignment in chunked transactions and is
  deterministic (`order_by(id)`).
- Opaque-platform set ships in code (`mwi.core._DEFAULT_OPAQUE_PLATFORMS`, ~150
  host suffixes), overridable via `settings.opaque_platforms`. **No migration.**
- New read-only diagnostic `scripts/measure_heuristic_resolution.py` reports, per
  opaque suffix, how often the HTML cascade improves domain resolution.
- New tests `tests/test_33_domain_heuristics.py` (37 tests).

### Added — LLM Verdicts & Controversy Mode (sprint validate-update)

- `land consolidate` now **respects stored LLM verdicts**. After the lexical
  relevance recompute, an expression with `validllm='non'` has its relevance
  forced to `0` — consolidate no longer silently resurrects pages the LLM had
  rejected. `validllm='oui'` or `NULL` keeps the lexical score as before.
  Consolidate does **not** call the LLM by default.
- New `land consolidate --llm=true` flag (same idiom as `land readable
  --llm=true`) — re-runs the OpenRouter relevance gate per expression
  (respecting `openrouter_readable_min_chars`), refreshes `validllm`/`validmodel`,
  then applies the verdict gate. If OpenRouter is not configured, the flag is
  ignored with a warning and consolidate proceeds without LLM (still respecting
  stored verdicts). Bound LLM calls with `--limit`/`--depth`/`--minrel`.
- New **controversy-analysis mode** for the LLM relevance gate, reachable two ways:
  - Global switch: setting `openrouter_issue_mode` (env `MWI_OPENROUTER_ISSUE_MODE`,
    default `false`) — honored by **every** gate call: crawl, readable,
    consolidate, `llm validate`.
  - Per-run override: CLI flag `--issuecrawl` on `land crawl`, `land readable`,
    `land consolidate` (with `--llm=true`), and `land llm validate`. The flag
    forces issue mode for that run; when absent, the gate falls back to the
    settings default.
  In issue mode the prompt keeps only editorial / position-taking pages that
  engage the project's issue (a stance, argument, opinion, analysis, or
  substantive information) and rejects index/summary/navigation pages and generic
  company-presentation pages that do not debate the issue (controversy-mapping
  tradition — Venturini/Latour). Same yes/no verdict semantics; `validllm='non'`
  still forces relevance `0`.
- New tests `tests/test_32_validate_update.py`.

### Changed

- LLM gate prompts are now **English everywhere** and explicitly state the
  project's working language (e.g. "The project's working language is French
  (fr)"), instructing the model to think and reason within that linguistic and
  cultural context. This applies to both the standard relevance prompt and the
  controversy/issue prompt, and **supersedes** the previous French/English
  template split (sprint-multilang "D7"). The yes/no parser still accepts
  oui/non and yes/no.
- Settings: new `openrouter_issue_mode` (env `MWI_OPENROUTER_ISSUE_MODE`,
  default `false`).

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
- 81 new tests (`tests/test_17` → `tests/test_25`), 89 % coverage on
  `mwi/search/`. One additional integration test is skipped by design
  when no live SearXNG instance is reachable.

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
