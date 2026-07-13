"""Writer 结构化输出：正文与图表解耦、组装为现有占位符格式。"""

from __future__ import annotations

import json
import re
from typing import Any

from llm.schemas import WriterOutputSchema

VALID_CHART_TYPES = frozenset(
    {"GANTT_DATA", "TIMELINE_DATA", "FLOW_DATA", "ORG_DATA", "SMART_DATA"}
)

_CHART_MARKER_RE = re.compile(r"\[\[CHART:(\d+)\]\]", re.IGNORECASE)

_WRITER_OUTPUT_JSON_HINT = """【JSON 输出格式（必须严格遵守）】
仅输出一个 JSON 对象，包含：
- markdown_content：纯正文 Markdown，不含 # 标题行，不含图表 JSON 数据
- embedded_charts：图表数组，每项含 type（GANTT_DATA/TIMELINE_DATA/FLOW_DATA/ORG_DATA/SMART_DATA）与 data（结构化数据）

在 markdown_content 需要插图的位置写 [[CHART:0]]、[[CHART:1]]……下标与 embedded_charts 顺序对应。
若无图表，embedded_charts 填空数组 []。"""


def writer_output_json_hint() -> str:
    return _WRITER_OUTPUT_JSON_HINT


def format_chart_placeholder(chart_type: str, data: Any) -> str:
    """生成 chart_service 可解析的单行占位符。"""
    ctype = (chart_type or "").strip().upper()
    if ctype not in VALID_CHART_TYPES:
        ctype = "GANTT_DATA"
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"[{ctype}: {payload}]"


def _normalize_chart_entry(raw: Any, index: int) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    chart_type = str(raw.get("type") or raw.get("chart_type") or "").strip().upper()
    if chart_type not in VALID_CHART_TYPES:
        return None
    data = raw.get("data")
    if data is None:
        return None
    marker = raw.get("marker")
    if marker is None:
        marker = str(index)
    return {"type": chart_type, "data": data, "marker": str(marker)}


def parse_writer_output(raw: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """校验并规范化 LLM 返回的章节 JSON。"""
    validated = WriterOutputSchema.model_validate(raw)
    markdown = validated.resolved_markdown()
    charts_raw = validated.resolved_charts_raw()

    charts: list[dict[str, Any]] = []
    for i, item in enumerate(charts_raw):
        normalized = _normalize_chart_entry(item, i)
        if normalized:
            charts.append(normalized)
    return markdown, charts


def assemble_chapter_content(markdown_content: str, embedded_charts: list[dict[str, Any]]) -> str:
    """将结构化输出组装为带 [TYPE: {...}] 占位符的正文。"""
    text = (markdown_content or "").strip()
    if not embedded_charts:
        return text

    placeholders: list[str] = []
    for i, chart in enumerate(embedded_charts):
        placeholders.append(format_chart_placeholder(chart["type"], chart["data"]))

    def _replace_marker(match: re.Match[str]) -> str:
        idx = int(match.group(1))
        if 0 <= idx < len(placeholders):
            return placeholders[idx]
        return match.group(0)

    if _CHART_MARKER_RE.search(text):
        assembled = _CHART_MARKER_RE.sub(_replace_marker, text)
        # 未替换的图表追加到文末
        used = {int(m.group(1)) for m in _CHART_MARKER_RE.finditer(text) if int(m.group(1)) < len(placeholders)}
        trailing = [placeholders[i] for i in range(len(placeholders)) if i not in used]
        if trailing:
            assembled = assembled.rstrip() + "\n\n" + "\n".join(trailing)
        return assembled.strip()

    if text:
        return text + "\n\n" + "\n".join(placeholders)
    return "\n".join(placeholders)


def structured_output_to_content(raw: dict[str, Any]) -> str:
    """解析 JSON 并组装为最终章正文。"""
    markdown, charts = parse_writer_output(raw)
    return assemble_chapter_content(markdown, charts)
