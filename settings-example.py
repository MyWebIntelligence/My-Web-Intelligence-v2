"""
Example settings for My Web Intelligence.

Copy this file to `settings.py` and fill in the blanks or replace values
with environment variables for your environment. All API keys default to
reading the `MWI_*` environment variables to simplify container setups.
"""

import os

# Paths & storage
# Allow override via env var for containerized runs
data_location = os.getenv("MYWI_DATA_DIR", "data")

archive = False

# Enable dynamic media extraction using headless browser (requires Playwright)
dynamic_media_extraction = True

default_timeout = 10  # Network HTTP timeout (crawl/fetch)

parallel_connections = 10  # Async HTTP concurrency for crawling

user_agent = ""  # Optionally set a custom UA

# ─────────────────────────────────────────────────────────────────────────
# Languages (sprint-multilang)
# ─────────────────────────────────────────────────────────────────────────
# Lands are created with `land create --lang=fr` (comma-separated list for
# multilingual lands, e.g. --lang=fr,en). Tokenization and stemming follow
# the land's language(s). Supported stemming languages (Snowball, ISO
# 639-1): ar, da, de, en, es, fi, fr, hu, it, nl, no, pt, ro, ru, sv —
# any other code falls back to lowercase identity (no stemming). ar/hu/ro
# have no NLTK punkt model and use a unicode fallback tokenizer. For
# non-French lands created before this feature, run:
#   python mywi.py db migrate && python mywi.py land relemm --name=LAND

# ─────────────────────────────────────────────────────────────────────────
# Crawl fallback cascade (sprint-403)
# ─────────────────────────────────────────────────────────────────────────
# When the primary aiohttp fetch returns a status that suggests TLS/JS
# bot detection (Cloudflare 403/429/etc.), MWI retries with progressively
# heavier strategies. The orchestrator preserves the original status code
# in expression.http_status — only `expression.fetch_method` (Sprint 4)
# tells you which strategy provided the body.
#
# crawl_fallback_curl_cffi: enable retry with curl_cffi (TLS-impersonating
#   client). Free, fast, ~70-80% effective on Cloudflare. Required dep:
#   `pip install curl_cffi` (in requirements.txt).
crawl_fallback_curl_cffi = True
crawl_fallback_curl_cffi_impersonate = "chrome120"  # or "safari17_2"

# crawl_fallback_playwright: real headless Chromium fallback. Solves
# Cloudflare JS challenges (cf_clearance) that curl_cffi cannot.
# OFF by default because each invocation costs ~3-5 seconds. Turn on
# only when curl_cffi is not enough for your sites.
# Requires: `playwright install chromium`.
crawl_fallback_playwright = False
crawl_fallback_playwright_max_concurrent = 4   # bounds RAM (1 page ~= 80 MB)
crawl_fallback_playwright_timeout_sec = 30

# crawl_retry_status_codes: status strings that trigger retry-only
# strategies (curl_cffi, Playwright). Keep "ERR" to retry on unhandled
# exceptions during the primary fetch.
crawl_retry_status_codes = [
    "403", "406", "429",
    "503", "520", "521", "523", "526",
    "ERR",
]

# fullhtml_max_size_kb: maximum size (in KB) of the raw HTML stored in
# expression.html when --fullhtml is active (sprint-html E). Pages above
# this threshold are truncated at the cap to protect the SQLite WAL cache
# from pathological pages (single-page-apps with embedded base64 PDFs,
# >50 MB JSON dumps, etc.). Set to 0 to disable the cap entirely.
# Defaults to 5 MB which fits 99 % of HTML pages while keeping a 100 k
# URL Land under ~500 GB worst case.
fullhtml_max_size_kb = 5120

# Link-context (sprint link-context): tailles max des métadonnées de lien
# stockées dans expressionlink (migration 012). context = paragraphe markdown
# du readable contenant le lien ; dom_html = outerHTML du bloc ancêtre du <a>.
link_context_max_chars = 1000     # troncature de expressionlink.context
link_dom_html_max_chars = 4000    # troncature de expressionlink.dom_html

