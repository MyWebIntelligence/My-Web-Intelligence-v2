# Changelog

All notable changes to MyWebIntelligence are documented in this file.
The format roughly follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added — Body-links benchmark and stratified gold set (sprint body-links, T0)

- **Ground truth** `benchmarks/body_links/gold_v1.csv` (1543 coded links of the
  `airegulation` land, 13 columns) plus `benchmarks/body_links/README.md`
  documenting provenance, the labelling function, and the limits of validity.
  Projected by `scripts/build_gold_v1.py` from a frozen 3-judge coding campaign;
  the file is versioned and immutable (a new labelling function yields `gold_v2`).
- **Stratified estimator.** The coding sample was drawn separately from the
  `retained` (600 of 7442) and `eliminated` (943 of 8559) strata, at different
  rates. Precision and recall are therefore ratios of Horvitz-Thompson totals,
  with a linearized 95% interval. The raw recall under-reports by ~4.5 points
  (0.813 vs **0.856**); it is still printed, explicitly labelled as biased.
- **Benchmark** `mwi/benchmark_body_links.py` (`make bench-links`): replays the
  extractor against the gold, offline and read-only, and reports precision,
  recall, the confusion matrix, population estimates, the volume of kept edges
  (Goodhart guard), false-kept by `place_code`, misses by `anchor_tag`, and
  deterministic work counters. Wall clock is isolated in `bench_perf.json`,
  excluded from the compared outputs.
- **Offline bench corpus** `scripts/build_bench_cache.py` (`make bench-cache`):
  extracts once the ~1100 gold source pages and the 20930 closed-network nodes
  from a land database into a ~60 MB SQLite, hashed per page. The benchmark
  never opens a multi-GB land database; the source is opened read-only, with
  `immutable=1` when the WAL is provably empty.
- **`make bench-determinism`**: two runs under different `PYTHONHASHSEED` must
  produce byte-identical outputs. Verified on the real corpus.
- **`link_context.build_url_index` / `add_to_url_index` / `resolve_url_in_index`
  accept an optional `rules` argument** to freeze URL normalization. Without it
  the resolution ladder reads the local configuration, which would make the
  measured metrics machine-dependent. `None` keeps the previous behaviour.
- **Baseline** (commit `cd850ea`, extractor replayed): precision **0.8812**
  (+/- 0.0247), weighted recall **0.8557** (+/- 0.0196), TP 536 / FP 72 / FN 123.
  False positives: TOC 27, RECO 17, NAV 8, META_REFTOOL 7, X_OTHER 6,
  DATA_LISTING 3, NOMAJ 2, EDIT 2 — **no REF_BIB**, which the gold labels as
  editorial. Loss attribution of the 123 misses: 26 recovered by Trafilatura's
  HTML output, 33 more by `favor_recall` on that leg, 64 reachable only from the
  raw HTML. No migration, no model change.

### Added — Unified Platform Heuristics & HTML-aware Domain Resolution (sprint-heuristique)

- **Unified platform heuristics table** (`mwi/platform_heuristics.py`, 144
  **host** entries — publishers/éditeurs excluded, LCEN criterion —
  `{host: {"url": regex|None, "html": signal}}`, overridable via
  `settings.platform_heuristics`). It **supersedes** the flat `settings.heuristics`
  dict (existing URL regexes merged in verbatim) and fixes the YouTube
  `channel`/`c`/`user` over-capture that collapsed every channel to one node.
  `domain_from_url` now reads this table; **only listed hosts are ever refined**,
  every other host keeps its bare netloc.
- `heuristic update` gains `--html`: for listed platforms it resolves the
  editorial entity from the page HTML via the platform's **declarative signal**
  (`ldjson_author` / `canonical` / `og_url` / `rel_author` / `ldjson_publisher`)
  instead of the URL, then re-resolves through the URL rule.
- `heuristic update` is now **safe by default**: it only re-groups listed-host
  expressions (never a global re-baseline), gains `--land`, honors `--limit`,
  and adds **`--dry-run`** (preview without writing). Writes are chunked and
  deterministic (`order_by(id)`).
- New `--fetch-missing` flag (requires `--html` **and** an explicit `--limit`):
  volatile async fetch of the HTML for listed-host expressions with no stored
  HTML. The HTML is used, not stored. Skipped under `--dry-run`.
- New `scripts/reconstruct_domains.py` — full-corpus domain reconstruction from
  URLs (dry-run by default, `--apply` to write); recovery/rebaseline tool that
  cleans section-path garbage left by an older heuristic state.
- New read-only diagnostic `scripts/measure_heuristic_resolution.py`.
- **No migration.** New tests `tests/test_33_domain_heuristics.py` (42 tests).

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
