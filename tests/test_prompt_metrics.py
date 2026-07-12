"""提示词体量估算测试。"""

from services.prompt_metrics import attach_stage_metrics, estimate_text_tokens


def test_estimate_text_tokens_empty():
    assert estimate_text_tokens("") == 0


def test_estimate_text_tokens_uses_chars_ratio():
    text = "中" * 60
    assert estimate_text_tokens(text, chars_per_token=0.6) == 100


def test_attach_stage_metrics_summarizes_stages():
    stages = [
        {"id": "writer", "label": "正文", "system": "a" * 60, "user": "b" * 120},
        {"id": "qa", "label": "质检", "system": "c" * 30, "user": "d" * 30},
    ]
    annotated, summary = attach_stage_metrics(stages)
    assert len(annotated) == 2
    assert annotated[0]["metrics"]["total_tokens_est"] > 0
    assert summary["stage_count"] == 2
    assert summary["total_tokens_est"] == sum(
        s["metrics"]["total_tokens_est"] for s in annotated
    )
