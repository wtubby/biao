from services.tender_detail_service import (
    apply_notice_to_project,
    empty_tender_detail,
    filter_qualification_items,
    get_tender_detail,
    mark_fields_manually_confirmed,
    merge_tender_detail,
    notice_values_equal,
    protectable_fields_from_notice_changes,
    protectable_fields_from_notice_keys,
    save_tender_detail_from_extraction,
    set_tender_detail,
    _normalize_qualification_items,
    _parse_duration_days,
)
from services.project_meta import set_meta
from db.database import SessionLocal, init_db
from db.models import Project
import uuid


def test_parse_duration_days_from_text():
    assert _parse_duration_days("自合同签订之日起 60 个日历天") == 60
    assert _parse_duration_days("90天") == 90
    assert _parse_duration_days("工期为180日历日") == 180
    assert _parse_duration_days("自合同签订之日起180个日历日内完工") == 180
    assert _parse_duration_days("") is None


def test_protectable_fields_from_notice_keys_only_maps_touched():
    assert protectable_fields_from_notice_keys(["blind_bid"]) == []
    assert protectable_fields_from_notice_keys(["blind_bid", "voltage_level"]) == ["voltage_level"]
    assert set(protectable_fields_from_notice_keys([
        "project_name", "duration_text", "bid_domain", "blind_bid", "tenderer",
    ])) == {"name", "duration_days", "engineering_domain"}


def test_protectable_fields_from_notice_changes_ignores_unchanged_values():
    stored = {
        "project_name": "电缆工程",
        "voltage_level": "10kV",
        "location": "成都",
        "budget_yuan": 1000000.0,
        "target_pages": 40,
    }
    touched = {
        "project_name": "电缆工程",
        "voltage_level": "10kV",
        "location": "成都",
        "budget_yuan": 1000000,
        "target_pages": 40,
        "blind_bid": True,
        "capacity": "新建 2km",
    }
    assert protectable_fields_from_notice_changes(stored, touched) == ["capacity"]


def test_notice_values_equal_treats_none_and_empty_string_as_same():
    assert notice_values_equal(None, "")
    assert notice_values_equal("", None)
    assert not notice_values_equal(None, "10kV")
    assert notice_values_equal(40, 40.0)


def test_apply_notice_to_project_parses_calendar_ri_duration():
    """招标详情保存（force=True）时，日历日措辞应同步 duration_days。"""
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        project = Project(id=pid, duration_days=90, status="confirming")
        db.add(project)
        db.commit()

        apply_notice_to_project(
            project,
            {"duration_text": "工期为180日历日"},
            force=True,
        )
        db.commit()
        db.refresh(project)

        assert project.duration_days == 180
    finally:
        db.close()


def test_merge_tender_detail_fills_notice_and_dedupes():
    target = empty_tender_detail()
    incoming = {
        "notice": {"project_name": "电缆工程", "project_code": "ZB-001"},
        "commerce_requirements": "投标保证金 6 万元",
        "qualification_items": [
            {"seq": 1, "item_label": "资格性废标", "description": "无营业执照"},
        ],
        "commerce_scores": [
            {"title": "业绩", "criteria": "有业绩得 5 分", "score_value": 5},
        ],
    }
    merge_tender_detail(target, incoming)
    merge_tender_detail(target, incoming)
    assert target["notice"]["project_name"] == "电缆工程"
    assert len(target["qualification_items"]) == 1
    assert len(target["commerce_scores"]) == 1


def test_merge_tender_detail_keeps_unnamed_scores_with_different_criteria():
    """标题缺失时兜底名相同，不能仅按 title 去重吞掉不同评分项。"""
    target = empty_tender_detail()
    incoming = {
        "commerce_scores": [
            {"title": "", "criteria": "报价合理性，满分5分", "score_value": 5},
            {"title": "", "criteria": "付款方式优惠程度，满分3分", "score_value": 3},
        ],
    }
    merge_tender_detail(target, incoming)
    assert len(target["commerce_scores"]) == 2
    assert {s["criteria"] for s in target["commerce_scores"]} == {
        "报价合理性，满分5分",
        "付款方式优惠程度，满分3分",
    }
    # 真正重复（同 title + 同 criteria）仍应去重
    merge_tender_detail(target, incoming)
    assert len(target["commerce_scores"]) == 2


