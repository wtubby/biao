import logging
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import Project, TechOutline
from services.assembler_service import assemble_document
from services.blind_bid_service import check_blind_bid_violations, is_blind_bid
from services.chapter_review_errors import parse_review_errors
from services.commercial_bid_service import (
    export_commercial_docx,
    get_bid_scope,
    validate_commercial_export_ready,
)
from services.compliance_service import (
    check_compliance_now,
    get_last_compliance_report,
    is_compliance_report_stale,
    run_compliance,
)
from services.export_debug_service import build_debug_zip
from services.outline_order import sort_outline_tree_dfs
from services.pdf_export_service import convert_docx_to_pdf
from services.project_status import ALLOW_EXPORT, require_status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["export"])


def yellow_chapter_risks(chapters: list[TechOutline]) -> list[dict]:
    risks: list[dict] = []
    for c in chapters:
        if c.is_leaf != 1 or c.review_status != "yellow":
            continue
        risks.append({
            "id": c.id,
            "title": c.title,
            "errors": parse_review_errors(c.review_errors),
        })
    return risks


def _load_export_chapters(db: Session, project: Project, action: str) -> list[TechOutline]:
    require_status(project, ALLOW_EXPORT, action)
    chapters = sort_outline_tree_dfs(
        db.query(TechOutline).filter(TechOutline.project_id == project.id).all()
    )
    if not chapters:
        raise HTTPException(400, "大纲为空，无法导出")
    return chapters


def _export_compliance_headers(report: dict, yellow_count: int, project: Project) -> dict[str, str]:
    return {
        "X-Compliance-Passed": "true" if report.get("passed") else "false",
        "X-Compliance-Failures": str(report.get("failure_count", 0)),
        "X-Compliance-Warnings": str(report.get("warning_count", 0)),
        "X-Yellow-Chapters": str(yellow_count),
        "X-Blind-Bid": "true" if is_blind_bid(project) else "false",
    }


def validate_export_ready(
    chapters: list[TechOutline],
    *,
    allow_yellow: bool = False,
    allow_incomplete: bool = False,
    project: Project | None = None,
) -> None:
    leaves = [c for c in chapters if c.is_leaf == 1]
    if not leaves:
        raise HTTPException(400, "大纲中没有叶子章节，无法导出")

    def _has_content(c: TechOutline) -> bool:
        return bool((c.generated_content or "").strip())

    missing = [c for c in leaves if not _has_content(c)]
    if missing and not allow_incomplete:
        preview = "、".join(c.title for c in missing[:5])
        more = f" 等 {len(missing)} 个章节" if len(missing) > 5 else ""
        raise HTTPException(400, f"仍有章节未生成正文：{preview}{more}")

    # 用户确认跳过空章后，空章不再参与质检状态门禁
    checkable = [c for c in leaves if _has_content(c)] if allow_incomplete else leaves

    red = [c for c in checkable if c.review_status == "red"]
    if red:
        preview = "、".join(f"{c.title}（red）" for c in red[:5])
        more = f" 等 {len(red)} 个章节" if len(red) > 5 else ""
        raise HTTPException(400, f"仍有章节生成失败，必须先修复：{preview}{more}")

    if project is not None and is_blind_bid(project):
        blind_hits: list[str] = []
        for c in checkable:
            for err in check_blind_bid_violations(c.generated_content or ""):
                blind_hits.append(f"{c.title}：{err}")
        if blind_hits:
            preview = "；".join(blind_hits[:3])
            more = f" 等 {len(blind_hits)} 处" if len(blind_hits) > 3 else ""
            raise HTTPException(400, f"暗标校验未通过：{preview}{more}")

    if allow_yellow:
        blocked = [c for c in checkable if c.review_status not in ("green", "yellow")]
        if blocked:
            preview = "、".join(f"{c.title}（{c.review_status}）" for c in blocked[:5])
            more = f" 等 {len(blocked)} 个章节" if len(blocked) > 5 else ""
            raise HTTPException(400, f"仍有章节状态异常，无法导出：{preview}{more}")
        return

    not_green = [c for c in checkable if c.review_status != "green"]
    if not_green:
        preview = "、".join(f"{c.title}（{c.review_status}）" for c in not_green[:5])
        more = f" 等 {len(not_green)} 个章节" if len(not_green) > 5 else ""
        raise HTTPException(400, f"仍有章节未通过质检，暂不允许导出：{preview}{more}")


