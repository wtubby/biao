"""领域注册表单测。"""

from prompts.writer_prompt import (
    _writer_identity,
    get_writer_system_prompt,
    load_domain_writing_guide,
)
from domains.registry import (
    DEFAULT_DOMAIN,
    clear_domain_cache,
    list_domain_keys,
    resolve_domain,
)


def test_default_domain_is_power():
    assert DEFAULT_DOMAIN == "电力工程"
    spec = resolve_domain(None)
    assert spec.key == "电力工程"


def test_resolve_domain_alias_architecture():
    spec = resolve_domain("房建工程")
    assert spec.key == "建筑工程"
    assert "房屋建筑" in spec.identity_prompt


def test_list_domain_keys_unique():
    items = list_domain_keys()
    keys = [i["key"] for i in items]
    assert keys.count("电力工程") == 1
    assert "市政工程" in keys
    assert "建筑工程" in keys
    assert "水利工程" in keys


def test_power_identity_matches_legacy():
    expected = "你是资深电力工程技术方案撰写专家，熟悉变电站、线路、设备安装等各类电力工程。"
    assert _writer_identity("电力工程") == expected
    assert _writer_identity(None) == expected


def test_power_guide_loads():
    guide = load_domain_writing_guide("电力工程")
    assert guide
    assert "电力" in guide or "EPC" in guide or "施工" in guide


def test_unknown_domain_no_guide_still_has_identity():
    clear_domain_cache()
    prompt = get_writer_system_prompt("轨道交通工程")
    assert "轨道交通工程" in prompt
    assert "技术方案撰写专家" in prompt
    # 无指南文件时不应挂空规范标题块导致异常
    assert "## 轨道交通工程技术标写作规范" not in prompt


def test_municipal_has_guide_section():
    prompt = get_writer_system_prompt("市政工程", compact=False)
    assert "市政工程" in prompt
    assert "技术标写作规范" in prompt


def test_municipal_compact_omits_full_guide():
    prompt = get_writer_system_prompt("市政工程", compact=True)
    assert "市政工程" in prompt
    assert "技术标写作规范" not in prompt
