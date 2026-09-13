# Changelog

All notable changes to MyWebIntelligence are documented in this file.
The format roughly follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added — Link profiles at export (sprint body-links, T4)

- **`kind` column appended at the END** of `*_pageslinks.csv` and
  `*_pageslinksfullhtml.csv`, so consumers selecting columns by name are
  unaffected. `NULL` is exported as `body`. Raw-only edges of the whole-page
  network carry an EMPTY kind, never `body`: a link absent from the body has
  no structural zone to report.
- **`--link-profile`** on `land export` (`editorial` by default,
  `editorial+reco`, `all`), overridable through `settings.link_profiles`. An
  unknown name falls back to the default with a warning rather than raising
  mid-export.
- **One point of control.** The filter is applied inside
  `Export.get_sql_cursor`, which every link query routes through. The
  whole-page network executes its SQL directly and is therefore **structurally
  exempt**: it is the comparator that validates the sprint, and filtering it
  would destroy the only measurement that says whether the body network is
  improving. A test asserts both files are byte-identical under every profile.
- **Bibliographies stay in the default profile.** The ground truth labels every
  `REF_BIB` link `EDITORIAL`; excluding them would turn 64 genuine citations
  into losses and drop recall from 0.92 to 0.76.

### Measured — the precision target is not reachable with structural rules

Reported rather than worked around. After T3 the benchmark stands at precision
**0.9162**, recall **0.9210**, with 55 false positives: RECO 21, X_OTHER 9,
NAV 8, META_REFTOOL 7, DATA_LISTING 3, TOC 2, NOMAJ 2, EDIT 2, META_BOILER 1.

- A **perfect** recommendation-block rule would yield precision **0.9462** --
  still short of the 0.95 target. Reaching it requires excluding a second
  family (reference tools and listings: 0.9621), which is a scoping decision,
  not a rule-writing one.
- No structural rule found separates recommendation blocks from editorial
  citations at a useful rate. The container prose ratio separates them in the
  median (0.93 against 0.48) but the distributions overlap: every candidate
  threshold removes roughly as many true citations as false ones. The best
  combination found (repeated sibling pattern, container prose ratio and
  anchor count) gains 1.0 point of precision for 0.5 point of recall -- below
  the admission threshold of 2 F1 points this sprint set for itself, so **no
  reco rule was shipped**.

### Added — Structural link classification, ExpressionLink.kind (sprint body-links, T3)

- **Migration 014** adds `expressionlink.kind`, `.kind_rule` and `.origin`
  (idempotent, template of 012, no backfill). `kind` is the structural zone
  (`body`/`nav`/`toc`/`reco`/`ref`), `kind_rule` the rule that decided, and
  `origin` the extraction leg. Zone and provenance are kept in separate
  columns on purpose: merging them would make the invariant "retained <=>
  kind == body" unfalsifiable. **NULL means `body`** everywhere it is read, so
  no pre-014 edge is ever excluded retroactively.
- **`body_links.classify`** returns `(kind, kind_rule)` from structural
  evidence only -- counts, lengths, ratios and booleans, never text. It reads
  the RAW DOM: Trafilatura's HTML output carries no class, no id and no
  sectioning element, so a rule written against it would be silently inert.
- **`LinkDomInfo` carries the structural features**, filled inside the single
  `find_all('a')` loop, with per-ancestor anchor counts computed in one
  ASCENDING pass -- a descending `find_all` per link is quadratic on a table
  of contents (median 180 anchors per block). The anchor's LENGTH is stored,
  never its text: storing the text is what makes a lexical rule easy to write.
- **Best occurrence wins.** `extract_link_dom_map` takes an optional `rank`
  callable; with it, a URL present both in the menu and in the body keeps its
  body occurrence. First-occurrence-wins was structurally biased toward
  navigation, which sits at the top of the document (median anchor position
  0.16 against 0.49 for an editorial link), and it dragged `context`/`dom`
  along with it.
