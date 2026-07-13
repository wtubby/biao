"""质检规则单元测试。"""

from services.qa_rules import (
    check_ai_spacing,
    check_chapter_scope,
    check_chart_renderability,
    check_descriptive_chapter_measures,
    check_first_paragraph_repeats_title,
    check_mandatory_elements,
    check_markdown_table_integrity,
    check_paragraph_opening_repetition,
    check_stitch_cheat,
    check_template_residues,
    check_truncation_risk,
    extract_coverage_candidates,
    normalize_for_match,
    trim_out_of_scope_content,
)


from services.writing_guidance import get_chapter_type, is_goal_chapter, is_overview_chapter


def test_is_goal_chapter():
    assert is_goal_chapter("项目目标（质量、工期、造价）")
    assert is_goal_chapter("质量目标")
    assert not is_goal_chapter("质量保证措施")
    assert not is_goal_chapter("施工组织设计")


def test_is_overview_chapter():
    assert is_overview_chapter("项目特点")
    assert is_overview_chapter("工程概况")
    assert is_overview_chapter("（一）工程概况与项目特点")
    assert not is_overview_chapter("施工组织设计")
    assert not is_overview_chapter("针对难点的施工方案")


def test_check_descriptive_chapter_measures_overview():
    text = "本工程位于山区。针对上述特点，我方将采取专项施工方案。"
    errs = check_descriptive_chapter_measures(text, "项目特点")
    assert errs and ("我方将" in errs[0] or "专项方案" in errs[0])


def test_check_descriptive_chapter_measures_detects_measures():
    text = "质量目标：合格。具体措施如下：建立质量管理体系。"
    errs = check_descriptive_chapter_measures(text, "质量目标")
    assert errs and "具体措施" in errs[0]


def test_check_descriptive_chapter_measures_ignores_non_goal_chapter():
    text = "具体措施如下：建立质量管理体系。"
    assert not check_descriptive_chapter_measures(text, "质量保证措施")


def test_normalize_for_match_strips_punctuation():
    assert normalize_for_match("施工方案（20分）") == "施工方案20分"


def test_extract_coverage_candidates_dedup():
    cands = extract_coverage_candidates("施工组织设计（15分）", "施工,组织")
    assert "施工组织设计（15分）" in cands
    assert len(cands) >= 2


def test_check_template_residues_detects_todo():
    errs = check_template_residues("本项目由XXX公司承建，TODO 待补充")
    assert any("TODO" in e or "模板残留" in e for e in errs)


def test_check_mandatory_elements_missing():
    errs = check_mandatory_elements("仅描述概况", "主变,GIS,电缆")
    assert errs and "主变" in errs[0]


def test_check_mandatory_elements_accepts_compliance_synonym():
    content = "本总体实施方案完全响应竞争性谈判文件各项要求，并据此编制。"
    assert check_mandatory_elements(content, "满足竞争性谈判文件要求") == []


def test_check_mandatory_elements_accepts_normalized_punctuation():
    content = "落实三级网络计划，并执行周报制度。"
    assert check_mandatory_elements(content, "三级网络计划、周报制度") == []


def test_heading_keyword_coverage_accepts_core_variant_and_cn_heading():
    from services.qa_rules import check_heading_keyword_coverage

    content = "一、进度保障措施\n工期节点受控。\n（二）质量保障\n落实三级质检。"
    errs = check_heading_keyword_coverage(
        content,
        "总体实施方案",
        ["工程进度保障", "工程质量保障", "工程安全保障", "方案其他评价"],
    )
    assert errs == []


def test_check_stitch_cheat_detects_keyword_stacking():
    text = "# 施工质量安全管理措施风险制度标准方法"
    errs = check_stitch_cheat(text, ["施工", "质量", "安全", "管理", "措施"])
    assert errs


def test_check_chapter_scope_detects_other_chapter_heading():
    content = "# 主变安装\n正文\n## 电缆敷设方案\n越界内容"
    errs = check_chapter_scope(content, "GIS安装", ["主变安装", "电缆敷设", "GIS安装"])
    assert errs
    assert any("电缆敷设" in e for e in errs)


def test_trim_out_of_scope_content_truncates_at_other_heading():
    content = "主变就位工序说明。\n# 电缆敷设方案\n越界内容"
    trimmed = trim_out_of_scope_content(content, "主变安装", ["电缆敷设", "GIS安装"])
    assert "主变就位" in trimmed
    assert "越界" not in trimmed


def test_trim_out_of_scope_content_truncates_at_numbered_heading():
    """编号式标题（无 #）也应截断，与 check_chapter_scope 标准一致。"""
    content = "主变就位工序说明。\n3.3 电缆敷设方案\n越界内容不应保留"
    trimmed = trim_out_of_scope_content(content, "主变安装", ["电缆敷设", "GIS安装"])
    assert "主变就位" in trimmed
    assert "越界" not in trimmed
    assert "3.3" not in trimmed
    # 截断后不应再被 scope 硬错误命中
    assert not check_chapter_scope(trimmed, "主变安装", ["电缆敷设", "GIS安装"])


def test_check_truncation_risk_detects_dangling_comma():
    assert check_truncation_risk("本章施工方案包括基础开挖、设备就位、")


def test_check_truncation_risk_passes_normal_ending():
    assert not check_truncation_risk("本章施工方案包括基础开挖、设备就位等工序。")


