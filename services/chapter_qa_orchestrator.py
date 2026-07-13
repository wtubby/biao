"""章节硬/软质检编排。"""

import logging
import re

from config import (
    MIN_DIGIT_RATIO,
    WORD_COUNT_MAX_RATIO,
    WORD_COUNT_MIN_RATIO,
)
from db.models import Project, TechOutline, TechRequirement
from llm.llm_client import call_llm_json
from llm.schemas import QAResult
from sqlalchemy.orm import Session
from prompts.qa_prompt import (
    build_qa_chat_messages,
    build_qa_user_prompt,
    sample_content_windows_for_qa,
)
from services.blind_bid_service import is_blind_bid
from services.chapter_generation_service import _count_chinese_chars, generate_summary
from services.chapter_review_errors import dump_review_errors, merge_review_errors
from services.project_meta import get_meta
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
    check_global_fact_consistency,
    check_heading_keyword_coverage,
    check_markdown_table_integrity,
    check_paragraph_opening_repetition,
    check_plan_key_points_coverage,
    check_scoring_coverage_in_content,
    check_stitch_cheat,
    check_template_residues,
    check_truncation_risk,
    split_keywords,
    trim_out_of_scope_content,
)
from services.response_matrix_service import matrix_issues_for_chapter
from services.writing_guidance import is_descriptive_chapter

logger = logging.getLogger(__name__)


def run_hard_qa(
    content: str,
    project: Project,
    requirements: list[TechRequirement],
    guidance: dict | None = None,
    chapter_title: str | None = None,
    other_leaf_titles: list[str] | None = None,
    *,
    allowed_standard_sources: str | None = None,
    content_plan: dict | None = None,
    facts_text: str | None = None,
    global_params: dict | None = None,
    prior_contents: list[str] | None = None,
) -> list[str]:
    errors: list[str] = []

    if other_leaf_titles:
        errors.extend(check_chapter_scope(content, chapter_title or "", other_leaf_titles))

    if project.duration_days:
        duration_mentions = re.findall(r"(\d+)\s*(天|日|日历天)", content)
        for num, _ in duration_mentions:
            if int(num) > project.duration_days * 2:
                errors.append(f"工期数字 {num} 与全局参数 {project.duration_days} 天偏差过大")

    digits = len(re.findall(r"\d", content))
    if (
        not is_descriptive_chapter(chapter_title)
        and len(content) > 500
        and digits / max(len(content) / 100, 1) < MIN_DIGIT_RATIO
    ):
        errors.append("内容密度不足：技术参数与数字偏少")

    errors.extend(check_template_residues(content))
    errors.extend(check_blind_bid_residues(content, enabled=is_blind_bid(project)))
    errors.extend(check_chart_renderability(content))
    errors.extend(check_ai_spacing(content))
    errors.extend(check_truncation_risk(content))
    errors.extend(check_descriptive_chapter_measures(content, chapter_title or ""))
    errors.extend(check_first_paragraph_repeats_title(content, chapter_title or ""))
    errors.extend(check_paragraph_opening_repetition(content))
    errors.extend(check_markdown_table_integrity(content))
    errors.extend(check_atomic_markdown_closure(content))
    errors.extend(check_ai_cliche_residues(content))
    domain = None
    if global_params and isinstance(global_params, dict):
        domain = global_params.get("engineering_domain")
    if not domain:
        from services.project_meta import get_meta
        domain = get_meta(project).get("engineering_domain")
    errors.extend(check_fabricated_standards(content, allowed_standard_sources, domain=domain))
    errors.extend(
        check_global_fact_consistency(
            content,
            facts_text=facts_text,
            global_params=global_params,
        )
    )
    errors.extend(check_cross_chapter_overlap(content, prior_contents))
    if content_plan and not is_descriptive_chapter(chapter_title):
        errors.extend(check_plan_key_points_coverage(content, content_plan.get("key_points")))

    # 评分覆盖进重试环（含刚性项实质性响应）
    if requirements and not is_descriptive_chapter(chapter_title):
        errors.extend(check_scoring_coverage_in_content(content, requirements))

    all_keywords: list[str] = []
    for req in requirements:
        all_keywords.extend(split_keywords(req.keyword))
        # mandatory / 刚性关键词已由 check_scoring_coverage_in_content 覆盖，避免重复报错

    unique_kw = list(dict.fromkeys(all_keywords))
    if unique_kw:
        errors.extend(check_heading_keyword_coverage(content, chapter_title or "", unique_kw))
        errors.extend(check_stitch_cheat(content, unique_kw))

    opens = len(re.findall(r"\[(GANTT|TIMELINE|FLOW|ORG|SMART)_DATA:", content, re.I))
    closes = content.count("]]") + content.count("}]")
    if opens > closes:
        errors.append("图表占位符未正确闭合")

    target_words = (guidance or {}).get("target_words")
    if target_words:
        actual = _count_chinese_chars(content)
        min_words = int(target_words * WORD_COUNT_MIN_RATIO)
        max_words = int(target_words * WORD_COUNT_MAX_RATIO)
        if actual < min_words:
            errors.append(f"篇幅不足：当前约 {actual} 字，目标 {target_words} 字（下限 {min_words}）")
        elif actual > max_words:
            errors.append(f"篇幅过长：当前约 {actual} 字，目标 {target_words} 字（上限 {max_words}）")

    # 去重保序
    seen: set[str] = set()
    unique_errors: list[str] = []
    for err in errors:
        if err not in seen:
            seen.add(err)
            unique_errors.append(err)
    return unique_errors


