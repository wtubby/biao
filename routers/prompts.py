from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import Project, TechOutline
from services.project_meta import get_outline_catalog
from services.outline_service import is_valid_outline_catalog
from services.prompt_debug_service import (
    build_chapter_prompt_preview,
    build_outline_prompt_preview,
    parse_stored_prompt_debug,
)

router = APIRouter(prefix="/api", tags=["prompts"])


@router.get("/projects/{project_id}/prompts/outline")
def preview_outline_prompts(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    catalog = get_outline_catalog(project)
    if not is_valid_outline_catalog(catalog):
        raise HTTPException(400, "请先保存目录大纲后再预览提示词")
    return build_outline_prompt_preview(db, project)


@router.get("/projects/{project_id}/chapters/{chapter_id}/prompts")
def preview_chapter_prompts(
    project_id: str,
    chapter_id: str,
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    chapter = (
        db.query(TechOutline)
        .filter(TechOutline.project_id == project_id, TechOutline.id == chapter_id)
        .first()
    )
    if not chapter:
        raise HTTPException(404, "章节不存在")
    if chapter.is_leaf != 1:
        raise HTTPException(400, "仅支持预览叶子章节的生成提示词")

    stored = parse_stored_prompt_debug(chapter.prompt_debug)
    preview = build_chapter_prompt_preview(db, project, chapter)
    if stored:
        preview["last_generation"] = stored
        preview["last_captured_at"] = stored.get("captured_at")
    return preview
