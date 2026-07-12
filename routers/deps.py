"""路由层共享依赖与工具。"""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from config import UPLOAD_DIR
from db.database import get_db
from db.models import Project


def find_source_file(project_id: str) -> Path | None:
    upload_dir = Path(UPLOAD_DIR) / project_id
    for name in ("source.pdf", "source.docx"):
        path = upload_dir / name
        if path.is_file():
            return path
    return None


def get_project_or_404(
    project_id: str,
    db: Session = Depends(get_db),
) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project