def _allowed_standard_sources(bundle: dict) -> str:
    parts = [
        bundle.get("retrieval_text") or "",
        bundle.get("global_facts_text") or "",
        bundle.get("requirements_text") or "",
        bundle.get("project_overview") or "",
        bundle.get("reference_bid_text") or "",
    ]
    params = bundle.get("global_params") or {}
    if isinstance(params, dict):
        parts.append(" ".join(str(v) for v in params.values() if v))
    return "\n".join(parts)


def _run_soft_qa_once(content: str, bundle: dict, *, segment_label: str | None = None) -> dict:
    return call_llm_json(
        build_qa_chat_messages(content, bundle, segment_label=segment_label),
        role="qa",
        schema=QAResult,
    )


def _prefix_issues(issues: list, label: str) -> list[str]:
    return [f"[{label}] {item}" for item in (issues or []) if item]


def run_soft_qa(content: str, bundle: dict) -> dict:
    """长文按头/中/尾分段抽检并合并问题；任一段 skipped 则整体 skipped。"""
    windows = sample_content_windows_for_qa(content)
    coverage: list[str] = []
    faithfulness: list[str] = []
    scope: list[str] = []
    specificity: list[str] = []
    any_failed = False
    try:
        for label, body in windows:
            segment_label = None if (len(windows) == 1 and label == "全文") else label
            result = _run_soft_qa_once(body, bundle, segment_label=segment_label)
            if result.get("skipped"):
                return {
                    "passed": False,
                    "skipped": True,
                    "skip_reason": result.get("skip_reason") or f"{label}抽检失败",
                    "coverage_issues": [],
                    "faithfulness_issues": [],
                    "scope_issues": [],
                    "specificity_issues": [],
                }
            if not result.get("passed", True):
                any_failed = True
            prefix = label if segment_label else ""
            if prefix:
                coverage.extend(_prefix_issues(result.get("coverage_issues"), prefix))
                faithfulness.extend(_prefix_issues(result.get("faithfulness_issues"), prefix))
                scope.extend(_prefix_issues(result.get("scope_issues"), prefix))
                specificity.extend(_prefix_issues(result.get("specificity_issues"), prefix))
            else:
                coverage.extend(result.get("coverage_issues") or [])
                faithfulness.extend(result.get("faithfulness_issues") or [])
                scope.extend(result.get("scope_issues") or [])
                specificity.extend(result.get("specificity_issues") or [])
        # 去重保序
        coverage = list(dict.fromkeys(coverage))
        faithfulness = list(dict.fromkeys(faithfulness))
        scope = list(dict.fromkeys(scope))
        specificity = list(dict.fromkeys(specificity))
        has_issues = bool(coverage or faithfulness or scope or specificity)
        return {
            "passed": not any_failed and not has_issues,
            "coverage_issues": coverage,
            "faithfulness_issues": faithfulness,
            "scope_issues": scope,
            "specificity_issues": specificity,
            "segments_checked": len(windows),
        }
    except Exception as exc:
        logger.warning("软质检失败: %s", exc)
        return {
            "passed": False,
            "skipped": True,
            "skip_reason": str(exc),
            "coverage_issues": [],
            "faithfulness_issues": [],
            "scope_issues": [],
            "specificity_issues": [],
        }


def _mark_chapter_failed(chapter: TechOutline, message: str) -> None:
    """生成异常时落库 red，避免卡在 generating。"""
    chapter.review_status = "red"
    chapter.review_errors = dump_review_errors([message])


