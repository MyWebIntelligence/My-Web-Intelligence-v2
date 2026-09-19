"""Query-planner statistics and durability pragmas (sprint-upgrade, D-9 suite).

Nothing in MWI ever produced SQLite's planner statistics: `ANALYZE` runs only
inside migration 013, and `db setup` creates the schema without going through
the migrations. Measured on a 4 000-page synthetic land (2026-09-19), the edge
query of the graph exports costs 7.02 s without statistics and 0.27 s with
them — and is quadratic in the page count instead of linear.

These tests pin the behaviour, not the mechanism: a command that ran must
leave the planner able to do its job, and must never fail because it could
not.
"""
import pytest


class TestPlannerStatistics:
    def _has_stats(self, model):
        rows = model.DB.execute_sql(
            "SELECT COUNT(*) FROM sqlite_master WHERE name = 'sqlite_stat1'"
        ).fetchone()
        if not rows or not rows[0]:
            return False
        return bool(model.DB.execute_sql(
            "SELECT COUNT(*) FROM sqlite_stat1").fetchone()[0])

    def test_no_statistics_before_any_command(self, populated_land):
        """The starting point: db setup leaves the planner with nothing."""
        assert self._has_stats(populated_land["model"]) is False

    def test_command_leaves_planner_statistics_behind(self, populated_land):
        cli = populated_land["controller"] and __import__(
            "mwi.cli", fromlist=["cli"])
        model = populated_land["model"]

        assert cli.command_run({"object": "land", "verb": "list",
                                "name": populated_land["name"]}) == 1

        assert self._has_stats(model) is True

    def test_statistics_failure_never_fails_the_command(self, populated_land,
                                                        monkeypatch, capsys):
        """A PRAGMA is an optimisation. A crawl that worked stays a success."""
        cli = __import__("mwi.cli", fromlist=["cli"])
        model = populated_land["model"]
        real = model.DB.execute_sql

        def boom(sql, *a, **k):
            if "optimize" in str(sql).lower():
                raise RuntimeError("database is locked")
            return real(sql, *a, **k)

        monkeypatch.setattr(model.DB, "execute_sql", boom)
        ret = cli.command_run({"object": "land", "verb": "list",
                               "name": populated_land["name"]})

        assert ret == 1
        assert "optimize" in capsys.readouterr().out.lower()


class TestDurabilityPragmas:
    def test_synchronous_is_normal_not_off(self, fresh_db):
        """OFF risks corruption on power loss; NORMAL is the documented
        minimum under WAL. Measured cost: +65 us per save()."""
        model = fresh_db["model"]

        assert model.SQLITE_PRAGMAS["synchronous"] == 1
        assert model.SQLITE_PRAGMAS["journal_mode"] == "wal"

    def test_switch_database_reuses_the_single_pragma_set(self, fresh_db,
                                                          tmp_path):
        """--db used to carry its own copy of the pragmas, so a change had to
        be made in two files or the two paths silently diverged."""
        cli = __import__("mwi.cli", fromlist=["cli"])
        model = fresh_db["model"]
        other = tmp_path / "other.db"
        other.write_bytes(b"")

        cli._switch_database(str(other))
        try:
            sync = model.DB.execute_sql("PRAGMA synchronous").fetchone()[0]
            journal = model.DB.execute_sql(
                "PRAGMA journal_mode").fetchone()[0]
        finally:
            model.DB.close()

        assert sync == 1
        assert journal == "wal"


@pytest.mark.parametrize("spelling", ["ignore_check_constraints"])
def test_pragma_spelling_is_the_real_one(fresh_db, spelling):
    """`ignore_check_constrains` is not a SQLite pragma: the name is silently
    ignored, so the line read as configuration while doing nothing."""
    model = fresh_db["model"]

    assert spelling in model.SQLITE_PRAGMAS
    assert "ignore_check_constrains" not in model.SQLITE_PRAGMAS
    assert model.SQLITE_PRAGMAS[spelling] == 0
