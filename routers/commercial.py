"""商务标轨道 API。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from db.migrations import BID_SCOPE_TECHNICAL_COMMERCIAL
from db.models import Project
from routers.deps import get_project_or_404
from services.commercial_bid_service import (
    commercial_status,
    get_bid_scope,
    list_commercial_sections,
    persist_commercial_draft,
    section_to_dict,
    set_bid_scope,
    update_commercial_section,
)

router = APIRouter(prefix="/api/projects", tags=["commercial"])


class ToggleBody(BaseModel):
    enabled: bool


class SectionUpdateBody(BaseModel):
    title: str | None = None
    content_markdown: str | None = None
    status: str | None = None


@router.get("/{project_id}/commercial/status")
def get_commercial_status(project_id: str, db: Session = Depends(get_db)):
    project = get_project_or_404(project_id, db)
    return commercial_status(db, project)


@router.post("/{project_id}/commercial/toggle")
def toggle_commercial_scope(project_id: str, body: ToggleBody, db: Session = Depends(get_db)):
    project = get_project_or_404(project_id, db)
    scope = set_bid_scope(project, body.enabled)
    if body.enabled:
        persist_commercial_draft(db, project, preserve_confirmed=True)
    db.commit()
    db.refresh(project)
    return {
        "success": True,
        "bid_scope": scope,
        "enabled": scope == BID_SCOPE_TECHNICAL_COMMERCIAL,
        **commercial_status(db, project),
    }


@router.post("/{project_id}/commercial/regenerate")
def regenerate_commercial_draft(project_id: str, db: Session = Depends(get_db)):
    project = get_project_or_404(project_id, db)
    if get_bid_scope(project) != BID_SCOPE_TECHNICAL_COMMERCIAL:
        raise HTTPException(400, "请先开启「技术标+商务标」生成范围")
    rows = persist_commercial_draft(db, project, preserve_confirmed=True)
    db.commit()
    return {
        "success": True,
        "section_count": len(rows),
        "sections": [section_to_dict(r) for r in rows],
    }


@router.get("/{project_id}/commercial/sections")
def get_commercial_sections(project_id: str, db: Session = Depends(get_db)):
    project = get_project_or_404(project_id, db)
    rows = list_commercial_sections(db, project.id)
    return {"sections": [section_to_dict(r) for r in rows]}


@router.patch("/{project_id}/commercial/sections/{section_id}")
def patch_commercial_section(
    project_id: str,
    section_id: str,
    body: SectionUpdateBody,
    db: Session = Depends(get_db),
):
    get_project_or_404(project_id, db)
    try:
        row = update_commercial_section(
            db,
            project_id,
            section_id,
            title=body.title,
            content_markdown=body.content_markdown,
            status=body.status,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    db.commit()
    db.refresh(row)
    return {"success": True, "section": section_to_dict(row)}