def test_check_truncation_risk_passes_markdown_table_ending():
    """正文以 Markdown 表格行收尾不应误判为截断。"""
    table = (
        "| 工序 | 时间 | 负责人 |\n"
        "| --- | --- | --- |\n"
        "| 基础开挖 | 6-10日 | 张三 |\n"
        "| 主体施工 | 6-20日 | 李四 |"
    )
    assert not check_truncation_risk(table)
    padded = ("本章进度安排说明。" * 20) + "\n\n" + table
    assert len(padded) > 200
    assert not check_truncation_risk(padded)


def test_check_ai_spacing_ignores_aligned_markdown_table():
    """表格列宽对齐空格不应触发连续半角空格硬错误。"""
    sample = (
        "进度安排如下。\n\n"
        "| 工序     | 起止时间 | 负责人 |\n"
        "|----------|----------|--------|\n"
        "| 基础开挖 | 1-5日    | 张三   |\n"
        "| 主体施工 | 6-20日   | 李四   |\n"
    )
    assert "存在连续多个半角空格" not in check_ai_spacing(sample)


def test_check_ai_spacing_flags_body_double_spaces():
    assert "存在连续多个半角空格" in check_ai_spacing("本工程  采用专项方案。")


def test_check_chart_renderability_flags_missing_graphviz(monkeypatch):
    content = '[FLOW_DATA: [{"from":"A","to":"B"}]]'
    monkeypatch.setattr("services.env_check.check_graphviz", lambda: False)
    errors = check_chart_renderability(content)
    assert errors
    assert "Graphviz" in errors[0]


def test_check_first_paragraph_repeats_title():
    content = "施工组织设计\n\n本工程采用专项施工方案。"
    errs = check_first_paragraph_repeats_title(content, "施工组织设计")
    assert errs
    assert "首段不应重复" in errs[0]


def test_check_first_paragraph_repeats_title_allows_normal_opening():
    content = "本工程施工组织设计围绕现场条件展开，重点说明工序安排。"
    assert not check_first_paragraph_repeats_title(content, "施工组织设计")


def test_check_paragraph_opening_repetition_detects_three_same_openings():
    content = "\n\n".join([
        "本工程采用标准化施工工艺，完成基础施工。",
        "本工程采用专项吊装方案，完成设备安装。",
        "本工程采用分区流水作业，完成电缆敷设。",
    ])
    errs = check_paragraph_opening_repetition(content)
    assert errs
    assert "连续 3 段" in errs[0]


def test_check_markdown_table_integrity_flags_column_mismatch():
    content = (
        "| 项目 | 参数 |\n"
        "| --- | --- |\n"
        "| 主变 | 180MVA | 2台 |\n"
    )
    errs = check_markdown_table_integrity(content)
    assert errs
    assert "列数不一致" in errs[0]


def test_check_markdown_table_integrity_flags_empty_row():
    content = (
        "| 项目 | 参数 |\n"
        "| --- | --- |\n"
        "|  |  |\n"
    )
    errs = check_markdown_table_integrity(content)
    assert errs
    assert "空行" in errs[0]


def test_check_fabricated_standards_flags_unknown_code():
    from services.qa_rules import check_fabricated_standards

    content = "施工按 GB/T 99999-2099 执行，并引用 DL/T 88888。"
    errs = check_fabricated_standards(content, allowed_sources="仅含一般工艺说明")
    assert errs
    assert "编造" in errs[0]


def test_check_fabricated_standards_allows_source_and_common():
    from services.qa_rules import check_fabricated_standards

    content = "电缆敷设执行 GB 50168，并按招标文件 DL/T 5168 验收。"
    errs = check_fabricated_standards(
        content,
        allowed_sources="招标要求引用 DL/T 5168-2002",
    )
    assert not errs


def test_check_fabricated_standards_detects_municipal_cjj():
    """市政 CJJ 前缀须能被识别，否则编造规范会漏检。"""
    from services.qa_rules import check_fabricated_standards, extract_standard_codes

    content = "道路基层施工执行 CJJ 1-2008，并引用 CJJ/T 99999-2099。"
    assert any("CJJ" in c.upper() for c in extract_standard_codes(content))
    errs = check_fabricated_standards(
        content,
        allowed_sources="仅含一般工艺说明",
        domain="市政工程",
    )
    assert errs
    assert "编造" in errs[0]
    assert "CJJ" in errs[0].upper()


def test_check_plan_key_points_coverage_insufficient():
    from services.qa_rules import check_plan_key_points_coverage

    errs = check_plan_key_points_coverage(
        "本章仅概述一般管理要求。",
        ["主变吊装双机抬吊", "GIS 交接试验", "电缆耐压试验", "接地网测试"],
    )
    assert errs
    assert "要点覆盖不足" in errs[0]


def test_check_plan_key_points_coverage_ok():
    from services.qa_rules import check_plan_key_points_coverage

    content = "主变吊装采用双机抬吊。GIS 完成交接试验。电缆进行耐压试验。接地网测试合格。"
    assert not check_plan_key_points_coverage(
        content,
        ["主变吊装双机抬吊", "GIS 交接试验", "电缆耐压试验", "接地网测试"],
    )


def test_check_ai_cliche_residues():
    from services.qa_rules import check_ai_cliche_residues

    errs = check_ai_cliche_residues("综上所述，本工程具有重要意义。")
    assert errs
    assert "套话" in errs[0]
