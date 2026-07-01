import json
from typing import Optional, List

import requests

from . import model
import settings


_call_count = 0


# Human-readable language names for the prompt (project working language).
# Covers at least the 15 Snowball stemming languages; falls back to the code.
_LANG_NAMES = {
    'ar': 'Arabic', 'da': 'Danish', 'de': 'German', 'en': 'English',
    'es': 'Spanish', 'fi': 'Finnish', 'fr': 'French', 'hu': 'Hungarian',
    'it': 'Italian', 'nl': 'Dutch', 'no': 'Norwegian', 'pt': 'Portuguese',
    'ro': 'Romanian', 'ru': 'Russian', 'sv': 'Swedish',
}


def _get_land_terms(land: model.Land) -> List[str]:
    """Retrieve all dictionary terms associated with a land.

    Args:
        land: Land object to retrieve terms for.

    Returns:
        List of term strings from the land's dictionary.
    """
    rows = (
        model.Word.select(model.Word.term)
        .join(model.LandDictionary)
        .where(model.LandDictionary.land == land)
    )
    return [r.term for r in rows]


def build_relevance_prompt(land: model.Land, expression: model.Expression,
                           readable_text: str, issue_mode: bool = False) -> str:
    """Build the LLM prompt for relevance evaluation.

    Args:
        land: Land object containing project context.
        expression: Expression object to evaluate.
        readable_text: Extracted readable content from the expression.
        issue_mode: When True, use the stricter "controversy analysis" prompt
            that keeps only editorial/position-taking pages on the project's
            issue and drops index/navigation and generic presentation pages.

    Returns:
        Formatted prompt string requesting a yes/no judgment.

    Note:
        The prompt wrapper is always English (lingua franca of LLMs) but it
        states the project's working language and asks the model to reason in
        that language, within the project's cultural and linguistic context.
        This supersedes the French/English template split of sprint-multilang
        (D7). The response parser still accepts both oui/non and yes/no
        (see _normalize_yesno).
    """
    terms = ", ".join(_get_land_terms(land))
    title = str(getattr(expression, "title", "") or "")
    desc = str(getattr(expression, "description", "") or "")
    url = str(getattr(expression, "url", "") or "")
    land_desc = str(getattr(land, "description", "") or "")
    primary_lang = str(getattr(land, "lang", "") or "fr").split(',')[0].split('-')[0].strip().lower()
    lang_name = _LANG_NAMES.get(primary_lang, primary_lang)

    # Shared block: English wrapper, but the model is told the project's working
    # language and asked to reason within its cultural/linguistic sphere.
    project_block = (
        f"The project's working language is {lang_name} ({primary_lang}). "
        f"Think and reason in {lang_name}, within the cultural and linguistic "
        "context of the project.\n"
        "Project:\n"
        f"- Name: {land.name}\n"
        f"- Description: {land_desc}\n"
        f"- Keywords: {terms}\n"
        "Page under review:\n"
        f"- URL = {url}\n"
        f"- Title: {title}\n"
        f"- Description: {desc}\n"
        f"- Readable (excerpt): {readable_text}\n"
    )

    if issue_mode:
        prompt = (
            "We are building a corpus of web pages for a CONTROVERSY ANALYSIS, and "
            "we need to decide whether the page is an EDITORIAL STATEMENT that takes "
            "a position, informs, or argues about the project's issue.\n"
            + project_block +
            "Answer \"yes\" ONLY if the page expresses a stance, an argument, an "
            "opinion, an analysis, or substantive information that ENGAGES with the "
            "project's issue.\n"
            "Answer \"no\" if the page is a table of contents, an index, a "
            "navigation or link-list page; an institutional or company-presentation "
            "page that does not debate the issue; a contact, legal-notice, or login "
            "page; or has no substantive content on the issue.\n"
            "You MUST answer with \"yes\" or \"no\" only, without any commentary."
        )
    else:
        prompt = (
            "We are building a corpus of web pages for content analysis, and we "
            "need to decide whether the crawled page is relevant to the project or "
            "not.\n"
            + project_block +
            "You MUST answer with \"yes\" or \"no\" only, without any commentary."
        )
    return prompt


def _normalize_yesno(text: str) -> str:
    """Normalize LLM response to standard yes/no format.

    Args:
        text: Raw response text from LLM.

    Returns:
        Normalized response: "oui", "non", or "?" for unclear responses.

    Note:
        Handles both French (oui/non) and English (yes/no) responses.
    """
    t = (text or "").strip().lower()
    # startswith (not equality): models often answer "Yes." / "No, ..." —
    # critical since English prompts became the default for non-fr lands
    # (sprint-multilang, D7).
    if t.startswith("non") or t.startswith("no"):
        return "non"
    if t.startswith("oui") or t.startswith("yes"):
        return "oui"
    return "?"


def ask_openrouter_yesno(prompt: str) -> str:
    """Send a yes/no question to OpenRouter API.

    Args:
        prompt: Formatted prompt string for the LLM.

    Returns:
        Raw response content from the LLM.

    Raises:
        requests.HTTPError: If the API request fails.

    Note:
        Uses temperature=0 for deterministic responses.
    """
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": settings.openrouter_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        data=json.dumps(body),
        timeout=settings.openrouter_timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def is_relevant_via_openrouter(land: model.Land, expression: model.Expression,
                               issue_mode: Optional[bool] = None) -> Optional[bool]:
    """Evaluate expression relevance using OpenRouter LLM.

    Args:
        land: Land object providing research context.
        expression: Expression object to evaluate for relevance.
        issue_mode: When True, force the stricter "controversy analysis"
            prompt; when False, force the standard prompt; when None (default),
            fall back to settings.openrouter_issue_mode. This lets the .env
            switch reach every caller (crawl, readable, consolidate, validate)
            with no extra plumbing, while a CLI flag can override per run.

    Returns:
        True if relevant, False if not relevant, None if inconclusive or
        disabled/error.

    Note:
        Respects settings for enabled status, API credentials, and call
        budget. Increments global call counter. Prints verdict to stdout.
    """
    global _call_count

    # Preconditions
    if not getattr(settings, "openrouter_enabled", False):
        return None
    if not settings.openrouter_api_key or not settings.openrouter_model:
        print("OpenRouter disabled: missing API key or model")
        return None
    # Per-run safety cap on LLM calls. 0 (or any non-positive value) means
    # "no limit", matching the codebase convention for budget knobs
    # (e.g. --limit, fullhtml_max_size_kb). A positive value bounds the run.
    max_calls = settings.openrouter_max_calls_per_run
    if max_calls > 0 and _call_count >= max_calls:
        print("OpenRouter budget reached for this run; skipping gate")
        return None

    if issue_mode is None:
        issue_mode = getattr(settings, "openrouter_issue_mode", False)

    readable_text = str(getattr(expression, "readable", "") or "")
    if readable_text:
        readable_text = readable_text[: settings.openrouter_readable_max_chars]
    else:
        # Fallback to a minimal context if readable is missing
        readable_text = ""

    prompt = build_relevance_prompt(land, expression, readable_text, issue_mode=issue_mode)

    try:
        _call_count += 1
        content = ask_openrouter_yesno(prompt)
        verdict = _normalize_yesno(content)
        if verdict == "non":
            print(f"OpenRouter gate verdict=NON for {expression.url}")
            return False
        if verdict == "oui":
            print(f"OpenRouter gate verdict=OUI for {expression.url}")
            return True
        print(f"OpenRouter gate verdict=INCONNU for {expression.url}: '{content[:50]}...'")
        return None
    except Exception as e:
        print(f"OpenRouter gate error for {expression.url}: {e}")
        return None

