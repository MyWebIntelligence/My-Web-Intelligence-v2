"""A06/D-15 - one simulation flag, read in one place, honoured everywhere.

`core.get_dryrun` was written in June 2026 to accept either spelling, but two
commands added afterwards never used it and read `args.dry_run` by hand:
`land delete` (2026-06-27) and `heuristic update` (2026-07-01). Consequences
reproduced with the real argparse shapes:

- `land delete --dryrun`      -> the land was really deleted;
- `--dry-run=FALSE`           -> read as a *simulation* (bool("FALSE") is True);
- `heuristic update --dryrun` -> domains really reassigned, no confirmation;
- `--dryrun --html --fetch-missing --limit=5` -> real network fetches "in
  simulation";
- `db fix_archive_domains` (any spelling) created `Domain` rows before the
  dry-run guard, so the next `domain crawl` went out to fetch domains that
  were never validated.

D-15 also removes the glued `--dryrun` from the command line: one official
spelling, `--dry-run`. `core.get_dryrun` keeps accepting BOTH attributes on
purpose -- controllers are called directly with a Namespace all over the test
suite -- which is why `SIM` below still exercises `dryrun=True`.
"""

import sys
from datetime import datetime

import pytest

# Programmatic simulation shapes. `dryrun=True` is no longer reachable from
# the command line but stays valid for a Namespace-level call.
SIM = [
    pytest.param({'dry_run': 'TRUE'}, id="dry_run_str"),
    pytest.param({'dry_run': True}, id="dry_run_bool"),
    pytest.param({'dryrun': True}, id="dryrun_attr"),
]
REAL = [
    pytest.param({'dry_run': 'FALSE'}, id="dry_run_false_str"),
    pytest.param({'dry_run': False}, id="dry_run_false_bool"),
    pytest.param({}, id="absent"),
]


def _land(fresh_db, name, relevance=3):
    m = fresh_db["model"]
    controller = fresh_db["controller"]
    core = fresh_db["core"]
    controller.LandController.create(
        core.Namespace(name=name, desc="d", lang=["fr"]))
    land = m.Land.get(m.Land.name == name)
    domain, _ = m.Domain.get_or_create(name="example.com")
    m.Expression.create(land=land, domain=domain,
                        url="https://example.com/a", depth=0,
                        relevance=relevance, fetched_at=datetime.now())
    return land


class TestDeleteHonoursEverySimulationShape:

    @pytest.mark.parametrize('flag', SIM)
    def test_simulation_keeps_the_land_and_never_confirms(self, fresh_db,
                                                          monkeypatch, flag):
        m, controller, core = (fresh_db["model"], fresh_db["controller"],
                               fresh_db["core"])
        _land(fresh_db, "dr_del_sim")
        calls = []
        monkeypatch.setattr(core, "confirm",
                            lambda msg: calls.append(msg) or True, raising=True)

        ret = controller.LandController.delete(
            core.Namespace(name="dr_del_sim", maxrel=None, **flag))

        assert ret == 1
        assert calls == []
        assert m.Land.get_or_none(m.Land.name == "dr_del_sim") is not None

    @pytest.mark.parametrize('flag', REAL)
    def test_real_run_deletes(self, fresh_db, monkeypatch, flag):
        m, controller, core = (fresh_db["model"], fresh_db["controller"],
                               fresh_db["core"])
        _land(fresh_db, "dr_del_real")
        monkeypatch.setattr(core, "confirm", lambda msg: True, raising=True)

        ret = controller.LandController.delete(
            core.Namespace(name="dr_del_real", maxrel=None, **flag))

        assert ret == 1
        assert m.Land.get_or_none(m.Land.name == "dr_del_real") is None


class TestHeuristicUpdateHonoursSimulation:

    def _youtube_land(self, fresh_db):
        m = fresh_db["model"]
        land = _land(fresh_db, "dr_heur")
        yt, _ = m.Domain.get_or_create(name="youtube.com")
        expr = m.Expression.create(
            land=land, domain=yt, depth=0,
            url="https://youtube.com/@unechaine/videos")
        return land, expr, yt

    @pytest.mark.parametrize('flag', SIM)
    def test_simulation_writes_nothing(self, fresh_db, flag):
        m, controller, core = (fresh_db["model"], fresh_db["controller"],
                               fresh_db["core"])
        land, expr, yt = self._youtube_land(fresh_db)

        ret = controller.HeuristicController.update(
            core.Namespace(land="dr_heur", **flag))

        assert ret == 1
        assert m.Expression.get_by_id(expr.id).domain_id == yt.id

    def test_real_run_reassigns(self, fresh_db):
        m, controller, core = (fresh_db["model"], fresh_db["controller"],
                               fresh_db["core"])
        land, expr, yt = self._youtube_land(fresh_db)

        ret = controller.HeuristicController.update(
            core.Namespace(land="dr_heur"))

        assert ret == 1
        assert m.Expression.get_by_id(expr.id).domain_id != yt.id

    @pytest.mark.parametrize('flag', SIM)
    def test_simulation_never_touches_the_network(self, fresh_db, monkeypatch,
                                                  flag):
        """`--fetch-missing` under simulation must stay strictly offline."""
        controller, core = fresh_db["controller"], fresh_db["core"]
        self._youtube_land(fresh_db)
        called = []

        async def spy(*args, **kwargs):
            called.append(args)
            return {}

        monkeypatch.setattr(controller.core, 'fetch_missing_opaque_html', spy)

        controller.HeuristicController.update(core.Namespace(
            land="dr_heur", html=True, fetch_missing=True, limit=5, **flag))

        assert called == []


