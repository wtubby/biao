"""标准库批量导入与覆盖度接口测试。"""

from __future__ import annotations

import io
import uuid

from db.database import SessionLocal, init_db
from routers.standards import parse_uploaded_table
from services.qa_rules import normalize_standard_core
from services.standards_service import import_standards_rows, list_standards, resolve_standard


def test_import_standards_rows_from_csv():
    init_db()
    n1 = 82000 + (uuid.uuid4().int % 1000)
    n2 = 83000 + (uuid.uuid4().int % 1000)
    code1 = f"GB/T {n1}"
    code2 = f"GB/T {n2}"
    csv_text = (
        "编号,标题,类别,状态,适用领域\n"
        f"{code1},电缆敷设规范,国标,active,电力工程\n"
        f"{code2},架空线路验收,国标,draft,电力工程；市政工程\n"
        ",空编号应跳过,国标,active,电力工程\n"
    )
    rows = parse_uploaded_table("sample.csv", csv_text.encode("utf-8-sig"))
    assert len(rows) == 3

    db = SessionLocal()
    try:
        # 预置一条以便覆盖 updated 分支
        from services.standards_service import upsert_standard, link_domains

        core1 = normalize_standard_core(code1)
        upsert_standard(db, code=core1, raw_code=code1, title="旧标题", status="draft")
        link_domains(db, core1, ["电力工程"])

        result = import_standards_rows(db, rows)
        assert result["created"] == 1
        assert result["updated"] == 1
        assert len(result["errors"]) == 1
        assert "编号为空" in result["errors"][0]

        hit = resolve_standard(db, code1)
        assert hit is not None
        assert hit["title"] == "电缆敷设规范"
        assert hit["status"] == "active"

        items = list_standards(db, domain="电力工程", q=str(n2))
        assert any(normalize_standard_core(code2) == it["code"] for it in items)
    finally:
        db.close()


def test_coverage_api_structure():
    from routers.standards import coverage_api

    init_db()
    db = SessionLocal()
    try:
        data = coverage_api(db)
        assert "domains" in data
        assert isinstance(data["domains"], list)
        assert data["domains"]
        row = data["domains"][0]
        assert {"domain", "label", "active", "draft"} <= set(row.keys())
    finally:
        db.close()


def test_parse_uploaded_table_xlsx():
    import pandas as pd

    bio = io.BytesIO()
    pd.DataFrame([
        {"编号": "GB/T 84111", "标题": "xlsx导入", "类别": "国标", "状态": "active", "适用领域": "电力工程"},
    ]).to_excel(bio, index=False)
    rows = parse_uploaded_table("demo.xlsx", bio.getvalue())
    assert len(rows) == 1
    assert rows[0]["编号"] == "GB/T 84111"
