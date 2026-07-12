from services.document_parser import ParsedContent, ParsedItem
from services.parser_service import (
    _annotate_pages,
    _chunk_by_pages,
    compute_parse_confidence,
    extract_with_llm,
    save_extraction_results,
)
from services.facts_service import prefill_facts_from_extraction
from services.project_meta import (
    PARSE_STAGE_EXTRACTING,
    get_meta,
    get_parse_progress,
    set_parse_progress,
)
from services.tender_detail_service import mark_fields_manually_confirmed
from db.database import SessionLocal, init_db
from db.models import GlobalFact, Project, TechRequirement
import uuid
from unittest.mock import patch


def test_chunk_by_pages_splits_document():
    items = [
        ParsedItem(text="p1", page=1, kind="paragraph"),
        ParsedItem(text="p10", page=10, kind="paragraph"),
        ParsedItem(text="p16", page=16, kind="paragraph"),
        ParsedItem(text="t20", page=20, kind="table"),
    ]
    chunks = _chunk_by_pages(items, chunk_page_size=15)
    assert len(chunks) == 2
    assert [i.page for i in chunks[0]] == [1, 10]
    assert [i.page for i in chunks[1]] == [16, 20]


def test_annotate_pages_includes_page_markers():
    items = [
        ParsedItem(text="表格A", page=3, kind="table"),
        ParsedItem(text="段落B", page=5, kind="paragraph"),
    ]
    tables = _annotate_pages(items, "table")
    paras = _annotate_pages(items, "paragraph")
    assert "[第3页]" in tables
    assert "表格A" in tables
    assert "[第5页]" in paras
    assert "段落B" in paras


def test_compute_parse_confidence_high_with_complete_extraction():
    parsed = ParsedContent(
        items=[
            ParsedItem(text="表格", page=1, kind="table"),
            *[ParsedItem(text=f"p{i}", page=1, kind="paragraph") for i in range(6)],
        ],
        page_count=10,
    )
    result = {
        "global_params": {
            "name": "测试工程",
            "project_type": "变电站",
            "voltage_level": "220kV",
            "location": "四川",
            "duration_days": 180,
        }
    }
    reqs = [
        TechRequirement(id="1", project_id="p", requirement_title="A", score_value=10, source_page=1, source_text="原文"),
        TechRequirement(id="2", project_id="p", requirement_title="B", score_value=5, source_page=2, source_text="原文"),
    ]
    info = compute_parse_confidence(parsed, result, reqs)
    assert info["confidence"] >= 0.75
    assert info["level"] == "high"


def test_compute_parse_confidence_low_without_requirements():
    parsed = ParsedContent(items=[], page_count=0, error="empty")
    info = compute_parse_confidence(parsed, {}, [])
    assert info["level"] == "low"
    assert info["confidence"] < 0.5
    assert any("未提取" in w for w in info["warnings"])


def test_compute_parse_confidence_municipal_without_voltage():
    """非电力项目无电压等级时，不得因缺 voltage_level 系统性扣置信度。"""
    parsed = ParsedContent(
        items=[
            ParsedItem(text="表格", page=1, kind="table"),
            *[ParsedItem(text=f"p{i}", page=1, kind="paragraph") for i in range(6)],
        ],
        page_count=10,
    )
    result = {
        "global_params": {
            "name": "某某市政道路工程",
            "project_type": "其他",
            "engineering_domain": "市政工程",
            "location": "四川",
            "duration_days": 180,
        }
    }
    reqs = [
        TechRequirement(id="1", project_id="p", requirement_title="A", score_value=10, source_page=1, source_text="原文"),
        TechRequirement(id="2", project_id="p", requirement_title="B", score_value=5, source_page=2, source_text="原文"),
    ]
    info = compute_parse_confidence(parsed, result, reqs)
    assert info["stats"]["global_params_filled"] == 4
    assert info["confidence"] >= 0.75
    assert info["level"] == "high"


def test_prefill_facts_from_extraction_fills_empty_only():
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        project = Project(id=pid, name="测试工程", status="confirming")
        db.add(project)
        db.commit()

        prefill_facts_from_extraction(db, project, [
            {"title": "施工组织配置", "content": "项目经理 1 名，安全员 2 名"},
            {"title": "项目基本信息", "content": "应被忽略"},
        ])
        fact = db.query(GlobalFact).filter(
            GlobalFact.project_id == pid,
            GlobalFact.title == "施工组织配置",
        ).first()
        assert fact is not None
        assert "项目经理" in fact.content

        prefill_facts_from_extraction(db, project, [
            {"title": "质量与安全目标", "content": "争创优质工程"},
        ])
        fact2 = db.query(GlobalFact).filter(
            GlobalFact.project_id == pid,
            GlobalFact.title == "质量与安全目标",
        ).first()
        assert "争创优质工程" in fact2.content

        prefill_facts_from_extraction(db, project, [
            {"title": "施工组织配置", "content": "不应覆盖"},
        ])
        db.refresh(fact)
        assert "项目经理" in fact.content
        assert "不应覆盖" not in fact.content
    finally:
        db.close()


