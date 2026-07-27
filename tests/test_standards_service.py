"""标准规范库服务层测试。"""

from __future__ import annotations

import uuid

from db.database import SessionLocal, init_db
from db.models import KnowledgeChunk, StandardChangeLog, StandardChunkLink, StandardReference
from services.qa_rules import normalize_standard_core
from services.standards_service import (
    bootstrap_from_knowledge_base,
    resolve_standard,
    upsert_standard,
)


def _unique_gb_code() -> tuple[str, str]:
    """返回 (raw, core)，数字后缀尽量避开白名单常见号。"""
    n = 80000 + (uuid.uuid4().int % 19999)
    raw = f"GB/T {n}"
    return raw, normalize_standard_core(raw)


def test_upsert_standard_insert():
    init_db()
    db = SessionLocal()
    try:
        raw, code = _unique_gb_code()
        ref = upsert_standard(
            db,
            code=code,
            raw_code=raw,
            title="新建标准",
            status="draft",
        )
        assert ref.code == code
        assert ref.title == "新建标准"
        assert ref.status == "draft"
        row = db.query(StandardReference).filter(StandardReference.code == code).first()
        assert row is not None
        assert row.title == "新建标准"
    finally:
        db.close()


def test_upsert_standard_update_writes_changelog():
    init_db()
    db = SessionLocal()
    try:
        raw, code = _unique_gb_code()
        upsert_standard(db, code=code, raw_code=raw, title="旧标题", status="draft")
        ref = upsert_standard(db, code=code, title="新标题", status="active")
        assert ref.title == "新标题"
        assert ref.status == "active"
        logs = (
            db.query(StandardChangeLog)
            .filter(StandardChangeLog.code == code)
            .order_by(StandardChangeLog.field)
            .all()
        )
        fields = {log.field for log in logs}
        assert "title" in fields
        assert "status" in fields
        title_log = next(log for log in logs if log.field == "title")
        assert title_log.old_value == "旧标题"
        assert title_log.new_value == "新标题"
    finally:
        db.close()


def test_resolve_standard_hit_and_miss():
    init_db()
    db = SessionLocal()
    try:
        raw, code = _unique_gb_code()
        upsert_standard(db, code=code, raw_code=raw, title="命中标准", status="active")
        hit = resolve_standard(db, f"{raw}-2020")
        assert hit is not None
        assert hit["code"] == code
        assert hit["title"] == "命中标准"
        assert hit["status"] == "active"
        assert resolve_standard(db, "GB99999ZZZ") is None
    finally:
        db.close()


def test_bootstrap_from_knowledge_base_creates_draft_and_chunk_links(tmp_path, monkeypatch):
    folder_name = "测试标准导入"
    knowledge_dir = tmp_path / folder_name
    knowledge_dir.mkdir()
    raw, core = _unique_gb_code()
    body = f"专项工艺须符合 {raw}-2099 的相关施工与验收要求，条文应完整引用。"
    (knowledge_dir / "sample.txt").write_text(body, encoding="utf-8")

    monkeypatch.setattr("config.KNOWLEDGE_ROOT", str(tmp_path))
    monkeypatch.setattr("services.standards_service.KNOWLEDGE_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "services.standards_service._resolve_bootstrap_folders",
        lambda domain=None: [folder_name],
    )

    init_db()
    db = SessionLocal()
    try:
        # 清掉可能残留
        db.query(StandardChunkLink).filter(StandardChunkLink.code == core).delete()
        db.query(StandardReference).filter(StandardReference.code == core).delete()
        db.commit()

        chunk = KnowledgeChunk(
            folder_path=folder_name,
            source_file=f"{folder_name}/sample.txt",
            chunk_hash=f"hash-{uuid.uuid4().hex[:12]}",
            text=body,
        )
        db.add(chunk)
        db.commit()
        chunk_id = chunk.id

        created = bootstrap_from_knowledge_base(db)
        assert created >= 1

        ref = db.query(StandardReference).filter(StandardReference.code == core).first()
        assert ref is not None
        assert ref.status == "draft"
        assert ref.source_note == "自动导入待人工核实"

        links = (
            db.query(StandardChunkLink)
            .filter(
                StandardChunkLink.code == core,
                StandardChunkLink.chunk_id == chunk_id,
            )
            .all()
        )
        assert links

        created_again = bootstrap_from_knowledge_base(db)
        assert created_again == 0
    finally:
        db.close()
