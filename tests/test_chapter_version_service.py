import uuid
from unittest.mock import patch

from db.database import SessionLocal, init_db
from db.models import ChapterVersion, Project, TechOutline
from services.chapter_version_service import (
    archive_chapter_snapshot,
    compare_chapter_versions,
    list_chapter_versions,
    restore_chapter_version,
)


def _seed_chapter(db, content: str = "初版正文", review_status: str = "green"):
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
        review_status=review_status,
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
        versions = list_chapter_versions(db, chapter.project_id, chapter.id)
        assert versions
        version_id = versions[0]["id"]

        chapter.generated_content = "修改后的正文"
        db.commit()

        with (
            patch("services.chapter_qa_orchestrator.run_soft_qa", return_value={"passed": True}),
            patch("services.chapter_qa_orchestrator.generate_summary", return_value="摘要"),
        ):
            restored = restore_chapter_version(db, chapter, version_id)
        assert restored.generated_content == "当前正文"
        assert db.query(ChapterVersion).filter(ChapterVersion.chapter_id == chapter.id).count() >= 2
    finally:
        db.close()


def test_restore_chapter_version_re_reviews_instead_of_copying_old_status():
    """恢复后必须重新验章，不能把存档时的 green 原样带回。"""
    init_db()
    db = SessionLocal()
    try:
        chapter = _seed_chapter(db, "旧版绿灯正文", review_status="green")
        archive_chapter_snapshot(db, chapter, "generate")
        db.commit()
        version_id = list_chapter_versions(db, chapter.project_id, chapter.id)[0]["id"]
        assert list_chapter_versions(db, chapter.project_id, chapter.id)[0]["review_status"] == "green"

        chapter.generated_content = "后来改过的正文"
        chapter.review_status = "yellow"
        db.commit()

        def _fake_review(db_sess, project, ch, **kwargs):
            assert ch.generated_content == "旧版绿灯正文"
            # 模拟上下文已变：重新验章不再是 green
            ch.review_status = "yellow"
            ch.review_errors = '["评分项绑定已变更"]'
            db_sess.commit()
            db_sess.refresh(ch)
            return ch

        with patch(
            "services.writer_service.review_chapter_content",
            side_effect=_fake_review,
        ) as review:
            restored = restore_chapter_version(db, chapter, version_id)

        review.assert_called_once()
        assert restored.generated_content == "旧版绿灯正文"
        assert restored.review_status == "yellow"
        assert restored.review_status != "green"
    finally:
        db.close()


def test_compare_chapter_versions_with_current_content():
    init_db()
    db = SessionLocal()
    try:
        chapter = _seed_chapter(db, "旧版本\n第二行")
        archive_chapter_snapshot(db, chapter, "manual")
        db.commit()
        version_id = list_chapter_versions(db, chapter.project_id, chapter.id)[0]["id"]

        chapter.generated_content = "新版本\n第二行"
        db.commit()

        result = compare_chapter_versions(
            db,
            chapter.project_id,
            chapter.id,
            version_id,
            current_content=chapter.generated_content,
        )
        assert "旧版本" in result["diff"]
        assert "新版本" in result["diff"]
    finally:
        db.close()


def test_version_queries_scoped_by_project_id():
    """同 chapter_id 跨项目时，列表/清理不得串号。"""
    from services.chapter_version_service import MAX_VERSIONS_PER_CHAPTER

    init_db()
    db = SessionLocal()
    try:
        shared_chapter_id = "ch-3"
        a = _seed_chapter(db, "项目A正文")
        a.id = shared_chapter_id
        db.commit()

        b_pid = str(uuid.uuid4())
        db.add(Project(id=b_pid, name="项目B"))
        b = TechOutline(
            project_id=b_pid,
            id=shared_chapter_id,
            title="施工组织设计",
            sort_order=1,
            level=1,
            is_leaf=1,
            generated_content="项目B正文",
            review_status="green",
        )
        db.add(b)
        db.commit()

        archive_chapter_snapshot(db, a, "manual")
        archive_chapter_snapshot(db, b, "manual")
        db.commit()

        a_versions = list_chapter_versions(db, a.project_id, shared_chapter_id)
        b_versions = list_chapter_versions(db, b.project_id, shared_chapter_id)
        assert len(a_versions) == 1
        assert len(b_versions) == 1
        assert a_versions[0]["preview"].startswith("项目A")
        assert b_versions[0]["preview"].startswith("项目B")

        # 给 A 灌满超出上限的版本，清理不得删掉 B
        for i in range(MAX_VERSIONS_PER_CHAPTER + 3):
            a.generated_content = f"项目A正文-v{i}"
            archive_chapter_snapshot(db, a, "manual")
        db.commit()

        assert (
            db.query(ChapterVersion)
            .filter(
                ChapterVersion.project_id == a.project_id,
                ChapterVersion.chapter_id == shared_chapter_id,
            )
            .count()
            == MAX_VERSIONS_PER_CHAPTER
        )
        assert (
            db.query(ChapterVersion)
            .filter(
                ChapterVersion.project_id == b.project_id,
                ChapterVersion.chapter_id == shared_chapter_id,
            )
            .count()
            == 1
        )
    finally:
        db.close()
