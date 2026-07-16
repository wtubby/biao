import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from config import UPLOAD_DIR
from db.database import get_db
from db.models import GlobalFact, KnowledgeItem, Project, TechOutline, TechRequirement
from domains.registry import DEFAULT_DOMAIN
from services.facts_service import init_default_facts, sync_basic_info_fact

from services.knowledge_registry import get_knowledge_folders
from routers.deps import find_source_file
from services.outline_catalog_source import apply_catalog_source, get_catalog_payload
from services.generation_config import TARGET_PAGES_MAX, TARGET_PAGES_MIN
from services.generation_mode import get_generation_mode
from services.outline_service import get_user_catalog, save_user_catalog
from services.project_meta import get_meta, get_parse_error, get_parse_progress, set_meta
from services.tender_detail_service import mark_fields_manually_confirmed, sync_project_to_notice

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str | None = None


class ProjectOut(BaseModel):
    id: str
    name: str | None
    project_type: str | None = None
    engineering_domain: str = DEFAULT_DOMAIN
    contract_mode: str | None = None
    voltage_level: str | None
    capacity: str | None
    duration_days: int | None
    transformer_count: str | None
    location: str | None
    extra_notes: str | None = None
    target_pages: int | None = None
    status: str
    created_at: datetime
    parse_error: str | None = None
    parse_progress: dict | None = None
    has_source: bool = False
    source_type: str | None = None
    generation_mode: str = "full"
    bid_scope: str = "technical"

    model_config = {"from_attributes": True}


def _project_out(project: Project) -> ProjectOut:
    meta = get_meta(project)
    source = find_source_file(project.id)
    return ProjectOut(
        id=project.id,
        name=project.name,
        project_type=meta.get("project_type"),
        engineering_domain=meta.get("engineering_domain") or DEFAULT_DOMAIN,
        contract_mode=meta.get("contract_mode"),
        voltage_level=project.voltage_level,
        capacity=project.capacity,
        duration_days=project.duration_days,
        transformer_count=project.transformer_count,
        location=project.location,
        extra_notes=meta.get("extra_notes"),
        target_pages=meta.get("target_pages"),
        status=project.status,
        created_at=project.created_at,
        parse_error=get_parse_error(project),
        parse_progress=get_parse_progress(project),
        has_source=source is not None,
        source_type=source.suffix.lstrip(".").lower() if source else None,
        generation_mode=get_generation_mode(project),
        bid_scope=getattr(project, "bid_scope", None) or "technical",
    )


class GlobalParamsUpdate(BaseModel):
    name: str
    project_type: str
    engineering_domain: str | None = None
    contract_mode: str | None = None
    voltage_level: str | None = None
    location: str
    duration_days: int
    capacity: str | None = None
    extra_notes: str | None = None
    transformer_count: str | None = None
    target_pages: int | None = Field(default=None, ge=TARGET_PAGES_MIN, le=TARGET_PAGES_MAX)


class OutlineCatalogSave(BaseModel):
    text: str


class OutlineCatalogSourceUpdate(BaseModel):
    source: str


def _get_project_or_404(db: Session, project_id: str) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


@router.get("/{project_id}/outline-catalog")
def get_outline_catalog(project_id: str, db: Session = Depends(get_db)):
    project = _get_project_or_404(db, project_id)
    return get_catalog_payload(db, project)


@router.put("/{project_id}/outline-catalog/source")
def update_outline_catalog_source(
    project_id: str,
    body: OutlineCatalogSourceUpdate,
    db: Session = Depends(get_db),
):
    project = _get_project_or_404(db, project_id)
    requirements = (
        db.query(TechRequirement)
        .filter(TechRequirement.project_id == project_id, TechRequirement.status == "confirmed")
        .all()
    )
    try:
        result = apply_catalog_source(project, requirements, body.source)
        db.commit()
        previews = get_catalog_payload(db, project)["previews"]
        return {"success": True, "previews": previews, **result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/{project_id}/outline-catalog")
def save_outline_catalog(project_id: str, body: OutlineCatalogSave, db: Session = Depends(get_db)):
    project = _get_project_or_404(db, project_id)
    try:
        catalog = save_user_catalog(project, body.text)
        db.commit()
        return {"success": True, "count": len(catalog), "catalog": catalog}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{project_id}/knowledge-folders")
def project_knowledge_folders(project_id: str, db: Session = Depends(get_db)):
    project = _get_project_or_404(db, project_id)
    meta = get_meta(project)
    return get_knowledge_folders(
        meta.get("project_type"),
        meta.get("engineering_domain") or DEFAULT_DOMAIN,
    )


@router.post("", response_model=ProjectOut)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(name=body.name, status="draft")
    db.add(project)
    db.commit()
    db.refresh(project)
    init_default_facts(db, project)
    return _project_out(project)


@router.get("", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return [_project_out(p) for p in db.query(Project).order_by(Project.created_at.desc()).all()]


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return _project_out(project)


@router.delete("/{project_id}")
def delete_project(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    db.query(TechRequirement).filter(TechRequirement.project_id == project_id).delete()
    db.query(TechOutline).filter(TechOutline.project_id == project_id).delete()
    db.query(GlobalFact).filter(GlobalFact.project_id == project_id).delete()
    db.query(KnowledgeItem).filter(KnowledgeItem.project_id == project_id).delete()
    from db.models import ChapterVersion, KnowledgeFolderStatus

    db.query(ChapterVersion).filter(ChapterVersion.project_id == project_id).delete()
    db.query(KnowledgeFolderStatus).filter(KnowledgeFolderStatus.project_id == project_id).delete()
    db.delete(project)
    db.commit()
    upload_dir = Path(UPLOAD_DIR) / project_id
    if upload_dir.exists():
        shutil.rmtree(upload_dir, ignore_errors=True)
    return {"success": True}


@router.patch("/{project_id}/global-params", response_model=ProjectOut)
def update_global_params(
    project_id: str,
    body: GlobalParamsUpdate,
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    project.name = body.name
    project.voltage_level = body.voltage_level
    project.capacity = body.capacity or None
    project.duration_days = body.duration_days
    project.location = body.location
    if body.transformer_count is not None:
        project.transformer_count = body.transformer_count or None
    meta_kwargs = {
        "project_type": body.project_type,
        "engineering_domain": body.engineering_domain or DEFAULT_DOMAIN,
        "contract_mode": body.contract_mode or None,
        "extra_notes": body.extra_notes or None,
    }
    if body.target_pages is not None:
        meta_kwargs["target_pages"] = body.target_pages
    set_meta(project, **meta_kwargs)
    mark_fields_manually_confirmed(project, [
        "name", "voltage_level", "capacity", "location", "duration_days",
        "project_type", "contract_mode", "engineering_domain", "budget_yuan", "target_pages",
    ])
    # 同步写回 notice.*，避免招标详情面板带着过期值再保存时覆盖回来
    sync_project_to_notice(project)
    db.commit()
    db.refresh(project)
    sync_basic_info_fact(db, project)
    return _project_out(project)
