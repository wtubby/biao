import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import UPLOAD_DIR
from db.database import SessionLocal, get_db
from db.models import Project, TechRequirement
from services.background_jobs import spawn_sync
from services.parser_service import process_upload
from services.project_meta import (
    PARSE_STAGE_READING,
    get_meta,
    get_parse_progress,
    set_parse_error,
    set_parse_progress,
)
from services.project_status import ALLOW_UPLOAD, require_status
from services.response_matrix_service import build_response_matrix
from services.tender_detail_service import (
    apply_notice_to_project,
    empty_tender_detail,
    get_tender_detail,
    mark_fields_manually_confirmed,
    protectable_fields_from_notice_keys,
    set_tender_detail,
)
from routers.deps import find_source_file

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["parse"])


class RequirementOut(BaseModel):
    id: str
    project_id: str
    requirement_title: str
    score_value: float | None
    score_category: str | None
    source_text: str | None
    source_page: int | None
    is_risk_item: int
    keyword: str | None
    evidence_materials: str | None = None
    mandatory_elements: str | None = None
    risk_hint: str | None = None
    status: str

    model_config = {"from_attributes": True}


class RequirementUpdate(BaseModel):
    requirement_title: str | None = None
    score_value: float | None = None
    score_category: str | None = None
    is_risk_item: int | None = None
    keyword: str | None = None
    evidence_materials: str | None = None
    mandatory_elements: str | None = None
    risk_hint: str | None = None
    status: str | None = None


class TenderNoticeUpdate(BaseModel):
    project_name: str | None = None
    project_code: str | None = None
    package_name: str | None = None
    package_no: str | None = None
    budget_wan: str | None = None
    budget_yuan: float | None = None
    tenderer: str | None = None
    agency: str | None = None
    bid_domain: str | None = None
    overview: str | None = None
    sme_targeted: str | None = None
    blind_bid: bool | None = None
    duration_text: str | None = None
    project_type: str | None = None
    contract_mode: str | None = None
    voltage_level: str | None = None
    capacity: str | None = None
    location: str | None = None
    target_pages: int | None = None


class QualificationItemUpdate(BaseModel):
    seq: int
    item_label: str
    description: str
    source_text: str | None = None
    source_page: int | None = None


class CommerceScoreUpdate(BaseModel):
    title: str
    criteria: str = ""
    score_value: float | None = None


class TenderDetailUpdate(BaseModel):
    notice: TenderNoticeUpdate | None = None
    commerce_requirements: str | None = None
    service_requirements: str | None = None
    bid_reference_catalog: str | None = None
    qualification_items: list[QualificationItemUpdate] | None = None
    commerce_scores: list[CommerceScoreUpdate] | None = None


def _run_parse_background(project_id: str, file_path: str):
    db = SessionLocal()
    project = None
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if project:
            process_upload(db, project, Path(file_path))
    except Exception as exc:
        logger.exception("后台解析失败 project=%s: %s", project_id, exc)
        if project:
            set_parse_error(project, f"解析异常: {exc}")
            project.status = "confirming"
            db.commit()
    finally:
        db.close()


