"""知识库条目化：LLM 预处理 + 标题/摘要/正文综合检索。"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import re
import sys
import uuid
from unittest.mock import MagicMock

import numpy as np

from db.database import SessionLocal, init_db
from db.models import KnowledgeFolderStatus, Project
from services import embedding_service
from services.knowledge_item_service import (
    extract_knowledge_items,
    get_folder_status_detail,
    mark_folder_processing,
    search_knowledge_items,
)


def _topic_embedder(texts: list[str]) -> np.ndarray:
    out = np.zeros((len(texts), 512), dtype=np.float32)
    for i, text in enumerate(texts):
        if any(k in text for k in ("接地", "阻值", "电阻")):
            out[i, 0] = 1.0
        else:
            out[i, 1] = 1.0
    return out


def test_search_knowledge_items_uses_content_matches(monkeypatch):
    monkeypatch.setattr(
        "services.knowledge_item_service.tokenize",
        lambda text: re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]{2,}", text),
    )
    monkeypatch.setattr("services.knowledge_item_service.expand_tokens", lambda tokens: tokens)
    monkeypatch.setattr("services.embedding_service.embedding_available", lambda: False)

    items = [
        SimpleNamespace(
            title="主变安装",
            resume="设备就位与吊装",
            content="主变压器基础验收、吊装就位和附件安装。",
            sort_order=1,
            source_file="main.md",
            embedding=None,
        ),
        SimpleNamespace(
            title="通用施工方案",
            resume="电气设备安装",
            content="GIS 气室抽真空、SF6 气体含水量控制和交接试验应连续记录。",
            sort_order=2,
            source_file="gis.md",
            embedding=None,
        ),
    ]

    monkeypatch.setattr(
        "services.knowledge_item_service.list_items",
        lambda folder_path, project_id, db: items,
    )

    results = search_knowledge_items("GIS 气室 交接试验", "GIS安装", "project-1", object(), top_k=1)

    assert len(results) == 1
    assert "通用施工方案" in results[0]
    assert "gis.md" in results[0]


def test_search_knowledge_items_semantic_hit_without_lexical_overlap(monkeypatch):
    monkeypatch.setattr(
        "services.knowledge_item_service.tokenize",
        lambda text: re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]{2,}", text),
    )
    monkeypatch.setattr("services.knowledge_item_service.expand_tokens", lambda tokens: tokens)

    import config as cfg

    ground_vec = _topic_embedder(["装置阻值检测"])[0]
    other_vec = _topic_embedder(["混凝土浇筑"])[0]
    items = [
        SimpleNamespace(
            title="混凝土浇筑",
            resume="结构施工",
            content="模板验收与钢筋绑扎检查。",
            sort_order=1,
            source_file="concrete.md",
            embedding=embedding_service.to_blob(other_vec),
            embedding_model=cfg.EMBEDDING_MODEL_PATH,
        ),
        SimpleNamespace(
            title="装置阻值检测",
            resume="回填前测量",
            content="装置阻值检测应在回填前完成并记录。",
            sort_order=2,
            source_file="ground.md",
            embedding=embedding_service.to_blob(ground_vec),
            embedding_model=cfg.EMBEDDING_MODEL_PATH,
        ),
    ]
    monkeypatch.setattr(
        "services.knowledge_item_service.list_items",
        lambda folder_path, project_id, db: items,
    )

    embedding_service.set_test_embedder(_topic_embedder)
    try:
        # 查询词与条目标题/正文几乎无字面重叠，但语义同属接地电阻主题
        results = search_knowledge_items("接地电阻测试", "接地网", "project-1", object(), top_k=1)
    finally:
        embedding_service.set_test_embedder(None)

    assert len(results) == 1
    assert "装置阻值检测" in results[0]


def test_search_knowledge_items_bm25_fallback_when_embedding_disabled(monkeypatch):
    monkeypatch.setattr(
        "services.knowledge_item_service.tokenize",
        lambda text: re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]{2,}", text),
    )
    monkeypatch.setattr("services.knowledge_item_service.expand_tokens", lambda tokens: tokens)
    monkeypatch.setattr("services.embedding_service.embedding_available", lambda: False)

    items = [
        SimpleNamespace(
            title="主变安装",
            resume="设备就位与吊装",
            content="主变压器基础验收、吊装就位和附件安装。",
            sort_order=1,
            source_file="main.md",
            embedding=None,
        ),
        SimpleNamespace(
            title="通用施工方案",
            resume="电气设备安装",
            content="GIS 气室抽真空、SF6 气体含水量控制和交接试验应连续记录。",
            sort_order=2,
            source_file="gis.md",
            embedding=None,
        ),
    ]
    monkeypatch.setattr(
        "services.knowledge_item_service.list_items",
        lambda folder_path, project_id, db: items,
    )

    hit = search_knowledge_items("GIS 气室 交接试验", "GIS安装", "project-1", object(), top_k=1)
    assert len(hit) == 1
    assert "通用施工方案" in hit[0]

    miss = search_knowledge_items("完全不相关的查询词xyz", "GIS安装", "project-1", object(), top_k=1)
    assert miss == []


def test_knowledge_folder_status_persists_processing_and_failure(monkeypatch):
    init_db()
    db = SessionLocal()
    project_id = f"project-kb-{uuid.uuid4().hex[:8]}"
    try:
        project = Project(id=project_id, name="知识库测试")
        db.add(project)
        db.commit()

        mark_folder_processing(project_id, "GIS安装", db)
        detail = get_folder_status_detail(project_id, "GIS安装", db)
        assert detail["status"] == "processing"

        monkeypatch.setattr(
            "services.knowledge_item_service._read_folder_texts",
            lambda folder_path: [("gis.md", "GIS 气室抽真空和交接试验记录要求。" * 20)],
        )
        monkeypatch.setattr(
            "services.knowledge_item_service.call_llm_json",
            lambda messages: (_ for _ in ()).throw(RuntimeError("LLM 调用失败")),
        )

        try:
            extract_knowledge_items("GIS安装", project_id, db)
        except RuntimeError:
            pass

        detail = get_folder_status_detail(project_id, "GIS安装", db)
        assert detail["status"] == "failed"
        assert detail["error"]

        row = (
            db.query(KnowledgeFolderStatus)
            .filter(
                KnowledgeFolderStatus.project_id == project_id,
                KnowledgeFolderStatus.folder_path == "GIS安装",
            )
            .first()
        )
        assert row is not None
        assert row.status == "failed"
        assert row.error_message
    finally:
        db.close()


def test_knowledge_folder_status_marks_stale_processing_as_failed():
    init_db()
    db = SessionLocal()
    project_id = f"project-kb-2-{uuid.uuid4().hex[:8]}"
    try:
        project = Project(id=project_id, name="知识库测试2")
        db.add(project)
        db.commit()

        row = KnowledgeFolderStatus(
            project_id=project_id,
            folder_path="主变安装",
            status="processing",
            error_message=None,
            updated_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        db.add(row)
        db.commit()

        detail = get_folder_status_detail(project_id, "主变安装", db)
        assert detail["status"] == "failed"
        assert "服务已重启" in detail["error"]
    finally:
        db.close()
