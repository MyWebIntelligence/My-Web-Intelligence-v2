# Changelog

All notable changes to MyWebIntelligence are documented in this file.
The format roughly follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### BREAKING — read this first if an automation suddenly stops working

Two interface changes ship in this release. Neither was preceded by an
inventory of the n8n scenarios, cron jobs and shell wrappers that drive
`mywi.py` (a deliberate call: correct them as they surface). If a pipeline of
yours goes quiet, the cause is almost certainly one of these two, and this
entry is here so the diagnosis takes a minute.

- **`--dryrun` (glued) is removed. Use `--dry-run`.** Only
  `db fix_archive_domains` still documented the glued spelling. Symptom:
  `unrecognized arguments: --dryrun` and exit code 2.
- **`--dry-run=FALSE` now means a real run** on `land delete` and
  `heuristic update`. It used to be read as a simulation on those two commands
  (`bool("FALSE")` is `True`), so a command that looked like it was applying
  changes silently did nothing. If you passed `=FALSE` expecting a no-op, it
  will now act.
- **The exit code now reflects the outcome.** `0` success, `1` business failure
  (land not found, nothing to do, a **cancelled confirmation**, an unhandled
  exception), `2` argparse usage error. Every run used to exit `0`, so a chain
  like `cmd1 && cmd2` carried on after a step that had failed. Typical symptom
  of the change: a scenario that "suddenly does nothing" right after a step
  which had been failing silently for months — look at that step, it is the
  real bug and it is now visible. `scripts/docker-compose-setup.sh` had its
  health probe switched from `land list` (which legitimately exits 1 on a
  brand-new install) to `db migrate`.

### Added — a real perceptual fingerprint on media (migration 016)

`media.image_hash` is a SHA-256 of the downloaded bytes: it answers "is this
the same FILE?". The code comment and the documentation called it a
"perceptual hash", which is a different promise — and the one researchers
acted on: re-encode an image at another compression level and the SHA-256 is
unrelated, so `media_stats` never surfaced the reuse of a photo across sites.

`media.perceptual_hash` now carries a 64-bit dHash (16 hex characters):
grayscale, resize to 9x8, one bit per pair of neighbouring pixels. Two images
are alike when the Hamming distance is small (default threshold 5/64,
`settings.media_near_duplicate_distance`). No new dependency — it is fifteen
lines of Pillow.

`land media_stats` now prints two sections, `Exact duplicates (SHA-256)` and
`Near-duplicates (dHash)`. `--near=N` additionally searches by distance; it is
opt-in because it is quadratic, and it refuses to run above
`settings.media_near_duplicate_max` (20 000) rather than churn for hours.

**The column is NULL for every media analysed before this migration** and
cannot be backfilled — the bytes are not kept. Run `db migrate`, then
`land reanalyze --name=LAND` (one download per media; use `--limit` in steps).

### Fixed — the user guides are back in the repository

Seven guides had been moved under `.claude/docs/` in June, a directory
`.gitignore` excludes (`.*/`). `git ls-tree -r HEAD docs/` listed two files
while both READMEs pointed at guides that nobody cloning the repository — or
downloading the Zenodo archive — could open: 13 of 17 relative links were dead.

`docs/` now carries `mwi_tutorial.md` / `.ipynb`, `mwi_tutorial_install.md`,
`mwi_tutorial_crawl.md`, `search_router.md`, `search_router_architecture.md`
and `searxng_setup.md`. The install link points at `mwi_tutorial_install.md`
(the old `INSTALL_ZERO_bis.md` no longer exists). Pointers from those guides to
unpublished files were rewritten, and one false claim was corrected on the way:
`expression.http_status` reflects the strategy that **delivered** the HTML, not
the origin server — it has done so since 2026-05-08.

`tests/test_50_doc_links.py` now fails the build if a README links to something
that does not exist or that lives under a dot-directory.

### Fixed — a paragraph is an occurrence of a page (migration 015)

`paragraph.text_hash` was UNIQUE across the whole database, so the first page
vectorised **anywhere** owned that text. Consequences, all of them silent:
the same paragraph on two pages produced one row and the pair never reached
`embedding similarity` (`pseudolinks` came out empty); generating a second land
returned `(0, 0)` because another land already owned the text, and
`embedding reset` on one land moved the occurrence into the other — results
depended on the order in which lands had been processed. `--minrel` was also
evaluated on the *owning* page, so a relevance-0 page crawled first could steal
a paragraph from a relevant one.

