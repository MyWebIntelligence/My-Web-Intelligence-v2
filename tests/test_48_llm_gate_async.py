"""O01 - the OpenRouter gate must not block the event loop.

`ask_openrouter_yesno` is a synchronous `requests.post` with a 15 s timeout,
and it was called straight from coroutines: `crawl_expression_with_media_analysis`
and, through `_process_single_expression`, the readable pipeline. Both run in
batches of `parallel_connections` coroutines, so one gate call froze the whole
batch — four 0.4 s gates in a `gather` measured 1.64 s instead of 0.4, with a
witness task getting a single tick. CLAUDE.md already forbids a blocking call
inside a coroutine, and `readable_pipeline` already applies the executor idiom
to trafilatura.

`consolidate_land` is deliberately LEFT ALONE: it is a coroutine, but its loop
is sequential — there is no sibling coroutine to starve — and `test_32` patches
the synchronous façade.

No timings and no `time.sleep` here: a wall-clock assertion is a flaky test on
a loaded CI runner. Concurrency is proven with a `threading.Barrier` (four
gates must be in flight at once or the barrier never releases) and with thread
identity.
"""

import asyncio
import inspect
import threading
from datetime import datetime
from unittest.mock import patch

import pytest

from mwi import llm_openrouter


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture()
def gate_on(fresh_db, monkeypatch):
    """Turn the gate ON everywhere the autouse fixture turned it off."""
    import settings

    from mwi import core
    for obj in (settings, llm_openrouter.settings, core.settings):
        monkeypatch.setattr(obj, 'openrouter_enabled', True, raising=False)
        monkeypatch.setattr(obj, 'openrouter_api_key', 'k', raising=False)
        monkeypatch.setattr(obj, 'openrouter_model', 'm', raising=False)
        monkeypatch.setattr(obj, 'openrouter_max_calls_per_run', 0,
                            raising=False)
        monkeypatch.setattr(obj, 'openrouter_readable_min_chars', 0,
                            raising=False)
    monkeypatch.setattr(llm_openrouter, '_call_count', 0, raising=False)
    return fresh_db


def _land_with_page(fresh_db, name, readable="Le climat change vite. " * 10):
    m = fresh_db["model"]
    controller = fresh_db["controller"]
    core = fresh_db["core"]
    controller.LandController.create(
        core.Namespace(name=name, desc="d", lang=["fr"]))
    controller.LandController.addterm(
        core.Namespace(land=name, terms="climat"))
    land = m.Land.get(m.Land.name == name)
    domain, _ = m.Domain.get_or_create(name="gate.example")
    expr = m.Expression.create(
        land=land, domain=domain, url="https://gate.example/%s" % name,
        depth=0, readable=readable, fetched_at=datetime.now())
    return land, expr


class TestGateRunsOffTheLoop:

    def test_the_blocking_call_happens_in_another_thread(self, gate_on):
        """The witness runs while the gate is in flight, and in another thread."""
        land, expr = _land_with_page(gate_on, "gate_thread")
        released = threading.Event()
        gate_thread = {}

        def fake_ask(prompt):
            gate_thread['id'] = threading.get_ident()
            assert released.wait(5), "the loop never got a turn"
            return "oui"

        async def scenario():
            with patch.object(llm_openrouter, 'ask_openrouter_yesno',
                              fake_ask):
                task = asyncio.ensure_future(
                    llm_openrouter.is_relevant_via_openrouter_async(land, expr))
                await asyncio.sleep(0)
                released.set()
                return await task

        verdict = _run(scenario())

        assert verdict is True
        assert gate_thread['id'] != threading.get_ident()
        assert llm_openrouter._call_count == 1

    def test_four_gates_are_in_flight_at_once(self, gate_on):
        """A Barrier of 4 cannot release unless all four calls overlap."""
        land, expr = _land_with_page(gate_on, "gate_barrier")
        barrier = threading.Barrier(4, timeout=5)
        answers = iter(["oui", "non", "oui", "oui"])
        lock = threading.Lock()

        def fake_ask(prompt):
            barrier.wait()
            with lock:
                return next(answers)

        async def scenario():
            with patch.object(llm_openrouter, 'ask_openrouter_yesno',
                              fake_ask):
                return await asyncio.gather(*[
                    llm_openrouter.is_relevant_via_openrouter_async(land, expr)
                    for _ in range(4)])

        verdicts = _run(scenario())

        assert sorted(v is True for v in verdicts).count(True) == 3
        assert llm_openrouter._call_count == 4

    def test_an_exception_in_the_thread_returns_none_and_spends_the_budget(
            self, gate_on):
        """Parity with the synchronous façade: budget is spent before the call."""
        land, expr = _land_with_page(gate_on, "gate_boom")

        def boom(prompt):
            raise RuntimeError("upstream is down")

        async def scenario():
            with patch.object(llm_openrouter, 'ask_openrouter_yesno', boom):
                return await llm_openrouter.is_relevant_via_openrouter_async(
                    land, expr)

        assert _run(scenario()) is None
        assert llm_openrouter._call_count == 1

    def test_the_sync_facade_is_unchanged(self, gate_on):
        """Contract: consolidate and `llm validate` keep calling the sync one."""
        land, expr = _land_with_page(gate_on, "gate_sync")

        with patch.object(llm_openrouter, 'ask_openrouter_yesno',
                          lambda prompt: "oui"):
            assert llm_openrouter.is_relevant_via_openrouter(land, expr) is True

        assert not inspect.iscoroutinefunction(
            llm_openrouter.is_relevant_via_openrouter)


