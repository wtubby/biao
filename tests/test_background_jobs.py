"""后台任务调度：同步走线程池，异步走独立事件循环线程。"""

import asyncio
import threading
import time

from services.background_jobs import spawn_async, spawn_sync


def test_spawn_sync_runs_off_caller_thread():
    caller = threading.get_ident()
    seen = {"tid": None, "done": False}

    def job():
        seen["tid"] = threading.get_ident()
        seen["done"] = True

    spawn_sync(job)
    deadline = time.time() + 2
    while not seen["done"] and time.time() < deadline:
        time.sleep(0.01)

    assert seen["done"] is True
    assert seen["tid"] is not None
    assert seen["tid"] != caller


def test_spawn_async_runs_coroutine_off_caller_thread():
    caller = threading.get_ident()
    seen = {"tid": None, "done": False}

    async def job():
        await asyncio.sleep(0.01)
        seen["tid"] = threading.get_ident()
        seen["done"] = True

    spawn_async(job, name="test-async")
    deadline = time.time() + 2
    while not seen["done"] and time.time() < deadline:
        time.sleep(0.01)

    assert seen["done"] is True
    assert seen["tid"] is not None
    assert seen["tid"] != caller


def test_spawn_sync_swallows_exceptions():
    def boom():
        raise RuntimeError("expected")

    spawn_sync(boom)
    time.sleep(0.05)
