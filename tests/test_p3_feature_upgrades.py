"""P3：暗标、以标写标无命中、刚性绑定、商务草稿等。"""

import sys
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

for _mod in ("jieba", "rank_bm25"):
    sys.modules.setdefault(_mod, MagicMock())

from db.database import SessionLocal, init_db
from db.models import Project, TechOutline, TechRequirement
from services.blind_bid_service import check_blind_bid_violations, detect_blind_bid, is_blind_bid
from services.commercial_bid_service import build_commercial_draft
from services.generation_config import update_generation_config
from services.outline_service import validate_coverage
from services.parser_service import apply_blind_bid_detection
from services.project_meta import get_meta
from services.reference_bid_service import select_reference_bid_snippets
from services.tender_detail_service import (
    empty_tender_detail,
    get_tender_detail,
    set_tender_detail,
)
from prompts.writer_prompt import build_writer_user_prompt, load_domain_writing_guide


def test_select_reference_bid_no_hit_returns_empty():
    ref = ("无关段落甲。" * 30 + "\n\n") * 20
    snippets = select_reference_bid_snippets(ref, "主变吊装专项方案 网络计划")
    assert snippets == ""


def test_select_reference_bid_fallback_to_head_when_enabled():
    ref = ("无关段落甲。" * 30 + "\n\n") * 20
    snippets = select_reference_bid_snippets(
        ref, "主变吊装专项方案", fallback_to_head=True
    )
    assert snippets.startswith("无关段落甲")


def test_blind_bid_violations_detect_company():
    errors = check_blind_bid_violations("由某某电力工程有限公司负责实施。")
    assert any("暗标违规" in e for e in errors)


def test_blind_bid_violations_allows_generic_power_company():
    """「电力公司」等行业通用词不应单独判为暗标身份泄露。"""
    errors = check_blind_bid_violations(
        "本工程建成后按规定移交属地电力公司统一调度运行。"
    )
    assert not any("电力公司" in e for e in errors)


def test_blind_bid_violations_detects_self_reference():
    errors = check_blind_bid_violations("我公司承诺按期完工。")
    assert any("我公司" in e for e in errors)


def test_is_blind_bid_reads_tender_detail():
    project = Project(id="p-blind", name="测", status="confirming", extra_params="{}")
    detail = empty_tender_detail()
    detail["notice"]["blind_bid"] = True
    set_tender_detail(project, detail)
    assert is_blind_bid(project) is True


def test_detect_blind_bid_markers():
    assert detect_blind_bid("本项目采用暗标评审方式") is True
    assert detect_blind_bid("技术文件不得出现投标人名称及标识") is True
    assert detect_blind_bid("普通明标项目，无相关要求") is None
    assert detect_blind_bid("") is None


def test_apply_blind_bid_detection_prefills_notice():
    project = Project(id="p-blind-auto", name="测", status="confirming", extra_params="{}")
    assert apply_blind_bid_detection(project, "评标办法：采用匿名评审") is True
    assert get_tender_detail(project)["notice"]["blind_bid"] is True
    assert get_meta(project).get("blind_bid_auto_detected") is True

    project2 = Project(id="p-blind-none", name="测2", status="confirming", extra_params="{}")
    assert apply_blind_bid_detection(project2, "无相关表述") is False
    assert get_tender_detail(project2)["notice"]["blind_bid"] is None
    assert get_meta(project2).get("blind_bid_auto_detected") is False


def test_writer_prompt_includes_blind_and_ref_miss():
    prompt = build_writer_user_prompt({
        "global_params": {"工程名称": "测"},
        "project_overview": "",
        "requirements_text": "评分",
        "retrieval_text": "",
        "last_summary": "",
        "chapter_title": "施工方案",
        "chapter_level": 2,
        "chapter_path": "方案 > 施工方案",
        "guidance": {"brief": "写方案", "content_boundary": "只写本章"},
        "sibling_leaf_titles": [],
        "other_leaf_titles": [],
        "blind_bid_constraints": "## 暗标约束（必须严格遵守）\n- 不得出现公司名",
        "reference_bid_miss": True,
    })
    assert "暗标约束" in prompt
    assert "未检索到相关参考片段" in prompt
    assert "写作惯例提示（非标准条文原文" in build_writer_user_prompt({
        **{
            "global_params": {"工程名称": "测"},
            "project_overview": "",
            "requirements_text": "评分",
            "retrieval_text": "",
            "last_summary": "",
            "chapter_title": "施工方案",
            "chapter_level": 2,
            "chapter_path": "a",
            "guidance": {},
            "sibling_leaf_titles": [],
            "other_leaf_titles": [],
            "standards_hint": "进度类写作提示",
        }
    })


def test_domain_writing_guide_exists_for_municipal():
    guide = load_domain_writing_guide("市政工程")
    assert "市政" in guide


def test_validate_coverage_blocks_uncovered_risk_by_default():
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        db.add(Project(id=pid, name="测试工程", status="planning"))
        risk_id = str(uuid.uuid4())
        db.add(
            TechRequirement(
                id=risk_id,
                project_id=pid,
                requirement_title="刚性项",
                score_value=10,
                status="confirmed",
                is_risk_item=1,
            )
        )
        db.add(
            TechOutline(
                id="leaf-1",
                project_id=pid,
                title="施工方案",
                sort_order=1,
                level=1,
                is_leaf=1,
                requirement_ids="[]",
            )
        )
        db.commit()
        result = validate_coverage(db, pid)
        assert result["passed"] is False
        assert result["require_risk_binding"] is True
        assert any(i["id"] == risk_id for i in result["uncovered_risk_items"])

        project = db.query(Project).filter(Project.id == pid).first()
        update_generation_config(project, require_risk_binding=False)
        db.commit()
        result2 = validate_coverage(db, pid)
        assert result2["passed"] is True
        assert result2["require_risk_binding"] is False
    finally:
        db.close()


def test_commercial_draft_builds_from_tender_detail():
    project = Project(id="p-com", name="示范变电站工程", status="confirming", extra_params="{}")
    detail = empty_tender_detail()
    detail["commerce_requirements"] = "投标保证金 50 万元"
    detail["qualification_items"] = [
        {"seq": 1, "item_label": "资格性审查", "description": "具备电力承装资质"}
    ]
    detail["commerce_scores"] = [
        {"title": "业绩", "criteria": "近三年同类业绩", "score_value": 10}
    ]
    set_tender_detail(project, detail)
    draft = build_commercial_draft(project)
    assert "商务与资格响应" in draft["markdown"]
    assert draft["qualification_count"] == 1
    assert "具备电力承装资质" in draft["markdown"]
