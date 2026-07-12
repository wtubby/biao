"""embedding_service 单元测试（不依赖真实模型下载）。"""

import numpy as np

from services import embedding_service


def _char_bag_embedder(texts: list[str]) -> np.ndarray:
    """确定性伪向量：按字符 ord 累加到固定维度后 L2 归一化。"""
    dim = 512
    out = np.zeros((len(texts), dim), dtype=np.float32)
    for i, text in enumerate(texts):
        for ch in text:
            out[i, ord(ch) % dim] += 1.0
        norm = np.linalg.norm(out[i])
        if norm > 0:
            out[i] /= norm
    return out


def test_cosine_scores_and_blob_roundtrip():
    embedding_service.set_test_embedder(_char_bag_embedder)
    try:
        vecs = embedding_service.embed_texts(["接地电阻", "完全无关内容xyz"])
        assert vecs is not None
        assert vecs.shape == (2, 512)

        blob = embedding_service.to_blob(vecs[0])
        restored = embedding_service.from_blob(blob)
        assert restored.shape == (512,)
        np.testing.assert_allclose(restored, vecs[0], rtol=1e-6)

        query = embedding_service.embed_query("接地电阻")
        assert query is not None
        scores = embedding_service.cosine_scores(query, vecs)
        assert float(scores[0]) > float(scores[1])
    finally:
        embedding_service.set_test_embedder(None)


def test_embedding_available_false_when_model_load_fails(monkeypatch):
    embedding_service.set_test_embedder(None)
    monkeypatch.setattr("config.EMBEDDING_ENABLED", True)
    monkeypatch.setattr("config.EMBEDDING_MODEL_PATH", "/nonexistent/model/path")

    # 强制重新加载
    embedding_service.set_test_embedder(None)
    import services.embedding_service as es

    es._model = None
    assert es.embedding_available() is False
    assert es._model is False


def test_embedding_disabled_by_config(monkeypatch):
    embedding_service.set_test_embedder(None)
    monkeypatch.setattr("config.EMBEDDING_ENABLED", False)
    import services.embedding_service as es

    es._model = None
    assert es.embedding_available() is False