class TestCallersAwaitTheGate:
    """The import is local, so a typo there would be swallowed by `except`."""

    @pytest.mark.parametrize('worker', ['with_media_analysis', 'legacy'])
    @pytest.mark.parametrize('answer,expect_relevance', [
        pytest.param('oui', True, id="oui_keeps_relevance"),
        pytest.param('non', False, id="non_forces_zero"),
    ])
    def test_crawl_applies_the_verdict(self, gate_on, worker, answer,
                                       expect_relevance):
        from mwi import core

        m = gate_on["model"]
        land, expr = _land_with_page(gate_on, "gate_crawl_%s_%s"
                                     % (worker, answer))
        dictionary = core.get_land_dictionary(land)
        html = "<html><body><p>%s</p></body></html>" % ("Le climat " * 40)

        class _Fetched:
            status_code = '200'
            html = "<html><body><p>%s</p></body></html>" % ("Le climat " * 40)
            method_used = 'aiohttp'
            error = None

        func = (core.crawl_expression_with_media_analysis
                if worker == 'with_media_analysis' else core.crawl_expression)

        async def fake_fetch(url, session=None, **kwargs):
            return _Fetched()

        with patch.object(core, 'fetch_html', fake_fetch):
            with patch.object(llm_openrouter, 'ask_openrouter_yesno',
                              lambda prompt: answer):
                _run(func(expr, dictionary, None))

        fresh = m.Expression.get_by_id(expr.id)
        assert llm_openrouter._call_count == 1, (
            "the gate was not reached: a bad local import would be swallowed "
            "by the surrounding except")
        if expect_relevance:
            assert fresh.relevance > 0
        else:
            assert fresh.relevance == 0
        assert html  # keep the fixture honest


class TestReadablePipelineAwaitsTheGate:

    def test_apply_updates_is_a_coroutine_and_applies_the_verdict(self,
                                                                  gate_on):
        from mwi.readable_pipeline import (ExpressionUpdate,
                                           MercuryReadablePipeline)

        m, core = gate_on["model"], gate_on["core"]
        land, expr = _land_with_page(gate_on, "gate_readable")
        pipeline = MercuryReadablePipeline(llm_enabled=True)

        assert inspect.iscoroutinefunction(pipeline._apply_updates)

        update = ExpressionUpdate(
            expression_id=expr.id,
            field_updates={'readable': (expr.readable, "Le climat " * 30)},
            media_additions=[], link_additions=[], update_reason="test")
        dictionary = core.get_land_dictionary(land)

        with patch.object(llm_openrouter, 'ask_openrouter_yesno',
                          lambda prompt: "non"):
            _run(pipeline._apply_updates(expr, update, dictionary))

        fresh = m.Expression.get_by_id(expr.id)
        assert fresh.relevance == 0
        assert fresh.readable == "Le climat " * 30
