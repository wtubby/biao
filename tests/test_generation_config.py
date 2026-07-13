from services.generation_config import (
    BID_CATEGORY_CONSTRUCTION_ORG,
    BID_CATEGORY_PROCUREMENT,
    BODY_FORMAT_LIST,
    CHART_DENSITY_ABUNDANT,
    bid_category_hint,
    body_format_hint,
    build_generation_hints,
    chart_density_hint,
    default_generation_config,
    get_generation_config,
    list_bid_category_options,
    smartart_hint,
    update_generation_config,
)
from services.word_estimate import estimate_from_leaves, format_word_count_display
from db.models import Project


def test_default_generation_config():
    cfg = default_generation_config()
    assert cfg["chart_density"] == "normal"
    assert cfg["use_knowledge_library"] is True


def test_chart_density_hint_variants():
    assert "尽量不插入" in chart_density_hint("none")
    assert "多使用" in chart_density_hint(CHART_DENSITY_ABUNDANT)


def test_estimate_from_leaves():
    leaves = [{"target_words": 1000}, {"target_words": 2000}]
    est = estimate_from_leaves(leaves, target_pages=40)
    assert est["total_words"] == 40 * est["words_per_page"]
    assert est["estimated_pages"] == 40
    assert est["leaf_words_sum"] == 3000
    assert format_word_count_display(67600) == "6.76万字"


def test_estimate_from_leaves_custom_word_count():
    leaves = [{"target_words": 1000}, {"target_words": 2000}]
    est = estimate_from_leaves(
        leaves,
        target_pages=40,
        custom_word_count=True,
        custom_total_words=50000,
    )
    assert est["total_words"] == 50000
    assert est["estimated_pages"] == round(50000 / est["words_per_page"])


def test_update_generation_config_on_project():
    project = Project(id="p1", extra_params="{}")
    update_generation_config(project, chart_density="none", use_knowledge_library=False)
    cfg = get_generation_config(project)
    assert cfg["chart_density"] == "none"
    assert cfg["use_knowledge_library"] is False


def test_default_generation_config_standards_pack_by_domain():
    assert default_generation_config("电力工程")["standards_pack"] == "epc_guide"
    assert default_generation_config("市政工程")["standards_pack"] == "none"
    assert default_generation_config(None)["standards_pack"] == "epc_guide"


def test_get_generation_config_defaults_non_power_domain_to_no_pack():
    project = Project(id="p2", extra_params='{"engineering_domain": "市政工程"}')
    cfg = get_generation_config(project)
    assert cfg["standards_pack"] == "none"


def test_bid_category_body_format_and_smartart_defaults():
    cfg = default_generation_config()
    assert cfg["bid_category"] == "engineering_tech"
    assert cfg["body_format"] == "general"
    assert cfg["smartart_enabled"] is False


def test_list_bid_category_options_has_five_types():
    options = list_bid_category_options()
    assert len(options) == 5
    labels = {opt["label"] for opt in options}
    assert "施工组织设计" in labels
    assert "危大工程方案" in labels


def test_legacy_bid_category_mapped_on_read():
    project = Project(
        id="p_legacy",
        extra_params='{"generation_config": {"bid_category": "engineering"}}',
    )
    cfg = get_generation_config(project)
    assert cfg["bid_category"] == "engineering_tech"


def test_build_generation_hints_includes_smartart_when_enabled():
    hints = build_generation_hints({
        "chart_density": "normal",
        "bid_category": "procurement_goods",
        "body_format": "list_items",
        "smartart_enabled": True,
    })
    assert "采购" in hints["bid_category_hint"]
    assert "列表" in hints["body_format_hint"]
    assert "ORG_DATA" in hints["chart_density_hint"]
    assert "SmartArt" in hints["chart_density_hint"]


def test_update_generation_config_new_fields():
    project = Project(id="p3", extra_params="{}")
    update_generation_config(
        project,
        bid_category=BID_CATEGORY_CONSTRUCTION_ORG,
        body_format=BODY_FORMAT_LIST,
        smartart_enabled=True,
    )
    cfg = get_generation_config(project)
    assert cfg["bid_category"] == "construction_org"
    assert cfg["body_format"] == "list_items"
    assert cfg["smartart_enabled"] is True


def test_smartart_hint_empty_when_disabled():
    assert smartart_hint(False) == ""
    assert "ORG_DATA" in smartart_hint(True)
