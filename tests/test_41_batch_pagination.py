"""A02/O04 - batch selection must not use OFFSET on a shrinking result set.

`crawl_land` and `consolidate_land` paginate with LIMIT/OFFSET over a query
whose WHERE clause the workers themselves rewrite (`fetched_at`,
`http_status`, `relevance`). Every processed row leaves the result set, so the
next OFFSET skips exactly as many rows as were just handled: batch 2 jumps
over the rows that slid into positions 11-20. The user-visible symptom is
"20 expressions processed (0 errors)" followed by `land list` still reporting
"remaining to crawl" -- and `scripts/crawl_robuste.sh` looping 230 times was
compensating for it without knowing.

The fix is keyset pagination by `id`. These tests pin the exhaustiveness
contract, not the implementation: they only ever assert which rows were
handed to the worker.

The worker double mutates the row exactly as the real one does (sets
`fetched_at`/`http_status` then `save()`). Running the real worker with
`fetch_html` patched was measured at ~1.3 s per expression, i.e. 30 s per
test, for no extra coverage of the selection logic.

O04 (`TestCrawlLandSingleSession`) rides along in the same file because it is
the same loop: the session and connector were rebuilt inside it.
"""

import asyncio
from datetime import datetime

import pytest


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _seed(m, name, count, **fields):
    """Create `count` expressions in a fresh land; return (land, sorted ids)."""
    domain = m.Domain.create(name=f"{name}.com")
    land = m.Land.create(name=name, description="t", lang="fr")
    ids = []
    for i in range(count):
        expr = m.Expression.create(
            land=land, domain=domain,
            url=f"https://{name}.com/{i:03d}",
            depth=0,
            **fields)
        ids.append(expr.id)
    return land, sorted(ids)


def _mutating_worker(seen, new_status='200'):
    """Double of crawl_expression_with_media_analysis that mutates like the real one.

    Soft signature (**kwargs): production passes store_html/issue_mode today
    and will pass more tomorrow; a rigid signature would raise TypeError into
    `gather(return_exceptions=True)` and the test would silently measure
    nothing.
    """
    async def worker(expr, dictionary, session, **kwargs):
        seen.append(expr.id)
        expr.fetched_at = datetime.now()
        expr.http_status = new_status
        expr.save()
        return 1
    return worker


def _batches(seq, size):
    return [set(seq[i:i + size]) for i in range(0, len(seq), size)]


@pytest.fixture()
def crawl_env(fresh_db, monkeypatch):
    """parallel_connections = 10 so 30 rows make exactly three batches."""
    core = fresh_db["core"]
    monkeypatch.setattr(core.settings, 'parallel_connections', 10,
                        raising=False)
    return fresh_db