# Cut Domains

heuristics = {
    "facebook.com": r"([a-z0-9\-_]+\.facebook\.com/(?!(?:permalink.php)|(?:notes))[a-zA-Z0-9\.\-_]+)/?\??",
    "twitter.com": r"([a-z0-9\-_]*\.?twitter\.com/(?!(?:hashtag)|(?:search)|(?:home)|(?:share))[a-zA-Z0-9\.\-_]+)",
    "linkedin.com": r"([a-z0-9\-_]+\.linkedin\.com/[a-zA-Z0-9\.\-_]+)/?\??",
    "slideshare.net": r"([a-z0-9\-_]+\.slideshare\.com/[a-zA-Z0-9\.\-_]+)/?\??",
    "instagram.com": r"([a-z0-9\-_]+\.instagram\.com/[a-zA-Z0-9\.\-_]+)/?\??",
    "youtube.com": r"([a-z0-9\-_]+\.youtube\.com/(?!watch)[a-zA-Z0-9\.\-_]+)/?\??",
    "vimeo.com": r"([a-z0-9\-_]+\.vimeo\.com/[a-zA-Z0-9\.\-_]+)/?\??",
    "dailymotion.com": r"([a-z0-9\-_]+\.dailymotion\.com/(?!video)[a-zA-Z0-9\.\-_]+)/?\??",
    "pinterest.com": r"([a-z0-9\-_]+\.pinterest\.com/(?!pin)[a-zA-Z0-9\.\-_]+)/?\??",
    "pinterest.fr": r"([a-z0-9\-_]+\.pinterest\.fr/[a-zA-Z0-9\.\-_]+)/?\??",
}

# Opaque platforms (sprint-heuristique) — hosts whose editorial entity
# (channel, author, blog) is NOT reliably derivable from the URL path, so
# `heuristic update --html` reads the page HTML (canonical / og:url / JSON-LD
# author) to recover a better URL before applying the heuristics above.
#
# The canonical ~150-suffix set lives in mwi.core._DEFAULT_OPAQUE_PLATFORMS.
# Define `opaque_platforms` below (a set/iterable of host suffixes, matched on
# a label boundary) ONLY to override that default; leave it undefined to use
# the built-in list. Example:
# opaque_platforms = {"youtube.com", "youtu.be", "linkedin.com", "mediapart.fr"}

# Media Analysis Settings
media_analysis = True
media_min_width = 200
media_min_height = 200
media_max_file_size = 10 * 1024 * 1024  # 10MB
media_download_timeout = 30
media_max_retries = 2
media_analyze_content = False
media_extract_colors = True
media_extract_exif = True
media_n_dominant_colors = 5


# OpenRouter relevance gate (disabled by default)
openrouter_enabled = os.getenv("MWI_OPENROUTER_ENABLED", "false").lower() == "true"
openrouter_api_key = os.getenv("MWI_OPENROUTER_API_KEY", "")
openrouter_model = os.getenv("MWI_OPENROUTER_MODEL", "deepseek/deepseek-v4-flash")
# Exemples de modèles compatibles OpenRouter (mini/éco)
# Renseignez `openrouter_model` avec l'un de ces slugs si vous activez la passerelle
openrouter_model_examples = [
    # OpenAI
    "openai/gpt-mini-latest",
    # Anthropic
    "anthropic/claude-3-haiku",
    # Google
    "google/gemini-3-flash-preview",
    # Meta (Llama 3.x Instruct – 8B)
    "meta-llama/llama-3.1-8b-instruct",
    # Mistral
    "mistralai/mistral-small-latest",
    # Qwen (Alibaba)
    "qwen/qwen2.5-7b-instruct",
    # Deepseek
    "deepseek/deepseek-v4-flash",
]
# "Controversy analysis" mode: when True, the LLM gate uses a stricter prompt
# that keeps only editorial / position-taking pages on the project's issue and
# drops index/navigation and generic company-presentation pages. Global default
# for every gate call (crawl, readable, consolidate, llm validate); the
# --issuecrawl CLI flag overrides it per run.
openrouter_issue_mode = os.getenv("MWI_OPENROUTER_ISSUE_MODE", "false").lower() == "true"
openrouter_timeout = int(os.getenv("MWI_OPENROUTER_TIMEOUT", "15"))
# Bounds to control costs/latency
openrouter_readable_min_chars = int(os.getenv("MWI_OPENROUTER_MIN_CHARS", "140"))
openrouter_readable_max_chars = int(os.getenv("MWI_OPENROUTER_MAX_CHARS", "12000"))
# Per-run safety cap on LLM gate calls. Set to 0 (or MWI_OPENROUTER_MAX_CALLS=0)
# for no limit — e.g. a full `land llm validate` over a large land in one run.
openrouter_max_calls_per_run = int(os.getenv("MWI_OPENROUTER_MAX_CALLS", "500"))



