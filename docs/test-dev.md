# Test Suite — État et Backlog

> Mémoire vivante de la suite de tests MyWebIntelligence.
> **Lire ce fichier avant** d'écrire un nouveau test — il documente ce qui existe déjà et ce qui reste à faire.
> Sources canoniques : `README.md` §Testing · `CLAUDE.md` §4.1 · `Makefile` · `TESTING.md` · `tests/conftest.py`.
>
> **Dernière revue** : 2026-05-07 (sprint-searchrouter — ajout tests 17 → 25).

---

## 1. État actuel

| Indicateur | Valeur |
|------------|-------|
| Fichiers actifs | 25 (`tests/test_0[1-9]_*.py`, `test_1[0-6]_*.py`, `test_1[7-9]_*.py`, `test_2[0-5]_*.py`) |
| Tests collectés | **303 passed, 5 skipped** (2 ML extras + 2 Playwright + 1 SearXNG live) |
| Couverture `mwi/search/` | **89 %** (cible ≥ 85 % — sprint-searchrouter J9) |
| Couverture revendiquée (README) | ~87 % global |
| Couverture honnête plomberie pure | **~48 %** sur le pré-existant (audit 2026-05-06) |
| CI/CD | `.github/workflows/tests.yml` (3 jobs : basic / mercury / integration) |
| Lancement standard | `make test` (≈ 25 s, sans réseau) |
| JOSS | Phases 1–6 terminées le 29 janvier 2026 |

Tests legacy : `tests/legacy/` (anciens `test_cli_commands.py`, `test_serpapi.py`, etc.) — conservés pour référence, **non joués par `make test`**.

### Sprints couverts par la numérotation

| Plage | Sprint | Périmètre |
|-------|--------|-----------|
| 01 → 08 | Socle JOSS | Installation, lands, collecte, exports, médias, embeddings, intégration, HTML feature |
| 09 | sprint-normalise | Pipeline canonicalisation URL + migration 008 |
| 10 → 15 | sprint-403 | Cascade `aiohttp → curl_cffi → playwright → archive_org`, retry-status, browser pool partagé |
| 16 | sprint-403 cont. | Router SerpAPI single-engine (legacy `land urlist`, ex `test_16_search_router`) |
| 17 → 25 | **sprint-searchrouter** | Routeur multi-API, 5 adaptateurs, controller, intégration |

---

## 2. Ce qui est couvert (par fichier)

### `test_01_installation.py` — 12 tests
- `TestDatabaseSetup` : création de mwi.db, présence des 12 tables, idempotence de `db setup`.
- `TestDatabaseMigrate` : `db migrate` sur DB fraîche + validation idempotente.
- `TestEmbeddingCheck` : `embedding check` retourne 1 et imprime le statut du provider.

### `test_02_land_management.py` — 19 tests
- `TestLandCreate` (5) : minimal, description, `--lang`, multi-langues, doublon échoue.
- `TestLandList` (3) : vide, après création, détail par nom.
- `TestLandAddTerm` (3) : simple, multiple, land inexistant.
- `TestLandAddUrl` (5) : direct, fichier, dedup, création de Domain.
- `TestLandDelete` (3) : land entier, `--maxrel` (int), nom inconnu.

### `test_03_data_collection.py` — 12 tests (2 skipped sans clés)
- `TestLandCrawlMocked` (3) : fetch, `--limit`, http_status (patche `mwi.core`).
- `TestLandReadableMocked` (2) : extraction et `--limit`.
- `TestLandSeorankMocked` (1) + `TestLandSeorank` (1, `@pytest.mark.seorank`).
- `TestLandLlmValidateMocked` (2) : verdicts `oui` / `non` + invariant `relevance=0` si `non`.
- `TestLandLlmValidate` (1, `@pytest.mark.openrouter`).
- `TestDomainCrawl` (1) + `TestLandConsolidate` (1).

### `test_04_export.py` — 12 tests
- `TestLandExportCSV` (7) : `pagecsv`, `fullpagecsv`, `nodecsv`, `mediacsv`, `corpus`, `nodelinkcsv` (4 fichiers), `--minrel`.
- `TestLandExportGEXF` (2) : `pagegexf`, `nodegexf`.
- `TestTagExport` (3) : `matrix`, `content`, `--minrel`.

