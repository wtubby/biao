"""知识检索降级提示测试。"""

from unittest.mock import MagicMock, patch

import numpy as np

from db.database import SessionLocal, init_db
from services import embedding_service
from services.retrieval_service import (
    DEFAULT_KNOWLEDGE_DOMAIN,
    _rrf_merge,
    build_retrieval_warning,
    has_knowledge_sources,
    retrieve_detailed,
)


def _topic_embedder(texts: list[str]) -> np.ndarray:
    """假向量：接地/电阻相关进 dim0，其它进 dim1。"""
    out = np.zeros((len(texts), 512), dtype=np.float32)
    for i, text in enumerate(texts):
        if any(k in text for k in ("接地", "阻值", "电阻")):
            out[i, 0] = 1.0
        else:
            out[i, 1] = 1.0
    return out


def test_build_retrieval_warning_for_non_power_domain_when_knowledge_empty():
    warning = build_retrieval_warning(
        "市政工程",
        "市政施工",
        "knowledge_empty",
        has_chunks=False,
    )
    assert warning is not None
    assert "市政工程" in warning
    assert "暂无该领域参考资料" in warning


def test_build_retrieval_warning_skips_power_domain():
    warning = build_retrieval_warning(
        DEFAULT_KNOWLEDGE_DOMAIN,
        "GIS安装",
        "knowledge_empty",
        has_chunks=False,
    )
    assert warning is None


def test_build_retrieval_warning_skips_when_chunks_found():
    warning = build_retrieval_warning(
        "建筑工程",
        "某文件夹",
        "no_match",
        has_chunks=True,
    )
    assert warning is None


def test_retrieve_detailed_marks_no_folder():
    result = retrieve_detailed("施工方案", folder=None)
    assert result.chunks == []
    assert result.empty_reason == "no_folder"
    assert result.knowledge_available is False


def test_retrieve_detailed_marks_knowledge_empty(tmp_path, monkeypatch):
    monkeypatch.setattr("services.retrieval_service.KNOWLEDGE_ROOT", str(tmp_path))
    monkeypatch.setattr("services.embedding_service.embedding_available", lambda: False)
    folder = tmp_path / "市政资料"
    folder.mkdir()
    result = retrieve_detailed("道路施工组织", folder="市政资料")
    assert result.chunks == []
    assert result.empty_reason == "knowledge_empty"
    assert result.knowledge_available is False


def test_retrieve_detailed_marks_no_match_when_chunks_exist(tmp_path, monkeypatch):
    monkeypatch.setattr("services.retrieval_service.KNOWLEDGE_ROOT", str(tmp_path))
    monkeypatch.setattr("services.embedding_service.embedding_available", lambda: False)
    folder = tmp_path / "资料"
    folder.mkdir()
    (folder / "note.txt").write_text(
        "变电站 GIS 组合电器安装工艺要求包含吊装、就位、抽真空、充气等关键步骤。\n\n" * 3,
        encoding="utf-8",
    )

    result = retrieve_detailed("完全不相关的查询词", folder="资料")
    assert result.chunks == []
    assert result.empty_reason == "no_match"
    assert result.knowledge_available is True


def test_rrf_merge_prefers_consensus():
    # index 2 在两路都靠前，应排第一
    merged = _rrf_merge([[0, 2, 1], [2, 3, 0]])
    assert merged[0] == 2


def test_retrieve_semantic_hit_without_lexical_overlap(tmp_path, monkeypatch):
    """语义相关但字面不重叠的 query 应能命中。"""
    monkeypatch.setattr("services.retrieval_service.KNOWLEDGE_ROOT", str(tmp_path))
    folder = tmp_path / "接地网敷设"
    folder.mkdir()
    (folder / "note.txt").write_text(
        "装置阻值检测应在回填前完成，并按规范记录测量数据与验收结论。\n\n"
        "混凝土浇筑前应完成模板验收与钢筋绑扎检查，确保结构尺寸符合设计。\n\n",
        encoding="utf-8",
    )

    embedding_service.set_test_embedder(_topic_embedder)
    try:
        init_db()
        db = SessionLocal()
        try:
            result = retrieve_detailed("接地电阻测试", folder="接地网敷设", db=db, top_k=1)
        finally:
            db.close()
    finally:
        embedding_service.set_test_embedder(None)

    assert result.chunks
    assert "阻值检测" in result.chunks[0]