class TestCrawlLandPagination:
    """Every pending expression is handed to the worker, in one pass."""

    def test_default_selection_processes_every_pending_expression(
            self, crawl_env, monkeypatch):
        m, core = crawl_env["model"], crawl_env["core"]
        land, ids = _seed(m, "pg_default", 30)
        seen = []
        monkeypatch.setattr(core, 'crawl_expression_with_media_analysis',
                            _mutating_worker(seen))

        processed, errors = run(core.crawl_land(land))

        assert (processed, errors) == (30, 0)
        assert sorted(seen) == ids
        remaining = (m.Expression.select()
                     .where(m.Expression.land == land,
                            m.Expression.fetched_at.is_null(True)).count())
        assert remaining == 0

    @pytest.mark.parametrize('mode', ['http', 'retry_status'])
    def test_shrinking_selection_processes_all(self, crawl_env, monkeypatch,
                                               mode):
        m, core = crawl_env["model"], crawl_env["core"]
        land, ids = _seed(m, f"pg_shrink_{mode}", 30,
                          http_status='503', fetched_at=datetime.now())
        seen = []
        monkeypatch.setattr(core, 'crawl_expression_with_media_analysis',
                            _mutating_worker(seen, new_status='200'))

        kwargs = ({'http': '503'} if mode == 'http'
                  else {'retry_status': ['503']})
        processed, errors = run(core.crawl_land(land, **kwargs))

        assert (processed, errors) == (30, 0)
        assert sorted(seen) == ids
        # Intra-batch order depends on gather; batch membership does not.
        assert _batches(seen, 10) == _batches(ids, 10)
        left = (m.Expression.select()
                .where(m.Expression.land == land,
                       m.Expression.http_status == '503').count())
        assert left == 0

    def test_persistent_failures_terminate_after_one_pass(self, crawl_env,
                                                          monkeypatch):
        """Contract: a selection that never shrinks must still terminate.

        Green before and after. It guards the 'offset 0' trap: a keyset walk
        that forgot to advance would loop forever on rows that keep matching.
        """
        m, core = crawl_env["model"], crawl_env["core"]
        land, ids = _seed(m, "pg_persist", 30,
                          http_status='403', fetched_at=datetime.now())
        seen = []

        async def failing(expr, dictionary, session, **kwargs):
            seen.append(expr.id)
            expr.http_status = '403'
            expr.save()
            return 0

        monkeypatch.setattr(core, 'crawl_expression_with_media_analysis',
                            failing)

        processed, errors = run(core.crawl_land(land, retry_status=['403']))

        assert processed + errors == 30
        assert len(seen) == 30
        assert sorted(seen) == ids

    def test_limit_takes_the_first_ids_in_order(self, crawl_env, monkeypatch):
        m, core = crawl_env["model"], crawl_env["core"]
        land, ids = _seed(m, "pg_limit", 30)
        seen = []
        monkeypatch.setattr(core, 'crawl_expression_with_media_analysis',
                            _mutating_worker(seen))

        processed, errors = run(core.crawl_land(land, limit=15))

        assert processed + errors == 15
        assert sorted(seen) == ids[:15]

    def test_last_id_resets_per_depth(self, crawl_env, monkeypatch):
        """A depth-1 row with a lower id than the last depth-0 row is not skipped.

        `land addurl` after a first crawl produces exactly this shape, so the
        keyset cursor has to restart at 0 inside the depth loop.
        """
        m, core = crawl_env["model"], crawl_env["core"]
        domain = m.Domain.create(name="pg_depth.com")
        land = m.Land.create(name="pg_depth", description="t", lang="fr")
        made = []
        for suffix, depth in [("a", 0), ("b", 0), ("c", 1), ("d", 1),
                              ("e", 0), ("f", 0)]:
            made.append(m.Expression.create(
                land=land, domain=domain,
                url=f"https://pg_depth.com/{suffix}", depth=depth))
        deep_ids = sorted(e.id for e in made if e.depth == 1)
        assert deep_ids[-1] < max(e.id for e in made if e.depth == 0)

        seen = []
        monkeypatch.setattr(core, 'crawl_expression_with_media_analysis',
                            _mutating_worker(seen))

        processed, errors = run(core.crawl_land(land))

        assert (processed, errors) == (6, 0)
        assert set(deep_ids).issubset(set(seen))


class TestConsolidateLandPagination:
    """Same defect, same fix, on the consolidation loop."""

    def _seed_consolidatable(self, m, name, count, relevance):
        domain = m.Domain.create(name=f"{name}.com")
        land = m.Land.create(name=name, description="t", lang="fr")
        ids = []
        for i in range(count):
            expr = m.Expression.create(
                land=land, domain=domain,
                url=f"https://{name}.com/{i:03d}",
                depth=0,
                relevance=relevance,
                readable="Texte simple sans lien.",
                readable_at=datetime.now())
            ids.append(expr.id)
        return land, sorted(ids)

    def test_minrel_filter_shrinking_processes_all(self, crawl_env):
        m, core = crawl_env["model"], crawl_env["core"]
        land, ids = self._seed_consolidatable(m, "cs_shrink", 30, 5)

        processed, errors = run(core.consolidate_land(land, min_relevance=1))

        assert (processed, errors) == (30, 0)
        still_five = (m.Expression.select()
                      .where(m.Expression.land == land,
                             m.Expression.relevance == 5).count())
        assert still_five == 0

    def test_limit_caps_attempts_in_id_order(self, crawl_env):
        """Contract: --limit is a cap on attempts, taken in id order.

        Green before and after: with min_relevance=0 the selection never
        shrinks, so OFFSET happened to be correct. What the fix adds is that
        the order stops depending on the SQLite query plan.
        """
        m, core = crawl_env["model"], crawl_env["core"]
        land, ids = self._seed_consolidatable(m, "cs_limit", 30, 5)

        processed, errors = run(core.consolidate_land(land, limit=15))

        assert processed + errors == 15
        touched = [e.id for e in m.Expression.select()
                   .where(m.Expression.land == land,
                          m.Expression.relevance == 0)]
        assert sorted(touched) == ids[:15]