def test_filter_qualification_items_by_tab():
    items = [
        {"seq": 1, "item_label": "资格性废标", "description": "a"},
        {"seq": 2, "item_label": "符合性废标", "description": "b"},
        {"seq": 3, "item_label": "实质性废标", "description": "c"},
        {"seq": 4, "item_label": "其他废标情形", "description": "d"},
    ]
    assert len(filter_qualification_items(items, "资格性审查")) == 1
    assert len(filter_qualification_items(items, "符合性审查")) == 1
    result = filter_qualification_items(items, "废标项")
    assert len(result) == 2
    assert {i["item_label"] for i in result} == {"实质性废标", "其他废标情形"}


def test_normalize_qualification_keeps_source_text_contrast():
    items = _normalize_qualification_items([
        {
            "seq": 1,
            "item_label": "资格性废标",
            "description": "未提供营业执照",
            "source_text": "投标人未提供有效的营业执照复印件的，作废标处理。",
            "source_page": 12,
        },
        {
            "seq": 2,
            "item_label": "符合性废标",
            "description": "响应文件密封不符合要求",
        },
    ])
    assert items[0]["source_text"].startswith("投标人未提供")
    assert items[0]["description"] == "未提供营业执照"
    assert items[0]["source_page"] == 12
    # 旧数据无 source_text 时回填为 description
    assert items[1]["source_text"] == "响应文件密封不符合要求"
    assert items[1]["description"] == "响应文件密封不符合要求"


def test_save_tender_detail_from_extraction_syncs_project():
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        project = Project(id=pid, status="confirming")
        db.add(project)
        db.commit()

        result = {
            "global_params": {
                "name": "未来城电缆工程",
                "project_type": "电缆工程",
                "engineering_domain": "电力工程",
                "voltage_level": "10kV",
                "location": "宜宾市叙州区",
                "duration_days": 60,
                "budget_yuan": 3593026,
            },
            "tender_detail": {
                "notice": {"tenderer": "四川某电力公司"},
                "commerce_requirements": "保证金 6 万",
                "service_requirements": "YJV22 电缆",
                "qualification_items": [],
                "commerce_scores": [],
            },
        }
        save_tender_detail_from_extraction(project, result)
        db.commit()
        db.refresh(project)

        assert project.name == "未来城电缆工程"
        assert project.duration_days == 60
        assert project.location == "宜宾市叙州区"
    finally:
        db.close()


def test_apply_notice_to_project_skips_manually_confirmed_fields():
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        project = Project(id=pid, name="用户手动改过的工程名", status="confirming")
        db.add(project)
        db.commit()

        mark_fields_manually_confirmed(project, ["name"])
        db.commit()
        db.refresh(project)

        apply_notice_to_project(project, {"project_name": "解析出来的旧工程名"})
        db.commit()
        db.refresh(project)

        assert project.name == "用户手动改过的工程名"  # 没有被覆盖
    finally:
        db.close()


def test_apply_notice_to_project_force_overwrites_confirmed_fields():
    """用户在招标详情面板保存时 force=True，应覆盖已确认字段。"""
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        project = Project(id=pid, name="旧确认名", status="confirming")
        db.add(project)
        db.commit()

        mark_fields_manually_confirmed(project, ["name"])
        db.commit()
        db.refresh(project)

        apply_notice_to_project(project, {"project_name": "招标详情里改的新名"}, force=True)
        db.commit()
        db.refresh(project)

        assert project.name == "招标详情里改的新名"
    finally:
        db.close()


def test_apply_notice_to_project_fills_unconfirmed_fields_normally():
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        project = Project(id=pid, status="confirming")
        db.add(project)
        db.commit()

        apply_notice_to_project(project, {"project_name": "首次解析出的工程名"})
        db.commit()
        db.refresh(project)

        assert project.name == "首次解析出的工程名"  # 未手动确认过，照常回填
    finally:
        db.close()


def test_sync_project_to_notice_writes_shared_fields():
    init_db()
    db = SessionLocal()
    try:
        pid = str(uuid.uuid4())
        project = Project(
            id=pid,
            name="同步工程名",
            voltage_level="10kV",
            capacity="80MVA",
            location="成都",
            duration_days=45,
            status="confirming",
        )
        db.add(project)
        db.commit()
        set_meta(project, project_type="变电工程", contract_mode="EPC", engineering_domain="电力工程")
        set_tender_detail(project, {"notice": {"agency": "保留代理"}})
        db.commit()
        db.refresh(project)

        from services.tender_detail_service import sync_project_to_notice

        sync_project_to_notice(project)
        db.commit()
        db.refresh(project)

        notice = get_tender_detail(project)["notice"]
        assert notice["project_name"] == "同步工程名"
        assert notice["voltage_level"] == "10kV"
        assert notice["duration_text"] == "45个日历天"
        assert notice["project_type"] == "变电工程"
        assert notice["agency"] == "保留代理"
    finally:
        db.close()
