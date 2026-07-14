"""电力术语同义词扩展 + BM25 / 向量混合检索（RRF）。"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import jieba
import numpy as np
from rank_bm25 import BM25Okapi
from sqlalchemy.orm import Session

from config import BM25_TOP_K, ENABLE_CHUNK_CONTEXT_PREFIX, KNOWLEDGE_ROOT, RETRIEVAL_RRF_K
from db.models import KnowledgeChunk
from services import embedding_service
from services.chunk_context import (
    build_chunk_context_prefix,
    chunk_display_text,
    chunk_embed_text,
)

logger = logging.getLogger(__name__)

DEFAULT_KNOWLEDGE_DOMAIN = "电力工程"

SYNONYMS: dict[str, list[str]] = {
    # 设备类
    "变压器": ["主变", "主变压器"],
    "组合电器": ["GIS", "气体绝缘开关设备", "气体绝缘金属封闭开关设备"],
    "断路器": ["开关", "真空断路器", "SF6断路器", "油断路器"],
    "隔离开关": ["刀闸", "隔刀", "隔离刀闸"],
    "负荷开关": ["负开", "环网柜"],
    "电流互感器": ["CT", "电流互感"],
    "电压互感器": ["PT", "电压互感"],
    "避雷器": ["防雷设备", "氧化锌避雷器", "MOA"],
    "穿墙套管": ["套管", "支柱绝缘子"],
    # 工程类
    "接地网": ["接地装置", "接地系统", "接地极", "接地体"],
    "继保": ["继电保护", "保护装置", "微机保护"],
    "调试": ["调试验收", "交接试验", "带电调试", "调试送电"],
    "交接试验": ["电气试验", "耐压试验", "预防性试验"],
    "电缆": ["电力电缆", "控制电缆", "信号电缆"],
    "母线": ["汇流排", "母排", "软母线", "硬母线"],
    # 施工类
    "安装": ["施工", "就位", "安装工程"],
    "敷设": ["铺设", "布设", "布放"],
    "开挖": ["土方开挖", "基坑开挖", "沟槽开挖"],
    "浇筑": ["混凝土浇筑", "灌注", "浇注"],
    "基础": ["设备基础", "混凝土基础", "基础施工"],
    # 市政/建筑/水利通用
    "导改": ["交通导改", "交通组织", "临时交通"],
    "管线": ["管线迁改", "管线改移", "地下管线"],
    "基坑": ["深基坑", "基坑支护", "基坑开挖"],
    "围堰": ["导流围堰", "土石围堰"],
    "度汛": ["防汛", "汛期施工", "度汛方案"],
    "扬尘": ["扬尘控制", "降尘", "文明施工"],
    "危大工程": ["危险性较大分部分项", "专项施工方案"],
}

_reverse: dict[str, str] = {}
for key, vals in SYNONYMS.items():
    for v in vals:
        _reverse[v] = key
    _reverse[key] = key


@dataclass
class RetrievalResult:
    chunks: list[str]
    empty_reason: str | None = None
    knowledge_available: bool = False


def format_labeled_chunk(text: str, source: str, folder: str | None = None) -> str:
    """为检索片段附加来源标签，供 writer 区分可引用依据。"""
    body = (text or "").strip()
    label = (source or "").strip()
    if folder and label and not label.startswith(folder):
        label = f"{folder}/{label}".strip("/")
    elif folder and not label:
        label = folder
    elif not label:
        label = "知识库"
    return f"[来源：{label}]\n{body}"


def expand_tokens(tokens: list[str]) -> list[str]:
    expanded = list(tokens)
    for t in tokens:
        if t in _reverse:
            key = _reverse[t]
            expanded.append(key)
            expanded.extend(SYNONYMS.get(key, []))
        for key, vals in SYNONYMS.items():
            if t in key or key in t:
                expanded.extend([key] + vals)
    return list(dict.fromkeys(expanded))


from services.retrieval_core import rrf_merge, tokenize

# 兼容旧私有名
_tokenize = tokenize
_rrf_merge = rrf_merge


_META_KEYWORD_RE = re.compile(r"^##\s*关键词[:：]\s*(.+)$", re.MULTILINE)
_META_SCOPE_RE = re.compile(r"^##\s*适用章节[:：]\s*(.+)$", re.MULTILINE)


def _split_meta(para: str) -> tuple[str, str]:
    """从段落头部剥离 `## 关键词:` / `## 适用章节:` 行，返回 (正文, 关键词串)。"""
    lines = para.splitlines()
    meta_kw: list[str] = []
    body_start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        m_kw = _META_KEYWORD_RE.match(stripped)
        m_scope = _META_SCOPE_RE.match(stripped)
        if m_kw:
            meta_kw.extend(x.strip() for x in m_kw.group(1).split(",") if x.strip())
            body_start = i + 1
            continue
        if m_scope:
            meta_kw.extend(x.strip() for x in m_scope.group(1).split(",") if x.strip())
            body_start = i + 1
            continue
        break  # 遇到第一行非元数据即停止，之后都算正文
    body = "\n".join(lines[body_start:]).strip()
    return body, "、".join(dict.fromkeys(meta_kw))


def _load_chunks(folder: str | None) -> list[dict]:
    root = Path(KNOWLEDGE_ROOT)
    search_dir = root / folder if folder else root
    if not search_dir.exists():
        return []

    chunks: list[dict] = []
    for path in search_dir.rglob("*.txt"):
        try:
            text_content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for para in re.split(r"\n\s*\n", text_content):
            para = para.strip()
            if len(para) < 20:
                continue
            body, keywords = _split_meta(para)
            if len(body) < 20:
                continue
            context_prefix = ""
            if ENABLE_CHUNK_CONTEXT_PREFIX:
                context_prefix = build_chunk_context_prefix(
                    folder=folder,
                    source_file=str(path.relative_to(root)),
                    keywords=keywords,
                    body=body,
                )
            chunks.append({
                "text": body,
                "keywords": keywords,
                "source": str(path.relative_to(root)),
                "context_prefix": context_prefix,
            })
    return chunks


def _sync_chunks_to_db(folder: str | None, db: Session) -> list[KnowledgeChunk]:
    """扫描磁盘 txt，按 chunk_hash 增量同步到 KnowledgeChunk 表。"""
    import config as cfg

    raw_chunks = _load_chunks(folder)
    folder_key = folder or ""
    existing: dict[str, KnowledgeChunk] = {}
    stale: list[KnowledgeChunk] = []
    # 同 folder 下历史重复 hash：保留一条，其余标记待删（避免 dict 覆盖后永远清不掉）
    for c in db.query(KnowledgeChunk).filter(KnowledgeChunk.folder_path == folder_key).all():
        if c.chunk_hash in existing:
            stale.append(c)
        else:
            existing[c.chunk_hash] = c
    seen_hashes: set[str] = set()
    result: list[KnowledgeChunk] = []
    to_embed: list[KnowledgeChunk] = []

    for raw in raw_chunks:
        h = embedding_service.text_hash(raw["text"])
        seen_hashes.add(h)
        prefix = raw.get("context_prefix") if ENABLE_CHUNK_CONTEXT_PREFIX else ""
        if h in existing:
            row = existing[h]
            result.append(row)
            changed = False
            if row.keywords != raw.get("keywords"):
                row.keywords = raw.get("keywords")
                changed = True
            if ENABLE_CHUNK_CONTEXT_PREFIX and row.context_prefix != prefix:
                row.context_prefix = prefix
                changed = True
            if row.embedding is None or row.embedding_model != cfg.EMBEDDING_MODEL_PATH or changed:
                to_embed.append(row)
            continue
        row = KnowledgeChunk(
            folder_path=folder_key,
            source_file=raw["source"],
            chunk_hash=h,
            text=raw["text"],
            keywords=raw.get("keywords"),
            context_prefix=prefix or None,
        )
        db.add(row)
        existing[h] = row  # 同批后续相同 hash 复用，避免重复建行
        result.append(row)
        to_embed.append(row)

    stale.extend(c for h, c in existing.items() if h not in seen_hashes)
    for c in stale:
        db.delete(c)
    db.commit()

    if to_embed and embedding_service.embedding_available():
        vecs = embedding_service.embed_texts([
            chunk_embed_text(c.text, c.context_prefix) for c in to_embed
        ])
        if vecs is not None:
            for c, v in zip(to_embed, vecs):
                c.embedding = embedding_service.to_blob(v)
                c.embedding_model = cfg.EMBEDDING_MODEL_PATH
            db.commit()
    return result


def _bm25_rank_indices(texts: list[str], query: str) -> list[int]:
    base_tokens = tokenize(query)
    query_tokens = expand_tokens(base_tokens)
    if not query_tokens or not texts:
        return []
    corpus = [tokenize(t) for t in texts]
    bm25 = BM25Okapi(corpus)
    scores = bm25.get_scores(query_tokens)
    return [i for i, s in sorted(enumerate(scores), key=lambda x: -x[1]) if s > 0]


def _semantic_rank_indices(
    embeddings: list[bytes | None],
    query: str,
    models: list[str | None] | None = None,
) -> list[int]:
    if not embedding_service.embedding_available():
        return []
    import config as cfg

    indexed: list[tuple[int, np.ndarray]] = []
    for i, blob in enumerate(embeddings):
        if not blob:
            continue
        if models is not None and models[i] != cfg.EMBEDDING_MODEL_PATH:
            continue
        try:
            indexed.append((i, embedding_service.from_blob(blob)))
        except (ValueError, TypeError):
            continue
    if not indexed:
        return []
    query_vec = embedding_service.embed_query(query)
    if query_vec is None:
        return []
    matrix = np.stack([v for _, v in indexed])
    scores = embedding_service.cosine_scores(query_vec, matrix)
    order = sorted(range(len(indexed)), key=lambda j: float(scores[j]), reverse=True)
    return [indexed[j][0] for j in order]


def _hybrid_select_indices(
    texts: list[str],
    embeddings: list[bytes | None],
    query: str,
    top_k: int,
    models: list[str | None] | None = None,
    search_texts: list[str] | None = None,
    *,
    use_vector: bool = True,
) -> list[int]:
    bm25_ranks = _bm25_rank_indices(search_texts or texts, query)
    semantic_ranks = _semantic_rank_indices(embeddings, query, models) if use_vector else []
    if semantic_ranks:
        merged = rrf_merge([bm25_ranks, semantic_ranks])
    else:
        merged = bm25_ranks
    return merged[:top_k]


def _hybrid_select(
    texts: list[str],
    embeddings: list[bytes | None],
    query: str,
    top_k: int,
    models: list[str | None] | None = None,
    search_texts: list[str] | None = None,
    *,
    use_vector: bool = True,
) -> list[str]:
    indices = _hybrid_select_indices(
        texts, embeddings, query, top_k, models,
        search_texts=search_texts,
        use_vector=use_vector,
    )
    return [texts[i] for i in indices]


def has_knowledge_sources(
    folder: str | None,
    project_id: str | None = None,
    db=None,
) -> bool:
    """判断知识库文件夹是否存在可检索内容（项目条目或静态文本分片）。"""
    if not folder:
        return False
    if project_id and db:
        from services.knowledge_item_service import get_folder_item_count

        if get_folder_item_count(folder, project_id, db) > 0:
            return True
    return bool(_load_chunks(folder))


def build_retrieval_warning(
    domain: str,
    folder: str | None,
    empty_reason: str | None,
    *,
    has_chunks: bool,
) -> str | None:
    """非电力工程且检索为空时，返回面向用户的降级提示。"""
    if has_chunks or not empty_reason:
        return None
    if (domain or DEFAULT_KNOWLEDGE_DOMAIN) == DEFAULT_KNOWLEDGE_DOMAIN:
        return None

    domain_label = domain or "其他"
    if empty_reason == "knowledge_empty":
        folder_part = f"文件夹「{folder}」" if folder else "知识库"
        return (
            f"当前项目领域为{domain_label}，{folder_part}暂无该领域参考资料，"
            "本章节内容主要依赖模型通用知识生成，建议人工重点核查。"
        )
    if empty_reason == "no_match":
        return (
            f"当前项目领域为{domain_label}，未从知识库检索到与本节相关的参考资料，"
            "本章节将主要依赖模型通用知识生成，建议人工重点核查。"
        )
    if empty_reason == "no_folder":
        return (
            f"当前项目领域为{domain_label}，本节未绑定知识库文件夹，"
            "将主要依赖模型通用知识生成，建议人工重点核查。"
        )
    return None


def retrieve_detailed(
    query: str,
    folder: str | None = None,
    top_k: int | None = None,
    project_id: str | None = None,
    db=None,
    *,
    use_vector: bool = True,
) -> RetrievalResult:
    top_k = top_k or BM25_TOP_K
    query_preview = (query or "")[:80]

    if not folder:
        logger.info("检索跳过：未绑定知识库文件夹 query=%s", query_preview)
        return RetrievalResult([], empty_reason="no_folder", knowledge_available=False)

    if project_id and db:
        from services.knowledge_item_service import get_folder_item_count, search_knowledge_items

        item_count = get_folder_item_count(folder, project_id, db)
        if item_count > 0:
            chunks = search_knowledge_items(
                query, folder, project_id, db, top_k, use_vector=use_vector,
            )
            if chunks:
                return RetrievalResult(chunks, knowledge_available=True)
            logger.info(
                "检索未命中（项目知识条目存在但未匹配） folder=%s query=%s",
                folder,
                query_preview,
            )
            return RetrievalResult([], empty_reason="no_match", knowledge_available=True)

    if db is not None:
        chunk_rows = _sync_chunks_to_db(folder, db)
        if not chunk_rows:
            logger.info("检索为空（知识库无可用内容） folder=%s query=%s", folder, query_preview)
            return RetrievalResult([], empty_reason="knowledge_empty", knowledge_available=False)
        texts = [chunk_display_text(c.text, c.context_prefix) for c in chunk_rows]
        sources = [
            f"{c.folder_path}/{c.source_file}".strip("/") if c.source_file else (c.folder_path or folder or "")
            for c in chunk_rows
        ]
        keywords_list = [c.keywords or "" for c in chunk_rows]
        embeddings = [c.embedding for c in chunk_rows]
        models = [c.embedding_model for c in chunk_rows]
        embed_texts = [chunk_embed_text(c.text, c.context_prefix) for c in chunk_rows]
        body_texts = [c.text for c in chunk_rows]
        search_texts = [
            f"{body} {prefix} {kw}".strip()
            for body, prefix, kw in zip(body_texts, [c.context_prefix or "" for c in chunk_rows], keywords_list)
        ]
        indices = _hybrid_select_indices(
            embed_texts, embeddings, query, top_k, models,
            search_texts=search_texts,
            use_vector=use_vector,
        )
        results = [
            format_labeled_chunk(texts[i], sources[i], folder)
            for i in indices
        ]
    else:
        chunks = _load_chunks(folder)
        if not chunks:
            logger.info("检索为空（知识库无可用内容） folder=%s query=%s", folder, query_preview)
            return RetrievalResult([], empty_reason="knowledge_empty", knowledge_available=False)
        texts = [chunk_display_text(c["text"], c.get("context_prefix")) for c in chunks]
        sources = [c.get("source") or folder or "" for c in chunks]
        keywords_list = [c.get("keywords") or "" for c in chunks]
        embeddings: list[bytes | None] = [None] * len(texts)
        embed_texts = [
            chunk_embed_text(c["text"], c.get("context_prefix")) for c in chunks
        ]
        if embedding_service.embedding_available():
            vecs = embedding_service.embed_texts(embed_texts)
            if vecs is not None:
                embeddings = [embedding_service.to_blob(v) for v in vecs]
        search_texts = [
            f"{c['text']} {c.get('context_prefix') or ''} {c.get('keywords') or ''}".strip()
            for c in chunks
        ]
        indices = _hybrid_select_indices(
            embed_texts, embeddings, query, top_k,
            search_texts=search_texts,
            use_vector=use_vector,
        )
        results = [
            format_labeled_chunk(texts[i], sources[i], folder)
            for i in indices
        ]

    if results:
        return RetrievalResult(results, knowledge_available=True)

    logger.info("检索未命中（混合检索无得分） folder=%s query=%s", folder, query_preview)
    return RetrievalResult([], empty_reason="no_match", knowledge_available=True)


def retrieve(
    query: str,
    folder: str | None = None,
    top_k: int | None = None,
    project_id: str | None = None,
    db=None,
) -> list[str]:
    return retrieve_detailed(query, folder, top_k, project_id, db).chunks
