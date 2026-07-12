from services.generation_config import (
    CHART_DENSITY_ABUNDANT,
    chart_density_hint,
    default_generation_config,
    get_generation_config,
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
