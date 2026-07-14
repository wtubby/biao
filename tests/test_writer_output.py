"""Writer 结构化输出组装测试。"""

import json

from services.writer_output import (
    assemble_chapter_content,
    format_chart_placeholder,
    parse_writer_output,
    structured_output_to_content,
)


def test_format_chart_placeholder_compact_json():
    ph = format_chart_placeholder(
        "GANTT_DATA",
        [{"工序": "基础施工", "开始第几天": 1, "持续天数": 10}],
    )
    assert ph.startswith("[GANTT_DATA: ")
    assert ph.endswith("]]")
    inner = ph[len("[GANTT_DATA: ") : -1]
    assert json.loads(inner)[0]["工序"] == "基础施工"


def test_assemble_replaces_chart_markers():
    charts = {
        0: {"type": "GANTT_DATA", "data": [{"工序": "A", "开始第几天": 1, "持续天数": 5}]},
        1: {"type": "FLOW_DATA", "data": [{"from": "开始", "to": "结束"}]},
    }
    md = "进度安排如下：\n\n[[CHART:0]]\n\n工艺流程：\n\n[[CHART:1]]"
    out = assemble_chapter_content(md, charts)
    assert "[[CHART:0]]" not in out
    assert "[GANTT_DATA:" in out
    assert "[FLOW_DATA:" in out


def test_assemble_appends_orphan_charts_at_end():
    charts = {0: {"type": "GANTT_DATA", "data": [{"工序": "X", "开始第几天": 1, "持续天数": 3}]}}
    out = assemble_chapter_content("正文段落。", charts)
    assert out.startswith("正文段落。")
    assert "[GANTT_DATA:" in out


def test_structured_output_to_content_full_pipeline():
    raw = {
        "markdown_content": "施工步骤一。\n\n[[CHART:0]]",
        "embedded_charts": [
            {"type": "GANTT_DATA", "data": [{"工序": "基础", "开始第几天": 1, "持续天数": 7}]},
        ],
    }
    out = structured_output_to_content(raw)
    assert "施工步骤一" in out
    assert "[GANTT_DATA:" in out


def test_parse_writer_output_skips_invalid_charts():
    md, charts = parse_writer_output({
        "markdown_content": "正文",
        "embedded_charts": [
            {"type": "GANTT_DATA", "data": [{"工序": "A", "开始第几天": 1, "持续天数": 1}]},
            {"type": "INVALID", "data": []},
            "not-a-dict",
        ],
    })
    assert md == "正文"
    assert charts == {
        0: {
            "type": "GANTT_DATA",
            "data": [{"工序": "A", "开始第几天": 1, "持续天数": 1}],
            "marker": "0",
        },
    }


def test_assemble_preserves_chart_indices_after_middle_chart_filtered():
    raw = {
        "markdown_content": "图一：[[CHART:0]]\n\n图三：[[CHART:2]]",
        "embedded_charts": [
            {"type": "GANTT_DATA", "data": [{"工序": "A", "开始第几天": 1, "持续天数": 1}]},
            {"type": "INVALID", "data": []},
            {"type": "FLOW_DATA", "data": [{"from": "开始", "to": "结束"}]},
        ],
    }
    out = structured_output_to_content(raw)
    assert "[[CHART:0]]" not in out
    assert "[[CHART:2]]" not in out
    assert "[GANTT_DATA:" in out
    assert "[FLOW_DATA:" in out
    assert out.index("[GANTT_DATA:") < out.index("[FLOW_DATA:")
