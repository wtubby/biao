import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import TARGET_PAGES_DEFAULT, UPLOAD_DIR
from db.database import get_db
from db.models import Project, TechOutline, TechRequirement
from services.typesetting_config import list_typesetting_options
from services.generation_config import (
    TARGET_PAGES_MAX,
    TARGET_PAGES_MIN,
    get_generation_config,
    list_bid_category_options,
    update_generation_config,
)
from services.reference_bid_service import extract_reference_text_from_file
from services.generation_mode import get_generation_mode, mode_label, set_generation_mode
from services.outline_split_service import find_long_leaves, split_long_leaves
from services.outline_service import (
    enrich_outline_nodes,
    generate_outline_ai,
    get_outline_tree,
    lock_outline,
    reapply_outline_generation_mode,
    regenerate_leaf_guidance,
    save_outline_tree,
    scale_leaves_to_total_words,
    validate_coverage,
)
from services.outline_template_service import get_outline_template, list_outline_templates
from services.project_meta import get_meta, get_outline_catalog_text, set_meta
from services.project_status import (
    ALLOW_GENERATION_CONFIG_RESCALE,
    ALLOW_OUTLINE_GENERATE,
    ALLOW_OUTLINE_LOCK,
    ALLOW_OUTLINE_SAVE,
    require_status,
)
from services.word_estimate import estimate_from_leaves, format_word_count_display

router = APIRouter(prefix="/api", tags=["outline"])


class OutlineNode(BaseModel):
    id: str
    title: str
    parent_id: str | None = None
    sort_order: int = 0
    level: int = 1
    is_leaf: int = 0
    bound_folder: str | None = None
    requirement_ids: list[str] = []
    writing_guidance: str | None = None
    guidance_brief: str | None = None
    content_boundary: str | None = None
    style_tier: str | None = None


class OutlineSave(BaseModel):
    nodes: list[OutlineNode]


class SplitLongLeavesBody(BaseModel):
    leaf_id: str | None = None


class GenerationModeUpdate(BaseModel):
    mode: str


class LeafGuidanceRegenerate(BaseModel):
    style_tier: str | None = None


class GenerationConfigUpdate(BaseModel):
    chart_density: str | None = None
    use_knowledge_library: bool | None = None
    reference_bid_enabled: bool | None = None
    reference_bid_text: str | None = None
    reference_bid_filename: str | None = None
    standards_pack: str | None = None
    target_pages: int | None = None
    custom_word_count: bool | None = None
    custom_total_words: int | None = None
    require_risk_binding: bool | None = None
    deep_humanize: bool | None = None
    bid_category: str | None = None
    body_format: str | None = None
    smartart_enabled: bool | None = None
    typesetting: dict | None = None


def _leaf_dicts_from_outline(outline: list[dict]) -> list[dict]:
    return [n for n in outline if int(n.get("is_leaf") or 0) == 1]


def _build_generation_payload(db: Session, project: Project) -> dict:
    config = get_generation_config(project)
    outline = get_outline_tree(db, project.id)
    leaves = _leaf_dicts_from_outline(outline)
    target_pages = int(get_meta(project).get("target_pages") or TARGET_PAGES_DEFAULT)
    estimate = estimate_from_leaves(
        leaves,
        target_pages,
        custom_word_count=bool(config.get("custom_word_count")),
        custom_total_words=config.get("custom_total_words"),
    )
    return {
        **config,
        "generation_mode": get_generation_mode(project),
        "target_pages": target_pages,
        "target_pages_range": {"min": TARGET_PAGES_MIN, "max": TARGET_PAGES_MAX},
        "catalog_text": get_outline_catalog_text(project),
        "outline_count": len(outline),
        "leaf_count": len(leaves),
        "estimate": {
            **estimate,
            "display_words": format_word_count_display(estimate["total_words"]),
        },
        "typesetting_options": list_typesetting_options(),
        "bid_category_options": list_bid_category_options(),
    }


