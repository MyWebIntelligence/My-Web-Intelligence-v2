"""Sprint validate-update: consolidate respects/refreshes LLM verdicts, and the
LLM gate supports a stricter "controversy analysis" prompt (--issuecrawl /
settings.openrouter_issue_mode), with English prompts that state the project's
language.

Boundaries mocked per testing.md: the network-facing
``llm_openrouter.is_relevant_via_openrouter`` / ``ask_openrouter_yesno`` are
patched; everything else runs against a real test DB (``fresh_db``). The autouse
``network_safe_settings`` fixture forces ``openrouter_enabled=False`` — tests
that exercise the gate re-enable it via monkeypatch.
"""

import asyncio
import datetime
import random
import string
from types import SimpleNamespace

import pytest


def run(coro):
    """Drive an async coroutine without pytest-asyncio (style of test_31)."""
    return asyncio.new_event_loop().run_until_complete(coro)


def rand_name(prefix="vu"):
    return f"{prefix}_" + "".join(random.choices(string.ascii_lowercase, k=8))


def _make_land(fresh_db, term="climat", lang=("fr",)):
    controller = fresh_db["controller"]
    core = fresh_db["core"]
    model = fresh_db["model"]
    name = rand_name()
    controller.LandController.create(
        core.Namespace(name=name, desc="enjeu climat", lang=list(lang)))
    controller.LandController.addterm(core.Namespace(land=name, terms=term))
    return name, model.Land.get(model.Land.name == name)


def _make_expr(fresh_db, land, validllm=None,
               readable="Le climat change beaucoup. climat climat climat.",
               relevance=0):
    model = fresh_db["model"]
    domain, _ = model.Domain.get_or_create(name="example.com")
    return model.Expression.create(
        land=land, domain=domain, url=f"https://example.com/{rand_name('p')}",
        title="climat", readable=readable, relevance=relevance,
        validllm=validllm, readable_at=datetime.datetime.now(), depth=0)


def _enable_openrouter(monkeypatch, min_chars=10):
    import settings
    monkeypatch.setattr(settings, "openrouter_enabled", True)
    monkeypatch.setattr(settings, "openrouter_api_key", "k")
    monkeypatch.setattr(settings, "openrouter_model", "test_model")
    monkeypatch.setattr(settings, "openrouter_readable_min_chars", min_chars)


def _consolidate_ns(core, name, llm='false', issuecrawl=False):
    return core.Namespace(name=name, llm=llm, limit=0, depth=None,
                          minrel=0, issuecrawl=issuecrawl)


class TestConsolidateRespectsLlmVerdict:
    """R1 — consolidate must respect a stored validllm='non' (the bug)."""

    def test_consolidate_keeps_zero_when_validllm_non(self, fresh_db):
        core = fresh_db["core"]
        model = fresh_db["model"]
        _, land = _make_land(fresh_db)
        expr = _make_expr(fresh_db, land, validllm='non', relevance=0)

        run(core.consolidate_land(land))

        # Lexical score would be > 0 (term "climat" in title+content), but the
        # LLM verdict 'non' must keep it at 0 — no resurrection.
        assert model.Expression.get_by_id(expr.id).relevance == 0

    @pytest.mark.parametrize("verdict", [None, 'oui'])
    def test_consolidate_recomputes_lexical_when_not_rejected(self, fresh_db, verdict):
        core = fresh_db["core"]
        model = fresh_db["model"]
        _, land = _make_land(fresh_db)
        expr = _make_expr(fresh_db, land, validllm=verdict, relevance=0)

        run(core.consolidate_land(land))

        assert model.Expression.get_by_id(expr.id).relevance > 0

    def test_consolidate_llm_flag_unconfigured_still_runs(self, fresh_db):
        # --llm=true but OpenRouter disabled (network_safe_settings) → consolidate
        # must still succeed and R1 must still apply.
        core = fresh_db["core"]
        model = fresh_db["model"]
        controller = fresh_db["controller"]
        name, land = _make_land(fresh_db)
        expr = _make_expr(fresh_db, land, validllm='non', relevance=7)

        ret = controller.LandController.consolidate(
            _consolidate_ns(core, name, llm='true'))

        assert ret == 1
        assert model.Expression.get_by_id(expr.id).relevance == 0


class TestConsolidateLlmRevalidate:
    """R2 — consolidate --llm=true re-runs the OpenRouter gate."""

    def test_revalidate_non_sets_validllm_and_zero(self, fresh_db, monkeypatch):
        from mwi import llm_openrouter
        _enable_openrouter(monkeypatch)
        monkeypatch.setattr(llm_openrouter, "is_relevant_via_openrouter",
                            lambda land, expr, issue_mode=None: False)
        core = fresh_db["core"]
        model = fresh_db["model"]
        controller = fresh_db["controller"]
        name, land = _make_land(fresh_db)
        expr = _make_expr(fresh_db, land, validllm=None, relevance=5)

        ret = controller.LandController.consolidate(
            _consolidate_ns(core, name, llm='true'))

        assert ret == 1
        got = model.Expression.get_by_id(expr.id)
        assert got.validllm == 'non'
        assert got.validmodel == 'test_model'
        assert got.relevance == 0

    def test_revalidate_oui_keeps_lexical(self, fresh_db, monkeypatch):
        from mwi import llm_openrouter
        _enable_openrouter(monkeypatch)
        monkeypatch.setattr(llm_openrouter, "is_relevant_via_openrouter",
                            lambda land, expr, issue_mode=None: True)
        core = fresh_db["core"]
        model = fresh_db["model"]
        controller = fresh_db["controller"]
        name, land = _make_land(fresh_db)
        expr = _make_expr(fresh_db, land, validllm=None, relevance=0)

        ret = controller.LandController.consolidate(
            _consolidate_ns(core, name, llm='true'))

        assert ret == 1
        got = model.Expression.get_by_id(expr.id)
        assert got.validllm == 'oui'
        assert got.relevance > 0


