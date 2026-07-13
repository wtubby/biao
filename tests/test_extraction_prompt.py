"""招标解析 Prompt 关键约束。"""

from prompts.extraction_prompt import build_extraction_user_prompt, get_extraction_system_prompt


def test_extraction_system_prompt_json_and_page_rules():
    prompt = get_extraction_system_prompt()
    assert "JSON 输出硬约束" in prompt
    assert "\\\\n" in prompt or "\\n" in prompt
    assert "[第X页]" in prompt
    assert "归类摘要" in prompt


def test_extraction_user_prompt_strict_compliance_block():
    user = build_extraction_user_prompt("表1", "段1")
    assert "严格合规要求" in user
    assert "JSON 规范转义" in user
    assert "description 仅写归类摘要" in user
    assert "以 { 开头" in user
    assert "禁止" in user and "```json" in user
    assert "表1" in user
    assert "段1" in user