- **Two rules, both qualified by measurement.** A sectioning element that is
  mostly prose is NOT an annex -- templates routinely wrap a whole article in
  `<header>`, and the unqualified rule exiled 4 genuine citations. An anchor
  grid is measured on the CONTAINER, not on the block ancestor -- a table of
  contents wraps each entry in its own `<p>`, which hides the grid entirely.
  Both failures are frozen as tests.
- **No lexical rule**, enforced two ways: an allowlist of tokens read off the
  module's AST and declared **in the test**, not in the module; and the same
  fixture replayed in Japanese, which must yield identical verdicts.
- **Two adjacent fixes.** `readable_pipeline` refused no self-loop, unlike the
  other two write sites. And a node merge that collided on the composite key
  deleted the losing edge outright, silently dropping its `context`/`dom`
  since 012 and its `kind` since 014: `normalize_pipeline._absorb_link` now
  folds the better kind and the non-empty fields into the survivor first.
- **Measured** (`make bench-links`, profile `editorial`): precision **0.8792
  -> 0.9162**, recall 0.9249 -> 0.9210. False positives 82 -> 55, of which
  table-of-contents links fall from 27 to **2**. One editorial citation out of
  659 is lost to the classification (coded `EDIT_LIST`). Remaining false
  positives: RECO 21, X_OTHER 9, NAV 8, META_REFTOOL 7, DATA_LISTING 3,
  NOMAJ 2, TOC 2, EDIT 2, META_BOILER 1.

### Added — Body links from Trafilatura's HTML output (sprint body-links, T2)

- **New leaf module `mwi/body_links.py`.** `extract_body_links(md_content,
  readable_html, base_url, soup=None)` returns the ordered, deduplicated union
  of Trafilatura's markdown links and the anchors of its HTML output, each
  carrying its origin (`md` / `html` / `both` / `raw`) and its literal markdown
  token. It never runs Trafilatura itself and reuses the caller's parse, so the
  page stays within its HTML-parse budget. Imports neither `core` nor `model`.
- **The HTML output is finally read for links.** It was already computed for
  media extraction and thrown away. Wired into `core._extract_content_and_links`
  and into `core.consolidate_land` (which recomputes it from the stored
  `expression.html` under `--fullhtml`).
- **`favor_recall` on the HTML leg only**, behind `settings.link_favor_recall`
  (default `True`). Never on the markdown leg: that one feeds
  `expression.readable`, hence relevance, the LLM gate, embeddings and the
  corpus export, and widening it would inject boilerplate into every corpus.
- **`url=` is now passed to both Trafilatura calls**, improving relative-href
  resolution at the source.
- **One parse instead of two.** `readable_html` was parsed twice in a row
  (`media_lines`, then `extract_medias`); the single parse is shared with the
  new link leg, so the HTML leg costs nothing.
- **`consolidate_land` no longer iterates a `set`.** Link order was
  `PYTHONHASHSEED`-dependent, which made the winning edge — and therefore its
  `context`/`dom` — non-deterministic. The legacy BS4-on-readable fallback is
  kept for lands without stored HTML, so no link is lost.
- **`link_context._resolve_href`** factors the single definition of what counts
  as an outgoing hyperlink, now shared by `extract_link_dom_map`,
  `extract_all_links` and `body_links`.
- **Measured** (`make bench-links`, gold v1): weighted recall **0.8557 ->
  0.9249**, precision 0.8812 -> 0.8792 (-0.002). The recall target of the sprint
  is met by this ticket alone. Remaining false positives, 82: TOC 27, RECO 21,
  X_OTHER 9, NAV 8, META_REFTOOL 7, NOMAJ 4, DATA_LISTING 3, EDIT 2,
  META_BOILER 1. Work counters confirm 2 Trafilatura calls and 1 parse per page.
  No migration, no model change.

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