# SEO Rank enrichment (land seorank)
seorank_api_base_url = os.getenv(
    "MWI_SEORANK_API_BASE_URL", "https://seo-rank.my-addr.com/api2/sr+fb"
)
seorank_api_key = os.getenv("MWI_SEORANK_API_KEY", "")
seorank_timeout = 15  # seconds
seorank_request_delay = 1.0  # polite sleep between API calls

# SerpAPI enrichment (land urlist)
serpapi_api_key = os.getenv("MWI_SERPAPI_API_KEY", "")
serpapi_base_url = "https://serpapi.com/search"
serpapi_timeout = 15  # seconds
serpapi_max_retries = 3  # attempts per request on timeout / 429 / 5xx (backoff 2s, 4s, 8s…)


# --- Embedding Settings ---

# Embedding settings (bi-encoder)
# Provider: one of 'fake', 'http', 'openai', 'mistral', 'gemini', 'huggingface', 'ollama'
embed_provider = os.getenv('MWI_EMBED_PROVIDER', 'mistral')

# Common
embed_model_name = os.getenv("MWI_EMBED_MODEL", "mistral-embed")
embed_batch_size = 32
embed_min_paragraph_chars = 150
embed_max_paragraph_chars = 6000
embed_similarity_threshold = 0.75
embed_similarity_method = 'cosine'  # 'cosine' | 'cosine_lsh'
embed_max_retries = 5
embed_backoff_initial = 1.0
embed_backoff_multiplier = 2.0
embed_backoff_max = 30.0
embed_sleep_between_batches = 0.0

# Generic HTTP provider
embed_api_url = os.getenv("MWI_EMBED_API_URL", "")
embed_http_headers = {}

# OpenAI API
embed_openai_base_url = "https://api.openai.com/v1"
embed_openai_api_key = os.getenv("MWI_OPENAI_API_KEY", "")

# Mistral API
embed_mistral_base_url = "https://api.mistral.ai/v1"
embed_mistral_api_key = os.getenv("MWI_MISTRAL_API_KEY", "")

# Google Gemini (Generative Language API)
embed_gemini_base_url = "https://generativelanguage.googleapis.com/v1beta"
embed_gemini_api_key = os.getenv("MWI_GEMINI_API_KEY", "")

# Hugging Face Inference API
embed_hf_base_url = "https://api-inference.huggingface.co/models"
embed_hf_api_key = os.getenv("MWI_HF_API_KEY", "")

# Ollama local API
embed_ollama_base_url = os.getenv("MWI_OLLAMA_BASE_URL", "http://localhost:11434")

# --- Semantic Search & NLI Settings ---
embedding_model_name = embed_model_name

# Cross-Encoder (NLI) model
nli_model_name = os.getenv(
    "MWI_NLI_MODEL_NAME",
    "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7",
)
nli_batch_size = 64

# Backend preference: 'auto', 'transformers', 'crossencoder', 'fallback'
nli_backend_preference = os.getenv("MWI_NLI_BACKEND", 'fallback')

