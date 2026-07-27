"""内置检查 Skill：包装现有 qa_rules / compliance 规则，并新增废标条款对照。"""

from __future__ import annotations

import re
from typing import Any

from services.check_registry import (
    ChapterCheckContext,
    Finding,
    ProjectCheckContext,
    CheckSkill,
    register_check,
    wrap_message_check,
)
from services.qa_rules import (
    check_ai_cliche_residues,
    check_ai_spacing,
    check_atomic_markdown_closure,
    check_blind_bid_residues,
    check_chart_renderability,
    check_chapter_scope,
    check_cross_chapter_overlap,
    check_descriptive_chapter_measures,
    check_fabricated_standards,
    check_first_paragraph_repeats_title,
    check_font_safety,
    check_global_fact_consistency,
    check_heading_keyword_coverage,
    check_markdown_table_integrity,
    check_opening_pattern_overuse,
    check_paragraph_opening_repetition,
    check_plan_key_points_coverage,
    check_scoring_coverage_in_content,
    check_stitch_cheat,
    check_template_residues,
    check_truncation_risk,
    split_keywords,
)
from services.writing_guidance import is_descriptive_chapter

_REGISTERED = False

# 废标条款中与技术标正文相关的触发词
_TECH_DISQUAL_HINTS = (
    "实质性",
    "负偏离",
    "未响应",
    "漏项",
    "缺项",
    "暗标",
    "雷同",
    "抄袭",
    "虚假",
    "技术偏离",
    "不满足",
    "低于要求",
    "未提供",
    "未盖章",
    "正本",
    "副本",
    "密封",
    "投标有效期",
    "保证金",
)

# 正文中可自动核验的风险模式（命中则 escalate）
_AUTO_RISK_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("template", re.compile(r"(XXX|xxx|【待|TODO|<甲方|<乙方|\[投标人)"), "疑似模板/占位残留，对照废标条款"),
    ("identity", re.compile(r"(本公司|我公司|我单位).{0,8}(中标|中选)"), "疑似承诺性身份表述，暗标/废标风险"),
]


def register_builtin_checks() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    _register_chapter_checks()
    _register_project_checks()
    _REGISTERED = True


