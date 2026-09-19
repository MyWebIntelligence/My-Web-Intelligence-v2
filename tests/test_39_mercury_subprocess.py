"""A01 - Mercury Parser subprocess: argv instead of a shell, bounded wait.

Security regression suite for `MercuryReadablePipeline._run_mercury`.

Before this sprint the URL was interpolated into a shell command line
(`create_subprocess_shell(f'{path} "{url}" --format=markdown ...')`), so any
crawled URL carrying `$(...)`, backticks or a quote break executed arbitrary
code with the crawler's rights -- the shell expands *before* looking the
command up, so the injection fired even without mercury-parser installed.
`communicate()` was also awaited without a bound, so one page served at a
trickle could hang a whole `land readable` run.

No network, no database, and deliberately **no** `mercury` marker: the real
binary is never spawned (the single exception is the reaping test, which uses
`/bin/sh`), so this file runs everywhere. The double replaces the module
attribute `asyncio.create_subprocess_exec`, which is why the implementation
must call it through the `asyncio` namespace and never `from asyncio import`.
"""
import asyncio
import os
import shutil
import sys

import pytest

from mwi.readable_pipeline import (
    DEFAULT_MERCURY_TIMEOUT,
    MercuryReadablePipeline,
)

MERCURY_FLAGS = ['--format=markdown', '--extract-media', '--extract-links']


class _FakeProc:
    """Stand-in for asyncio.subprocess.Process that answers immediately."""

    def __init__(self, stdout=b'{"title": "t"}', stderr=b'', returncode=0):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self.killed = 0
        self.waited = 0

    async def communicate(self):
        return self._stdout, self._stderr

    def kill(self):
        self.killed += 1

    async def wait(self):
        self.waited += 1
        return self.returncode


class _HangingProc(_FakeProc):
    """Never completes communicate(): stands for a page served at a trickle."""

    def __init__(self):
        super().__init__()
        self.returncode = None
        self._never = asyncio.Event()

    async def communicate(self):
        await self._never.wait()
        return b'', b''

    def kill(self):
        self.killed += 1
        self.returncode = -9
        self._never.set()


def _record_exec(monkeypatch, proc_factory):
    """Record every argv passed to create_subprocess_exec; forbid the shell."""
    calls = []

    async def fake_exec(*argv, **kwargs):
        calls.append(list(argv))
        return proc_factory()

    async def forbidden_shell(*args, **kwargs):
        raise AssertionError('create_subprocess_shell must not be used (A01)')

    monkeypatch.setattr(asyncio, 'create_subprocess_exec', fake_exec)
    monkeypatch.setattr(asyncio, 'create_subprocess_shell', forbidden_shell)
    return calls


def _record_sleeps(monkeypatch):
    """Record backoff delays without actually waiting for them."""
    sleeps = []
    real_sleep = asyncio.sleep

    async def fake_sleep(delay, *args, **kwargs):
        sleeps.append(delay)
        return await real_sleep(0, *args, **kwargs)

    monkeypatch.setattr(asyncio, 'sleep', fake_sleep)
    return sleeps


