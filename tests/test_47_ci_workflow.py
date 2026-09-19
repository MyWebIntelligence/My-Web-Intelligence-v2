"""A12 - the CI workflow must exist, be versioned, and run tools that exist.

`.gitignore` starts with `.*/`, which ignores `.github/` — so no workflow has
EVER been committed (`git log --all -- .github` is empty), while
`JOSS_Conformite` claimed "CI/CD ✅ tests.yml", `pyproject.toml` referenced
`tests.yml` and the README pointed at `.github/workflows/`. The local `ci.yml`
also ran `ruff`, which is not in the project at all (`uv.lock` has no ruff, and
the 2026-06-24 decision was explicitly "Ruff dropped, keep flake8").

These are contract tests on the YAML as text, deliberately without pyyaml:
adding a dependency to check a config file is a poor trade, and a regex over
non-comment lines is enough to answer the three questions that matter — is a
workflow there, is it versioned, and does every tool it invokes exist in the
synchronised environment.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_DIR = REPO_ROOT / '.github' / 'workflows'
MAKEFILE = REPO_ROOT / 'Makefile'


def _workflows():
    if not WORKFLOW_DIR.is_dir():
        return []
    return sorted(p for p in WORKFLOW_DIR.iterdir() if p.suffix in ('.yml',
                                                                    '.yaml'))


def _uncommented(path):
    """Workflow text with full-line comments stripped."""
    return "\n".join(line for line in path.read_text(encoding='utf-8').splitlines()
                     if not line.lstrip().startswith('#'))


def _git(*args):
    return subprocess.run(['git'] + list(args), cwd=str(REPO_ROOT),
                          capture_output=True, text=True)


class TestWorkflowExists:

    def test_at_least_one_workflow_is_present(self):
        assert _workflows(), "no workflow under .github/workflows/"

    def test_no_workflow_invokes_ruff(self):
        """Ruff was explicitly dropped in favour of flake8 (2026-06-24)."""
        for path in _workflows():
            assert 'ruff' not in _uncommented(path), (
                "%s still invokes ruff, which is not a project dependency"
                % path.name)


class TestToolsExistInTheEnvironment:

    @pytest.mark.parametrize('tool', ['flake8', 'mypy', 'pytest'])
    def test_tool_is_installed_in_the_synced_environment(self, tool):
        """`uv run <tool>` must not silently fall back to a system binary."""
        assert shutil.which(tool, path=str(Path(sys.executable).parent)), (
            "%s is not in the synchronised environment" % tool)

    def test_every_uv_run_tool_of_the_workflows_exists(self):
        venv_bin = str(Path(sys.executable).parent)
        missing = []
        for path in _workflows():
            for tool in re.findall(r'uv run (?:--\S+ )*([a-zA-Z0-9_.-]+)',
                                   _uncommented(path)):
                if tool in ('python', 'python3'):
                    continue
                if not shutil.which(tool, path=venv_bin):
                    missing.append("%s: %s" % (path.name, tool))
        assert not missing, "workflow tools absent from the environment: %s" % missing


class TestMakeTargetsExist:

    def test_every_make_target_called_by_a_workflow_is_defined(self):
        assert MAKEFILE.is_file()
        makefile = MAKEFILE.read_text(encoding='utf-8')
        defined = set(re.findall(r'^([a-zA-Z0-9_-]+):', makefile, re.MULTILINE))
        called = set()
        for path in _workflows():
            called.update(re.findall(r'\bmake ([a-zA-Z0-9_-]+)',
                                     _uncommented(path)))
        assert called <= defined, (
            "workflows call undefined make targets: %s" % (called - defined))

    @pytest.mark.parametrize('target', ['lint', 'lint-all', 'typecheck'])
    def test_quality_targets_are_defined(self, target):
        makefile = MAKEFILE.read_text(encoding='utf-8')
        assert re.search(r'^%s:' % re.escape(target), makefile, re.MULTILINE)


class TestWorkflowsAreVersioned:
    """The whole point: `.gitignore` used to swallow .github/ entirely."""

    def test_workflow_files_are_not_git_ignored(self):
        probe = _git('--version')
        if probe.returncode != 0:
            pytest.skip("git unavailable")
        for path in _workflows():
            rel = str(path.relative_to(REPO_ROOT))
            # --no-index is required: without it the check passes vacuously as
            # soon as the file is tracked, which would hide a broken rule.
            res = _git('check-ignore', '-q', '--no-index', rel)
            if res.returncode == 128:
                pytest.skip("git cannot inspect this tree (%s)"
                            % res.stderr.strip())
            assert res.returncode == 1, (
                "%s is ignored by .gitignore and can never be committed" % rel)

    def test_dot_claude_stays_ignored(self):
        """The `.*/ ` rule must keep ignoring the local-only directories."""
        probe = _git('--version')
        if probe.returncode != 0:
            pytest.skip("git unavailable")
        res = _git('check-ignore', '-q', '--no-index', '.claude/rules/testing.md')
        if res.returncode == 128:
            pytest.skip("git cannot inspect this tree")
        assert res.returncode == 0, ".claude/ must stay out of version control"


class TestNoStaleWorkflowReference:

    def test_documentation_does_not_reference_tests_yml(self):
        """`tests.yml` is removed; nothing should still point at it."""
        targets = ['README.md', 'CONTRIBUTING.md', 'pyproject.toml']
        offenders = []
        for rel in targets:
            path = REPO_ROOT / rel
            if path.is_file() and 'tests.yml' in path.read_text(encoding='utf-8'):
                offenders.append(rel)
        assert not offenders, "stale reference to tests.yml in %s" % offenders

    def test_only_one_workflow_remains(self):
        assert [p.name for p in _workflows()] == ['ci.yml']


def test_repo_root_is_the_project(self=None):
    """Guard: the path arithmetic above must point at the real repository."""
    assert (REPO_ROOT / 'mywi.py').is_file()
    assert os.path.isdir(REPO_ROOT / 'mwi')