def _register_chapter_checks() -> None:
    @wrap_message_check("chapter_scope", "scope", scopes=("chapter", "segment"))
    def _scope(ctx: ChapterCheckContext) -> list[str]:
        if not ctx.other_leaf_titles:
            return []
        return check_chapter_scope(ctx.content, ctx.chapter_title or "", ctx.other_leaf_titles)

    @wrap_message_check("duration_number", "fact_consistency", scopes=("chapter",))
    def _duration(ctx: ChapterCheckContext) -> list[str]:
        errors: list[str] = []
        duration = getattr(ctx.project, "duration_days", None)
        if not duration:
            return errors
        for num, _ in re.findall(r"(\d+)\s*(天|日|日历天)", ctx.content):
            if int(num) > duration * 2:
                errors.append(f"工期数字 {num} 与全局参数 {duration} 天偏差过大")
        return errors

    @wrap_message_check("digit_density", "digit_density", scopes=("chapter",))
    def _digits(ctx: ChapterCheckContext) -> list[str]:
        from config import MIN_DIGIT_RATIO

        if is_descriptive_chapter(ctx.chapter_title):
            return []
        if len(ctx.content) <= 500:
            return []
        digits = len(re.findall(r"\d", ctx.content))
        if digits / max(len(ctx.content) / 100, 1) < MIN_DIGIT_RATIO:
            return ["内容密度不足：技术参数与数字偏少"]
        return []

    @wrap_message_check(
        "template_residue",
        "template_residue",
        severity="block",
        scopes=("chapter", "segment"),
    )
    def _template(ctx: ChapterCheckContext) -> list[str]:
        return check_template_residues(ctx.content)

    @wrap_message_check("blind_bid", "blind_bid", severity="block", scopes=("chapter",))
    def _blind(ctx: ChapterCheckContext) -> list[str]:
        from services.blind_bid_service import is_blind_bid

        return check_blind_bid_residues(ctx.content, enabled=is_blind_bid(ctx.project))

    @wrap_message_check("chart_render", "chart_integrity", scopes=("chapter", "segment"))
    def _chart(ctx: ChapterCheckContext) -> list[str]:
        return check_chart_renderability(ctx.content)

    @wrap_message_check("ai_spacing", "writing_quality", scopes=("chapter", "segment"))
    def _spacing(ctx: ChapterCheckContext) -> list[str]:
        return check_ai_spacing(ctx.content)

    @wrap_message_check("truncation", "truncation", scopes=("chapter",))
    def _trunc(ctx: ChapterCheckContext) -> list[str]:
        return check_truncation_risk(ctx.content)

    @wrap_message_check("descriptive_measures", "writing_quality", scopes=("chapter",))
    def _desc(ctx: ChapterCheckContext) -> list[str]:
        return check_descriptive_chapter_measures(ctx.content, ctx.chapter_title or "")

    @wrap_message_check("first_para_title", "writing_quality", scopes=("chapter",))
    def _first(ctx: ChapterCheckContext) -> list[str]:
        return check_first_paragraph_repeats_title(ctx.content, ctx.chapter_title or "")

    @wrap_message_check("para_opening", "writing_quality", scopes=("chapter",))
    def _opening(ctx: ChapterCheckContext) -> list[str]:
        return check_paragraph_opening_repetition(ctx.content)

    @wrap_message_check("opening_pattern", "writing_quality", scopes=("chapter",))
    def _pattern(ctx: ChapterCheckContext) -> list[str]:
        return check_opening_pattern_overuse(ctx.content)

    @wrap_message_check("markdown_table", "table_integrity", scopes=("chapter", "segment"))
    def _table(ctx: ChapterCheckContext) -> list[str]:
        return check_markdown_table_integrity(ctx.content)

    @wrap_message_check("atomic_md", "table_integrity", scopes=("chapter", "segment"))
    def _atomic(ctx: ChapterCheckContext) -> list[str]:
        return check_atomic_markdown_closure(ctx.content)

    @wrap_message_check("ai_cliche", "ai_cliche", scopes=("chapter",))
    def _cliche(ctx: ChapterCheckContext) -> list[str]:
        return check_ai_cliche_residues(ctx.content)

    @wrap_message_check(
        "fabricated_standards",
        "fabricated_standards",
        severity="block",
        scopes=("chapter", "segment"),
    )
    def _standards(ctx: ChapterCheckContext) -> list[str]:
        domain = None
        if ctx.global_params and isinstance(ctx.global_params, dict):
            domain = ctx.global_params.get("engineering_domain")
        if not domain:
            from services.project_meta import get_meta

            domain = get_meta(ctx.project).get("engineering_domain")
        return check_fabricated_standards(
            ctx.content, ctx.allowed_standard_sources, domain=domain
        )

    @wrap_message_check("fact_consistency", "fact_consistency", scopes=("chapter",))
    def _facts(ctx: ChapterCheckContext) -> list[str]:
        return check_global_fact_consistency(
            ctx.content,
            facts_text=ctx.facts_text,
            global_params=ctx.global_params,
        )

    @wrap_message_check("cross_chapter", "cross_chapter", scopes=("chapter",))
    def _cross(ctx: ChapterCheckContext) -> list[str]:
        return check_cross_chapter_overlap(ctx.content, ctx.prior_contents)

    @wrap_message_check("plan_coverage", "plan_coverage", scopes=("chapter", "segment"))
    def _plan(ctx: ChapterCheckContext) -> list[str]:
        if not ctx.content_plan or is_descriptive_chapter(ctx.chapter_title):
            return []
        return check_plan_key_points_coverage(ctx.content, ctx.content_plan.get("key_points"))

    @wrap_message_check("scoring_coverage", "scoring_coverage", scopes=("chapter",))
    def _scoring(ctx: ChapterCheckContext) -> list[str]:
        if not ctx.requirements or is_descriptive_chapter(ctx.chapter_title):
            return []
        return check_scoring_coverage_in_content(ctx.content, ctx.requirements)

    @wrap_message_check("heading_keywords", "title_keywords", scopes=("chapter",))
    def _heading_kw(ctx: ChapterCheckContext) -> list[str]:
        all_keywords: list[str] = []
        for req in ctx.requirements or []:
            all_keywords.extend(split_keywords(getattr(req, "keyword", None)))
        unique_kw = list(dict.fromkeys(all_keywords))
        if not unique_kw:
            return []
        return check_heading_keyword_coverage(
            ctx.content, ctx.chapter_title or "", unique_kw
        )

    @wrap_message_check("stitch_cheat", "writing_quality", scopes=("chapter",))
    def _stitch(ctx: ChapterCheckContext) -> list[str]:
        all_keywords: list[str] = []
        for req in ctx.requirements or []:
            all_keywords.extend(split_keywords(getattr(req, "keyword", None)))
        unique_kw = list(dict.fromkeys(all_keywords))
        if not unique_kw:
            return []
        return check_stitch_cheat(ctx.content, unique_kw)

    @wrap_message_check("chart_closure", "chart_integrity", scopes=("chapter",))
    def _chart_close(ctx: ChapterCheckContext) -> list[str]:
        opens = len(re.findall(r"\[(GANTT|TIMELINE|FLOW|ORG|SMART)_DATA:", ctx.content, re.I))
        closes = ctx.content.count("]]") + ctx.content.count("}]")
        if opens > closes:
            return ["图表占位符未正确闭合"]
        return []

    @wrap_message_check("word_count", "word_count", scopes=("chapter",))
    def _words(ctx: ChapterCheckContext) -> list[str]:
        from config import WORD_COUNT_MAX_RATIO, WORD_COUNT_MIN_RATIO
        from services.chapter_generation_service import _count_chinese_chars

        target_words = (ctx.guidance or {}).get("target_words")
        if not target_words:
            return []
        actual = _count_chinese_chars(ctx.content)
        min_words = int(target_words * WORD_COUNT_MIN_RATIO)
        max_words = int(target_words * WORD_COUNT_MAX_RATIO)
        if actual < min_words:
            return [f"篇幅不足：当前约 {actual} 字，目标 {target_words} 字（下限 {min_words}）"]
        if actual > max_words:
            return [f"篇幅过长：当前约 {actual} 字，目标 {target_words} 字（上限 {max_words}）"]
        return []

    @wrap_message_check(
        "segment_no_heading",
        "writing_quality",
        scopes=("segment",),
    )
    def _seg_heading(ctx: ChapterCheckContext) -> list[str]:
        if ctx.content.strip().lstrip().startswith("#"):
            return ["分段正文严禁输出 # 标题行"]
        return []

    # 避免未使用告警：装饰器已注册
    _ = (
        _scope,
        _duration,
        _digits,
        _template,
        _blind,
        _chart,
        _spacing,
        _trunc,
        _desc,
        _first,
        _opening,
        _pattern,
        _table,
        _atomic,
        _cliche,
        _standards,
        _facts,
        _cross,
        _plan,
        _scoring,
        _heading_kw,
        _stitch,
        _chart_close,
        _words,
        _seg_heading,
    )


