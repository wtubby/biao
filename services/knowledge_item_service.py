"""知识库条目化：LLM 预处理 + 标题/摘要/正文综合检索（BM25 + 向量 RRF）。"""

import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi
from sqlalchemy.orm import Session

from config import KNOWLEDGE_ROOT
from db.models import KnowledgeFolderStatus, KnowledgeItem, Project
from domains.registry import resolve_domain
from llm.llm_client import call_llm_json
from services import embedding_service
from services.project_meta import get_meta
from services.retrieval_core import rrf_merge, tokenize
from services.retrieval_service import expand_tokens, format_labeled_chunk

logger = logging.getLogger(__name__)

_STALE_PROCESSING_SECONDS = 120


def _extract_prompt(domain: str | None) -> str:
    identity = resolve_domain(domain).identity_prompt
    return f"""{identity}
从以下文档内容中，提取所有独立的技术知识点、施工工艺、规范要求、案例经验。
每个知识条目必须：
- title：一行话概括该条目的核心内容（20字以内）
- resume：2-3句话摘要
- content：包含具体数字、步骤、参数的完整技术内容
按 JSON 数组输出，每个元素含 title / resume / content 三字段。
不要提取目录、封面、前言等非技术内容。"""


_ACTIVE_PROCESSING: set[str] = set()


def _folder_key(project_id: str, folder_path: str) -> str:
    return f"{project_id}:{folder_path}"