def _record_http(monkeypatch, core):
    """Record every ClientSession / TCPConnector built by crawl_land.

    Factories, not subclasses: subclassing aiohttp.ClientSession emits a
    DeprecationWarning in aiohttp 3.13.
    """
    sessions, connectors = [], []
    real_session = core.aiohttp.ClientSession
    real_connector = core.aiohttp.TCPConnector

    def make_connector(*args, **kwargs):
        connector = real_connector(*args, **kwargs)
        connectors.append(connector)
        return connector

    def make_session(*args, **kwargs):
        session = real_session(*args, **kwargs)
        sessions.append(session)
        return session

    monkeypatch.setattr(core.aiohttp, 'TCPConnector', make_connector)
    monkeypatch.setattr(core.aiohttp, 'ClientSession', make_session)
    return sessions, connectors


async def _noop_worker(expr, dictionary, session, **kwargs):
    expr.fetched_at = datetime.now()
    expr.http_status = '200'
    expr.save()
    return 1


def _sync_boom(*args, **kwargs):
    """Synchronous double: raises inside the list-comprehension itself.

    Monkeypatching asyncio.gather would be wrong here -- aiohttp uses it in
    connector._wait_for_close, so the teardown under test would break too.
    """
    raise RuntimeError("boom")


class TestCrawlLandSingleSession:
    """O04 - one aiohttp session per crawl_land call, closed on every path."""

    def test_crawl_land_opens_single_session_for_three_batches(
            self, crawl_env, monkeypatch):
        core = crawl_env["model"], crawl_env["core"]
        m, core = core
        land, _ = _seed(m, "ss_batches", 30)
        sessions, connectors = _record_http(monkeypatch, core)
        monkeypatch.setattr(core, 'crawl_expression_with_media_analysis',
                            _noop_worker)

        run(core.crawl_land(land))

        assert len(sessions) == 1
        assert len(connectors) == 1

    def test_crawl_land_single_session_spans_depths(self, crawl_env,
                                                    monkeypatch):
        m, core = crawl_env["model"], crawl_env["core"]
        domain = m.Domain.create(name="ss_depth.com")
        land = m.Land.create(name="ss_depth", description="t", lang="fr")
        for suffix, depth in [("a", 0), ("b", 1)]:
            m.Expression.create(land=land, domain=domain,
                                url=f"https://ss_depth.com/{suffix}",
                                depth=depth)
        sessions, connectors = _record_http(monkeypatch, core)
        monkeypatch.setattr(core, 'crawl_expression_with_media_analysis',
                            _noop_worker)

        run(core.crawl_land(land))

        assert len(sessions) == 1
        assert len(connectors) == 1

    def test_crawl_land_session_closed_after_limit_early_return(
            self, crawl_env, monkeypatch):
        m, core = crawl_env["model"], crawl_env["core"]
        land, _ = _seed(m, "ss_limit", 30)
        sessions, _c = _record_http(monkeypatch, core)
        monkeypatch.setattr(core, 'crawl_expression_with_media_analysis',
                            _noop_worker)

        run(core.crawl_land(land, limit=5))

        assert sessions and all(s.closed for s in sessions)

    def test_crawl_land_session_closed_when_every_expression_raises(
            self, crawl_env, monkeypatch):
        m, core = crawl_env["model"], crawl_env["core"]
        land, _ = _seed(m, "ss_raise", 4)
        sessions, _c = _record_http(monkeypatch, core)

        async def always_raises(expr, dictionary, session, **kwargs):
            raise ValueError("per-expression failure")

        monkeypatch.setattr(core, 'crawl_expression_with_media_analysis',
                            always_raises)

        assert run(core.crawl_land(land)) == (0, 4)
        assert sessions and all(s.closed for s in sessions)

    def test_crawl_land_session_closed_on_hard_exception(self, crawl_env,
                                                         monkeypatch):
        m, core = crawl_env["model"], crawl_env["core"]
        land, _ = _seed(m, "ss_hard", 4)
        sessions, _c = _record_http(monkeypatch, core)
        monkeypatch.setattr(core, 'crawl_expression_with_media_analysis',
                            _sync_boom)

        with pytest.raises(RuntimeError):
            run(core.crawl_land(land))

        assert sessions and all(s.closed for s in sessions)