@router.get("/projects/{project_id}/export/yellow-risks")
def get_yellow_export_risks(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    chapters = sort_outline_tree_dfs(
        db.query(TechOutline).filter(TechOutline.project_id == project_id).all()
    )
    risks = yellow_chapter_risks(chapters)
    return {"count": len(risks), "chapters": risks}


@router.get("/projects/{project_id}/export")
def export_word(
    project_id: str,
    allow_yellow: bool = False,
    allow_incomplete: bool = False,
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    chapters = _load_export_chapters(db, project, "导出 Word")
    validate_export_ready(
        chapters,
        allow_yellow=allow_yellow,
        allow_incomplete=allow_incomplete,
        project=project,
    )

    yellow_count = sum(
        1 for c in chapters if c.is_leaf == 1 and c.review_status == "yellow"
    )

    try:
        # 先用章节正文做合规终审，再组装 docx，便于前端在下载前拿到风险结论
        report = run_compliance(db, project, docx_path=None, chapters=chapters)
        out_path = assemble_document(project, chapters, mark_yellow=allow_yellow)
    except Exception as exc:
        logger.exception("导出失败 project=%s: %s", project_id, exc)
        raise HTTPException(500, f"导出失败: {exc}") from exc

    return FileResponse(
        path=str(out_path),
        filename=Path(out_path).name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=_export_compliance_headers(report, yellow_count, project),
    )


@router.get("/projects/{project_id}/export-pdf")
def export_pdf(
    project_id: str,
    allow_yellow: bool = False,
    allow_incomplete: bool = False,
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    chapters = _load_export_chapters(db, project, "导出 PDF")
    validate_export_ready(
        chapters,
        allow_yellow=allow_yellow,
        allow_incomplete=allow_incomplete,
        project=project,
    )
    try:
        run_compliance(db, project, docx_path=None, chapters=chapters)
        docx_path = assemble_document(project, chapters, mark_yellow=allow_yellow)
        pdf_path = convert_docx_to_pdf(docx_path)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("导出 PDF 失败 project=%s: %s", project_id, exc)
        raise HTTPException(500, f"导出 PDF 失败: {exc}") from exc

    return FileResponse(
        path=str(pdf_path),
        filename=Path(pdf_path).name,
        media_type="application/pdf",
    )


@router.get("/projects/{project_id}/export-commercial")
def export_commercial(
    project_id: str,
    allow_draft: bool = False,
    db: Session = Depends(get_db),
):
    from db.migrations import BID_SCOPE_TECHNICAL_COMMERCIAL

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    if get_bid_scope(project) != BID_SCOPE_TECHNICAL_COMMERCIAL:
        raise HTTPException(400, "未开启商务标生成范围，请先在确认页打开「技术标+商务标」")
    try:
        draft_count = validate_commercial_export_ready(
            db, project, allow_draft=allow_draft
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    try:
        out_path = export_commercial_docx(project, db=db)
    except Exception as exc:
        logger.exception("导出商务资格稿失败 project=%s: %s", project_id, exc)
        raise HTTPException(500, f"导出失败: {exc}") from exc
    return FileResponse(
        path=str(out_path),
        filename=Path(out_path).name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"X-Draft-Sections": str(draft_count)},
    )


@router.post("/projects/{project_id}/compliance/check")
def recheck_compliance(project_id: str, db: Session = Depends(get_db)):
    """随时触发一次合规检查（不依赖已导出的 docx）。"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")

    leaves = (
        db.query(TechOutline)
        .filter(TechOutline.project_id == project_id, TechOutline.is_leaf == 1)
        .all()
    )
    if not any(c.generated_content for c in leaves):
        raise HTTPException(400, "尚未生成任何章节内容，无法检查")

    report = check_compliance_now(db, project)
    return report


@router.get("/projects/{project_id}/compliance/report")
def get_compliance_report(project_id: str, db: Session = Depends(get_db)):
    """读取最近一次合规报告（导出时或手动检查时生成）。"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")

    report = get_last_compliance_report(project)
    if not report:
        return {"exists": False}

    return {
        "exists": True,
        "stale": is_compliance_report_stale(db, project, report),
        **report,
    }


@router.get("/projects/{project_id}/export-debug")
def export_debug(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")

    chapters = db.query(TechOutline).filter(TechOutline.project_id == project_id).all()
    if not chapters:
        raise HTTPException(400, "大纲为空，无法导出调试包")

    try:
        data, filename = build_debug_zip(db, project)
    except Exception as exc:
        logger.exception("导出调试包失败 project=%s: %s", project_id, exc)
        raise HTTPException(500, f"导出调试包失败: {exc}") from exc

    # Starlette 响应头必须是 latin-1；中文项目名用 RFC 5987 filename*
    ascii_name = f"{project_id}_debug.zip"
    disposition = (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{quote(filename)}"
    )
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": disposition},
    )