class TestFixArchiveDomainsSimulation:

    def _archive_land(self, fresh_db):
        m = fresh_db["model"]
        land = _land(fresh_db, "dr_arch")
        arch, _ = m.Domain.get_or_create(name="web.archive.org")
        expr = m.Expression.create(
            land=land, domain=arch, depth=0,
            url="https://web.archive.org/web/2020/https://example.org/p")
        return land, expr, arch

    @pytest.mark.parametrize('flag', SIM)
    def test_simulation_creates_no_domain_row(self, fresh_db, capsys, flag):
        m, controller, core = (fresh_db["model"], fresh_db["controller"],
                               fresh_db["core"])
        land, expr, arch = self._archive_land(fresh_db)
        before = m.Domain.select().count()

        ret = controller.DbController.fix_archive_domains(
            core.Namespace(**flag))

        assert ret == 1
        assert m.Domain.select().count() == before
        assert m.Expression.get_by_id(expr.id).domain_id == arch.id
        assert "Would create new domain: example.org" in capsys.readouterr().out

    @pytest.mark.parametrize('preexisting', [True, False])
    def test_real_run_reassigns_whether_the_domain_exists_or_not(
            self, fresh_db, preexisting):
        m, controller, core = (fresh_db["model"], fresh_db["controller"],
                               fresh_db["core"])
        land, expr, arch = self._archive_land(fresh_db)
        if preexisting:
            m.Domain.get_or_create(name="example.org")

        ret = controller.DbController.fix_archive_domains(core.Namespace())

        assert ret == 1
        target = m.Domain.get(m.Domain.name == "example.org")
        assert m.Expression.get_by_id(expr.id).domain_id == target.id


class TestNormalizeSimulation:

    def test_dry_run_modifies_no_url(self, fresh_db):
        m, controller, core = (fresh_db["model"], fresh_db["controller"],
                               fresh_db["core"])
        land = _land(fresh_db, "dr_norm")
        expr = m.Expression.create(
            land=land, domain=m.Domain.get(m.Domain.name == "example.com"),
            url="https://example.com/p?utm_source=x", depth=0)

        controller.LandController.normalize(
            core.Namespace(name="dr_norm", dry_run='TRUE'))

        assert m.Expression.get_by_id(expr.id).url == \
            "https://example.com/p?utm_source=x"


class TestDryrunSpellingRemoved:
    """D-15 - the glued `--dryrun` is gone from the command line."""

    def test_dryrun_is_rejected_by_argparse(self, fresh_db, monkeypatch,
                                            capsys):
        cli = fresh_db["cli"]
        monkeypatch.setattr(sys, "argv",
                            ["mywi.py", "land", "delete", "--name=X",
                             "--dryrun"])

        with pytest.raises(SystemExit) as exc:
            cli.command_input()

        assert exc.value.code == 2
        assert "--dry-run" in capsys.readouterr().err

    def test_bare_dry_run_still_means_true(self, fresh_db, monkeypatch):
        m, cli, core = fresh_db["model"], fresh_db["cli"], fresh_db["core"]
        _land(fresh_db, "dr_argv")
        monkeypatch.setattr(core, "confirm", lambda msg: True, raising=True)
        monkeypatch.setattr(sys, "argv",
                            ["mywi.py", "land", "delete", "--name=dr_argv",
                             "--dry-run"])

        cli.command_input()

        assert m.Land.get_or_none(m.Land.name == "dr_argv") is not None

    def test_bare_dry_run_does_not_swallow_the_next_flag(self, fresh_db,
                                                        monkeypatch):
        cli = fresh_db["cli"]
        seen = {}

        def capture(args):
            seen['dry_run'] = getattr(args, 'dry_run', None)
            seen['html'] = getattr(args, 'html', None)
            return 1

        monkeypatch.setattr(fresh_db["controller"].HeuristicController,
                            'update', staticmethod(capture))
        monkeypatch.setattr(sys, "argv",
                            ["mywi.py", "heuristic", "update", "--dry-run",
                             "--html"])

        cli.command_input()

        assert seen['dry_run'] == 'TRUE'
        assert seen['html'] is True
