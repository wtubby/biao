"""context_blocks 单元测试。"""

from prompts.context_blocks import (
    format_generation_extras,
    format_scope_constraints,
)


def test_format_generation_extras_plan_and_writer_share_markdown_heading():
    bundle = {"chart_density_hint": "每章至少 1 张表"}
    plan = format_generation_extras(bundle, style="plan")
    writer = format_generation_extras(bundle, style="writer")
    assert plan == writer
    assert "## 图表要求" in plan
    assert "每章至少 1 张表" in plan


def test_format_generation_extras_qa_uses_inline_labels():
    bundle = {
        "chart_density_hint": "每章至少 1 张表",
        "standards_hint": "引用 GB 规范时写全称",
    }
    block = format_generation_extras(bundle, style="qa")
    assert block.startswith("\n")
    assert "图表要求：每章至少 1 张表" in block
    assert "写作惯例提示：引用 GB 规范时写全称" in block
    assert "## 图表要求" not in block


def test_format_generation_extras_strips_trailing_blank_lines_from_parts():
    bundle = {
        "chart_density_hint": "提示\n\n",
        "standards_hint": "惯例\n",
    }
    block = format_generation_extras(bundle, style="writer")
    assert "\n\n\n" not in block


def test_format_scope_constraints_uses_non_sibling_only_for_plan():
    bundle = {
        "sibling_leaf_titles": ["A", "B"],
        "other_leaf_titles": ["A", "B"],
    }
    block = format_scope_constraints(bundle, style="plan")
    assert "全书其他叶子：（无）" in block
    assert "同节兄弟：A、B" in block


def test_format_scope_constraints_writer_falls_back_chapter_title():
    block = format_scope_constraints({}, style="writer")
    assert "仅撰写「当前章节」正文" in block


def test_format_scope_constraints_writer_skips_other_leaves_when_all_siblings():
    bundle = {
        "chapter_title": "劳动力配置",
        "sibling_leaf_titles": ["A", "B"],
        "other_leaf_titles": ["A", "B"],
    }
    block = format_scope_constraints(bundle, style="writer")
    assert "劳动力配置" in block
    assert "全书其他叶子章节" not in block
