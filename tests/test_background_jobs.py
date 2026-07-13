"""后台任务调度：同步走线程池，异步走独立事件循环线程。"""

import asyncio
import threading
import time

from services import background_jobs
from services.background_jobs import (
    is_job_running,
    release_job,
    spawn_async,
    spawn_sync,
    try_acquire_job,
)


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


def test_try_acquire_job_is_exclusive():
    key = "generate:acquire-test"
    release_job(key)
    assert try_acquire_job(key) is True
    assert try_acquire_job(key) is False
    assert is_job_running(key) is True
    release_job(key)
    assert is_job_running(key) is False
    assert try_acquire_job(key) is True
    release_job(key)


def test_spawn_async_dedupe_key_skips_duplicate():
    release = threading.Event()
    started = threading.Event()
    runs = {"n": 0}

    async def job():
        runs["n"] += 1
        started.set()
        await asyncio.to_thread(release.wait)

    key = "generate:dedupe-test"
    release_job(key)

    assert spawn_async(job, name="a", dedupe_key=key) is True
    assert started.wait(timeout=2)
    assert spawn_async(job, name="b", dedupe_key=key) is False

    release.set()
    deadline = time.time() + 2
    while key in background_jobs._running_keys and time.time() < deadline:
        time.sleep(0.01)

    assert runs["n"] == 1
    assert spawn_async(job, name="c", dedupe_key=key) is True
    deadline = time.time() + 2
    while key in background_jobs._running_keys and time.time() < deadline:
        time.sleep(0.01)


def test_spawn_async_already_acquired_releases_on_finish():
    key = "generate:preacquired"
    release_job(key)
    assert try_acquire_job(key) is True
    done = threading.Event()

    async def job():
        done.set()

    assert spawn_async(job, name="pre", dedupe_key=key, already_acquired=True) is True
    assert done.wait(timeout=2)
    deadline = time.time() + 2
    while is_job_running(key) and time.time() < deadline:
        time.sleep(0.01)
    assert is_job_running(key) is False


def test_spawn_sync_swallows_exceptions():
    def boom():
        raise RuntimeError("expected")

    spawn_sync(boom)
    time.sleep(0.05)