@router.get("/projects/{project_id}/generation-config")
def get_generation_config_api(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    return _build_generation_payload(db, project)


@router.put("/projects/{project_id}/generation-config")
def update_generation_config_api(
    project_id: str,
    body: GenerationConfigUpdate,
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    try:
        updates = body.model_dump(exclude_unset=True)
        target_pages = updates.pop("target_pages", None)
        custom_total_words = updates.pop("custom_total_words", None)
        custom_word_count = updates.pop("custom_word_count", None)
        # generating/done 允许改展示配置，但不重算 target_words，避免冲掉已生成正文
        can_rescale = project.status in ALLOW_GENERATION_CONFIG_RESCALE

        if target_pages is not None:
            if target_pages < TARGET_PAGES_MIN or target_pages > TARGET_PAGES_MAX:
                raise ValueError(
                    f"目标页数须在 {TARGET_PAGES_MIN}~{TARGET_PAGES_MAX} 之间"
                )
            set_meta(project, target_pages=int(target_pages))
            if can_rescale:
                reapply_outline_generation_mode(db, project)

        if updates:
            update_generation_config(project, **updates)

        if custom_word_count and custom_total_words and custom_total_words > 0:
            if can_rescale:
                scale_leaves_to_total_words(db, project, int(custom_total_words))
            update_generation_config(
                project,
                custom_word_count=True,
                custom_total_words=int(custom_total_words),
            )
        elif custom_word_count is False:
            update_generation_config(project, custom_word_count=False, custom_total_words=None)
            if can_rescale:
                reapply_outline_generation_mode(db, project)

        db.commit()
        return {"success": True, **_build_generation_payload(db, project)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/projects/{project_id}/generation-config/confirm-format")
def confirm_bid_format(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    now = datetime.now(timezone.utc).isoformat()
    update_generation_config(project, format_confirmed_at=now)
    db.commit()
    return {"success": True, "format_confirmed_at": now}


@router.post("/projects/{project_id}/reference-bid/upload")
async def upload_reference_bid(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """上传历史中标标书（pdf/docx），提取文本写入以标写标配置。"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")

    filename = file.filename or "reference.bin"
    suffix = Path(filename).suffix.lower()
    if suffix not in (".pdf", ".docx", ".txt", ".md"):
        raise HTTPException(400, "仅支持 PDF / DOCX / TXT / MD 参考标书")

    upload_dir = Path(UPLOAD_DIR) / project_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    save_path = upload_dir / f"reference_bid{suffix}"
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        if suffix in (".txt", ".md"):
            text = save_path.read_text(encoding="utf-8", errors="ignore").strip()
            if not text:
                raise ValueError("参考标书文本为空")
            if len(text) > 120_000:
                text = text[:120_000].rstrip() + "\n\n…（已截断）"
        else:
            text = extract_reference_text_from_file(save_path)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    update_generation_config(
        project,
        reference_bid_enabled=True,
        reference_bid_text=text,
        reference_bid_filename=filename,
    )
    db.commit()
    return {
        "success": True,
        "filename": filename,
        "char_count": len(text),
        "message": f"已导入参考标书「{filename}」（{len(text)} 字），已启用以标写标",
        **_build_generation_payload(db, project),
    }


@router.get("/outline/templates")
def outline_templates():
    return {"templates": list_outline_templates()}


@router.get("/outline/templates/{template_id}")
def outline_template_detail(template_id: str):
    try:
        return get_outline_template(template_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.put("/projects/{project_id}/generation-mode")
def update_generation_mode(project_id: str, body: GenerationModeUpdate, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    try:
        set_generation_mode(project, body.mode)
        updated_nodes = reapply_outline_generation_mode(db, project)
        db.commit()
        return {
            "success": True,
            "mode": get_generation_mode(project),
            "mode_label": mode_label(body.mode),
            "outline_updated": updated_nodes > 0,
            "message": (
                f"已切换为{mode_label(body.mode)}，并更新 {updated_nodes} 个章节目标字数"
                if updated_nodes > 0
                else f"已切换为{mode_label(body.mode)}，请重新 AI 深化大纲以调整章节结构"
            ),
        }
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/projects/{project_id}/outline/generate")
def generate_outline(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    require_status(project, ALLOW_OUTLINE_GENERATE, "生成大纲")
    try:
        outlines, source, warnings = generate_outline_ai(db, project)
        return {
            "success": True,
            "count": len(outlines),
            "source": source,
            "warnings": warnings,
            "message": "已根据用户目录深化大纲",
        }
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/projects/{project_id}/outline/leaves/{leaf_id}/regenerate-guidance")
def regenerate_leaf_guidance_api(
    project_id: str,
    leaf_id: str,
    body: LeafGuidanceRegenerate | None = None,
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    require_status(project, ALLOW_OUTLINE_SAVE, "重新生成编写思路")
    try:
        node = regenerate_leaf_guidance(
            db,
            project,
            leaf_id,
            style_tier=(body.style_tier if body else None),
        )
        return {"success": True, "node": node}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/projects/{project_id}/outline/split-long-leaves/preview")
def preview_split_long_leaves(project_id: str, db: Session = Depends(get_db)):
    """列出可结构拆分的长叶子章节（规划期）。"""
    from config import LONG_LEAF_SPLIT_THRESHOLD

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    nodes = get_outline_tree(db, project_id)
    candidates = find_long_leaves(nodes)
    return {
        "threshold": LONG_LEAF_SPLIT_THRESHOLD,
        "count": len(candidates),
        "candidates": [
            {
                "id": n["id"],
                "title": n.get("title"),
                "target_words": n.get("target_words"),
                "level": n.get("level"),
            }
            for n in candidates
        ],
    }


@router.post("/projects/{project_id}/outline/split-long-leaves")
def split_long_leaves_api(
    project_id: str,
    body: SplitLongLeavesBody | None = None,
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    require_status(project, ALLOW_OUTLINE_SAVE, "拆分长章节")
    leaf_id = body.leaf_id if body else None
    try:
        result = split_long_leaves(db, project, leaf_id=leaf_id)
        return result
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/projects/{project_id}/outline")
def get_outline(project_id: str, db: Session = Depends(get_db)):
    from services.outline_service import get_outline_warnings

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    return {
        "nodes": get_outline_tree(db, project_id),
        "warnings": get_outline_warnings(project),
    }


@router.put("/projects/{project_id}/outline")
def save_outline(project_id: str, body: OutlineSave, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    require_status(project, ALLOW_OUTLINE_SAVE, "保存大纲")
    requirements = (
        db.query(TechRequirement)
        .filter(TechRequirement.project_id == project_id, TechRequirement.status == "confirmed")
        .all()
    )
    req_dicts = [
        {
            "id": r.id,
            "title": r.requirement_title,
            "score_value": r.score_value,
            "is_risk_item": r.is_risk_item,
            "score_category": r.score_category,
        }
        for r in requirements
    ]
    target_pages = int(get_meta(project).get("target_pages") or TARGET_PAGES_DEFAULT)
    generation_mode = get_generation_mode(project)
    nodes = enrich_outline_nodes(
        [n.model_dump() for n in body.nodes], req_dicts, target_pages, generation_mode=generation_mode,
    )
    save_outline_tree(db, project_id, nodes)
    return {"success": True}


@router.post("/projects/{project_id}/outline/validate")
def validate_outline(project_id: str, db: Session = Depends(get_db)):
    return validate_coverage(db, project_id)


@router.post("/projects/{project_id}/outline/lock")
def lock_outline_api(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    require_status(project, ALLOW_OUTLINE_LOCK, "锁定大纲")
    try:
        lock_outline(db, project_id)
        project = db.query(Project).filter(Project.id == project_id).first()
        return {"success": True, "is_locked": True, "status": project.status if project else "outline_locked"}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
