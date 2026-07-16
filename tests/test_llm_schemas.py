"""LLM Schema 与模型分路单元测试。"""

import pytest
from pydantic import ValidationError

from llm.llm_client import resolve_model
from llm.schemas import QAMultiWindowResult, QAResult, WriterOutputSchema


def test_qa_result_coerces_issue_lists():
    result = QAResult.model_validate({
        "passed": False,
        "coverage_issues": ["漏写工期", "", None],
        "faithfulness_issues": None,
    })
    assert result.passed is False
    assert result.coverage_issues == ["漏写工期"]
    assert result.faithfulness_issues == []


def test_qa_result_ignores_extra_fields():
    result = QAResult.model_validate({"passed": True, "skipped": True, "unknown": 1})
    assert result.passed is True
    assert not hasattr(result, "skipped") or getattr(result, "skipped", None) is not True


def test_qa_multi_window_result_merges_shape():
    result = QAMultiWindowResult.model_validate({
        "segments": [
            {
                "label": "开头",
                "passed": True,
                "coverage_issues": [],
            },
            {
                "label": "中段",
                "passed": False,
                "coverage_issues": ["缺工序"],
                "specificity_issues": ["未见电压等级"],
            },
        ],
        "extra": 1,
    })
    assert len(result.segments) == 2
    assert result.segments[1].coverage_issues == ["缺工序"]
    assert result.segments[1].specificity_issues == ["未见电压等级"]


def test_writer_output_schema_resolves_aliases():
    schema = WriterOutputSchema.model_validate({
        "content": "正文段落",
        "charts": [{"type": "GANTT_DATA", "data": [{"工序": "A"}]}],
    })
    assert schema.resolved_markdown() == "正文段落"
    assert len(schema.resolved_charts_raw()) == 1


def test_writer_output_schema_filters_invalid_chart_entries():
    schema = WriterOutputSchema.model_validate({
        "markdown_content": "正文",
        "embedded_charts": [
            {"type": "GANTT_DATA", "data": []},
            "not-a-dict",
        ],
    })
    assert len(schema.resolved_charts_raw()) == 1


def test_writer_output_schema_coerces_non_list_charts():
    schema = WriterOutputSchema.model_validate({
        "markdown_content": "正文",
        "embedded_charts": "bad",
    })
    assert schema.resolved_charts_raw() == []


def test_writer_output_schema_rejects_empty_object():
    with pytest.raises(ValidationError):
        WriterOutputSchema.model_validate({})


def test_writer_output_schema_rejects_wrong_field_names():
    with pytest.raises(ValidationError):
        WriterOutputSchema.model_validate({"markdown": "正文段落"})


def test_writer_output_schema_rejects_whitespace_only_markdown():
    with pytest.raises(ValidationError):
        WriterOutputSchema.model_validate({"markdown_content": "   \n  "})


def test_resolve_model_role_fallback(monkeypatch):
    monkeypatch.setattr("config.DEEPSEEK_MODEL", "default-model")
    monkeypatch.setattr("config.WRITER_MODEL", "")
    monkeypatch.setattr("config.QA_MODEL", "")
    assert resolve_model(role="default") == "default-model"
    assert resolve_model(role="writer") == "default-model"
    assert resolve_model(role="qa") == "default-model"


def test_resolve_model_role_specific(monkeypatch):
    monkeypatch.setattr("config.DEEPSEEK_MODEL", "default-model")
    monkeypatch.setattr("config.WRITER_MODEL", "cheap-writer")
    monkeypatch.setattr("config.QA_MODEL", "strong-qa")
    assert resolve_model(role="writer") == "cheap-writer"
    assert resolve_model(role="qa") == "strong-qa"
    assert resolve_model(model="override") == "override"