class TestRunMercuryArgv:
    """The URL is an argument, never a fragment of a command line."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize('url', [
        pytest.param('https://ex.test/$(echo INJ)', id='command_substitution'),
        pytest.param('https://ex.test/`echo INJ`', id='backticks'),
        pytest.param('https://ex.test/"; echo INJ; "', id='quote_break'),
        pytest.param('https://ex.test/a?b=c&d=$(id)|cat', id='pipe_and_subshell'),
    ])
    async def test_url_shell_metacharacters_stay_literal(self, test_env,
                                                         monkeypatch, url):
        calls = _record_exec(monkeypatch, _FakeProc)

        await MercuryReadablePipeline()._run_mercury(url)

        assert calls, 'no argv recorded: the shell path is still in use'
        argv = calls[0]
        assert argv[1] == url
        assert argv[2:] == MERCURY_FLAGS

    @pytest.mark.asyncio
    async def test_executable_resolved_via_which(self, test_env, monkeypatch):
        calls = _record_exec(monkeypatch, _FakeProc)
        monkeypatch.setattr(shutil, 'which',
                            lambda cmd, *a, **k: '/opt/npm/bin/mercury-parser')

        await MercuryReadablePipeline()._run_mercury('https://ex.test/a')

        assert calls[0][0] == '/opt/npm/bin/mercury-parser'

    @pytest.mark.asyncio
    async def test_unresolved_executable_keeps_the_raw_path(self, test_env,
                                                            monkeypatch):
        calls = _record_exec(monkeypatch, _FakeProc)
        monkeypatch.setattr(shutil, 'which', lambda cmd, *a, **k: None)

        await MercuryReadablePipeline(
            mercury_path='mercury-parser')._run_mercury('https://ex.test/a')

        assert calls[0][0] == 'mercury-parser'


class TestRunMercuryTimeout:
    """A page that hangs is killed, reported, and not retried (D-12)."""

    @pytest.mark.asyncio
    async def test_hanging_subprocess_is_killed_reported_and_not_retried(
            self, test_env, monkeypatch):
        procs = []

        def factory():
            proc = _HangingProc()
            procs.append(proc)
            return proc

        calls = _record_exec(monkeypatch, factory)
        sleeps = _record_sleeps(monkeypatch)

        result = await MercuryReadablePipeline(timeout=0.05)._run_mercury(
            'https://ex.test/slow')

        assert 'timed out' in (result.error or '')
        assert len(calls) == 1, 'a hanging page must not be retried'
        assert procs[0].killed == 1
        assert procs[0].waited == 1
        assert sleeps == []

    @pytest.mark.skipif(sys.platform == 'win32', reason='POSIX process reaping')
    @pytest.mark.asyncio
    async def test_real_process_is_reaped_after_timeout(self, test_env,
                                                        monkeypatch, tmp_path):
        script = tmp_path / 'slow-mercury'
        script.write_text('#!/bin/sh\nexec sleep 30\n')
        script.chmod(0o755)

        created = []
        real_exec = asyncio.create_subprocess_exec

        async def spy_exec(*argv, **kwargs):
            proc = await real_exec(*argv, **kwargs)
            created.append(proc)
            return proc

        monkeypatch.setattr(asyncio, 'create_subprocess_exec', spy_exec)

        # Point the pipeline AT the sleeping script. Without this the test
        # spawned the real `mercury-parser`, so it proved nothing on a machine
        # that has it and failed outright on one that does not (the CI runner:
        # "[Errno 2] No such file or directory: 'mercury-parser'"). What is
        # under test is that a hanging child is killed and reaped — which has
        # nothing to do with Mercury specifically.
        result = await MercuryReadablePipeline(
            mercury_path=str(script), timeout=0.2)._run_mercury(
            'https://ex.test/slow')

        assert 'timed out' in (result.error or '')
        assert created, 'the real subprocess was never spawned'
        proc = created[0]
        assert proc.returncode is not None and proc.returncode < 0
        with pytest.raises(ChildProcessError):
            os.waitpid(proc.pid, os.WNOHANG)

    @pytest.mark.asyncio
    async def test_nonzero_exit_still_retried_with_backoff(self, test_env,
                                                           monkeypatch):
        """Contract: a failing (not hanging) Mercury run keeps its retries."""
        calls = _record_exec(
            monkeypatch,
            lambda: _FakeProc(stdout=b'', stderr=b'boom', returncode=1))
        sleeps = _record_sleeps(monkeypatch)

        result = await MercuryReadablePipeline()._run_mercury(
            'https://ex.test/broken')

        assert len(calls) == 3
        assert sleeps == [1, 2]
        assert result.error == 'boom'


class TestMercuryTimeoutSetting:
    """The bound comes from settings, then from the module default (D-12)."""

    @pytest.mark.parametrize('configured, explicit, expected', [
        pytest.param(7, None, 7, id='from_settings'),
        pytest.param(None, None, DEFAULT_MERCURY_TIMEOUT, id='module_default'),
        pytest.param(7, 3, 3, id='explicit_argument_wins'),
    ])
    def test_default_timeout_comes_from_settings_then_constant(
            self, test_env, monkeypatch, configured, explicit, expected):
        import settings

        if configured is None:
            monkeypatch.delattr(settings, 'mercury_timeout', raising=False)
        else:
            monkeypatch.setattr(settings, 'mercury_timeout', configured,
                                raising=False)

        pipeline = (MercuryReadablePipeline(timeout=explicit)
                    if explicit is not None else MercuryReadablePipeline())

        assert pipeline.timeout == expected

    def test_module_default_is_sixty_seconds(self):
        assert DEFAULT_MERCURY_TIMEOUT == 60