def _register_project_checks() -> None:
    def _run_template(ctx: ProjectCheckContext) -> list[Finding]:
        msgs = check_template_residues(ctx.docx_text)
        return [
            Finding(
                check_id="project_template_residue",
                category="template_residue",
                severity="block",
                message=m,
            )
            for m in msgs
        ]

    def _run_scoring(ctx: ProjectCheckContext) -> list[Finding]:
        from services.compliance_service import check_scoring_coverage

        findings: list[Finding] = []
        for row in check_scoring_coverage(ctx.docx_text, ctx.requirements):
            status = row.get("status")
            if status == "covered":
                continue
            sev = "block" if status == "missing" else "warn"
            findings.append(
                Finding(
                    check_id="project_scoring_coverage",
                    category="scoring_coverage",
                    severity=sev,
                    message=f"{row.get('title')}（{status}）",
                    evidence=", ".join(row.get("matched") or []),
                )
            )
        return findings

    def _run_substantial(ctx: ProjectCheckContext) -> list[Finding]:
        from services.compliance_service import check_substantial_response

        findings: list[Finding] = []
        for row in check_substantial_response(ctx.docx_text, ctx.requirements):
            if row.get("responded"):
                continue
            findings.append(
                Finding(
                    check_id="project_substantial_response",
                    category="substantial_response",
                    severity="warn",
                    message=f"刚性项未检出实质性响应：{row.get('title')}",
                    evidence=row.get("evidence") or "",
                )
            )
        return findings

    def _run_title_kw(ctx: ProjectCheckContext) -> list[Finding]:
        from services.compliance_service import check_title_keywords_from_outline

        findings: list[Finding] = []
        for row in check_title_keywords_from_outline(ctx.chapters, ctx.requirements):
            findings.append(
                Finding(
                    check_id="project_title_keywords",
                    category="title_keywords",
                    severity="warn",
                    message=(
                        f"章节「{row.get('chapter')}」标题缺关键词："
                        f"{', '.join(row.get('missing_keywords') or [])}"
                    ),
                )
            )
        return findings

    def _run_mandatory(ctx: ProjectCheckContext) -> list[Finding]:
        from services.compliance_service import check_mandatory_elements_doc

        findings: list[Finding] = []
        for row in check_mandatory_elements_doc(ctx.docx_text, ctx.requirements):
            findings.append(
                Finding(
                    check_id="project_mandatory",
                    category="mandatory_coverage",
                    severity="warn",
                    message=(
                        f"{row.get('title')} 缺必备要素："
                        f"{', '.join(row.get('missing') or [])}"
                    ),
                )
            )
        return findings

    def _run_length(ctx: ProjectCheckContext) -> list[Finding]:
        from services.compliance_service import check_chapter_length_balance

        return [
            Finding(
                check_id="project_length_balance",
                category="length_balance",
                severity="warn",
                message=row.get("message") or "",
            )
            for row in check_chapter_length_balance(ctx.chapters)
            if row.get("message")
        ]

    def _run_font(ctx: ProjectCheckContext) -> list[Finding]:
        if not ctx.docx_path:
            return []
        path = ctx.docx_path
        if hasattr(path, "exists") and not path.exists():
            return []
        return [
            Finding(
                check_id="project_font_safety",
                category="font_safety",
                severity="warn",
                message=msg,
            )
            for msg in check_font_safety(path)
        ]

    def _run_cross(ctx: ProjectCheckContext) -> list[Finding]:
        from services.compliance_service import check_cross_consistency

        findings: list[Finding] = []
        for row in check_cross_consistency(ctx.project, ctx.docx_text, ctx.meta):
            level = row.get("level")
            if level == "pass":
                continue
            findings.append(
                Finding(
                    check_id="project_cross_consistency",
                    category="fact_consistency",
                    severity="block" if level == "fail" else "warn",
                    message=row.get("message") or "",
                )
            )
        return findings

    def _run_disqualification(ctx: ProjectCheckContext) -> list[Finding]:
        return check_disqualification_risks(ctx.docx_text, ctx.qualification_items)

    register_check(
        CheckSkill(
            check_id="project_template_residue",
            category="template_residue",
            severity="block",
            scopes=("project",),
            run_project=_run_template,
        )
    )
    register_check(
        CheckSkill(
            check_id="project_scoring_coverage",
            category="scoring_coverage",
            severity="block",
            scopes=("project",),
            run_project=_run_scoring,
        )
    )
    register_check(
        CheckSkill(
            check_id="project_substantial_response",
            category="substantial_response",
            severity="warn",
            scopes=("project",),
            run_project=_run_substantial,
        )
    )
    register_check(
        CheckSkill(
            check_id="project_title_keywords",
            category="title_keywords",
            severity="warn",
            scopes=("project",),
            run_project=_run_title_kw,
        )
    )
    register_check(
        CheckSkill(
            check_id="project_mandatory",
            category="mandatory_coverage",
            severity="warn",
            scopes=("project",),
            run_project=_run_mandatory,
        )
    )
    register_check(
        CheckSkill(
            check_id="project_length_balance",
            category="length_balance",
            severity="warn",
            scopes=("project",),
            run_project=_run_length,
        )
    )
    register_check(
        CheckSkill(
            check_id="project_font_safety",
            category="font_safety",
            severity="warn",
            scopes=("project",),
            run_project=_run_font,
        )
    )
    register_check(
        CheckSkill(
            check_id="project_cross_consistency",
            category="fact_consistency",
            severity="warn",
            scopes=("project",),
            run_project=_run_cross,
        )
    )
    register_check(
        CheckSkill(
            check_id="project_disqualification",
            category="disqualification_risk",
            severity="warn",
            scopes=("project",),
            run_project=_run_disqualification,
            description="招标废标条款与正文风险对照",
        )
    )


