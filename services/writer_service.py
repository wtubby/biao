"""章节撰写门面：组装上下文 → 生成 → 质检 → 落库。"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from config import ENABLE_CONTENT_PLAN, MAX_QA_RETRY
from db.models import Project, TechOutline
from services.chapter_context_service import (
    _enrich_retrieval_with_plan,
    _init_key_chapter_messages,
    _is_key_chapter,
    build_context_bundle,
    group_leaves_by_section,
)
from services.chapter_generation_service import (
    _chunk_key_points,
    _should_segment_chapter,
    generate_chapter_content,
    resolve_content_plan,
)
from services.chapter_qa_orchestrator import (
    _apply_matrix_issues_to_chapter,
    _apply_qa_result_to_chapter,
    _mark_chapter_failed,
    _run_chapter_qa,
    _soft_issue_list,
    run_hard_qa,
    run_soft_qa,
)
from services.chapter_version_service import archive_chapter_snapshot
from services.generation_config import get_generation_config
from services.humanizer_service import humanize_content
from services.prompt_debug_service import capture_generation_prompt_debug
from services.qa_rules import normalize_ai_spacing, trim_out_of_scope_content
from services.chapter_review_errors import dump_review_errors

logger = logging.getLogger(__name__)


def write_and_qa_chapter(
    db: Session,
    project: Project,
    chapter: TechOutline,
    section_leaves: list[TechOutline] | None = None,
    chat_messages: list[dict] | None = None,
    entry_summary: str | None = None,
    use_section_summary_pool: bool = False,
) -> tuple[TechOutline, list[dict] | None, str | None]:
    retrieval_warning: str | None = None
    is_key = False
    messages = chat_messages
    try:
        if (chapter.generated_content or "").strip():
            archive_chapter_snapshot(db, chapter, "generate")
        bundle = build_context_bundle(
            db,
            project,
            chapter,
            section_leaves,
            entry_summary=entry_summary,
            use_section_summary_pool=use_section_summary_pool,
        )
        retrieval_warning = bundle.get("retrieval_warning")
        guidance = bundle["guidance"]
        is_key = _is_key_chapter(chapter, bundle["requirements"])
        messages = chat_messages
        if is_key and messages is None:
            messages = _init_key_chapter_messages(
                db, project, bundle["requirements"], bundle["all_nodes"]
            )

        if ENABLE_CONTENT_PLAN:
            plan = resolve_content_plan(bundle)
            if plan:
                target_words = guidance.get("target_words")
                if target_words:
                    plan["word_count_target"] = target_words
                chapter.content_plan = json.dumps(plan, ensure_ascii=False)
                bundle["content_plan"] = plan
                _enrich_retrieval_with_plan(bundle, project, chapter, db)

        fix_instructions: str | None = None
        content = ""

        for attempt in range(MAX_QA_RETRY + 1):
            chapter.prompt_debug = capture_generation_prompt_debug(
                bundle,
                chapter,
                fix_instructions=fix_instructions,
            )
            content, messages = generate_chapter_content(
                bundle,
                fix_instructions,
                chat_messages=messages,
                use_chat=is_key,
            )
            other_titles = bundle.get("other_leaf_titles") or []
            if other_titles:
                content = trim_out_of_scope_content(content, chapter.title, other_titles)
            deep = bool(get_generation_config(project).get("deep_humanize"))
            content = humanize_content(content, deep=deep)
            hard_errors, soft = _run_chapter_qa(
                content,
                project,
                chapter,
                bundle,
                content_plan=bundle.get("content_plan"),
            )

            if hard_errors:
                if attempt < MAX_QA_RETRY:
                    fix_instructions = "修复以下问题：\n" + "\n".join(hard_errors)
                    chapter.retry_count += 1
                    continue
                _apply_qa_result_to_chapter(
                    chapter, content, hard_errors=hard_errors, soft=None, refresh_summary=False,
                )
                break

            chapter.prompt_debug = capture_generation_prompt_debug(
                bundle,
                chapter,
                fix_instructions=fix_instructions,
                content_for_qa=content,
            )
            soft_issues = _soft_issue_list(soft)
            if soft.get("skipped"):
                _apply_qa_result_to_chapter(
                    chapter, content, hard_errors=[], soft=soft, refresh_summary=True,
                )
                chapter.generated_at = datetime.now(timezone.utc)
                break
            if not soft.get("passed", True) and soft_issues:
                if attempt < MAX_QA_RETRY:
                    fix_instructions = "修复以下问题：\n" + "\n".join(soft_issues)
                    chapter.retry_count += 1
                    continue
                _apply_qa_result_to_chapter(
                    chapter, content, hard_errors=[], soft=soft, refresh_summary=False,
                )
                break

            _apply_qa_result_to_chapter(
                chapter, content, hard_errors=[], soft=soft, refresh_summary=True,
            )
            chapter.generated_at = datetime.now(timezone.utc)
            break

        if chapter.review_status in ("green", "yellow") and (chapter.generated_content or "").strip():
            _apply_matrix_issues_to_chapter(db, project, chapter)

        db.commit()
        db.refresh(chapter)
        return chapter, messages if is_key else chat_messages, retrieval_warning
    except Exception as exc:
        logger.exception("章节生成失败 chapter=%s: %s", chapter.id, exc)
        _mark_chapter_failed(chapter, f"生成失败：{exc}")
        try:
            db.commit()
            db.refresh(chapter)
        except Exception:
            db.rollback()
        raise


def review_chapter_content(
    db: Session,
    project: Project,
    chapter: TechOutline,
    *,
    refresh_summary: bool = True,
) -> TechOutline:
    """对已有正文重新执行硬/软质检（人工修订、选区改写后验章放行）。"""
    content = (chapter.generated_content or "").strip()
    if not content:
        chapter.review_status = "red"
        chapter.review_errors = dump_review_errors(["章节正文为空"])
        db.commit()
        db.refresh(chapter)
        return chapter

    # 与生成链路一致：先清全角/连续空格，避免粘贴排版残留卡死验章
    content = normalize_ai_spacing(content)

    bundle = build_context_bundle(db, project, chapter)
    plan = None
    if chapter.content_plan:
        try:
            parsed_plan = json.loads(chapter.content_plan)
            if isinstance(parsed_plan, dict):
                plan = parsed_plan
        except json.JSONDecodeError:
            plan = None

    hard_errors, soft = _run_chapter_qa(
        content, project, chapter, bundle, content_plan=plan,
    )
    _apply_qa_result_to_chapter(
        chapter,
        content,
        hard_errors=hard_errors,
        soft=soft,
        refresh_summary=refresh_summary,
    )

    if chapter.review_status in ("green", "yellow") and content:
        _apply_matrix_issues_to_chapter(db, project, chapter)

    db.commit()
    db.refresh(chapter)
    return chapter

# 向后兼容：子模块公开 API 重导出
from services.chapter_context_service import (  # noqa: E402
    build_context_bundle,
    group_leaves_by_section,
)
from services.chapter_generation_service import (  # noqa: E402
    _chunk_key_points,
    _should_segment_chapter,
    estimate_chapter_max_tokens,
    generate_chapter_content,
    generate_summary,
    resolve_content_plan,
)
from services.chapter_qa_orchestrator import run_hard_qa, run_soft_qa  # noqa: E402
