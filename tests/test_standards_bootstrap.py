"""标准库 bootstrap 后台任务与状态接口。"""

from __future__ import annotations

import threading
import time
from unittest.mock import patch

from routers import standards as standards_router
from routers.standards import bootstrap_api, bootstrap_status_api
from services.background_jobs import is_job_running, release_job, try_acquire_job


def _clear_bootstrap(domain: str | None = None) -> None:
    key = domain or "__all__"
    standards_router._bootstrap_progress.pop(key, None)
    release_job(f"standards-bootstrap:{key}")


def test_bootstrap_api_spawns_background_and_reports_status():
    _clear_bootstrap()
    started_gate = threading.Event()
    finish_gate = threading.Event()

    def _slow_bootstrap(db, domain=None):
        started_gate.set()
        finish_gate.wait(timeout=5)
        return 3

    try:
        with patch("routers.standards.bootstrap_from_knowledge_base", side_effect=_slow_bootstrap) as boot:
            started = bootstrap_api(domain=None)
            assert started == {"status": "running"}
            assert started_gate.wait(timeout=2)
            assert bootstrap_status_api().get("status") == "running"

            finish_gate.set()
            deadline = time.time() + 5
            while is_job_running("standards-bootstrap:__all__") and time.time() < deadline:
                time.sleep(0.05)

            status = bootstrap_status_api()
            assert status == {"status": "done", "created": 3}
            boot.assert_called_once()
            assert boot.call_args.kwargs.get("domain") is None
    finally:
        finish_gate.set()
        _clear_bootstrap()


def test_bootstrap_api_dedupes_concurrent_start():
    _clear_bootstrap(domain="电力工程")
    try:
        assert try_acquire_job("standards-bootstrap:电力工程") is True
        assert bootstrap_api(domain="电力工程") == {"status": "already_running"}
    finally:
        _clear_bootstrap(domain="电力工程")


def test_bootstrap_status_idle_by_default():
    key = "__idle_probe__"
    standards_router._bootstrap_progress.pop(key, None)
    assert bootstrap_status_api(domain=key) == {"status": "idle"}
