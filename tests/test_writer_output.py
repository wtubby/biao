"""Writer 结构化输出组装测试。"""

import json

from services.writer_output import (
    assemble_chapter_content,
    format_chart_placeholder,
    parse_writer_output,
    structured_output_to_content,
    writer_output_json_hint,
)


def test_format_chart_placeholder_compact_json():
    ph = format_chart_placeholder(
        "FLOW_DATA",
        [{"from": "开始", "to": "结束"}],
    )
    assert ph.startswith("[FLOW_DATA: ")
    assert ph.endswith("]]")
    inner = ph[len("[FLOW_DATA: ") : -1]
    assert json.loads(inner)[0]["from"] == "开始"


def test_format_chart_placeholder_unknown_falls_back_to_flow():
    ph = format_chart_placeholder("UNKNOWN", [{"from": "A", "to": "B"}])
    assert ph.startswith("[FLOW_DATA: ")


def test_assemble_replaces_chart_markers():
    charts = {
        0: {"type": "TIMELINE_DATA", "data": [{"事件": "开工", "第几天": 1}]},
        1: {"type": "FLOW_DATA", "data": [{"from": "开始", "to": "结束"}]},
    }
    md = "节点安排如下：\n\n[[CHART:0]]\n\n工艺流程：\n\n[[CHART:1]]"
    out = assemble_chapter_content(md, charts)
    assert "[[CHART:0]]" not in out
    assert "[TIMELINE_DATA:" in out
    assert "[FLOW_DATA:" in out


def test_assemble_appends_orphan_charts_at_end():
    charts = {0: {"type": "ORG_DATA", "data": {"name": "项目部", "children": []}}}
    out = assemble_chapter_content("正文段落。", charts)
    assert out.startswith("正文段落。")
    assert "[ORG_DATA:" in out


def test_structured_output_to_content_full_pipeline():
    raw = {
        "markdown_content": "施工步骤一。\n\n[[CHART:0]]",
        "embedded_charts": [
            {"type": "FLOW_DATA", "data": [{"from": "准备", "to": "完工"}]},
        ],
    }
    out = structured_output_to_content(raw)
    assert "施工步骤一" in out
    assert "[FLOW_DATA:" in out


def test_parse_writer_output_skips_invalid_charts():
    md, charts = parse_writer_output({
        "markdown_content": "正文",
        "embedded_charts": [
            {"type": "FLOW_DATA", "data": [{"from": "A", "to": "B"}]},
            {"type": "INVALID", "data": []},
            "not-a-dict",
        ],
    })
    assert md == "正文"
    assert charts == {
        0: {
            "type": "FLOW_DATA",
            "data": [{"from": "A", "to": "B"}],
            "marker": "0",
        },
    }


def test_parse_writer_output_drops_gantt_data():
    """章节结构化输出不再接受 GANTT_DATA（末尾统一生成）。"""
    md, charts = parse_writer_output({
        "markdown_content": "进度说明。\n\n[[CHART:0]]",
        "embedded_charts": [
            {"type": "GANTT_DATA", "data": [{"工序": "A", "开始第几天": 1, "持续天数": 1}]},
            {"type": "FLOW_DATA", "data": [{"from": "开始", "to": "结束"}]},
        ],
    })
    assert md.startswith("进度说明")
    assert 0 not in charts
    assert charts[1]["type"] == "FLOW_DATA"


def test_assemble_preserves_chart_indices_after_middle_chart_filtered():
    raw = {
        "markdown_content": "图一：[[CHART:0]]\n\n图三：[[CHART:2]]",
        "embedded_charts": [
            {"type": "ORG_DATA", "data": {"name": "项目部"}},
            {"type": "INVALID", "data": []},
            {"type": "FLOW_DATA", "data": [{"from": "开始", "to": "结束"}]},
        ],
    }
    out = structured_output_to_content(raw)
    assert "[[CHART:0]]" not in out
    assert "[[CHART:2]]" not in out
    assert "[ORG_DATA:" in out
    assert "[FLOW_DATA:" in out
    assert out.index("[ORG_DATA:") < out.index("[FLOW_DATA:")


def test_assemble_strips_unmatched_chart_markers():
    charts = {
        0: {"type": "FLOW_DATA", "data": [{"from": "A", "to": "B"}]},
    }
    out = assemble_chapter_content(
        "有图：[[CHART:0]]\n\n无图：[[CHART:2]]\n\n收尾。",
        charts,
    )
    assert "[FLOW_DATA:" in out
    assert "[[CHART:" not in out
    assert "无图：" in out
    assert "收尾。" in out


def test_assemble_strips_markers_when_all_charts_invalid():
    out = assemble_chapter_content("正文[[CHART:0]]结尾", {})
    assert out == "正文结尾"
    assert "[[CHART:" not in out


def test_parse_writer_output_warns_on_index_mismatch(caplog):
    import logging

    with caplog.at_level(logging.WARNING, logger="services.writer_output"):
        md, charts = parse_writer_output({
            "markdown_content": "见图[[CHART:0]]与[[CHART:1]]",
            "embedded_charts": [
                {"type": "INVALID_TYPE", "data": []},
                {"type": "FLOW_DATA"},  # data 缺失
            ],
        })
    assert md == "见图[[CHART:0]]与[[CHART:1]]"
    assert charts == {}
    assert any("writer chart index mismatch" in r.message for r in caplog.records)


def test_writer_output_json_hint_forbids_gantt():
    hint = writer_output_json_hint()
    assert "不要输出 GANTT_DATA" in hint
    assert "GANTT_DATA/TIMELINE" not in hint