The logical key is now `(expression, text_hash)`. The embedding is still
computed once per `(text_hash, model_name)`: occurrences share the provider
cost, not the row.

**Migration**: `db migrate` applies `015_paragraph_occurrences`. On databases
built by migration 003 the uniqueness came from an inline column constraint,
which SQLite implements as an undroppable autoindex — the table is rebuilt (row
counts checked before and after, foreign keys verified). **Back up first**:
`sqlite3 data/mwi.db ".backup data/mwi.db.bak_$(date +%Y%m%d_%H%M%S)"`. Then
re-run `embedding generate` (no provider call: existing vectors are reused) and
`embedding similarity`. `land list` will report more paragraphs than before —
that is the fix, not a duplication.

### Added — `verbatim` similarity method and a `Method` column on pseudolinks

Two pages carrying a rigorously identical paragraph are now reported under
their own method, `verbatim` (score 1.0), instead of being folded into
`cosine`/`nli` — verbatim circulation and semantic proximity are different
objects, and one repeated boilerplate block over n pages would otherwise add
C(n,2) pairs at 1.0 and drown real proximities. The `pseudolinks` export gains
a `Method` column, and `--method=verbatim|cosine|cosine_lsh|nli|all` restricts
the file to one of them. `ParagraphSimilarity` already carried `method` in its
composite key, so no migration was needed. The page- and domain-level
aggregations are unchanged and do not count verbatim pairs.

### Fixed — `land readable` fills the body of pages extracted from stored HTML

When `expression.html` was available the pipeline extracted locally (no network,
no Mercury) but wrote the result to a field it never read back, so the page was
timestamped as "read", reported as updated because its title had changed, and
kept an empty body. The local extraction now uses the exact same Trafilatura
call as the crawl, which also means re-running `land readable` on a
`--fullhtml` land no longer rewrites every page (and no longer replays the LLM
gate on each of them).

A non-empty `readable` is now never replaced by a **shorter** one: stored HTML
is capped by `settings.fullhtml_max_size_kb`, so re-extracting from a truncated
archive could only lose text. Longer extractions still replace as before.

Affected pages are the ones with stored HTML and an empty `readable`; the README
(*Fetch Readable Content*) carries the one-query recovery runbook.

### Changed — `land readable` memory is bounded, not just its concurrency

The pipeline held every selected row — `html` blobs included — for the whole
run. It now freezes the selection as a list of ids and loads one batch at a
time: measured 39.4 MB → 4.0 MB on 200 pages of 200 KB. No behaviour change.

### Fixed — the simulation flag is honoured, and simulates nothing into the database

- `land delete` and `heuristic update` read the flag through `core.get_dryrun`
  like every other command. Before, `land delete --dryrun` deleted the land and
  `heuristic update --dryrun` reassigned domains for real, without even asking
  for confirmation.
- `heuristic update --dry-run --html --fetch-missing` no longer goes to the
  network. A "simulation" used to issue real HTTP requests.
- `db fix_archive_domains --dry-run` no longer creates `Domain` rows. The
  `get_or_create` ran before the guard, so a simulation left new domains behind
  and the next `domain crawl` went out to fetch them. It now prints
  `Would create new domain: …` and writes nothing.

### Changed — `land delete` refuses a `--maxrel` below 1, and says what it will delete

`--maxrel=0`, a negative value, or a bare `--maxrel` (argparse turns it into 0)
all fell through to "delete the entire land", because the controller could not
tell an absent option from a zero. Since `relevance` is NULL or a non-negative
integer, `relevance < 0` matches nothing — the intent could never have been to
delete everything. These now print why they are refused and return without
touching anything, *before* the confirmation prompt.

The confirmation prompt (and the dry-run line) now name the exact scope:
`the ENTIRE land "X" and all its data (N expression(s))` versus
`N crawled expression(s) with relevance < R in land "X"`, plus
`+ N uncrawled orphan(s)` with `--prune-orphans`. Both scopes used to print the
same sentence. Omitting `--maxrel` still deletes the whole land: that is
deliberate and unchanged.

### Changed — Node identity, id mapping, one resolution ladder (sprint body-links, T1)

Neutral on the benchmark by design, and it closes by PROVING that neutrality:
`make bench-links` returns precision 0.9162 and recall 0.9210 before and after,
with byte-identical nominative lists. Node duplicates never caused a lookup
failure — the relaxed rung of the resolution ladder already absorbed them — so
this is graph quality and a migration deliverable, not a metric.