@router.post("/projects/{project_id}/upload")
async def upload_document(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    require_status(project, ALLOW_UPLOAD, "上传招标文件")

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in (".pdf", ".docx"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 和 DOCX 格式")

    upload_dir = Path(UPLOAD_DIR) / project_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    save_path = upload_dir / f"source{suffix}"
    # 避免 PDF/DOCX 并存时预览取到旧文件
    for other in ("source.pdf", "source.docx"):
        other_path = upload_dir / other
        if other_path != save_path and other_path.is_file():
            other_path.unlink(missing_ok=True)

    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    project.status = "parsing"
    set_parse_progress(project, PARSE_STAGE_READING, "文件已上传，正在阅读文档…")
    db.commit()

    spawn_sync(_run_parse_background, project_id, str(save_path))

    return {"success": True, "message": "文件已上传，正在后台解析", "project_id": project_id}


@router.get("/projects/{project_id}/source")
def get_project_source(project_id: str, db: Session = Depends(get_db)):
    """返回已上传的招标原文（PDF 可内嵌预览，DOCX 触发下载）。"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    source = find_source_file(project_id)
    if not source:
        raise HTTPException(status_code=404, detail="尚未上传招标文件")
    media = (
        "application/pdf"
        if source.suffix.lower() == ".pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    disposition = "inline" if source.suffix.lower() == ".pdf" else "attachment"
    return FileResponse(
        path=source,
        media_type=media,
        filename=source.name,
        content_disposition_type=disposition,
    )


@router.get("/projects/{project_id}/source/meta")
def get_project_source_meta(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    source = find_source_file(project_id)
    return {
        "has_source": source is not None,
        "source_type": source.suffix.lstrip(".").lower() if source else None,
        "filename": source.name if source else None,
    }


@router.get("/projects/{project_id}/tender-detail")
def get_project_tender_detail(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return get_tender_detail(project)


@router.patch("/projects/{project_id}/tender-detail")
def update_project_tender_detail(
    project_id: str,
    body: TenderDetailUpdate,
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    detail = get_tender_detail(project)
    if body.notice is not None:
        notice = detail.setdefault("notice", empty_tender_detail()["notice"])
        touched = body.notice.model_dump(exclude_unset=True)
        for key, value in touched.items():
            notice[key] = value
        # 用户在招标详情面板保存，属于明确确认：强制回填并打标记
        apply_notice_to_project(project, notice, force=True)
        confirm_fields = protectable_fields_from_notice_keys(touched.keys())
        if confirm_fields:
            mark_fields_manually_confirmed(project, confirm_fields)

    if body.commerce_requirements is not None:
        detail["commerce_requirements"] = body.commerce_requirements
    if body.service_requirements is not None:
        detail["service_requirements"] = body.service_requirements
    if body.bid_reference_catalog is not None:
        detail["bid_reference_catalog"] = body.bid_reference_catalog
    if body.qualification_items is not None:
        from services.tender_detail_service import _normalize_qualification_items
        detail["qualification_items"] = _normalize_qualification_items(
            [item.model_dump() for item in body.qualification_items]
        )
    if body.commerce_scores is not None:
        detail["commerce_scores"] = [item.model_dump() for item in body.commerce_scores]

    set_tender_detail(project, detail)
    db.commit()
    db.refresh(project)
    return get_tender_detail(project)


@router.get("/projects/{project_id}/requirements", response_model=list[RequirementOut])
def list_requirements(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return (
        db.query(TechRequirement)
        .filter(TechRequirement.project_id == project_id)
        .order_by(TechRequirement.is_risk_item.desc(), TechRequirement.score_value.desc())
        .all()
    )


@router.get("/projects/{project_id}/parse/contradictions")
def list_parse_contradictions(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    contradictions = get_meta(project).get("contradictions")
    return {
        "items": contradictions if isinstance(contradictions, list) else [],
    }


@router.get("/projects/{project_id}/parse/summary")
def get_parse_summary(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    meta = get_meta(project)
    return {
        "confidence": meta.get("parse_confidence"),
        "level": meta.get("parse_confidence_level"),
        "warnings": meta.get("parse_warnings") or [],
        "stats": meta.get("parse_stats") or {},
        "parse_error": meta.get("parse_error"),
        "progress": get_parse_progress(project),
        "blind_bid_auto_detected": bool(meta.get("blind_bid_auto_detected")),
    }


@router.get("/projects/{project_id}/response-matrix")
def get_response_matrix(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return build_response_matrix(db, project)


@router.patch("/requirements/{req_id}", response_model=RequirementOut)
def update_requirement(req_id: str, body: RequirementUpdate, db: Session = Depends(get_db)):
    req = db.query(TechRequirement).filter(TechRequirement.id == req_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="评分项不存在")

    if body.requirement_title is not None:
        req.requirement_title = body.requirement_title
    if body.score_value is not None:
        req.score_value = body.score_value
    if body.score_category is not None:
        req.score_category = body.score_category
    if body.is_risk_item is not None:
        req.is_risk_item = body.is_risk_item
    if body.keyword is not None:
        req.keyword = body.keyword
    if body.evidence_materials is not None:
        req.evidence_materials = body.evidence_materials
    if body.mandatory_elements is not None:
        req.mandatory_elements = body.mandatory_elements
    if body.risk_hint is not None:
        req.risk_hint = body.risk_hint
    if body.status is not None:
        req.status = body.status

    db.commit()
    db.refresh(req)
    return req


@router.post("/projects/{project_id}/requirements/confirm-all")
def confirm_all_requirements(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    requirements = (
        db.query(TechRequirement).filter(TechRequirement.project_id == project_id).all()
    )

    # 评分项可选：无评分项时只要工程信息完整即可进入大纲策划
    risk_items = [r for r in requirements if r.is_risk_item == 1]
    unconfirmed_risk = [r for r in risk_items if r.status != "confirmed"]
    if unconfirmed_risk:
        raise HTTPException(
            status_code=400,
            detail=f"还有 {len(unconfirmed_risk)} 个刚性风险项未确认，不允许进入下一步",
        )

    missing_globals = []
    meta = get_meta(project)
    detail = get_tender_detail(project)
    notice = detail.get("notice") or {}
    if not (project.name or notice.get("project_name")):
        missing_globals.append("工程名称")
    if not (meta.get("project_type") or notice.get("project_type")):
        missing_globals.append("项目类型")
    from domains.registry import DEFAULT_DOMAIN, resolve_domain
    domain_key = resolve_domain(
        meta.get("engineering_domain") or notice.get("bid_domain")
    ).key
    if domain_key == DEFAULT_DOMAIN and not (project.voltage_level or notice.get("voltage_level")):
        missing_globals.append("电压等级")
    if not (project.location or notice.get("location")):
        missing_globals.append("建设地点")
    if not (project.duration_days or notice.get("duration_text")):
        missing_globals.append("总工期")

    if missing_globals:
        raise HTTPException(
            status_code=400,
            detail=f"全局技术变量未填写完整：{', '.join(missing_globals)}",
        )

    for req in requirements:
        if req.status == "pending":
            req.status = "confirmed"

    # 已锁定大纲或更后阶段时，勿回退为 planning（否则节点仍 is_locked，前端会误开生成入口）
    if project.status in ("outline_locked", "generating", "done"):
        db.commit()
        return {"success": True, "status": project.status}

    project.status = "planning"
    db.commit()

    return {"success": True, "status": "planning"}