class TestIssueModeThreading:
    """R3 — issue mode reachable via settings default and per-command flag."""

    def test_gate_issue_mode_defaults_to_settings(self, fresh_db, monkeypatch):
        import settings
        from mwi import llm_openrouter
        _enable_openrouter(monkeypatch)
        monkeypatch.setattr(settings, "openrouter_issue_mode", True, raising=False)
        monkeypatch.setattr(llm_openrouter, "_call_count", 0)

        captured = {}
        real_build = llm_openrouter.build_relevance_prompt

        def spy(land, expr, readable_text, issue_mode=False):
            captured['issue_mode'] = issue_mode
            return real_build(land, expr, readable_text, issue_mode=issue_mode)

        monkeypatch.setattr(llm_openrouter, "build_relevance_prompt", spy)
        monkeypatch.setattr(llm_openrouter, "ask_openrouter_yesno", lambda prompt: "oui")

        _, land = _make_land(fresh_db)
        expr = _make_expr(fresh_db, land)

        verdict = llm_openrouter.is_relevant_via_openrouter(land, expr)  # no explicit mode

        assert verdict is True
        assert captured['issue_mode'] is True

    @pytest.mark.parametrize("flag,expected", [(True, True), (False, None)])
    def test_llm_validate_threads_issuecrawl(self, fresh_db, monkeypatch, flag, expected):
        from mwi import llm_openrouter
        _enable_openrouter(monkeypatch)
        captured = []
        monkeypatch.setattr(
            llm_openrouter, "is_relevant_via_openrouter",
            lambda land, expr, issue_mode=None: captured.append(issue_mode) or True)
        core = fresh_db["core"]
        controller = fresh_db["controller"]
        name, land = _make_land(fresh_db)
        _make_expr(fresh_db, land)

        ret = controller.LandController.llm_validate(
            core.Namespace(name=name, limit=None, force=False, issuecrawl=flag))

        assert ret == 1
        assert captured == [expected]

    def test_consolidate_threads_issuecrawl(self, fresh_db, monkeypatch):
        from mwi import llm_openrouter
        _enable_openrouter(monkeypatch)
        captured = []
        monkeypatch.setattr(
            llm_openrouter, "is_relevant_via_openrouter",
            lambda land, expr, issue_mode=None: captured.append(issue_mode) or True)
        core = fresh_db["core"]
        controller = fresh_db["controller"]
        name, land = _make_land(fresh_db)
        _make_expr(fresh_db, land)

        controller.LandController.consolidate(
            _consolidate_ns(core, name, llm='true', issuecrawl=True))

        assert captured and captured[0] is True

    def test_crawl_passes_issue_mode(self, fresh_db, monkeypatch):
        core = fresh_db["core"]
        controller = fresh_db["controller"]
        name, _ = _make_land(fresh_db)
        captured = {}

        async def fake_crawl_land(land, limit=0, http=None, depth=None,
                                  store_html=False, retry_status=None, issue_mode=None):
            captured['issue_mode'] = issue_mode
            return (0, 0)

        monkeypatch.setattr(core, "crawl_land", fake_crawl_land)

        controller.LandController.crawl(core.Namespace(
            name=name, limit=0, http=None, depth=None, retry_status=None,
            fullhtml=None, issuecrawl=True))

        assert captured['issue_mode'] is True


class TestIssuePrompts:
    """R4 — English prompts that state the project language; issue variant."""

    def _land_and_expr(self, fresh_db):
        model = fresh_db["model"]
        land = model.Land.create(name=rand_name(), description="enjeu", lang="fr,en")
        expr = SimpleNamespace(title="T", description="D", url="https://x.example")
        return land, expr

    def test_standard_prompt_english_states_project_language(self, fresh_db):
        from mwi import llm_openrouter
        land, expr = self._land_and_expr(fresh_db)

        prompt = llm_openrouter.build_relevance_prompt(land, expr, "texte")

        assert '"yes" or "no"' in prompt
        assert 'French' in prompt
        assert 'Think and reason in' in prompt
        assert 'CONTROVERSY' not in prompt

    def test_issue_prompt_controversy_english(self, fresh_db):
        from mwi import llm_openrouter
        land, expr = self._land_and_expr(fresh_db)

        prompt = llm_openrouter.build_relevance_prompt(land, expr, "texte", issue_mode=True)

        assert 'CONTROVERSY ANALYSIS' in prompt
        assert '"yes" or "no"' in prompt
        assert 'French' in prompt
        assert 'table of contents' in prompt
