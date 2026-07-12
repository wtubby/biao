"""SSE 跨线程投递：后台事件循环可向主循环订阅者推送。"""

import asyncio
import threading

from services.sse_manager import push_event, reset_queue, subscribe, unsubscribe


def test_push_event_same_loop():
    async def _run():
        q = subscribe("p1")
        try:
            await push_event("p1", {"type": "ping"})
            assert q.get_nowait()["type"] == "ping"
        finally:
            unsubscribe("p1", q)

    asyncio.run(_run())


def test_push_event_from_background_thread():
    async def _main():
        q = subscribe("p2")
        errors: list[BaseException] = []
        done = threading.Event()

        def worker():
            async def _run():
                await push_event("p2", {"type": "from-bg", "n": 1})

            try:
                asyncio.run(_run())
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                done.set()

        t = threading.Thread(target=worker)
        t.start()
        for _ in range(100):
            if not q.empty() or errors or done.is_set():
                break
            await asyncio.sleep(0.02)
        t.join(timeout=2)

        assert not errors, errors
        assert q.get_nowait() == {"type": "from-bg", "n": 1}
        unsubscribe("p2", q)

    asyncio.run(_main())


def test_reset_queue_clears_events():
    async def _run():
        q = subscribe("p3")
        await push_event("p3", {"type": "old"})
        reset_queue("p3")
        assert q.empty()
        unsubscribe("p3", q)

    asyncio.run(_run())
