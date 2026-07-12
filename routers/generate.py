import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import Project, TechOutline
from services.background_jobs import spawn_async
from services.generation_service import generate_single_chapter, run_generation
from services.project_status import ALLOW_GENERATE, require_status
from services.prompt_debug_service import parse_stored_prompt_debug
from services.sse_manager import reset_queue, subscribe, unsubscribe
from services.selection_rewrite_service import apply_selection_rewrite
from services.chapter_review_errors import parse_review_errors
from services.chapter_version_service import (
    archive_chapter_snapshot,
    compare_chapter_versions,
    list_chapter_versions,
    restore_chapter_version,
)
from services.humanizer_service import detect_ai_cliches
from services.writer_service import review_chapter_content

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["generate"])


class ChapterUpdate(BaseModel):
    generated_content: str | None = None
    writing_guidance: str | None = None


class SelectionRewriteRequest(BaseModel):
    selected_text: str
    instruction: str
    context_before: str | None = None
    context_after: str | None = None
    selection_start: int | None = None
    selection_end: int | None = None


class DetectAiClichesRequest(BaseModel):
    content: str | None = None


def _claim_generation_slot(project: Project, db: Session, action: str) -> None:
    """同步抢占生成槽位，避免连点启动多个后台任务。"""
    require_status(project, ALLOW_GENERATE, action)
    if project.status == "generating":
        raise HTTPException(409, "批量生成进行中，请稍后再试")
    project.status = "generating"
    project.pause_requested = 0
    db.commit()


def _require_format_confirmed(project: Project) -> None:
    from services.generation_config import get_generation_config

    gen_cfg = get_generation_config(project)
    if not gen_cfg.get("format_confirmed_at"):
        raise HTTPException(
            400,
            "请先确认投标文件格式：在「内容生成」页确认目录与格式后再启动批量生成",
        )


def _require_locked_outline(db: Session, project_id: str) -> None:
    locked = (
        db.query(TechOutline)
        .filter(TechOutline.project_id == project_id, TechOutline.is_locked == 1)
        .first()
    )
    if not locked:
        raise HTTPException(400, "请先锁定大纲：请返回「大纲策划」步骤，生成并锁定大纲后再试")


