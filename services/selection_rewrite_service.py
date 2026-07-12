from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from db.models import Project, TechOutline
from llm.llm_client import call_llm_text
from prompts.selection_rewrite_prompt import (
    get_selection_rewrite_system_prompt,
    build_selection_rewrite_user_prompt,
)
from services.chapter_version_service import archive_chapter_snapshot
from services.humanizer_service import humanize_content
from services.project_meta import get_meta
from services.writer_service import review_chapter_content

_CONTEXT_CHARS = 600


def rewrite_selection(
    chapter: TechOutline,
    project: Project,
    selected_text: str,
    instruction: str,
    context_before: str = "",
    context_after: str = "",
) -> str:
    chapter_line = chapter.title
    if project.voltage_level:
        chapter_line += f"（工程电压等级：{project.voltage_level}）"
    user_prompt = build_selection_rewrite_user_prompt(
        chapter_title=chapter_line,
        selected_text=selected_text,
        instruction=instruction,
        context_before=(context_before or "")[-_CONTEXT_CHARS:],
        context_after=(context_after or "")[:_CONTEXT_CHARS],
    )
    domain = get_meta(project).get("engineering_domain")
    raw = call_llm_text(
        [
            {"role": "system", "content": get_selection_rewrite_system_prompt(domain)},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=2048,
        timeout=90.0,
    )
    new_text = raw.strip()
    if new_text.startswith("```"):
        lines = new_text.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        new_text = "\n".join(lines).strip()
    return humanize_content(new_text)


def apply_selection_rewrite(
    db: Session,
    chapter: TechOutline,
    project: Project,
    *,
    selected_text: str,
    instruction: str,
    context_before: str = "",
    context_after: str = "",
    selection_start: int | None = None,
    selection_end: int | None = None,
) -> tuple[TechOutline, str, str]:
    """校验选区、改写、落库并验章。返回 (chapter, original_text, new_text)。"""
    if chapter.is_leaf != 1:
        raise HTTPException(400, "仅支持对叶子章节进行选区改写")

    selected = (selected_text or "").strip()
    instr = (instruction or "").strip()
    if not selected:
        raise HTTPException(400, "请先选中要改写的文本")
    if not instr:
        raise HTTPException(400, "请填写改写指令")
    if len(selected) > 8000:
        raise HTTPException(400, "选中文本过长，请缩小选区后重试")

    full_content = chapter.generated_content or ""
    if selection_start is not None and selection_end is not None:
        start, end = selection_start, selection_end
        if 0 <= start < end <= len(full_content):
            actual = full_content[start:end]
            if actual.strip() != selected.strip():
                raise HTTPException(400, "选区与正文不一致，请重新选中后重试")
        else:
            raise HTTPException(400, "选区位置无效，请重新选中后重试")
    elif selected not in full_content:
        raise HTTPException(400, "选中文本与当前章节正文不匹配，请重新选中")

    new_text = rewrite_selection(
        chapter,
        project,
        selected_text=selected,
        instruction=instr,
        context_before=context_before or "",
        context_after=context_after or "",
    )

    if selection_start is not None and selection_end is not None:
        updated_content = full_content[:selection_start] + new_text + full_content[selection_end:]
    else:
        updated_content = full_content.replace(selected, new_text, 1)

    archive_chapter_snapshot(db, chapter, "rewrite")
    chapter.generated_content = updated_content
    reviewed = review_chapter_content(db, project, chapter)
    return reviewed, selected, new_text