def check_disqualification_risks(
    docx_text: str,
    qualification_items: list[dict[str, Any]] | None,
) -> list[Finding]:
    """对照招标废标项：技术相关条款列入核对清单，命中正文风险模式则升级。"""
    items = qualification_items or []
    if not items:
        return []

    text = docx_text or ""
    findings: list[Finding] = []
    tech_items = []
    for item in items:
        label = str(item.get("item_label") or "")
        desc = str(item.get("description") or item.get("source_text") or "")
        blob = f"{label} {desc}"
        if any(h in blob for h in _TECH_DISQUAL_HINTS):
            tech_items.append(item)

    # 无技术相关废标项时不报噪
    scan_items = tech_items or items[:8]

    auto_hits: list[str] = []
    for _key, pattern, msg in _AUTO_RISK_PATTERNS:
        if pattern.search(text):
            auto_hits.append(msg)

    for item in scan_items:
        seq = item.get("seq")
        label = str(item.get("item_label") or "废标项").strip()
        desc = str(item.get("description") or item.get("source_text") or "").strip()
        short = desc if len(desc) <= 80 else desc[:77] + "…"
        related_hit = any(h in f"{label} {desc}" for h in _TECH_DISQUAL_HINTS)

        if auto_hits and related_hit:
            findings.append(
                Finding(
                    check_id="project_disqualification",
                    category="disqualification_risk",
                    severity="block",
                    message=f"废标条款「{label}」存在正文风险：{auto_hits[0]}",
                    evidence=short,
                )
            )
        else:
            findings.append(
                Finding(
                    check_id="project_disqualification",
                    category="disqualification_risk",
                    severity="info" if not related_hit else "warn",
                    message=f"请人工核对废标条款#{seq}「{label}」：{short}",
                    evidence=desc,
                )
            )
    return findings
