"""标准规范库管理接口。"""

from __future__ import annotations

import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from services.standards_service import (
    bootstrap_from_knowledge_base,
    get_standard_detail,
    import_standards_rows,
    link_domains,
    list_standards,
    mark_superseded,
    mark_withdrawn,
    upsert_standard,
)

router = APIRouter(prefix="/api/standards", tags=["standards"])


class StandardUpsertBody(BaseModel):
    raw_code: str | None = None
    title: str | None = None
    category: str | None = None
    issuing_body: str | None = None
    status: str | None = None
    effective_date: str | None = None
    superseded_by: str | None = None
    summary: str | None = None
    key_clauses: str | None = None
    source_note: str | None = None
    domains: list[str] | None = None


class SupersededBody(BaseModel):
    by_code: str


def parse_uploaded_table(filename: str, raw: bytes) -> list[dict]:
    """按 xlsx skill 约定：CSV/TSV 用 pandas；xlsx 用 pandas.read_excel（底层 openpyxl）。"""
    import pandas as pd

    name = (filename or "").lower()
    bio = io.BytesIO(raw)
    try:
        if name.endswith(".csv") or name.endswith(".tsv"):
            sep = "\t" if name.endswith(".tsv") else ","
            df = pd.read_csv(bio, dtype=str, sep=sep).fillna("")
        elif name.endswith((".xlsx", ".xlsm")):
            df = pd.read_excel(bio, dtype=str, engine="openpyxl").fillna("")
        else:
            raise HTTPException(status_code=400, detail="仅支持 .csv / .tsv / .xlsx 文件")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"表格解析失败：{exc}") from exc
    return df.to_dict(orient="records")


@router.get("")
def list_standards_api(
    domain: str | None = None,
    status: str | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
):
    return {"items": list_standards(db, domain=domain, status=status, q=q)}


@router.get("/coverage")
def coverage_api(db: Session = Depends(get_db)):
    from domains.registry import list_domain_keys

    result = []
    for d in list_domain_keys():
        key = d["key"]
        active = len(list_standards(db, domain=key, status="active"))
        draft = len(list_standards(db, domain=key, status="draft"))
        result.append({
            "domain": key,
            "label": d["label"],
            "active": active,
            "draft": draft,
        })
    return {"domains": result}


@router.post("/import")
async def import_standards(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    raw = await file.read()
    rows = parse_uploaded_table(file.filename or "", raw)
    return import_standards_rows(db, rows)


@router.post("/bootstrap")
def bootstrap_api(domain: str | None = None, db: Session = Depends(get_db)):
    count = bootstrap_from_knowledge_base(db, domain=domain)
    return {"created": count}


@router.get("/{code}")
def get_standard_api(code: str, db: Session = Depends(get_db)):
    detail = get_standard_detail(db, code)
    if detail is None:
        raise HTTPException(status_code=404, detail="标准不存在")
    return detail


@router.put("/{code}")
def upsert_standard_api(
    code: str,
    body: StandardUpsertBody,
    db: Session = Depends(get_db),
):
    data = body.model_dump(exclude_unset=True)
    domains = data.pop("domains", None)
    ref = upsert_standard(db, code=code, **data)
    if domains is not None:
        link_domains(db, ref.code, domains)
    return {"code": ref.code}


@router.post("/{code}/mark-superseded")
def mark_superseded_api(
    code: str,
    body: SupersededBody,
    db: Session = Depends(get_db),
):
    mark_superseded(db, code, body.by_code)
    return {"ok": True}


@router.post("/{code}/mark-withdrawn")
def mark_withdrawn_api(code: str, db: Session = Depends(get_db)):
    mark_withdrawn(db, code)
    return {"ok": True}