- **Root path converges under `strip`.** `_apply_trailing_slash` kept `'/'` as
  `'/'` while `''` stayed `''`, so the two root forms never met under the one
  policy whose purpose is to make them meet. **Only `strip` changes**:
  `preserve` is the default on every existing land and touching it would
  rename nodes everywhere at the next `land normalize`. A test pins that.
- **Percent-escapes are uppercased** (RFC 3986 §2.1), on path and query, never
  decoded. Unconditional: it is the only transformation here that cannot merge
  two distinct resources. Gain on the test land is 1 node and 3 edges — it
  ships for conformance, not for yield, and it is the one change that renames
  URLs under every policy.
- **`path_casefold`** (opt-in, default off) uses `lower()`, not `casefold()`:
  the project uses one case operation everywhere, and `casefold()` changes
  length (`ß` → `ss`), which would turn a normalized URL into a 404 when it is
  re-fetched. Applied before the escape step, otherwise it would lowercase the
  hex digits back.
- **`strip_trackers_by_host`** matches on a host suffix BOUNDARY — `h == key`
  or `h.endswith('.' + key)`, never a bare `endswith`, which would make
  `notlinkedin.com` match `linkedin.com`. Case-sensitive, like the global
  list. `?s=` and `?ref=` stay untouched off the listed hosts: `?s=` is the
  WordPress search query and stripping it collapses every result page onto the
  site root, a silent and irreversible node merge.
- **`MWI_URL_TRAILING_SLASH`** added: `trailing_slash` was the only URL rule
  with no environment variable, which made the `strip` policy unreachable
  without editing a gitignored file.
- **`land normalize --mapping-out=PATH`** writes `old_id,new_id,old_url,
  canonical_url`. `old_id == new_id` marks a renaming rather than a merge. The
  pipeline takes a `mapping_sink` callable instead of a path, so it stays free
  of file I/O; the return type is unchanged. **Produced in `--dry-run` too**,
  which is its highest-value use: deciding whether to apply at all. An
  unwritable path fails in a second, before any merge — merges are not
  reversible.
- **Deterministic plan order.** `_collect_pairs` walked dicts built from a
  SELECT with no ORDER BY: the mapping, the execution order and the `--limit`
  slice all depended on SQLite's query plan. Now sorted by id.
- **`--limit` caps collision GROUPS, not elementary operations.** The previous
  formula spent the budget on renames first, so on a land with more pending
  renames than `limit` no merge ever ran — and merges are the risky half
  (edge remapping, backfill, cascading delete), precisely the one an operator
  slices in order to rehearse. Note: the arithmetic of the old formula was
  correct, contrary to what the sprint card claimed; the defect was its
  semantics.
- **One resolution ladder.** `Export._host_path_key` and
  `Export._index_url_key` are gone and `_fullhtml_lookup` delegates to
  `link_context`. Characterisation tests on 30 witness hrefs — malformed
  hosts, archive wrappers, an ambiguous key — were run GREEN against the old
  copy before deleting it, so the refactor cannot be hiding a pre-existing
  divergence. **The PERIMETER stays separate**: the export indexes only
  expressions at `relevance >= minrel` because its file is a closed network,
  while `consolidate` indexes the whole land because it resolves in order to
  avoid creating a duplicate. A test pins that too.

### Added — Link profiles at export (sprint body-links, T4)

- **`kind` column appended at the END** of `*_pageslinks.csv` and
  `*_pageslinksfullhtml.csv`, so consumers selecting columns by name are
  unaffected. `NULL` is exported as `body`. Raw-only edges of the whole-page
  network carry an EMPTY kind, never `body`: a link absent from the body has
  no structural zone to report.
- **`--link-profile`** on `land export` (`citation` by default,
  `citation+reco`, `all`), overridable through `settings.link_profiles`. An
  unknown name falls back to the default with a warning rather than raising
  mid-export. `citation` names what the profile selects: the links attributable
  to the text's author (body plus reference blocks), as opposed to the links
  the site's own apparatus contributes (`nav`, `toc`, `reco`).
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
- No structural rule found separates recommendation blocks from genuine
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
  0.16 against 0.49 for a body link), and it dragged `context`/`dom`
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
- **Measured** (`make bench-links`, profile `citation`): precision **0.8792
  -> 0.9162**, recall 0.9249 -> 0.9210. False positives 82 -> 55, of which
  table-of-contents links fall from 27 to **2**. One citation out of
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
  DATA_LISTING 3, NOMAJ 2, EDIT 2 — **no REF_BIB**, which the gold counts as a
  citation (`place_group` EDITORIAL, an older naming). Loss attribution of the 123 misses: 26 recovered by Trafilatura's
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
