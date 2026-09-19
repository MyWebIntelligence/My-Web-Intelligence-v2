"""A09 - the process exit code reflects the outcome (decisions D-13/D-17).

Every controller already returned 1 (success) / 0 (business failure), but
`cli.command_run` and `cli.command_input` dropped that value and `mywi.py` had
no `sys.exit`. So `mywi.py land list --name=does-not-exist` printed
"No land created" and exited 0, and a refused destructive confirmation exited 0
too. Anything chaining commands with `&&` kept going as if the step had worked.

D-13: a refused confirmation exits 1, like a business failure — the chain stops
there, on a corpus left intact. No third code (YAGNI).

D-17: no prior inventory of the n8n scenarios, cron jobs and shell wrappers
that drive mywi.py. The consequence is accepted and written at the top of the
changelog: a chain that used to ignore failures will now stop.

Mapping pinned here: 0 success, 1 business failure / cancelled confirmation /
unhandled exception / `--db` not found, 2 argparse usage error.
"""

import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HAS_SETTINGS = os.path.exists(os.path.join(REPO_ROOT, 'settings.py'))


def _run_mywi(argv, db_path, stdin=None):
    """Run mywi.py in a subprocess against an isolated database (~1.5 s)."""
    return subprocess.run(
        [sys.executable, 'mywi.py'] + argv + ['--db', str(db_path)],
        cwd=REPO_ROOT, input=stdin, capture_output=True, text=True)


class TestControllerReturnValueReachesTheCaller:

    @pytest.mark.parametrize('name,expected', [
        pytest.param('a09_ok', 1, id="success"),
        pytest.param(None, 0, id="business_failure"),
    ])
    def test_command_run_returns_the_controller_code(self, fresh_db, name,
                                                     expected):
        cli = fresh_db["cli"]
        if name:
            fresh_db["controller"].LandController.create(
                fresh_db["core"].Namespace(name=name, desc="d", lang=["fr"]))
            args = {'object': 'land', 'verb': 'list', 'name': name}
        else:
            args = {'object': 'land', 'verb': 'list', 'name': 'nope_a09'}

        assert cli.command_run(args) == expected

    def test_command_input_returns_the_controller_code(self, fresh_db,
                                                       monkeypatch):
        cli = fresh_db["cli"]
        monkeypatch.setattr(sys, "argv",
                            ["mywi.py", "land", "list", "--name=nope_a09"])

        assert cli.command_input() == 0

    @pytest.mark.parametrize('result,exit_code', [
        pytest.param(1, 0, id="success_exits_zero"),
        pytest.param(0, 1, id="failure_exits_one"),
        pytest.param(None, 1, id="none_is_treated_as_failure"),
    ])
    def test_main_maps_the_code_fail_safe(self, monkeypatch, result,
                                          exit_code):
        """Anything that is not an explicit 1 is a failure (fail-safe)."""
        import mywi
        from mwi import cli
        monkeypatch.setattr(cli, "command_input", lambda: result)

        assert mywi.main() == exit_code


class TestDbSetupRefusal:

    def test_db_setup_returns_zero_when_confirmation_refused(self, fresh_db,
                                                             monkeypatch,
                                                             capsys):
        """DbController.setup was the one target falling through to None."""
        m, controller, core = (fresh_db["model"], fresh_db["controller"],
                               fresh_db["core"])
        controller.LandController.create(
            core.Namespace(name="a09_keep", desc="d", lang=["fr"]))
        monkeypatch.setattr(controller.core, "confirm", lambda msg: False,
                            raising=True)

        ret = controller.DbController.setup(core.Namespace())

        assert ret == 0
        assert 'Aborted' in capsys.readouterr().out
        assert m.Land.get_or_none(m.Land.name == "a09_keep") is not None


@pytest.mark.skipif(not HAS_SETTINGS,
                    reason="settings.py is not versioned; subprocess run needs it")
class TestRealProcessExitCodes:
    """End to end, in a real subprocess: this is what a shell actually sees."""

    def test_success_exits_zero(self, fresh_db):
        controller, core = fresh_db["controller"], fresh_db["core"]
        controller.LandController.create(
            core.Namespace(name="a09_success_land", desc="d", lang=["fr"]))
        db_path = os.path.join(str(fresh_db["data_dir"]), "mwi.db")

        proc = _run_mywi(['land', 'list', '--name=a09_success_land'], db_path)

        assert proc.returncode == 0, proc.stderr
        assert 'a09_success_land' in proc.stdout
        assert 'Traceback' not in proc.stderr

    def test_business_failure_exits_one(self, fresh_db):
        db_path = os.path.join(str(fresh_db["data_dir"]), "mwi.db")

        proc = _run_mywi(['land', 'list', '--name=a09_absent'], db_path)

        assert proc.returncode == 1
        assert 'No land created' in proc.stdout
        assert 'Traceback' not in proc.stderr

    def test_cancelled_confirmation_exits_one_and_keeps_the_land(self,
                                                                 fresh_db):
        """D-13: answering 'n' must stop an `&&` chain, corpus untouched."""
        m, controller, core = (fresh_db["model"], fresh_db["controller"],
                               fresh_db["core"])
        controller.LandController.create(
            core.Namespace(name="a09_cancel", desc="d", lang=["fr"]))
        db_path = os.path.join(str(fresh_db["data_dir"]), "mwi.db")

        proc = _run_mywi(['land', 'delete', '--name=a09_cancel'], db_path,
                         stdin='n\n')

        assert proc.returncode == 1
        assert 'Traceback' not in proc.stderr
        assert m.Land.get_or_none(m.Land.name == "a09_cancel") is not None

    def test_argparse_usage_error_still_exits_two(self, fresh_db):
        db_path = os.path.join(str(fresh_db["data_dir"]), "mwi.db")

        proc = _run_mywi(['land', 'list', '--not-an-option'], db_path)

        assert proc.returncode == 2
