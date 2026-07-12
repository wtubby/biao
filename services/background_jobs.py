"""后台任务调度：避免长任务阻塞 uvicorn 主事件循环。

FastAPI/Starlette 的 BackgroundTasks 对 async 可调用对象会在主循环上 await；
而本项目的 LLM/解析多为同步阻塞调用，挂在主循环上会导致整站 API 超时。
同步任务走线程池，异步协程在独立线程中 asyncio.run。
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


def spawn_sync(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    """在线程池中执行同步后台任务。"""

    def _wrapper() -> None:
        try:
            fn(*args, **kwargs)
        except Exception:
            logger.exception("后台同步任务失败: %s", getattr(fn, "__name__", repr(fn)))

    _executor.submit(_wrapper)


def spawn_async(
    factory: Callable[[], Coroutine[Any, Any, Any]],
    *,
    name: str = "async-job",
) -> None:
    """在独立守护线程 + 独立事件循环中运行协程工厂。"""

    def _runner() -> None:
        try:
            asyncio.run(factory())
        except Exception:
            logger.exception("后台异步任务失败: %s", name)

    threading.Thread(target=_runner, name=f"bg-{name}", daemon=True).start()