def _get_or_create_status(
    project_id: str,
    folder_path: str,
    db: Session,
) -> KnowledgeFolderStatus:
    row = (
        db.query(KnowledgeFolderStatus)
        .filter(
            KnowledgeFolderStatus.project_id == project_id,
            KnowledgeFolderStatus.folder_path == folder_path,
        )
        .first()
    )
    if row:
        return row
    row = KnowledgeFolderStatus(
        project_id=project_id,
        folder_path=folder_path,
        status="pending",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _set_folder_status(
    project_id: str,
    folder_path: str,
    db: Session,
    *,
    status: str,
    error_message: str | None = None,
    item_count: int | None = None,
) -> None:
    row = _get_or_create_status(project_id, folder_path, db)
    row.status = status
    row.error_message = error_message
    if item_count is not None:
        row.item_count = item_count
    row.updated_at = datetime.now(timezone.utc)
    db.commit()


def mark_folder_processing(project_id: str, folder_path: str, db: Session) -> None:
    _set_folder_status(
        project_id,
        folder_path,
        db,
        status="processing",
        error_message=None,
    )


def mark_folder_failed(
    project_id: str,
    folder_path: str,
    db: Session,
    error_message: str,
) -> None:
    _set_folder_status(
        project_id,
        folder_path,
        db,
        status="failed",
        error_message=error_message,
        item_count=get_folder_item_count(folder_path, project_id, db),
    )


def get_folder_status_detail(project_id: str, folder_path: str, db: Session) -> dict:
    row = (
        db.query(KnowledgeFolderStatus)
        .filter(
            KnowledgeFolderStatus.project_id == project_id,
            KnowledgeFolderStatus.folder_path == folder_path,
        )
        .first()
    )
    key = _folder_key(project_id, folder_path)
    count = get_folder_item_count(folder_path, project_id, db)

    if row and row.status == "processing" and key not in _ACTIVE_PROCESSING:
        updated_at = row.updated_at
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        age_seconds = (datetime.now(timezone.utc) - updated_at).total_seconds()
        if age_seconds > _STALE_PROCESSING_SECONDS:
            error = row.error_message or "处理中断（服务已重启）"
            _set_folder_status(
                project_id,
                folder_path,
                db,
                status="failed",
                error_message=error,
                item_count=count,
            )
            return {"status": "failed", "error": error, "count": count}
        return {"status": "processing", "error": None, "count": count}

    if row:
        status = row.status
        if status == "ready" and count == 0:
            status = "pending"
        return {
            "status": status,
            "error": row.error_message,
            "count": count if count > 0 else row.item_count,
        }

    return {
        "status": "ready" if count > 0 else "pending",
        "error": None,
        "count": count,
    }


def get_folder_status(project_id: str, folder_path: str, db: Session) -> str:
    return get_folder_status_detail(project_id, folder_path, db)["status"]


def get_folder_item_count(folder_path: str, project_id: str, db: Session) -> int:
    return (
        db.query(KnowledgeItem)
        .filter(KnowledgeItem.project_id == project_id, KnowledgeItem.folder_path == folder_path)
        .count()
    )


def list_items(folder_path: str, project_id: str, db: Session) -> list[KnowledgeItem]:
    return (
        db.query(KnowledgeItem)
        .filter(KnowledgeItem.project_id == project_id, KnowledgeItem.folder_path == folder_path)
        .order_by(KnowledgeItem.sort_order)
        .all()
    )


def _read_folder_texts(folder_path: str) -> list[tuple[str, str]]:
    root = Path(KNOWLEDGE_ROOT)
    search_dir = root / folder_path if folder_path else root
    if not search_dir.exists():
        return []
    texts: list[tuple[str, str]] = []
    for path in search_dir.rglob("*"):
        if path.suffix.lower() not in (".txt", ".md"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").strip()
        except OSError:
            continue
        if len(text) >= 50:
            texts.append((path.name, text[:12000]))
    return texts


def _item_embed_text(item: KnowledgeItem) -> str:
    return f"{item.title}\n{item.resume or ''}\n{item.content or ''}".strip()


def _embed_items(items: list[KnowledgeItem], db: Session) -> None:
    if not items or not embedding_service.embedding_available():
        return
    import config as cfg

    vecs = embedding_service.embed_texts([_item_embed_text(i) for i in items])
    if vecs is None:
        return
    for item, v in zip(items, vecs):
        item.embedding = embedding_service.to_blob(v)
        item.embedding_model = cfg.EMBEDDING_MODEL_PATH
    db.commit()


def extract_knowledge_items(folder_path: str, project_id: str, db: Session) -> list[KnowledgeItem]:
    key = _folder_key(project_id, folder_path)
    _ACTIVE_PROCESSING.add(key)
    mark_folder_processing(project_id, folder_path, db)
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        domain = get_meta(project).get("engineering_domain") if project else None
        extract_prompt = _extract_prompt(domain)

        db.query(KnowledgeItem).filter(
            KnowledgeItem.project_id == project_id,
            KnowledgeItem.folder_path == folder_path,
        ).delete()
        db.commit()

        texts = _read_folder_texts(folder_path)
        if not texts:
            _set_folder_status(
                project_id,
                folder_path,
                db,
                status="pending",
                error_message=None,
                item_count=0,
            )
            return []

        items: list[KnowledgeItem] = []
        sort_order = 0
        for source_file, text in texts:
            try:
                raw = call_llm_json(
                    [
                        {"role": "system", "content": extract_prompt},
                        {"role": "user", "content": text},
                    ]
                )
                entries = raw if isinstance(raw, list) else raw.get("items", [])
            except Exception as exc:
                logger.warning("知识条目提取失败 %s: %s", source_file, exc)
                continue

            for entry in entries:
                title = (entry.get("title") or "").strip()
                content = (entry.get("content") or "").strip()
                if not title or not content:
                    continue
                item = KnowledgeItem(
                    project_id=project_id,
                    folder_path=folder_path,
                    source_file=source_file,
                    title=title,
                    resume=(entry.get("resume") or "").strip(),
                    content=content,
                    sort_order=sort_order,
                )
                db.add(item)
                items.append(item)
                sort_order += 1

        db.commit()
        if not items:
            _set_folder_status(
                project_id,
                folder_path,
                db,
                status="failed",
                error_message="未能从知识库文件中提取有效条目",
                item_count=0,
            )
            return []

        _embed_items(items, db)
        _set_folder_status(
            project_id,
            folder_path,
            db,
            status="ready",
            error_message=None,
            item_count=len(items),
        )
        return items
    except Exception as exc:
        logger.exception("知识库条目提取失败 %s/%s", project_id, folder_path)
        _set_folder_status(
            project_id,
            folder_path,
            db,
            status="failed",
            error_message=str(exc),
            item_count=get_folder_item_count(folder_path, project_id, db),
        )
        raise
    finally:
        _ACTIVE_PROCESSING.discard(key)


def _format_item(item: KnowledgeItem, folder_path: str | None = None) -> str:
    source = item.source_file or item.title or "项目知识库"
    body = f"【{item.title}】\n{item.resume}\n\n{item.content}".strip()
    return format_labeled_chunk(body, source, folder_path)


def _lexical_rank_items(items: list[KnowledgeItem], query: str) -> list[int]:
    query_tokens = expand_tokens(tokenize(query))
    if not query_tokens:
        return []
    query_token_set = set(query_tokens)
    corpus = [
        expand_tokens(tokenize(f"{item.title} {item.resume} {item.content}")) or [item.title]
        for item in items
    ]
    bm25 = BM25Okapi(corpus)
    bm25_scores = bm25.get_scores(query_tokens)

    scored: list[tuple[float, int, int]] = []
    for idx, item in enumerate(items):
        title_tokens = set(expand_tokens(tokenize(item.title)))
        resume_tokens = set(expand_tokens(tokenize(item.resume or "")))
        content_tokens = set(expand_tokens(tokenize(item.content or "")))
        title_overlap = len(query_token_set & title_tokens)
        resume_overlap = len(query_token_set & resume_tokens)
        content_overlap = len(query_token_set & content_tokens)
        item_content = item.content or ""
        substring_hit = 1 if any(t and t in item_content for t in query_token_set) else 0

        lexical_boost = title_overlap * 3 + resume_overlap * 2 + content_overlap + substring_hit
        base_score = float(bm25_scores[idx])
        score = base_score + lexical_boost
        if score > 0:
            scored.append((score, item.sort_order or 0, idx))

    scored.sort(key=lambda x: (-x[0], x[1]))
    return [idx for _, _, idx in scored]


def _semantic_rank_items(items: list[KnowledgeItem], query: str) -> list[int]:
    if not embedding_service.embedding_available():
        return []
    import config as cfg

    indexed: list[tuple[int, np.ndarray]] = []
    for i, item in enumerate(items):
        blob = getattr(item, "embedding", None)
        if not blob or getattr(item, "embedding_model", None) != cfg.EMBEDDING_MODEL_PATH:
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


def search_knowledge_items(
    query: str,
    folder_path: str,
    project_id: str,
    db: Session,
    top_k: int = 5,
    *,
    use_vector: bool = True,
) -> list[str]:
    items = list_items(folder_path, project_id, db)
    if not items:
        return []
    if not expand_tokens(tokenize(query)):
        return []

    lexical_ranks = _lexical_rank_items(items, query)
    semantic_ranks = _semantic_rank_items(items, query) if use_vector else []
    if semantic_ranks:
        merged = rrf_merge([lexical_ranks, semantic_ranks])
    else:
        merged = lexical_ranks

    return [_format_item(items[i], folder_path) for i in merged[:top_k]]


def delete_item(item_id: str, db: Session) -> bool:
    item = db.query(KnowledgeItem).filter(KnowledgeItem.id == item_id).first()
    if not item:
        return False
    db.delete(item)
    db.commit()
    return True