def test_retrieve_falls_back_to_bm25_when_embedding_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr("services.retrieval_service.KNOWLEDGE_ROOT", str(tmp_path))
    monkeypatch.setattr("config.EMBEDDING_ENABLED", False)
    monkeypatch.setattr("services.embedding_service.embedding_available", lambda: False)
    folder = tmp_path / "资料"
    folder.mkdir()
    # 多篇不同文档，避免 BM25 在全库相同分片时 IDF 塌缩为非正分
    (folder / "gis.txt").write_text(
        "变电站 GIS 组合电器安装工艺要求包含吊装、就位、抽真空、充气等关键步骤。\n\n",
        encoding="utf-8",
    )
    (folder / "concrete.txt").write_text(
        "混凝土浇筑前应完成模板验收与钢筋绑扎检查，确保结构尺寸符合设计要求。\n\n",
        encoding="utf-8",
    )
    (folder / "road.txt").write_text(
        "市政道路交通导改应设置临时标志标线，并安排专人疏导通行。\n\n",
        encoding="utf-8",
    )

    result = retrieve_detailed("GIS 组合电器安装", folder="资料")

    assert result.chunks
    assert "GIS" in result.chunks[0]
    assert result.chunks[0].startswith("[来源：")

    # 字面无关时与改造前一致：无命中
    miss = retrieve_detailed("完全不相关的查询词", folder="资料")
    assert miss.chunks == []
    assert miss.empty_reason == "no_match"


def test_has_knowledge_sources_detects_txt_chunks(tmp_path, monkeypatch):
    monkeypatch.setattr("services.retrieval_service.KNOWLEDGE_ROOT", str(tmp_path))
    folder = tmp_path / "资料"
    folder.mkdir()
    (folder / "note.txt").write_text("这是一段足够长的知识库文本内容，用于测试检索分片加载逻辑。\n\n" * 2, encoding="utf-8")
    assert has_knowledge_sources("资料") is True


def test_build_context_bundle_sets_retrieval_warning():
    from db.models import GlobalFact, Project, TechOutline, TechRequirement
    from services.writer_service import build_context_bundle

    project = Project(id="p1", name="测试工程")
    chapter = TechOutline(
        id="c1",
        project_id="p1",
        title="道路施工方案",
        is_leaf=1,
        bound_folder="市政资料",
    )
    db = MagicMock()

    outline_query = MagicMock()
    outline_query.filter.return_value.order_by.return_value.all.return_value = [chapter]
    facts_query = MagicMock()
    facts_query.filter.return_value.order_by.return_value.all.return_value = []
    req_query = MagicMock()
    req_query.filter.return_value.all.return_value = []

    def query_side(model):
        if model is TechOutline:
            return outline_query
        if model is GlobalFact:
            return facts_query
        if model is TechRequirement:
            return req_query
        return MagicMock()

    db.query.side_effect = query_side

    retrieval = type("R", (), {
        "chunks": [],
        "empty_reason": "knowledge_empty",
        "knowledge_available": False,
    })()

    with patch("services.chapter_context_service.get_meta", return_value={"engineering_domain": "市政工程"}), patch(
        "services.chapter_context_service.retrieve_detailed",
        return_value=retrieval,
    ), patch(
        "services.chapter_context_service.parse_writing_guidance",
        return_value={"brief": "", "content_boundary": "", "target_words": None},
    ), patch(
        "services.chapter_context_service._collect_sibling_leaf_titles",
        return_value=[],
    ), patch(
        "services.chapter_context_service._collect_other_leaf_titles",
        return_value=[],
    ):
        bundle = build_context_bundle(db, project, chapter)

    assert bundle["retrieval_warning"]
    assert "市政工程" in bundle["retrieval_warning"]
