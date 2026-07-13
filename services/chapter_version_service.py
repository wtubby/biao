"""章节正文版本快照与对比。"""

from __future__ import annotations

import difflib

from sqlalchemy.orm import Session

from db.models import ChapterVersion, Project, TechOutline
from services.chapter_review_errors import dump_review_errors

MAX_VERSIONS_PER_CHAPTER = 20

_SOURCE_LABELS = {
    "manual": "手动保存",
    "generate": "AI 生成",
    "regenerate": "重新生成",
    "rewrite": "选区改写",
    "restore": "版本恢复",
}


def archive_chapter_snapshot(db: Session, chapter: TechOutline, source: str) -> ChapterVersion | None:
    """在覆盖章节正文前，将当前内容存档。"""
    content = chapter.generated_content or ""
    if not content.strip():
        return None

    latest = (
        db.query(ChapterVersion)
        .filter(ChapterVersion.chapter_id == chapter.id)
        .order_by(ChapterVersion.created_at.desc())
        .first()
    )
    if latest and latest.content == content:
        return None

    version = ChapterVersion(
        project_id=chapter.project_id,
        chapter_id=chapter.id,
        content=content,
        source=source,
        review_status=chapter.review_status,
        char_count=len(content),
    )
    db.add(version)
    db.flush()
    _prune_old_versions(db, chapter.id)
    return version


def list_chapter_versions(db: Session, chapter_id: str) -> list[dict]:
    rows = (
        db.query(ChapterVersion)
        .filter(ChapterVersion.chapter_id == chapter_id)
        .order_by(ChapterVersion.created_at.desc())
        .limit(MAX_VERSIONS_PER_CHAPTER)
        .all()
    )
    return [
        {
            "id": row.id,
            "chapter_id": row.chapter_id,
            "source": row.source,
            "source_label": _SOURCE_LABELS.get(row.source, row.source),
            "review_status": row.review_status,
            "char_count": row.char_count,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "preview": (row.content or "")[:120],
        }
        for row in rows
    ]


def get_chapter_version(db: Session, chapter_id: str, version_id: str) -> ChapterVersion | None:
    return (
        db.query(ChapterVersion)
        .filter(ChapterVersion.chapter_id == chapter_id, ChapterVersion.id == version_id)
        .first()
    )


def compare_chapter_versions(
    db: Session,
    chapter_id: str,
    from_version_id: str,
    to_version_id: str | None = None,
    current_content: str | None = None,
) -> dict:
    left = get_chapter_version(db, chapter_id, from_version_id)
    if not left:
        raise ValueError("左侧版本不存在")

    if to_version_id:
        right = get_chapter_version(db, chapter_id, to_version_id)
        if not right:
            raise ValueError("右侧版本不存在")
        right_content = right.content
        right_label = right.created_at.isoformat() if right.created_at else to_version_id
    else:
        right_content = current_content or ""
        right_label = "当前正文"

    diff_lines = list(
        difflib.unified_diff(
            left.content.splitlines(),
            right_content.splitlines(),
            fromfile=f"版本 {left.created_at.isoformat() if left.created_at else from_version_id}",
            tofile=right_label,
            lineterm="",
        )
    )
    return {
        "from_version_id": from_version_id,
        "to_version_id": to_version_id,
        "diff": "\n".join(diff_lines),
        "added_lines": sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++")),
        "removed_lines": sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---")),
    }


def restore_chapter_version(db: Session, chapter: TechOutline, version_id: str) -> TechOutline:
    """恢复历史正文后重新验章，不信任存档时的 review_status。

    评分项绑定、内容边界、大纲结构等可能在存档后已变化，旧绿灯不能原样带入。
    """
    # 惰性导入：避免与 writer_service → archive_chapter_snapshot 循环依赖
    from services.writer_service import review_chapter_content

    version = get_chapter_version(db, chapter.id, version_id)
    if not version:
        raise ValueError("版本不存在")
    archive_chapter_snapshot(db, chapter, "restore")
    chapter.generated_content = version.content

    project = db.query(Project).filter(Project.id == chapter.project_id).first()
    if not project:
        chapter.review_status = "yellow"
        chapter.review_errors = dump_review_errors(["已恢复历史版本，建议重新验章"])
        db.commit()
        db.refresh(chapter)
        return chapter

    return review_chapter_content(db, project, chapter)

def _prune_old_versions(db: Session, chapter_id: str) -> None:
    rows = (
        db.query(ChapterVersion)
        .filter(ChapterVersion.chapter_id == chapter_id)
        .order_by(ChapterVersion.created_at.desc())
        .all()
    )
    for row in rows[MAX_VERSIONS_PER_CHAPTER:]:
        db.delete(row)
