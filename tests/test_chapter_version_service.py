import uuid

from db.database import SessionLocal, init_db
from db.models import ChapterVersion, Project, TechOutline
from services.chapter_version_service import (
    archive_chapter_snapshot,
    compare_chapter_versions,
    list_chapter_versions,
    restore_chapter_version,
)


def _seed_chapter(db, content: str = "初版正文"):
    pid = str(uuid.uuid4())
    chapter_id = str(uuid.uuid4())
    project = Project(id=pid, name="测试")
    chapter = TechOutline(
        project_id=pid,
        id=chapter_id,
        title="施工组织设计",
        sort_order=1,
        level=1,
        is_leaf=1,
        generated_content=content,
        review_status="green",
    )
    db.add(project)
    db.add(chapter)
    db.commit()
    return chapter


def test_archive_chapter_snapshot_skips_duplicate():
    init_db()
    db = SessionLocal()
    try:
        chapter = _seed_chapter(db, "相同正文")
        first = archive_chapter_snapshot(db, chapter, "manual")
        db.commit()
        second = archive_chapter_snapshot(db, chapter, "manual")
        db.commit()
        assert first is not None
        assert second is None
        assert db.query(ChapterVersion).filter(ChapterVersion.chapter_id == chapter.id).count() == 1
    finally:
        db.close()


def test_restore_chapter_version_replaces_content():
    init_db()
    db = SessionLocal()
    try:
        chapter = _seed_chapter(db, "当前正文")
        archive_chapter_snapshot(db, chapter, "manual")
        db.commit()
        versions = list_chapter_versions(db, chapter.id)
        assert versions
        version_id = versions[0]["id"]

        chapter.generated_content = "修改后的正文"
        db.commit()

        restored = restore_chapter_version(db, chapter, version_id)
        assert restored.generated_content == "当前正文"
        assert db.query(ChapterVersion).filter(ChapterVersion.chapter_id == chapter.id).count() >= 2
    finally:
        db.close()


def test_compare_chapter_versions_with_current_content():
    init_db()
    db = SessionLocal()
    try:
        chapter = _seed_chapter(db, "旧版本\n第二行")
        archive_chapter_snapshot(db, chapter, "manual")
        db.commit()
        version_id = list_chapter_versions(db, chapter.id)[0]["id"]

        chapter.generated_content = "新版本\n第二行"
        db.commit()

        result = compare_chapter_versions(
            db,
            chapter.id,
            version_id,
            current_content=chapter.generated_content,
        )
        assert "旧版本" in result["diff"]
        assert "新版本" in result["diff"]
    finally:
        db.close()