def test_save_extraction_results_skips_manually_confirmed_fields():
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        project = Project(
            id=pid,
            name="用户手动改过的工程名",
            voltage_level="10kV",
            location="宜宾市",
            status="confirming",
        )
        db.add(project)
        db.commit()

        mark_fields_manually_confirmed(project, ["name", "voltage_level", "location", "engineering_domain"])
        db.commit()
        db.refresh(project)

        save_extraction_results(db, project, {
            "global_params": {
                "name": "解析出来的旧工程名",
                "voltage_level": "220kV",
                "location": "成都市",
                "engineering_domain": "市政工程",
                "project_type": "电缆工程",
                "duration_days": 90,
            },
            "requirements": [],
            "tender_detail": {},
        })
        db.refresh(project)

        assert project.name == "用户手动改过的工程名"
        assert project.voltage_level == "10kV"
        assert project.location == "宜宾市"
        assert get_meta(project).get("engineering_domain") != "市政工程"
        assert project.duration_days == 90  # 未确认字段仍可回填
    finally:
        db.close()


def test_save_extraction_results_fills_unconfirmed_fields_normally():
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        project = Project(id=pid, status="confirming")
        db.add(project)
        db.commit()

        save_extraction_results(db, project, {
            "global_params": {
                "name": "首次解析出的工程名",
                "voltage_level": "110kV",
                "location": "泸州市",
                "duration_days": 60,
            },
            "requirements": [],
            "tender_detail": {},
        })
        db.refresh(project)

        assert project.name == "首次解析出的工程名"
        assert project.voltage_level == "110kV"
        assert project.location == "泸州市"
        assert project.duration_days == 60
    finally:
        db.close()


def test_set_parse_progress_writes_stage_and_percent():
    project = Project(id="p-progress", status="parsing")
    set_parse_progress(project, PARSE_STAGE_EXTRACTING, "提取中", chunk_index=2, chunk_total=4)
    progress = get_parse_progress(project)
    assert progress is not None
    assert progress["stage"] == PARSE_STAGE_EXTRACTING
    assert progress["chunk_index"] == 2
    assert progress["chunk_total"] == 4
    assert 15 < progress["percent"] < 85
    assert "提取" in progress["message"]


def test_extract_with_llm_invokes_on_chunk():
    parsed = ParsedContent(
        items=[
            ParsedItem(text="a", page=1, kind="paragraph"),
            ParsedItem(text="b", page=16, kind="paragraph"),
        ],
        page_count=16,
    )
    calls = []

    def on_chunk(idx, total, hint):
        calls.append((idx, total, hint))

    with patch("services.parser_service._extract_single_chunk", return_value={
        "global_params": {},
        "contradictions": [],
        "requirements": [],
        "fact_groups": [],
        "tender_detail": {},
    }):
        extract_with_llm(parsed, on_chunk=on_chunk)

    assert len(calls) == 2
    assert calls[0][0] == 1 and calls[1][0] == 2
    assert calls[0][1] == 2


def test_extract_with_llm_fallback_fills_reference_catalog():
    """单页超长文档：LLM 漏抽时，用全文启发式回填投标文件格式目录。"""
    toc = [
        "一、投标函及投标函附录",
        "二、授权委托书",
        "三、投标保证金",
        "四、报价清单",
        "五、项目实施方案",
        "六、资格审查资料",
    ]
    parsed = ParsedContent(
        items=[ParsedItem(text=t, page=1, kind="paragraph") for t in toc],
        page_count=0,
    )
    with patch("services.parser_service._extract_single_chunk", return_value={
        "global_params": {},
        "contradictions": [],
        "requirements": [],
        "fact_groups": [],
        "tender_detail": {"bid_reference_catalog": ""},
    }):
        # 字数很少，仍走单块路径，但会触发启发式回填
        result = extract_with_llm(parsed)

    assert "项目实施方案" in (result.get("tender_detail") or {}).get("bid_reference_catalog", "")