def _apply_matrix_issues_to_chapter(
    db: Session,
    project: Project,
    chapter: TechOutline,
) -> None:
    """定稿前合并评分覆盖缺口。

    普通评分项缺口：green → yellow；
    刚性风险项缺口：直接打 red，导出拦截自动生效。
    """
    try:
        issues = matrix_issues_for_chapter(db, project, chapter)
    except Exception as exc:
        logger.warning("评分覆盖检查失败 chapter=%s: %s", chapter.id, exc)
        return
    if not issues:
        return
    chapter.review_errors = merge_review_errors(chapter.review_errors, issues)
    risk_issues = [i for i in issues if i.startswith("刚性风险项")]
    if risk_issues:
        chapter.review_status = "red"
    elif chapter.review_status == "green":
        chapter.review_status = "yellow"


def _soft_issue_list(soft: dict) -> list[str]:
    return (
        (soft.get("coverage_issues") or [])
        + (soft.get("faithfulness_issues") or [])
        + (soft.get("scope_issues") or [])
        + (soft.get("specificity_issues") or [])
    )


def run_segment_qa(
    content: str,
    project: Project,
    chapter: TechOutline,
    bundle: dict,
    *,
    segment_label: str,
    content_plan: dict | None = None,
) -> tuple[list[str], dict]:
    """分段撰写时的轻量质检：硬规则子集 + 单段软检。"""
    guidance = bundle.get("guidance") or {}
    other_titles = bundle.get("other_leaf_titles") or []
    hard_errors: list[str] = []

    if other_titles:
        hard_errors.extend(check_chapter_scope(content, chapter.title or "", other_titles))
    hard_errors.extend(check_template_residues(content))
    hard_errors.extend(check_chart_renderability(content))
    hard_errors.extend(check_ai_spacing(content))
    hard_errors.extend(check_markdown_table_integrity(content))
    hard_errors.extend(check_atomic_markdown_closure(content))
    hard_errors.extend(
        check_fabricated_standards(
            content,
            _allowed_standard_sources(bundle),
            domain=bundle.get("engineering_domain"),
        )
    )
    if content.strip().lstrip().startswith("#"):
        hard_errors.append("分段正文严禁输出 # 标题行")

    seen: set[str] = set()
    unique_hard: list[str] = []
    for err in hard_errors:
        if err not in seen:
            seen.add(err)
            unique_hard.append(err)
    if unique_hard:
        return unique_hard, {}

    seg_plan = content_plan if isinstance(content_plan, dict) else None
    if seg_plan and not is_descriptive_chapter(chapter.title):
        plan_errors = check_plan_key_points_coverage(
            content, seg_plan.get("key_points"),
        )
        if plan_errors:
            return plan_errors, {}

    soft = _run_soft_qa_once(content, bundle, segment_label=segment_label)
    return [], soft


def _apply_qa_result_to_chapter(
    chapter: TechOutline,
    content: str,
    *,
    hard_errors: list[str],
    soft: dict | None,
    refresh_summary: bool = True,
) -> None:
    """根据硬/软质检结果写回 review_status / review_errors / content。"""
    chapter.generated_content = content
    if hard_errors:
        chapter.review_status = "yellow"
        chapter.review_errors = dump_review_errors(hard_errors)
        return

    soft = soft or {}
    soft_issues = _soft_issue_list(soft)
    if soft.get("skipped"):
        chapter.review_status = "yellow"
        chapter.review_errors = dump_review_errors(
            [f"软质检未执行：{soft.get('skip_reason', '未知原因')}"]
        )
        if refresh_summary:
            chapter.last_summary = generate_summary(content)
        return
    if not soft.get("passed", True) and soft_issues:
        chapter.review_status = "yellow"
        chapter.review_errors = dump_review_errors(soft_issues)
        return

    chapter.review_status = "green"
    chapter.review_errors = None
    if refresh_summary:
        chapter.last_summary = generate_summary(content)


def _run_chapter_qa(
    content: str,
    project: Project,
    chapter: TechOutline,
    bundle: dict,
    *,
    content_plan: dict | None = None,
) -> tuple[list[str], dict]:
    guidance = bundle["guidance"]
    other_titles = bundle.get("other_leaf_titles") or []
    hard_errors = run_hard_qa(
        content,
        project,
        bundle["requirements"],
        guidance,
        chapter_title=chapter.title,
        other_leaf_titles=other_titles,
        allowed_standard_sources=_allowed_standard_sources(bundle),
        content_plan=content_plan,
        facts_text=bundle.get("global_facts_text"),
        global_params=bundle.get("global_params"),
        prior_contents=bundle.get("prior_contents"),
    )
    if hard_errors:
        return hard_errors, {}
    soft = run_soft_qa(content, bundle)
    return [], soft