# CPU threading
nli_torch_num_threads = int(os.getenv("MWI_NLI_TORCH_THREADS", "1"))

# Fallback NLI model
nli_fallback_model_name = os.getenv(
    "MWI_NLI_FALLBACK_MODEL_NAME",
    "typeform/distilbert-base-uncased-mnli",
)

# Max tokens fed to the NLI tokenizer/model
nli_max_tokens = 512

# Progress reporting during NLI scoring
nli_progress_every_pairs = 1000
nli_show_throughput = True

# ANN Backend Configuration (recall)
similarity_backend = os.getenv('MWI_SIMILARITY_BACKEND', 'faiss')
similarity_top_k = int(os.getenv('MWI_SIMILARITY_TOP_K', '50'))

# NLI Classification Thresholds
nli_entailment_threshold = float(os.getenv('MWI_NLI_ENTAILMENT_THRESHOLD', '0.8'))
nli_contradiction_threshold = float(os.getenv('MWI_NLI_CONTRADICTION_THRESHOLD', '0.8'))


# ────────────────────────────────────────────────────────────────────────
# URL normalization (sprint-normalise)
# ────────────────────────────────────────────────────────────────────────
# Configures the canonicalization pipeline applied to every URL ingested
# into MWI (seeds, SerpAPI results, links extracted at crawl time, etc.).
# See mwi/url_normalizer.py and .claude/project/sprint-normalise.md.
#
# Conservative defaults: only operations that don't risk breaking existing
# Lands are enabled by default. force_https / strip_www / strip_mobile
# require explicit opt-in.
url_normalization = {
    "unwrap_archive": True,
    # Unwrap linkedin.com/redir?url=… and cold-join?session_redirect=…
    # wrappers to their real target. Off by default (may diverge existing
    # lands, like force_https/strip_www). See sprint-extractlinks LINK-6.
    "unwrap_linkedin_redirect": os.getenv(
        "MWI_URL_UNWRAP_LINKEDIN", "false").lower() == "true",
    "lowercase_host": True,
    "force_https": os.getenv("MWI_URL_FORCE_HTTPS", "false").lower() == "true",
    "strip_www": os.getenv("MWI_URL_STRIP_WWW", "false").lower() == "true",
    "strip_mobile_subdomain": os.getenv("MWI_URL_STRIP_MOBILE", "false").lower() == "true",
    "strip_trackers": [
        "utm_*", "fbclid", "gclid", "mc_eid", "ref_src", "_ga",
        "yclid", "_openstat", "wt_*", "msclkid", "igshid", "spm",
    ],
    "normalize_query_order": True,
    "trailing_slash": "preserve",  # 'preserve' | 'strip' | 'add'
}


# ────────────────────────────────────────────────────────────────────────
# Multi-API search router (sprint-searchrouter)
# ────────────────────────────────────────────────────────────────────────
# Configuration for `python mywi.py search …` — a multi-provider URL
# collector independent from the historical `land urlist` SerpAPI path.
# Every value can be overridden by an environment variable of the same
# name (or via a .env file at the project root).

# Self-hosted SearXNG instance — primary, free provider. The default
# matches the docker-compose published in `docker/searxng/`.
SEARXNG_BASE_URL = os.getenv("SEARXNG_BASE_URL", "http://localhost:8888")

# Commercial providers — keep these as None unless you have credentials.
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")  # distinct from the historical
                                                # `serpapi_api_key` (snake-case)
                                                # used by `land urlist`. The
                                                # search router falls back to
                                                # the snake-case key when the
                                                # UPPER one is unset.
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

# Default orchestration strategy:
#   - "fallback" preserves quotas (try providers in order, stop at first hit).
#   - "parallel" triangulates (query everyone in parallel and merge results).
SEARCH_DEFAULT_STRATEGY = os.getenv("SEARCH_DEFAULT_STRATEGY", "fallback")

# Per-provider HTTP timeout in seconds.
SEARCH_PROVIDER_TIMEOUT = int(os.getenv("SEARCH_PROVIDER_TIMEOUT", "30"))
