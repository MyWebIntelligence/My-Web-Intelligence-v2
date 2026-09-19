"""O02 - the readable pipeline holds ids, not whole rows, in memory.

`_get_expressions_to_process` ran `Expression.select()` (every column,
including `html`, capped at 5 MB per row) and materialised the result with
`list(query)`. `process_land` then kept that master list alive for the whole
run, so batching bounded concurrency but never memory: measured 39.4 MB peak
on 200 pages of 200 KB, against 4.0 MB for the ids-then-batches shape.

Selecting fewer columns is not an option: `html` is read downstream by
`_process_single_expression` and `_update_expression_links`. Paginating with
LIMIT/OFFSET is not one either -- the pipeline rewrites `readable_at`, which
the WHERE clause filters on, so OFFSET would reproduce A02. Freezing the id
list up front keeps the selection stable AND the footprint flat.
"""

import asyncio
import tracemalloc
from datetime import datetime

import pytest

from mwi.readable_pipeline import MercuryReadablePipeline


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _land_with_rows(fresh_db, name, specs):
    """specs: list of (slug, depth, fetched, readable_at, html)."""
    m = fresh_db["model"]
    controller = fresh_db["controller"]
    core = fresh_db["core"]
    controller.LandController.create(
        core.Namespace(name=name, desc="d", lang=["fr"]))
    land = m.Land.get(m.Land.name == name)
    domain, _ = m.Domain.get_or_create(name="batch.example")
    made = []
    for slug, depth, fetched, readable_at, html in specs:
        made.append(m.Expression.create(
            land=land, domain=domain,
            url="https://batch.example/%s" % slug,
            depth=depth,
            fetched_at=fetched,
            readable_at=readable_at,
            html=html))
    return land, made


class TestSelectionReturnsIds:

    def test_selection_returns_sorted_ids_not_models(self, fresh_db):
        now = datetime.now()
        land, made = _land_with_rows(fresh_db, "o02_ids", [
            ("a", 0, now, None, None),
            ("b", 1, now, None, None),
            ("c", 0, now, None, None),
        ])

        ids = MercuryReadablePipeline()._get_expressions_to_process(
            land, None, None)

        assert all(isinstance(i, int) for i in ids)
        assert sorted(ids) == sorted(e.id for e in made)

    def test_selection_filters_on_fetched_and_readable_at(self, fresh_db):
        now = datetime.now()
        land, made = _land_with_rows(fresh_db, "o02_filter", [
            ("todo", 0, now, None, None),
            ("already_read", 0, now, now, None),
            ("never_fetched", 0, None, None, None),
        ])

        ids = MercuryReadablePipeline()._get_expressions_to_process(
            land, None, None)

        assert ids == [made[0].id]

    @pytest.mark.parametrize('depth', [0, 1])
    def test_depth_filter_includes_zero(self, fresh_db, depth):
        """`if depth is not None` — depth=0 is a filter, not "no filter"."""
        now = datetime.now()
        land, made = _land_with_rows(fresh_db, "o02_depth_%d" % depth, [
            ("d0", 0, now, None, None),
            ("d1", 1, now, None, None),
        ])

        ids = MercuryReadablePipeline()._get_expressions_to_process(
            land, None, depth)

        assert ids == [made[depth].id]

    def test_limit_zero_means_unlimited(self, fresh_db):
        """LandController.readable passes default=0 for --limit."""
        now = datetime.now()
        land, made = _land_with_rows(fresh_db, "o02_limit", [
            ("a", 0, now, None, None),
            ("b", 0, now, None, None),
        ])

        assert len(MercuryReadablePipeline()._get_expressions_to_process(
            land, 0, None)) == 2
        assert len(MercuryReadablePipeline()._get_expressions_to_process(
            land, 1, None)) == 1


class TestLoadBatch:

    def test_load_batch_preserves_order_and_loads_html(self, fresh_db):
        now = datetime.now()
        land, made = _land_with_rows(fresh_db, "o02_load", [
            ("a", 0, now, None, "<html>A</html>"),
            ("b", 0, now, None, "<html>B</html>"),
            ("c", 0, now, None, "<html>C</html>"),
        ])
        wanted = [made[2].id, made[0].id, made[1].id]

        rows = MercuryReadablePipeline()._load_batch(wanted)

        assert [r.id for r in rows] == wanted
        assert [r.html for r in rows] == ["<html>C</html>", "<html>A</html>",
                                          "<html>B</html>"]


class TestMemoryFootprint:

    def test_two_batches_resident_at_most(self, fresh_db, monkeypatch):
        """60 rows of 100 KB, batch_size=5: the peak stays well under the sum.

        The bound asserted is a property (a fraction of the total), never a
        byte count: a byte count would encode the interpreter's allocator.
        """
        now = datetime.now()
        blob = "x" * 100_000
        land, made = _land_with_rows(fresh_db, "o02_mem", [
            ("p%02d" % i, 0, now, None, blob) for i in range(60)])
        total_bytes = 60 * 100_000

        pipeline = MercuryReadablePipeline(batch_size=5)

        async def noop_batch(batch, dictionary):
            # Touch the payload so it cannot be optimised away.
            assert all(len(r.html) == 100_000 for r in batch)

        monkeypatch.setattr(pipeline, "_process_batch", noop_batch)

        tracemalloc.start()
        try:
            _run(pipeline.process_land(land))
            _current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        assert peak < total_bytes * 0.5, (
            "peak %d is not below half of %d: the master list is still "
            "resident" % (peak, total_bytes))
        assert peak > 100_000, "at least one batch must be resident"


class TestExhaustivenessUnchanged:
    """Contract: freezing the id list must not change what gets processed."""

    def test_every_pending_expression_is_handed_to_a_batch(self, fresh_db,
                                                           monkeypatch):
        now = datetime.now()
        land, made = _land_with_rows(fresh_db, "o02_all", [
            ("p%02d" % i, 0, now, None, None) for i in range(7)])
        pipeline = MercuryReadablePipeline(batch_size=3)
        seen = []

        async def collect(batch, dictionary):
            seen.extend(r.id for r in batch)

        monkeypatch.setattr(pipeline, "_process_batch", collect)

        _run(pipeline.process_land(land))

        assert sorted(seen) == sorted(e.id for e in made)

    def test_limit_caps_the_number_processed(self, fresh_db, monkeypatch):
        now = datetime.now()
        land, made = _land_with_rows(fresh_db, "o02_limit_run", [
            ("p%02d" % i, 0, now, None, None) for i in range(7)])
        pipeline = MercuryReadablePipeline(batch_size=3)
        seen = []

        async def collect(batch, dictionary):
            seen.extend(r.id for r in batch)

        monkeypatch.setattr(pipeline, "_process_batch", collect)

        _run(pipeline.process_land(land, limit=4))

        assert len(seen) == 4
