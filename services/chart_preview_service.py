"""供预览页实时调用的图表渲染服务：处理图片型图表（GANTT/TIMELINE/FLOW/ORG），
SMART 是纯要点对照，交给前端直接用 JSON 渲染 HTML 表格。"""

import base64
import json
import logging

from chart.chart_service import (
    CHART_PATTERN,
    next_caption,
    parse_chart_match,
    render_flow,
    render_gantt,
    render_org,
    render_timeline,
)

logger = logging.getLogger(__name__)

_IMAGE_CHART_TYPES = {"GANTT_DATA", "TIMELINE_DATA", "FLOW_DATA", "ORG_DATA"}
_MAX_CHARTS_PER_REQUEST = 15
_MAX_CACHE_SIZE = 64
_render_cache: dict[tuple, str | None] = {}


def _cache_get(key: tuple) -> str | None | object:
    if key not in _render_cache:
        return _CACHE_MISS
    return _render_cache[key]


_CACHE_MISS = object()


def _cache_set(key: tuple, value: str | None) -> None:
    if len(_render_cache) >= _MAX_CACHE_SIZE:
        _render_cache.pop(next(iter(_render_cache)))
    _render_cache[key] = value


def _render_one(chart_type: str, raw_json: str, duration: int | None = None) -> str | None:
    cache_key = (chart_type, raw_json, duration)
    cached = _cache_get(cache_key)
    if cached is not _CACHE_MISS:
        return cached  # type: ignore[return-value]
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        _cache_set(cache_key, None)
        return None
    try:
        if chart_type == "GANTT_DATA":
            path = render_gantt(data, duration)
        elif chart_type == "TIMELINE_DATA":
            path = render_timeline(data)
        elif chart_type == "FLOW_DATA":
            path = render_flow(data)
        elif chart_type == "ORG_DATA":
            path = render_org(data)
        else:
            _cache_set(cache_key, None)
            return None
        if not path:
            _cache_set(cache_key, None)
            return None
        image_bytes = path.read_bytes()
        path.unlink(missing_ok=True)
        encoded = base64.b64encode(image_bytes).decode("ascii")
        _cache_set(cache_key, encoded)
        return encoded
    except Exception as exc:
        logger.warning("图表预览渲染失败 %s: %s", chart_type, exc)
        _cache_set(cache_key, None)
        return None


def render_chart_previews(content: str, duration_days: int | None = None) -> list[dict]:
    results: list[dict] = []
    counters: dict = {}
    for match in CHART_PATTERN.finditer(content):
        if len(results) >= _MAX_CHARTS_PER_REQUEST:
            break
        chart_type, raw_json = parse_chart_match(match)
        if chart_type not in _IMAGE_CHART_TYPES:
            continue
        caption = next_caption(counters, chart_type)
        results.append({
            "start": match.start(),
            "end": match.end(),
            "chart_type": chart_type,
            "caption": caption,
            "image_base64": _render_one(chart_type, raw_json, duration_days),
        })
    return results
