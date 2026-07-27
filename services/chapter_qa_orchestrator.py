"""章节硬/软质检编排。"""

import logging

from db.models import Project, TechOutline, TechRequirement
from llm.llm_client import call_llm_json
from llm.schemas import QAMultiWindowResult, QAResult
from prompts.qa_prompt import (
    build_qa_chat_messages,
    sample_content_windows_for_qa,
)
from services.chapter_generation_service import generate_summary
from services.chapter_review_errors import dump_review_errors
from services.check_registry import (
    ChapterCheckContext,
    findings_to_messages,
    run_chapter_checks,
)

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
    """章级硬质检：经 CheckSkill 注册表执行，返回兼容的字符串错误列表。"""
    findings = run_chapter_checks(
        ChapterCheckContext(
            content=content,
            project=project,
            requirements=requirements or [],
            guidance=guidance,
            chapter_title=chapter_title,
            other_leaf_titles=other_leaf_titles,
            allowed_standard_sources=allowed_standard_sources,
            content_plan=content_plan,
            facts_text=facts_text,
            global_params=global_params,
            prior_contents=prior_contents,
            scope="chapter",
        )
    )
    return findings_to_messages(findings)


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


def _merge_multi_window_soft_qa(raw: dict, *, window_count: int) -> dict:
    """将多窗结构化结果合并为与单窗一致的扁平 issues。"""
    segments = raw.get("segments") or []
    coverage: list[str] = []
    faithfulness: list[str] = []
    scope: list[str] = []
    specificity: list[str] = []
    any_failed = False
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        label = str(seg.get("label") or "").strip() or "片段"
        if not seg.get("passed", True):
            any_failed = True
        coverage.extend(_prefix_issues(seg.get("coverage_issues"), label))
        faithfulness.extend(_prefix_issues(seg.get("faithfulness_issues"), label))
        scope.extend(_prefix_issues(seg.get("scope_issues"), label))
        specificity.extend(_prefix_issues(seg.get("specificity_issues"), label))

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
        "segments_checked": window_count,
    }


def _run_soft_qa_multi(windows: list[tuple[str, str]], bundle: dict) -> dict:
    """长文多窗一次 LLM 调用，避免重复发送项目前缀。"""
    raw = call_llm_json(
        build_qa_chat_messages("", bundle, windows=windows),
        role="qa",
        schema=QAMultiWindowResult,
    )
    return _merge_multi_window_soft_qa(raw, window_count=len(windows))


def run_soft_qa(content: str, bundle: dict) -> dict:
    """长文头/中/尾多窗抽检；多窗合并为一次 LLM 调用。任一段失败则整体不通过。"""
    windows = sample_content_windows_for_qa(content)
    try:
        if len(windows) <= 1:
            label, body = windows[0] if windows else ("全文", "")
            segment_label = None if label == "全文" else label
            result = _run_soft_qa_once(body, bundle, segment_label=segment_label)
            if result.get("skipped"):
                return result
            coverage = list(result.get("coverage_issues") or [])
            faithfulness = list(result.get("faithfulness_issues") or [])
            scope = list(result.get("scope_issues") or [])
            specificity = list(result.get("specificity_issues") or [])
            if segment_label:
                coverage = _prefix_issues(coverage, segment_label)
                faithfulness = _prefix_issues(faithfulness, segment_label)
                scope = _prefix_issues(scope, segment_label)
                specificity = _prefix_issues(specificity, segment_label)
            has_issues = bool(coverage or faithfulness or scope or specificity)
            return {
                "passed": bool(result.get("passed", True)) and not has_issues,
                "coverage_issues": coverage,
                "faithfulness_issues": faithfulness,
                "scope_issues": scope,
                "specificity_issues": specificity,
                "segments_checked": 1,
            }

        return _run_soft_qa_multi(windows, bundle)
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
    """分段撰写时的轻量质检：注册表 segment 子集 + 单段软检。"""
    guidance = bundle.get("guidance") or {}
    other_titles = bundle.get("other_leaf_titles") or []
    global_params = dict(bundle.get("global_params") or {})
    if bundle.get("engineering_domain") and "engineering_domain" not in global_params:
        global_params["engineering_domain"] = bundle.get("engineering_domain")

    hard_errors = findings_to_messages(
        run_chapter_checks(
            ChapterCheckContext(
                content=content,
                project=project,
                requirements=bundle.get("requirements") or [],
                guidance=guidance,
                chapter_title=chapter.title,
                other_leaf_titles=other_titles,
                allowed_standard_sources=_allowed_standard_sources(bundle),
                content_plan=content_plan if isinstance(content_plan, dict) else None,
                global_params=global_params,
                scope="segment",
            )
        )
    )
    if hard_errors:
        return hard_errors, {}

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