@router.post("/projects/{project_id}/generate")
def start_generate(
    project_id: str,
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    _require_locked_outline(db, project_id)
    _require_format_confirmed(project)
    _claim_generation_slot(project, db, "启动内容生成")
    reset_queue(project_id)
    spawn_async(lambda: run_generation(project_id, False), name=f"generate-{project_id}")
    return {"success": True, "message": "生成任务已启动"}


@router.post("/projects/{project_id}/generate/pause")
def pause_generate(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    project.pause_requested = 1
    db.commit()
    return {"success": True, "message": "已请求暂停，当前章节完成后停止"}


@router.post("/projects/{project_id}/generate/resume")
def resume_generate(
    project_id: str,
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    _require_locked_outline(db, project_id)
    _require_format_confirmed(project)
    _claim_generation_slot(project, db, "继续内容生成")
    reset_queue(project_id)
    spawn_async(lambda: run_generation(project_id, True), name=f"resume-{project_id}")
    return {"success": True, "message": "生成任务已恢复"}


@router.get("/projects/{project_id}/stream")
async def stream_progress(project_id: str):
    queue = subscribe(project_id)

    async def event_generator():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=300)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    if event.get("type") in ("complete", "error") and not event.get("chapter_id"):
                        break
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'ping'})}\n\n"
        finally:
            # 连接断开（客户端关闭标签页/网络中断）时退订，避免队列泄漏
            unsubscribe(project_id, queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.put("/chapters/{chapter_id}")
def update_chapter(chapter_id: str, body: ChapterUpdate, db: Session = Depends(get_db)):
    ch = db.query(TechOutline).filter(TechOutline.id == chapter_id).first()
    if not ch:
        raise HTTPException(404, "章节不存在")
    if body.generated_content is not None:
        archive_chapter_snapshot(db, ch, "manual")
        ch.generated_content = body.generated_content
    if body.writing_guidance is not None:
        ch.writing_guidance = body.writing_guidance
    db.commit()
    return {"success": True}


@router.post("/projects/{project_id}/chapters/{chapter_id}/generate")
def generate_chapter(project_id: str, chapter_id: str, db: Session = Depends(get_db)):
    chapter = generate_single_chapter(db, project_id, chapter_id)
    debug = parse_stored_prompt_debug(chapter.prompt_debug)
    return {
        "success": True,
        "id": chapter.id,
        "review_status": chapter.review_status,
        "generated_content": chapter.generated_content,
        "retrieval_warning": (debug or {}).get("retrieval_warning"),
    }


@router.post("/chapters/{chapter_id}/regenerate")
def regenerate_chapter(chapter_id: str, db: Session = Depends(get_db)):
    ch = db.query(TechOutline).filter(TechOutline.id == chapter_id).first()
    if not ch:
        raise HTTPException(404, "章节不存在")
    chapter = generate_single_chapter(db, ch.project_id, chapter_id)
    return {
        "success": True,
        "review_status": chapter.review_status,
        "generated_content": chapter.generated_content,
    }


@router.post("/chapters/{chapter_id}/selection-rewrite")
def selection_rewrite_chapter(chapter_id: str, body: SelectionRewriteRequest, db: Session = Depends(get_db)):
    ch = db.query(TechOutline).filter(TechOutline.id == chapter_id).first()
    if not ch:
        raise HTTPException(404, "章节不存在")

    project = db.query(Project).filter(Project.id == ch.project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")

    try:
        chapter, selected_text, new_text = apply_selection_rewrite(
            db,
            ch,
            project,
            selected_text=body.selected_text,
            instruction=body.instruction,
            context_before=body.context_before or "",
            context_after=body.context_after or "",
            selection_start=body.selection_start,
            selection_end=body.selection_end,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "选区改写失败 project=%s chapter=%s: %s", ch.project_id, chapter_id, exc
        )
        raise HTTPException(500, f"选区改写失败: {exc}") from exc

    return {
        "success": True,
        "original_text": selected_text,
        "new_text": new_text,
        "generated_content": chapter.generated_content,
        "review_status": chapter.review_status,
        "review_errors": parse_review_errors(chapter.review_errors),
    }


@router.post("/chapters/{chapter_id}/review")
def review_chapter(chapter_id: str, db: Session = Depends(get_db)):
    """对章节已有正文重新执行质检（人工修订后验章放行）。"""
    ch = db.query(TechOutline).filter(TechOutline.id == chapter_id).first()
    if not ch:
        raise HTTPException(404, "章节不存在")
    if ch.is_leaf != 1:
        raise HTTPException(400, "仅支持对叶子章节验章")
    if not (ch.generated_content or "").strip():
        raise HTTPException(400, "章节正文为空，无法验章")

    project = db.query(Project).filter(Project.id == ch.project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")

    chapter = review_chapter_content(db, project, ch)
    return {
        "success": True,
        "review_status": chapter.review_status,
        "review_errors": parse_review_errors(chapter.review_errors),
        "generated_content": chapter.generated_content,
    }


@router.post("/chapters/{chapter_id}/detect-ai-cliches")
def detect_chapter_ai_cliches(
    chapter_id: str,
    body: DetectAiClichesRequest | None = None,
    db: Session = Depends(get_db),
):
    ch = db.query(TechOutline).filter(TechOutline.id == chapter_id).first()
    if not ch:
        raise HTTPException(404, "章节不存在")
    content = (body.content if body and body.content is not None else ch.generated_content) or ""
    hits = detect_ai_cliches(content)
    return {"count": len(hits), "hits": hits}


@router.get("/chapters/{chapter_id}/versions")
def get_chapter_versions(chapter_id: str, db: Session = Depends(get_db)):
    ch = db.query(TechOutline).filter(TechOutline.id == chapter_id).first()
    if not ch:
        raise HTTPException(404, "章节不存在")
    return {"versions": list_chapter_versions(db, chapter_id)}


@router.get("/chapters/{chapter_id}/versions/compare")
def compare_versions(
    chapter_id: str,
    from_version_id: str,
    to_version_id: str | None = None,
    db: Session = Depends(get_db),
):
    ch = db.query(TechOutline).filter(TechOutline.id == chapter_id).first()
    if not ch:
        raise HTTPException(404, "章节不存在")
    try:
        return compare_chapter_versions(
            db,
            chapter_id,
            from_version_id,
            to_version_id=to_version_id,
            current_content=ch.generated_content if not to_version_id else None,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/chapters/{chapter_id}/versions/{version_id}/restore")
def restore_version(chapter_id: str, version_id: str, db: Session = Depends(get_db)):
    ch = db.query(TechOutline).filter(TechOutline.id == chapter_id).first()
    if not ch:
        raise HTTPException(404, "章节不存在")
    if ch.is_leaf != 1:
        raise HTTPException(400, "仅支持恢复叶子章节版本")
    try:
        chapter = restore_chapter_version(db, ch, version_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {
        "success": True,
        "generated_content": chapter.generated_content,
        "review_status": chapter.review_status,
    }
