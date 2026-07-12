"""本地向量 embedding：BGE 小模型，失败时降级为纯 BM25。"""

from __future__ import annotations

import hashlib
import logging
from typing import Callable

import numpy as np

logger = logging.getLogger(__name__)

_model = None  # SentenceTransformer | False | 测试注入对象
_EMBED_DIM = 512


def _get_model():
    global _model
    if _model is None:
        import config as cfg

        if not cfg.EMBEDDING_ENABLED:
            _model = False
            return _model
        try:
            from sentence_transformers import SentenceTransformer

            _model = SentenceTransformer(cfg.EMBEDDING_MODEL_PATH)
        except Exception as exc:
            logger.warning("向量模型加载失败，将降级为纯 BM25 检索: %s", exc)
            _model = False
    return _model


def embedding_available() -> bool:
    import config as cfg

    if not cfg.EMBEDDING_ENABLED:
        return False
    return _get_model() is not False


def set_test_embedder(fn: Callable[[list[str]], np.ndarray] | None) -> None:
    """测试用：注入确定性的假 embedding 函数，绕过真实模型加载。传 None 重置。"""
    global _model
    if fn is None:
        _model = None
        return

    class _FakeModel:
        def encode(self, texts, normalize_embeddings=True, convert_to_numpy=True):
            return fn(list(texts))

    _model = _FakeModel()


def embed_texts(texts: list[str]) -> np.ndarray | None:
    model = _get_model()
    if not model or not texts:
        return None
    return model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)


def embed_query(text: str) -> np.ndarray | None:
    result = embed_texts([text])
    return result[0] if result is not None else None


def cosine_scores(query_vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    # 已归一化，点积即余弦相似度
    return matrix @ query_vec


def to_blob(vec: np.ndarray) -> bytes:
    return vec.astype(np.float32).tobytes()


def from_blob(blob: bytes, dim: int = _EMBED_DIM) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32).reshape(dim)


def text_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()
