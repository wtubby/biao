"""SSE 进度广播：支持从后台线程向主事件循环上的订阅者投递事件。"""

from __future__ import annotations

import asyncio
from collections import defaultdict

# project_id -> [(queue, owning_loop), ...]
# 一个项目允许多个前端标签页同时订阅；事件广播给每一个订阅者。
_subscribers: dict[str, list[tuple[asyncio.Queue, asyncio.AbstractEventLoop]]] = defaultdict(list)


def subscribe(project_id: str) -> asyncio.Queue:
    """为一个新的 SSE 连接创建独立队列并登记为订阅者。"""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    _subscribers[project_id].append((queue, loop))
    return queue


def unsubscribe(project_id: str, queue: asyncio.Queue) -> None:
    """SSE 连接断开时移除对应队列，避免内存泄漏。"""
    subs = _subscribers.get(project_id)
    if not subs:
        return
    _subscribers[project_id] = [(q, loop) for q, loop in subs if q is not queue]
    if not _subscribers[project_id]:
        _subscribers.pop(project_id, None)


async def push_event(project_id: str, event: dict) -> None:
    """将事件广播给该项目当前所有订阅者（可从后台线程的事件循环调用）。"""
    try:
        current = asyncio.get_running_loop()
    except RuntimeError:
        current = None

    for queue, loop in list(_subscribers.get(project_id, [])):
        if current is loop:
            await queue.put(event)
            continue
        if loop.is_closed():
            continue
        fut = asyncio.run_coroutine_threadsafe(queue.put(event), loop)
        await asyncio.wrap_future(fut)


def reset_queue(project_id: str) -> None:
    """开始新一轮生成前，清空该项目所有现存订阅者队列里的旧事件。"""
    for queue, loop in list(_subscribers.get(project_id, [])):
        if loop.is_closed():
            continue
        try:
            current = asyncio.get_running_loop()
        except RuntimeError:
            current = None

        if current is loop:
            _drain_queue(queue)
            continue

        fut = asyncio.run_coroutine_threadsafe(_drain_queue_async(queue), loop)
        try:
            fut.result(timeout=5)
        except Exception:
            pass


def _drain_queue(queue: asyncio.Queue) -> None:
    while not queue.empty():
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            break


async def _drain_queue_async(queue: asyncio.Queue) -> None:
    _drain_queue(queue)
