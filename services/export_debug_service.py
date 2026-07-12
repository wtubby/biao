import io
import json
import re
import zipfile
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from db.models import Project, TechOutline, TechRequirement
from services.chapter_review_errors import parse_review_errors
from services.compliance_service import get_last_compliance_report
from services.outline_service import get_outline_tree
from services.project_meta import get_meta
from services.writing_guidance import guidance_to_outline_dict


def _safe_filename(title: str, chapter_id: str) -> str:
    safe = re.sub(r'[\\/:*?"<>|]', "_", title).strip() or chapter_id
    return f"{chapter_id}_{safe[:40]}.md"


def build_debug_zip(db: Session, project: Project) -> tuple[bytes, str]:
    project_id = project.id
    outline = get_outline_tree(db, project_id)
    requirements = db.query(TechRequirement).filter(TechRequirement.project_id == project_id).all()
    chapters = (
        db.query(TechOutline)
        .filter(TechOutline.project_id == project_id)
        .order_by(TechOutline.sort_order)
        .all()
    )

    req_payload = [
        {
            "id": r.id,
            "title": r.requirement_title,
            "score_value": r.score_value,
            "score_category": r.score_category,
            "is_risk_item": r.is_risk_item,
            "keyword": r.keyword,
            "evidence_materials": r.evidence_materials,
            "mandatory_elements": r.mandatory_elements,
            "risk_hint": r.risk_hint,
            "status": r.status,
        }
        for r in requirements
    ]

    qa_report = []
    for ch in chapters:
        if ch.is_leaf != 1:
            continue
        errors = parse_review_errors(ch.review_errors)
        guidance = guidance_to_outline_dict(ch.writing_guidance)
        content = ch.generated_content or ""
        qa_report.append(
            {
                "chapter_id": ch.id,
                "title": ch.title,
                "review_status": ch.review_status,
                "retry_count": ch.retry_count,
                "target_words": guidance.get("target_words"),
                "actual_chars": len(re.sub(r"\s+", "", content)),
                "errors": errors,
            }
        )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    project_name = (project.name or project_id)[:30]
    zip_name = f"{timestamp}_{project_name}_debug.zip"

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "project.json",
            json.dumps(
                {
                    "id": project.id,
                    "name": project.name,
                    "status": project.status,
                    "voltage_level": project.voltage_level,
                    "duration_days": project.duration_days,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
        zf.writestr("requirements.json", json.dumps(req_payload, ensure_ascii=False, indent=2))
        zf.writestr("outline.json", json.dumps(outline, ensure_ascii=False, indent=2))
        zf.writestr("qa_report.json", json.dumps(qa_report, ensure_ascii=False, indent=2))
        meta = get_meta(project)
        zf.writestr(
            "contradictions.json",
            json.dumps(meta.get("contradictions") or [], ensure_ascii=False, indent=2),
        )
        report = get_last_compliance_report(project)
        if report:
            zf.writestr("compliance_report.md", report.get("markdown") or "")
            zf.writestr(
                "compliance_report.json",
                json.dumps(
                    {
                        "passed": report.get("passed"),
                        "failure_count": report.get("failure_count"),
                        "warning_count": report.get("warning_count"),
                        "checked_at": report.get("checked_at"),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )

        for ch in chapters:
            if ch.is_leaf != 1 or not ch.generated_content:
                continue
            zf.writestr(f"chapters/{_safe_filename(ch.title, ch.id)}", ch.generated_content)

    return buffer.getvalue(), zip_name
