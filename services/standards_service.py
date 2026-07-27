"""标准规范库：登记、状态变更、知识库冷启动导入。"""

from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import or_
from sqlalchemy.orm import Session

from config import KNOWLEDGE_ROOT
from db.models import (
    KnowledgeChunk,
    StandardChangeLog,
    StandardChunkLink,
    StandardDomainLink,
    StandardReference,
)
from services.qa_rules import extract_standard_codes, normalize_standard_core

_UPDATABLE_FIELDS = frozenset({
    "raw_code",
    "title",
    "category",
    "issuing_body",
    "status",
    "effective_date",
    "superseded_by",
    "summary",
    "key_clauses",
    "source_note",
})

_INSERT_DEFAULTS = {
    "title": "",
    "category": "国标",
    "status": "draft",
}


def normalize_code(raw: str) -> str:
    return normalize_standard_core(raw)


def _to_dict(ref: StandardReference) -> dict:
    return {
        "code": ref.code,
        "raw_code": ref.raw_code,
        "title": ref.title,
        "category": ref.category,
        "issuing_body": ref.issuing_body,
        "status": ref.status,
        "effective_date": ref.effective_date,
        "superseded_by": ref.superseded_by,
        "summary": ref.summary,
        "key_clauses": ref.key_clauses,
        "source_note": ref.source_note,
    }


def _str_val(value: object | None) -> str | None:
    if value is None:
        return None
    return str(value)


def upsert_standard(
    db: Session,
    *,
    code: str,
    raw_code: str | None = None,
    title: str | None = None,
    category: str | None = None,
    status: str | None = None,
    **kwargs,
) -> StandardReference:
    """存在则按传入字段更新并写变更日志；不存在则插入。"""
    norm = normalize_code(code)
    incoming: dict = {}
    if raw_code is not None:
        incoming["raw_code"] = raw_code
    if title is not None:
        incoming["title"] = title
    if category is not None:
        incoming["category"] = category
    if status is not None:
        incoming["status"] = status
    for key, value in kwargs.items():
        if key in _UPDATABLE_FIELDS:
            incoming[key] = value

    existing = db.query(StandardReference).filter(StandardReference.code == norm).first()
    if existing is None:
        data = {**_INSERT_DEFAULTS, **incoming}
        data["raw_code"] = data.get("raw_code") or code
        ref = StandardReference(code=norm, **data)
        db.add(ref)
        db.commit()
        db.refresh(ref)
        return ref

    for field, new_val in incoming.items():
        old_val = getattr(existing, field)
        if _str_val(old_val) != _str_val(new_val):
            db.add(
                StandardChangeLog(
                    code=norm,
                    field=field,
                    old_value=_str_val(old_val),
                    new_value=_str_val(new_val),
                )
            )
            setattr(existing, field, new_val)
    db.commit()
    db.refresh(existing)
    return existing


def mark_superseded(db: Session, code: str, by_code: str) -> None:
    upsert_standard(db, code=code, status="superseded", superseded_by=by_code)


def mark_withdrawn(db: Session, code: str) -> None:
    upsert_standard(db, code=code, status="withdrawn")


def mark_active(db: Session, code: str) -> None:
    upsert_standard(db, code=code, status="active")


def resolve_standard(db: Session, code: str) -> dict | None:
    norm = normalize_code(code)
    ref = db.query(StandardReference).filter(StandardReference.code == norm).first()
    if ref is None:
        return None
    return _to_dict(ref)


def list_standards(
    db: Session,
    *,
    domain: str | None = None,
    status: str | None = None,
    q: str | None = None,
    limit: int = 200,
) -> list[dict]:
    query = db.query(StandardReference)
    if domain:
        query = query.join(
            StandardDomainLink,
            StandardDomainLink.code == StandardReference.code,
        ).filter(StandardDomainLink.domain_key == domain)
    if status:
        query = query.filter(StandardReference.status == status)
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                StandardReference.code.like(like),
                StandardReference.raw_code.like(like),
                StandardReference.title.like(like),
            )
        )
    rows = query.order_by(StandardReference.code).limit(limit).all()
    return _attach_domains(db, [_to_dict(r) for r in rows])


def _attach_domains(db: Session, items: list[dict]) -> list[dict]:
    if not items:
        return items
    codes = [item["code"] for item in items]
    links = (
        db.query(StandardDomainLink)
        .filter(StandardDomainLink.code.in_(codes))
        .all()
    )
    by_code: dict[str, list[str]] = {}
    for link in links:
        by_code.setdefault(link.code, []).append(link.domain_key)
    for item in items:
        item["domains"] = by_code.get(item["code"], [])
    return items


