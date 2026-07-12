"""生成流水线编排：阶段状态、超时重试、SSE 进度（借鉴 AI-Bid-System pipeline_stages）。"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from config import PIPELINE_STAGE_MAX_RETRIES, PIPELINE_STAGE_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class StageResult:
    stage_name: str
    status: StageStatus
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    elapsed_ms: int = 0
    retry_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_name": self.stage_name,
            "status": self.status.value,
            "data": self.data,
            "error": self.error,
            "elapsed_ms": self.elapsed_ms,
            "retry_count": self.retry_count,
        }


StageFn = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]
StageCallback = Callable[[str, str, float, str, dict[str, Any]], Awaitable[None] | None]


class GenerationPipeline:
    def __init__(self, project_id: str, on_stage: StageCallback | None = None):
        self.project_id = project_id
        self.context: dict[str, Any] = {}
        self.on_stage = on_stage
        self._stages: list[tuple[str, StageFn]] = []

    def add_stage(self, name: str, fn: StageFn) -> None:
        self._stages.append((name, fn))

    async def _emit(self, stage: str, status: str, progress: float, message: str, data: dict | None = None) -> None:
        if not self.on_stage:
            return
        payload = data or {}
        result = self.on_stage(stage, status, progress, message, payload)
        if asyncio.iscoroutine(result):
            await result

    async def _run_stage(self, name: str, fn: StageFn, index: int, total: int) -> StageResult:
        start = time.time()
        base_progress = index / max(total, 1)

        for attempt in range(PIPELINE_STAGE_MAX_RETRIES + 1):
            await self._emit(
                name,
                StageStatus.RUNNING.value,
                base_progress,
                f"阶段 {index + 1}/{total}：{name}（尝试 {attempt + 1}/{PIPELINE_STAGE_MAX_RETRIES + 1}）",
            )
            try:
                result = await asyncio.wait_for(fn(self.context), timeout=PIPELINE_STAGE_TIMEOUT_SECONDS)
                if result:
                    self.context.update(result)
                elapsed = int((time.time() - start) * 1000)
                await self._emit(
                    name,
                    StageStatus.COMPLETED.value,
                    (index + 1) / max(total, 1),
                    f"{name} 完成（{elapsed}ms）",
                    {"elapsed_ms": elapsed},
                )
                return StageResult(
                    stage_name=name,
                    status=StageStatus.COMPLETED,
                    elapsed_ms=elapsed,
                    retry_count=attempt,
                )
            except asyncio.TimeoutError:
                err = f"阶段超时（{PIPELINE_STAGE_TIMEOUT_SECONDS}s）"
                logger.warning("[%s] %s", name, err)
            except Exception as exc:
                err = str(exc)
                logger.warning("[%s] 执行失败: %s (尝试 %d)", name, err, attempt + 1)

            if attempt >= PIPELINE_STAGE_MAX_RETRIES:
                elapsed = int((time.time() - start) * 1000)
                await self._emit(name, StageStatus.FAILED.value, base_progress, err)
                return StageResult(
                    stage_name=name,
                    status=StageStatus.FAILED,
                    error=err,
                    elapsed_ms=elapsed,
                    retry_count=attempt + 1,
                )
            await asyncio.sleep(2**attempt)

        return StageResult(stage_name=name, status=StageStatus.FAILED, error="未知错误")

    async def run(self) -> list[StageResult]:
        results: list[StageResult] = []
        total = len(self._stages)
        for index, (name, fn) in enumerate(self._stages):
            result = await self._run_stage(name, fn, index, total)
            results.append(result)
            if result.status == StageStatus.FAILED:
                break
        return results
