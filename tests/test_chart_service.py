import json

from chart.chart_service import (
    CHART_PATTERN,
    iter_chart_matches,
    next_caption,
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
