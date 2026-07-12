"""提示词体量估算（用于生成质量观测与调试）。"""

from __future__ import annotations

from typing import Any

from config import CHARS_PER_TOKEN_CN


def estimate_text_tokens(text: str, *, chars_per_token: float | None = None) -> int:
    """按中英混合经验系数估算 token 数。"""
    ratio = chars_per_token if chars_per_token is not None else CHARS_PER_TOKEN_CN
    if ratio <= 0:
        ratio = CHARS_PER_TOKEN_CN
    cleaned = text or ""
    if not cleaned:
        return 0
    return max(1, int(len(cleaned) / ratio))


def estimate_prompt_stage(system: str, user: str) -> dict[str, int]:
    sys_text = system or ""
    user_text = user or ""
    sys_tokens = estimate_text_tokens(sys_text)
    user_tokens = estimate_text_tokens(user_text)
    return {
        "system_chars": len(sys_text),
        "user_chars": len(user_text),
        "system_tokens_est": sys_tokens,
        "user_tokens_est": user_tokens,
        "total_tokens_est": sys_tokens + user_tokens,
    }


def attach_stage_metrics(stages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """为各 stage 附加 metrics，并返回汇总。"""
    annotated: list[dict[str, Any]] = []
    total_tokens = 0
    total_chars = 0
    for stage in stages:
        metrics = estimate_prompt_stage(
            str(stage.get("system") or ""),
            str(stage.get("user") or ""),
        )
        total_tokens += metrics["total_tokens_est"]
        total_chars += metrics["system_chars"] + metrics["user_chars"]
        item = dict(stage)
        item["metrics"] = metrics
        annotated.append(item)
    summary = {
        "stage_count": len(annotated),
        "total_chars": total_chars,
        "total_tokens_est": total_tokens,
    }
    return annotated, summary
