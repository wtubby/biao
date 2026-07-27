import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import SessionLocal, get_db
from db.models import Project
from services import knowledge_item_service as kis
from services.background_jobs import release_job, spawn_sync, try_acquire_job
from services.project_meta import get_meta

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["knowledge"])


class ProcessFolderBody(BaseModel):
    folder_path: str


def _run_extract(folder_path: str, domain: str | None) -> None:
    db = SessionLocal()
    try:
        kis.extract_knowledge_items(folder_path, db, domain=domain)
    except Exception as exc:
        logger.exception("知识库后台提取失败 folder=%s", folder_path)
        try:
            kis.mark_folder_failed(folder_path, db, str(exc))
        except Exception:
            logger.exception("写入知识库失败状态也失败 folder=%s", folder_path)
    finally:
        db.close()


@router.post("/projects/{project_id}/knowledge/process-folder")
def process_folder(
    project_id: str,
    body: ProcessFolderBody,
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    folder_path = body.folder_path.strip()
    if not folder_path:
        raise HTTPException(400, "folder_path 不能为空")

    kis.enable_folder_for_project(project_id, folder_path, db)

    detail = kis.get_folder_status_detail(folder_path, db)
    if detail["status"] == "ready" and detail["count"] > 0:
        return {
            "status": "ready",
            "folder_path": folder_path,
            "count": detail["count"],
            "reused": True,
        }
    if detail["status"] == "processing":
        return {"status": "processing", "folder_path": folder_path}

    # 先占槽再 mark/spawn，堵住双击窗口（与 generate.py 同模式）
    job_key = f"knowledge-extract:{folder_path}"
    if not try_acquire_job(job_key):
        return {"status": "processing", "folder_path": folder_path}

    try:
        domain = get_meta(project).get("engineering_domain")
        kis.mark_folder_processing(folder_path, db)
        if not spawn_sync(
            _run_extract,
            folder_path,
            domain,
            name=f"knowledge-extract-{folder_path}",
            dedupe_key=job_key,
            already_acquired=True,
        ):
            release_job(job_key)
            return {"status": "processing", "folder_path": folder_path}
    except Exception:
        release_job(job_key)
        raise
    return {"status": "processing", "folder_path": folder_path}


@router.get("/projects/{project_id}/knowledge/items")
def list_knowledge_items(
    project_id: str,
    folder_path: str,
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    items = kis.list_items(folder_path, db)
    detail = kis.get_folder_status_detail(folder_path, db)
    return {
        "status": detail["status"],
        "count": len(items),
        "error": detail.get("error"),
        "items": [
            {
                "id": i.id,
                "title": i.title,
                "resume": i.resume,
                "content": i.content,
                "source_file": i.source_file,
            }
            for i in items
        ],
    }


@router.delete("/knowledge-items/{item_id}")
def delete_knowledge_item(item_id: str, db: Session = Depends(get_db)):
    if not kis.delete_item(item_id, db):
        raise HTTPException(404, "知识条目不存在")
    return {"success": True}
