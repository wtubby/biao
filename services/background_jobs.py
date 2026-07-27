"""后台任务调度：避免长任务阻塞 uvicorn 主事件循环。

FastAPI/Starlette 的 BackgroundTasks 对 async 可调用对象会在主循环上 await；
而本项目的 LLM/解析多为同步阻塞调用，挂在主循环上会导致整站 API 超时。
同步任务走线程池，异步协程在独立线程中 asyncio.run。

约定：任何会改同一业务实体（项目/文件夹等）的后台任务，应传 dedupe_key
给 spawn_sync / spawn_async；若调用方需在 spawn 前做 DB/文件准备，先
try_acquire_job，再以 already_acquired=True 交给 spawn（由 spawn finally
release）。标准写法见 routers/generate.py。
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable, Coroutine
from concurrent.futures import ThreadPoolExecutor
from typing import Any

logger = logging.getLogger(__name__)

_SYNC_WORKERS = 4
_executor = ThreadPoolExecutor(max_workers=_SYNC_WORKERS, thread_name_prefix="bg-sync")

# 进程内去重：同 dedupe_key 同时只允许一个异步后台任务在跑
_running_keys: set[str] = set()
_running_lock = threading.Lock()


def try_acquire_job(dedupe_key: str) -> bool:
    """尝试占用进程内任务槽；已占用则返回 False。"""
    with _running_lock:
        if dedupe_key in _running_keys:
            return False
        _running_keys.add(dedupe_key)
        return True


def release_job(dedupe_key: str) -> None:
    """释放进程内任务槽。"""
    with _running_lock:
        _running_keys.discard(dedupe_key)


def is_job_running(dedupe_key: str) -> bool:
    with _running_lock:
        return dedupe_key in _running_keys


def spawn_sync(
    fn: Callable[..., Any],
    *args: Any,
    name: str = "sync-job",
    dedupe_key: str | None = None,
    already_acquired: bool = False,
    **kwargs: Any,
) -> bool:
    """在线程池中执行同步后台任务。dedupe_key 非空且已被占用时跳过，返回 False。

    already_acquired=True 表示调用方已通过 try_acquire_job 占槽，此处只负责收尾释放。
    """
    if dedupe_key is not None and not already_acquired:
        if not try_acquire_job(dedupe_key):
            logger.warning("跳过重复后台任务: %s (key=%s)", name, dedupe_key)
            return False

    def _wrapper() -> None:
        try:
            fn(*args, **kwargs)
        except Exception:
            logger.exception("后台同步任务失败: %s", name)
        finally:
            if dedupe_key is not None:
                release_job(dedupe_key)

    _executor.submit(_wrapper)
    return True


def spawn_async(
    factory: Callable[[], Coroutine[Any, Any, Any]],
    *,
    name: str = "async-job",
    dedupe_key: str | None = None,
    already_acquired: bool = False,
) -> bool:
    """在独立守护线程 + 独立事件循环中运行协程工厂。

    若提供 dedupe_key 且同 key 任务仍在跑，则跳过并返回 False。
    already_acquired=True 表示调用方已通过 try_acquire_job 占槽，此处只负责收尾释放。
    """
    if dedupe_key is not None and not already_acquired:
        if not try_acquire_job(dedupe_key):
            logger.warning("跳过重复后台任务: %s (key=%s)", name, dedupe_key)
            return False

    def _runner() -> None:
        try:
            asyncio.run(factory())
        except Exception:
            logger.exception("后台异步任务失败: %s", name)
        finally:
            if dedupe_key is not None:
                release_job(dedupe_key)

    threading.Thread(target=_runner, name=f"bg-{name}", daemon=True).start()
    return True
