"""GoalExecutor._run_async must not leak an un-awaited coroutine.

Observed at the end of a real capability-benchmark run: once the process was
shutting down the thread pool could not schedule the worker
("cannot schedule new futures after shutdown"), so the coroutine handed to
`_run_async` was never awaited and Python emitted
`RuntimeWarning: coroutine 'ModelRouter.complete' was never awaited`.
"""

from __future__ import annotations

import asyncio
import concurrent.futures

import pytest

from friday.executor import GoalExecutor


def test_unschedulable_work_does_not_leak_a_coroutine(monkeypatch, recwarn):
    executor = GoalExecutor()

    class _DeadPool:
        def submit(self, fn, *a, **kw):
            raise RuntimeError("cannot schedule new futures after shutdown")

        def shutdown(self, wait=True):
            return None

    monkeypatch.setattr(
        concurrent.futures, "ThreadPoolExecutor", lambda *a, **kw: _DeadPool()
    )

    async def _work():
        await asyncio.sleep(0)
        return "never reached"

    coro = _work()
    with pytest.raises(RuntimeError, match="cannot schedule"):
        executor._run_async(coro)

    # Force collection so any un-awaited coroutine would surface its warning.
    import gc

    del coro
    gc.collect()
    leaked = [w for w in recwarn if "never awaited" in str(w.message)]
    assert not leaked, f"coroutine leaked: {[str(w.message) for w in leaked]}"


def test_normal_path_still_returns_a_result():
    executor = GoalExecutor()

    async def _work():
        await asyncio.sleep(0.01)
        return "ok"

    assert executor._run_async(_work(), timeout=10) == "ok"


def test_timeout_still_raises_and_does_not_leak(recwarn):
    executor = GoalExecutor()

    async def _slow():
        await asyncio.sleep(30)
        return "never"

    with pytest.raises((TimeoutError, concurrent.futures.TimeoutError)):
        executor._run_async(_slow(), timeout=0.3)

    import gc

    gc.collect()
    leaked = [w for w in recwarn if "never awaited" in str(w.message)]
    assert not leaked


def test_factory_form_creates_nothing_when_the_worker_cannot_start(monkeypatch, recwarn):
    """A factory must not create a coroutine at all if the work never runs."""
    executor = GoalExecutor()
    created = []

    class _DeadPool:
        def submit(self, fn, *a, **kw):
            raise RuntimeError("cannot schedule new futures after shutdown")

        def shutdown(self, wait=True):
            return None

    monkeypatch.setattr(
        concurrent.futures, "ThreadPoolExecutor", lambda *a, **kw: _DeadPool()
    )

    async def _work():
        return "never"

    def _factory():
        created.append(True)
        return _work()

    with pytest.raises(RuntimeError, match="cannot schedule"):
        executor._run_async(_factory)

    assert not created, "the factory must not be invoked when the worker cannot start"

    import gc

    gc.collect()
    leaked = [w for w in recwarn if "never awaited" in str(w.message)]
    assert not leaked


def test_factory_form_returns_a_result_normally():
    executor = GoalExecutor()

    async def _work():
        await asyncio.sleep(0.01)
        return "ok"

    assert executor._run_async(lambda: _work(), timeout=10) == "ok"
