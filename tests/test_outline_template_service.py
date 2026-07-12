from services.outline_template_service import get_outline_template, list_outline_templates


def test_list_outline_templates_includes_builtin_templates():
    templates = list_outline_templates()
    ids = {item["id"] for item in templates}
    assert "substation_new" in ids
    assert "transmission_line" in ids
    assert "epc_general" in ids


def test_get_outline_template_returns_catalog_text():
    tpl = get_outline_template("substation_new")
    assert tpl["name"]
    assert "工程概况" in tpl["text"]
    assert "施工组织设计" in tpl["text"]
    assert tpl["text"].startswith("（一）")