def get_standard_detail(db: Session, code: str) -> dict | None:
    ref = resolve_standard(db, code)
    if ref is None:
        return None
    norm = normalize_code(code)
    domains = [
        link.domain_key
        for link in db.query(StandardDomainLink).filter(StandardDomainLink.code == norm).all()
    ]
    chunk_ids = [
        link.chunk_id
        for link in db.query(StandardChunkLink).filter(StandardChunkLink.code == norm).all()
    ]
    chunks: list[dict] = []
    if chunk_ids:
        rows = db.query(KnowledgeChunk).filter(KnowledgeChunk.id.in_(chunk_ids)).all()
        for chunk in rows:
            text = chunk.text or ""
            chunks.append({
                "id": chunk.id,
                "folder_path": chunk.folder_path,
                "source_file": chunk.source_file,
                "text": text[:500],
            })
    return {**ref, "domains": domains, "chunks": chunks}


def import_standards_rows(db: Session, rows: list[dict]) -> dict:
    """批量导入表格行；列名：编号/标题/类别/状态/适用领域。"""
    created, updated = 0, 0
    errors: list[str] = []
    for i, row in enumerate(rows):
        code = str(row.get("编号") or "").strip()
        if not code:
            errors.append(f"第 {i + 2} 行：编号为空，已跳过")
            continue
        existed = resolve_standard(db, normalize_code(code)) is not None
        ref = upsert_standard(
            db,
            code=code,
            raw_code=code,
            title=str(row.get("标题") or "").strip(),
            category=str(row.get("类别") or "国标").strip() or "国标",
            status=str(row.get("状态") or "active").strip() or "active",
        )
        domains_raw = str(row.get("适用领域") or "")
        domains = [
            d.strip()
            for d in domains_raw.replace(";", "；").split("；")
            if d.strip()
        ]
        if domains:
            link_domains(db, ref.code, domains)
        if existed:
            updated += 1
        else:
            created += 1
    return {"created": created, "updated": updated, "errors": errors}


def link_domains(db: Session, code: str, domain_keys: list[str]) -> None:
    """全量覆盖式更新：先删再按传入列表重建。"""
    norm = normalize_code(code)
    db.query(StandardDomainLink).filter(StandardDomainLink.code == norm).delete()
    seen: set[str] = set()
    for key in domain_keys:
        dk = (key or "").strip()
        if not dk or dk in seen:
            continue
        seen.add(dk)
        db.add(StandardDomainLink(code=norm, domain_key=dk))
    db.commit()


def _resolve_bootstrap_folders(domain: str | None) -> list[str]:
    from services.knowledge_registry import disk_knowledge_folders, get_knowledge_folders

    if domain:
        return list(get_knowledge_folders(engineering_domain=domain))
    return sorted(disk_knowledge_folders())


def _ensure_chunks_for_folder(db: Session, folder: str) -> list[KnowledgeChunk]:
    existing = (
        db.query(KnowledgeChunk)
        .filter(KnowledgeChunk.folder_path == folder)
        .all()
    )
    if existing:
        return existing

    root = Path(KNOWLEDGE_ROOT)
    folder_dir = root / folder
    if not folder_dir.is_dir():
        return []

    rows: list[KnowledgeChunk] = []
    for path in sorted(folder_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".txt", ".md"}:
            continue
        if path.name.startswith("_") or path.name.lower() == "readme.md":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").strip()
        except OSError:
            continue
        if len(text) < 10:
            continue
        chunk_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:40]
        row = KnowledgeChunk(
            folder_path=folder,
            source_file=str(path.relative_to(root)).replace("\\", "/"),
            chunk_hash=chunk_hash,
            text=text,
        )
        db.add(row)
        rows.append(row)
    if rows:
        db.flush()
    return rows


def _ensure_chunk_link(db: Session, code: str, chunk_id: str) -> None:
    exists = (
        db.query(StandardChunkLink)
        .filter(
            StandardChunkLink.code == code,
            StandardChunkLink.chunk_id == chunk_id,
        )
        .first()
    )
    if exists is None:
        db.add(StandardChunkLink(code=code, chunk_id=chunk_id))


def _ensure_domain_link(db: Session, code: str, domain_key: str) -> None:
    exists = (
        db.query(StandardDomainLink)
        .filter(
            StandardDomainLink.code == code,
            StandardDomainLink.domain_key == domain_key,
        )
        .first()
    )
    if exists is None:
        db.add(StandardDomainLink(code=code, domain_key=domain_key))


def bootstrap_from_knowledge_base(db: Session, *, domain: str | None = None) -> int:
    """从知识库文本提取标准号，冷启动写入 draft 条目与 chunk 关联。已存在编号跳过。"""
    folders = _resolve_bootstrap_folders(domain)
    created = 0
    for folder in folders:
        chunks = _ensure_chunks_for_folder(db, folder)
        for chunk in chunks:
            codes = extract_standard_codes(chunk.text or "")
            for raw in codes:
                core = normalize_code(raw)
                if not core:
                    continue
                existing = (
                    db.query(StandardReference)
                    .filter(StandardReference.code == core)
                    .first()
                )
                if existing is None:
                    upsert_standard(
                        db,
                        code=core,
                        raw_code=raw,
                        status="draft",
                        source_note="自动导入待人工核实",
                    )
                    created += 1
                _ensure_chunk_link(db, core, chunk.id)
                if domain:
                    _ensure_domain_link(db, core, domain)
        db.commit()
    return created