### `test_05_media_analysis.py` — 9 tests
- `TestMediaExtraction` (1) : depuis HTML.
- `TestMediaAnalysis` (2) : dimensions, couleurs dominantes.
- `TestMediaFiltering` (1) : dimensions min.
- `TestMediaMetadata` (3) : EXIF partiel, hash perceptuel, conformité.
- `TestMediaDuplicateDetection` (2) : par hash.

### `test_06_embeddings.py` — 12 tests
- `TestEmbeddingGeneration` (3) : provider `fake`, bornes min/max chars, `--limit`.
- `TestSimilarityCosine` (2) : exact + threshold.
- `TestSimilarityLSH` (2) : `cosine_lsh` + topk.
- `TestEmbeddingReset` (1).
- `TestPseudolinksExport` (3) : `pseudolinks`, `pseudolinkspage`, `pseudolinksdomain` (vérifient l'écriture, pas le contenu).
- `TestEmbeddingCheck` (1).

### `test_07_integration.py` — 11 tests
- `TestFullResearchWorkflow` (1) : create → addterm → addurl → crawl → readable → export.
- `TestRelevanceCalculation` (2) : indirect via crawl ; le calcul brut n'est pas testé.
- `TestCascadeDelete` (3) : Expression → Media, Expression → ExpressionLink, Land → tout.
- `TestErrorHandling` (3) : timeout, HTML malformé, mercury absent.
- `TestDataIntegrity` (2).

### `test_08_expression_html.py` — 11 tests
- Stockage HTML quand `--fullhtml=TRUE`, défaut `Land.fullhtml`, override CLI vs land, migration 007 idempotente, isolation entre lands.

### `test_09_url_normalize.py` — 46 tests (sprint-normalise)
- Idempotence, unwrap_archive récursif, lowercase host, force_https / strip_www opt-in, strip_trackers (utm_*, fbclid…), normalize_query_order, trailing_slash, integration avec `add_expression`.

### `test_10_fetcher.py` à `test_15_dynamic_media_pool.py` — sprint-403
- `test_10_fetcher` (13) : `FetchResult`, default chain, circuit breaker archive.org.
- `test_11_curl_cffi_strategy` (12, 1 skip) : TLS impersonation chrome120, opt-out via settings.
- `test_12_playwright_strategy` (11, 1 skip) : opt-in, sémaphore, BrowserContext isolés.
- `test_13_fetch_method` (8) : audit `expression.fetch_method`, distribution par stratégie.
- `test_14_retry_status` (11) : `--retry-status=403,429`, ignore `fetched_at`, mise à jour cascade.
- `test_15_dynamic_media_pool` (3) : pool Chromium partagé entre `extract_dynamic_medias` et la cascade fetch.

### `test_16_serpapi_router.py` — 17 tests (legacy `land urlist`)
- Router SerpAPI single-engine (Google / Bing / DuckDuckGo).
- Originalement `test_16_search_router.py` ; renommé J0 du sprint-searchrouter pour libérer le namespace `mwi/search/`.

### `test_17_search_models.py` — 11 tests (sprint-searchrouter J2)
- Insertion `SearchQuery` / `SearchResultLog`, contrainte unique `(search_query, url)`, cascade DELETE Land → SearchQuery → Log, FK `expression` SET NULL, JSON round-trip de `usage_report`, idempotence migration 010, dataclasses applicatives (`ProviderStatus`, `ProviderUsage`, `SearchResult.to_dict()`).

### `test_18_search_provider_searxng.py` — 21 tests (sprint-searchrouter J3)
- `canonicalize_url` (6 cas paramétrés) + `merge_results` (dédup, concat providers, drop empty URLs).
- Adaptateur SearXNG : success, respect du `--num`, empty query, retry sur 429 puis succès, 429 quota après retry, 5xx, network error, skip results sans URL, response vide, résolution `SEARXNG_BASE_URL` depuis env, `is_configured`, `usage()` snapshot.

### `test_19_search_provider_brave.py` — 8 tests (sprint-searchrouter J4)
- success, missing key, quota_exceeded sur 402 et 429, invalid key 401, network error, empty response, résolution `BRAVE_API_KEY` depuis env.

### `test_20_search_provider_serper.py` — 6 tests (sprint-searchrouter J4)
- success (POST), missing key, quota_exceeded, network error, empty response, invalid key 403.

### `test_21_search_provider_serpapi.py` — 7 tests (sprint-searchrouter J4)
- success, missing key (avec env + settings nettoyés), quota_exceeded HTTP 429, quota dans le body JSON 200 OK (cas spécifique SerpAPI), network error, empty response, fallback vers `settings.serpapi_api_key` (legacy snake-case).

### `test_22_search_provider_tavily.py` — 5 tests (sprint-searchrouter J5)
- success (POST), missing key, quota_exceeded, network error, empty response.

### `test_23_search_router.py` — 11 tests (sprint-searchrouter J6)
- Registration : skip unconfigured, dedup by name, unsupported strategy raises.
- Fallback : first success court-circuite, first empty enchaîne, all fail retourne `[]`.
- Parallel : merge + dedup + concat providers + best rank, isolation des échecs (un raise n'invalide pas le batch), filtre par whitelist `--providers`.
- No provider configured ⇒ `[]`. usage_report JSON round-trip.

### `test_24_search_controller.py` — 8 tests (sprint-searchrouter J7)
- `search run` persiste SearchQuery + SearchResultLog + Expression ; deux runs = pas de doublon Expression mais 2 SearchQuery + 4 logs ; required `--land`/`--query` ; no provider ⇒ rc=0 ; `search list` imprime ; `search usage` agrège ; `search check` liste les 5 providers ; `search run --providers=…` filtre correctement.

### `test_25_search_integration.py` — 5 tests, 1 skip (sprint-searchrouter J9)
- 1. SearXNG live (skipped si `SEARXNG_BASE_URL` injoignable via TCP probe).
- 2. Mock parallel : 3 providers avec URL partagée → fusion correcte (3 providers concaténés, rank=min).
- 3. Mock fallback : premier provider qui échoue → second appelé.
- 4. `search run` end-to-end : Expression rows créées dans le Land, FK `expression` rempli sur les logs.
- 5. `usage_report` JSON persisté + décodé via Peewee.

---

## 3. Conventions

### Fixtures (`tests/conftest.py`)
- `test_env` — isole `data_location` dans `tmp_path`, ré-importe les modules avec ce chemin.
- `fresh_db` — DB SQLite vierge avec schéma complet ; auto-confirme les actions destructives.
- `populated_land` — Land avec 20 expressions, liens, médias, tags pour les exports.
- `mock_http_server` — `pytest-httpserver` pour simuler des pages HTTP.

### Marqueurs pytest
| Marqueur | Skip si |
|----------|---------|
| `serpapi` | `MWI_SERPAPI_API_KEY` absent |
| `seorank` | `MWI_SEORANK_API_KEY` absent |
| `openrouter` | `MWI_OPENROUTER_API_KEY` absent |
| `mercury` | binaire `mercury-parser` absent |
| `playwright` | navigateurs Playwright absents |
| `integration` | tests lents end-to-end |
| `slow` | > 5 s |

Test live SearXNG (`test_25` scenario 1) : skip via `pytest.mark.skipif` dynamique
qui pingue `SEARXNG_BASE_URL` en TCP au moment de la collecte (pas de marqueur).

### Mocking — patterns établis
- **HTTP** : `responses` (synchrone) ou `pytest-httpserver` (réel, local).
- **Async aiohttp** : `monkeypatch.setattr(mwi.core, '_fetch_url', ...)` — patcher le module, pas l'instance importée localement (correction historique 2026-01-29).
- **Async aiohttp via `aioresponses`** (ajouté sprint-searchrouter) — pattern préféré pour les nouveaux adaptateurs HTTP. Exemple : `with aioresponses() as m: m.get(re.compile(r"https://api\.x\.com/.*"), status=200, payload=…)`. Ne nécessite pas de patcher le module ; intercepte au niveau du transport.
- **OpenRouter** : `responses.add(POST, …)` ou `monkeypatch` sur `llm_openrouter.classify`.
- **Mercury** : `monkeypatch` sur `subprocess.run` ; charger le JSON de réponse depuis `tests/fixtures/mock_mercury_response.json`.
- **Embeddings** : `monkeypatch` sur `embedding_pipeline.settings.embed_provider = 'fake'` (sinon les imports ML cassent en CI).
- **Search router** : monkeypatch `SearchController._build_router` pour injecter un router `SearchRouter()` peuplé de `FakeProvider` retournant des `SearchResult` cannés — évite tout HTTP.

### Règles
- Aucun credential en dur. Variables d'env uniquement.
- Un test par invariant — pas de tests « teste tout en même temps ».
- Nommer `test_<action>_<expected_result>` (ex: `test_addurl_deduplication`).
- Ne pas dupliquer ce qui est dans `tests/legacy/` ; si on a besoin du test, le **migrer** dans la suite numérotée.

---

## 4. Backlog — issu de l'audit plomberie (2026-05-06)

> Audit complet : voir l'historique de conversation Claude du 2026-05-06.
> Couverture plomberie estimée à 48 % avec 5 invariants critiques jamais validés.

### Priority 1 — Invariants métier centraux (jamais testés)

| Test à écrire | Cible | Effort |
|---------------|-------|--------|
| `test_expression_relevance_title_weighted_10x` | `core.expression_relevance` — règle `title×10 + content×1` | 30 min |
| `test_expression_relevance_zero_on_lang_mismatch` | `core.expression_relevance` — invariant lang | 20 min |
| `test_smart_merge_keeps_longer_title` | `readable_pipeline.smart_merge` (logique pure) | 30 min |
| `test_mercury_priority_overwrites_existing` | `readable_pipeline` — stratégie 2/3 | 20 min |
| `test_preserve_existing_does_not_overwrite` | `readable_pipeline` — stratégie 3/3 | 20 min |
| `test_expressionlink_composite_pk_rejects_duplicate` | `model.ExpressionLink` — clé composite | 15 min |
| `test_paragraph_text_hash_unique_constraint` | `model.Paragraph.text_hash UNIQUE` | 15 min |
| `test_landdictionary_composite_pk_rejects_duplicate` | `model.LandDictionary` (land, word) | 15 min |

### Priority 2 — Helpers et parsing (jamais appelés)

| Test à écrire | Cible |
|---------------|-------|
| `test_extract_md_links_handles_images_and_links` | `core.extract_md_links` |
| `test_remove_anchor_strips_fragment` | `core.remove_anchor` |
| `test_is_crawlable_filters_extensions` | `core.is_crawlable` |
| `test_stem_word_french_lemmatization` | `core.stem_word` (FrenchStemmer) |
| `test_get_arg_option_type_conversion` | `core.get_arg_option` (int/str/bool) |
| `test_split_into_paragraphs_respects_length_bounds` | `embedding_pipeline.split_into_paragraphs` |

### Priority 3 — Exports : valider le contenu, pas seulement la création

| Test à écrire | Cible |
|---------------|-------|
| `test_pagecsv_includes_seorank_columns_when_populated` | colonnes dynamiques `sr_*`, `fb_*` |
| `test_export_pseudolinks_columns_match_doc` | header CSV vs doc README |
| `test_export_pseudolinkspage_aggregations_correct` | `PairCount`, `EntailCount`, etc. |
| `test_export_pseudolinksdomain_aggregations_correct` | agrégation domaine↔domaine |
| `test_export_minrel_actually_filters_rows` | invariant : aucune ligne `relevance < minrel` |
| `test_corpus_export_zip_structure` | un fichier `id-title.txt` par expression, front-matter YAML |
| `test_pagegexf_includes_seorank_attributes` | `<attribute>` + `<attvalue>` SEO Rank |

### Priority 4 — Migrations (0 % testé)

| Test à écrire | Cible |
|---------------|-------|
| `test_migration_001_idempotent` | run 2× sans erreur |
| `test_migration_005_adds_validllm_to_populated_db` | data preservation |
| `test_migration_006_adds_seorank_to_populated_db` | data preservation |
| `test_migration_007_adds_html_fields_to_populated_db` | déjà partiellement couvert dans `test_08` |
| `test_migrate_full_chain_001_to_007` | replay complet sur DB ancienne |

### Priority 5 — Commandes oubliées

| Test à écrire | Cible |
|---------------|-------|
| `test_db_fix_archive_domains_dryrun_writes_nothing` | mode preview |
| `test_db_fix_archive_domains_apply_reattributes` | mode apply |
| `test_heuristic_update_changes_domain` | `core` heuristics regex |
| `test_llm_validate_force_overrides_non_only` | sémantique de `--force` (re-traite `non`, pas `oui`) |

**Estimation totale Priority 1–5 : ~25 tests, ~6 h de travail.**
Atteindre une plomberie « solide » (couverture 75 %+ des fonctions pures et invariants DB).

---

## 5. Reporté (hors plomberie — accepté)

Ces tests touchent les contrats réseau / dépendances externes. Ils sont **délibérément reportés** car :
- ils sont fragiles (cassent quand l'API change),
- les mocks sur la plomberie suffisent pour valider notre code.

Liste pour mémoire :
- NLI Cross-Encoder + FAISS (`embedding similarity --method=nli --backend=faiss`) — non testé.
- OpenRouter budget exhaustion (`openrouter_max_calls_per_run`) — non testé.
- SerpAPI date windows réelles (`--datestart`/`--dateend`/`--timestep`) — testé en `legacy/` seulement.
- Concurrence asyncio (bornes `parallel_connections`, race conditions) — non testé.
- Providers d'embeddings autres que `fake` (`openai`, `mistral`, `gemini`, `huggingface`, `ollama`) — non testés.
- Mercury Parser absent du PATH — pas de test du fallback.
- Erreurs réseau réelles (timeouts, 5xx, JSON malformé venant de tiers) — peu de tests.

À reprendre si :
- nous publions un service/API qui dépend de ces composants (ex : déploiement HF Spaces),
- une régression utilisateur en production survient sur l'un d'eux.

---

## 6. Procédure pour ajouter un test

1. **Vérifier qu'il n'existe pas déjà** : `grep -rn "test_<verbe>_<expected>" tests/`.
2. **Choisir le bon fichier** : 01 = install/migration, 02 = CRUD land, 03 = collection (crawl/readable/seorank/llm), 04 = export, 05 = média, 06 = embeddings, 07 = end-to-end, 08 = HTML storage. **Si aucun ne convient**, créer `test_09_*.py` avec une convention claire.
3. **Réutiliser les fixtures** (`fresh_db`, `populated_land`).
4. **Mocker la couche réseau** (cf. patterns §3).
5. **Marquer si nécessaire** (`@pytest.mark.serpapi`, `slow`, etc.).
6. **Lancer en isolation** : `pytest tests/test_XX::TestClass::test_function -v`.
7. **Lancer la suite complète** : `make test`. Doit rester < 30 s.
8. **Mettre à jour ce fichier** : déplacer le test du backlog (§4) vers la couverture (§2).

---

## 7. Historique court

- **2026-01-29** — Phases 1–6 du plan JOSS terminées : 7 fichiers, 87 tests. Mercury en mock. Provider embeddings forcé à `fake` en CI.
- **2026-02-XX** — Ajout de `test_08_expression_html.py` (11 tests) pour la fonctionnalité HTML storage (migration 007, options `--fullhtml`).
- **2026-05-06** — Audits README + plomberie. CLAUDE.md mis à jour. Backlog plomberie consolidé (§4 ci-dessus).

Le plan original (1745 lignes, pseudocode complet par phase) reste consultable via `git log --follow -- .claude/project/test-dev.md` ou dans l'historique de PR.

---

## 8. Référence rapide — commandes

```bash
make test                      # Suite standard (sans réseau, ~7 s)
make test-cov                  # Avec rapport HTML dans htmlcov/
make test-apis                 # Tests gated par les clés API
make test-quick                # Smoke (test_01 seul)
make test-08                   # Cibler un fichier précis (cibles 01..05 dispo)
make joss-test                 # Replay du flow d'évaluation JOSS

pytest tests/test_06_embeddings.py::TestSimilarityCosine -v   # Une classe
pytest tests/ -k "merge"       # Tous les tests dont le nom contient "merge"
pytest --collect-only -q       # Inventaire sans exécution
pytest --markers               # Liste les marqueurs
```

---

**Mainteneur** : Amar LAKEL · **Sources** : `README.md`, `CLAUDE.md`, `.claude/rules/Agent.md`, `.claude/rules/Pipelines.md`.
