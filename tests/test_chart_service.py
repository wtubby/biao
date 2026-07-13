import json

from chart.chart_service import (
    CHART_PATTERN,
    iter_chart_matches,
    next_caption,
    normalize_gantt_data,
    render_gantt,
)


def test_render_gantt_produces_png_file():
    data = [
        {"工序": "基础施工", "开始第几天": 1, "持续天数": 10},
        {"工序": "设备安装", "开始第几天": 8, "持续天数": 15},
    ]
    path = render_gantt(data, duration=40)
    try:
        assert path.exists()
        assert path.suffix == ".png"
        assert path.stat().st_size > 0
    finally:
        path.unlink(missing_ok=True)


def test_render_gantt_handles_empty_data():
    path = render_gantt([])
    try:
        assert path.exists()
    finally:
        path.unlink(missing_ok=True)


def test_iter_chart_matches_nested_bracket_in_string():
    content = '[GANTT_DATA: [{"工序": "测试]工序", "开始第几天": 1, "持续天数": 3}]]'
    matches = list(iter_chart_matches(content))
    assert len(matches) == 1
    data = json.loads(matches[0].raw_json)
    assert data[0]["工序"] == "测试]工序"


def test_iter_chart_matches_org_object():
    content = '[ORG_DATA: {"name": "项目部", "children": []}]'
    matches = list(iter_chart_matches(content))
    assert len(matches) == 1
    assert matches[0].chart_type == "ORG_DATA"


def test_chart_pattern_compat_with_iter():
    content = '[TIMELINE_DATA: [{"第几天": 1, "节点": "开工"}]]'
    assert len(list(CHART_PATTERN.finditer(content))) == 1


def test_next_caption_increments_figure_and_table():
    counters: dict = {}
    assert next_caption(counters, "GANTT_DATA") == "图1 施工进度横道图"
    assert next_caption(counters, "SMART_DATA") == "表1 要点对照表"
    assert next_caption(counters, "TIMELINE_DATA") == "图2 里程碑时间轴"


def test_iter_chart_matches_block_gantt_object():
    content = """前文

[GANTT_DATA]
{
  "title": "进度计划",
  "startDate": "2026-07-01",
  "tasks": [
    {"id": 1, "name": "设计", "start": "2026-07-01", "end": "2026-07-20", "duration": 20},
    {"id": 2, "name": "施工", "start": "2026-07-15", "end": "2026-08-15", "duration": 32}
  ]
}
[/GANTT_DATA]

后文"""
    matches = list(iter_chart_matches(content))
    assert len(matches) == 1
    assert matches[0].chart_type == "GANTT_DATA"
    assert content[matches[0].end_pos :].lstrip().startswith("后文")
    data = json.loads(matches[0].raw_json)
    rows = normalize_gantt_data(data)
    assert len(rows) == 2
    assert rows[0]["工序"] == "设计"
    assert rows[0]["开始第几天"] == 1
    assert rows[0]["持续天数"] == 20
    assert rows[1]["开始第几天"] == 15


def test_iter_chart_matches_unwraps_json_fence():
    content = """说明如下：

```json
[GANTT_DATA]
{
  "tasks": [
    {"name": "基础", "start": 0, "end": 10}
  ]
}
```

后续正文"""
    matches = list(iter_chart_matches(content))
    assert len(matches) == 1
    assert matches[0].chart_type == "GANTT_DATA"
    assert content[matches[0].start_pos : matches[0].start_pos + 3] == "```"
    assert "后续正文" in content[matches[0].end_pos :]
    assert "```" not in content[matches[0].end_pos :]
    rows = normalize_gantt_data(json.loads(matches[0].raw_json))
    assert rows[0]["工序"] == "基础"


def test_normalize_gantt_numeric_offsets():
    rows = normalize_gantt_data(
        {
            "tasks": [
                {"name": "采购", "start": 0, "end": 30},
                {"name": "到货", "start": 30, "end": 90},
            ]
        }
    )
    assert rows[0] == {"工序": "采购", "开始第几天": 1, "持续天数": 30}
    assert rows[1] == {"工序": "到货", "开始第几天": 31, "持续天数": 60}


def test_normalize_gantt_day_labels():
    rows = normalize_gantt_data(
        {
            "tasks": [
                {"name": "预验收", "start": "第151天", "end": "第165天"},
            ]
        }
    )
    assert rows[0]["开始第几天"] == 151
    assert rows[0]["持续天数"] == 14


def test_render_gantt_accepts_block_object_schema():
    path = render_gantt(
        {
            "tasks": [
                {"name": "基础", "start": 0, "end": 10},
            ]
        }
    )
    try:
        assert path.exists()
        assert path.stat().st_size > 0
    finally:
        path.unlink(missing_ok=True)


def test_merge_gantt_payloads_dedupes_by_task_name():
    from chart.chart_service import merge_gantt_payloads

    a = [{"工序": "基础施工", "开始第几天": 1, "持续天数": 10}]
    b = [{"name": "基础施工", "start": 0, "end": 10}, {"name": "架线", "start": 20, "end": 40}]
    merged = merge_gantt_payloads([a, b])
    assert [r["工序"] for r in merged] == ["基础施工", "架线"]
