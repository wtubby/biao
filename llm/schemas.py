"""LLM 结构化输出 Schema（Pydantic 强约束）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class QAResult(BaseModel):
    """软质检 LLM 输出（单窗/全文）。"""

    model_config = ConfigDict(extra="ignore")

    passed: bool = True
    coverage_issues: list[str] = Field(default_factory=list)
    faithfulness_issues: list[str] = Field(default_factory=list)
    scope_issues: list[str] = Field(default_factory=list)
    specificity_issues: list[str] = Field(default_factory=list)

    @field_validator(
        "coverage_issues",
        "faithfulness_issues",
        "scope_issues",
        "specificity_issues",
        mode="before",
    )
    @classmethod
    def _coerce_issues(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [
                str(item).strip()
                for item in value
                if item is not None and str(item).strip()
            ]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []


class QASegmentResult(QAResult):
    """多窗软质检中单个窗口的结果。"""

    label: str = ""


class QAMultiWindowResult(BaseModel):
    """长文头/中/尾多窗一次性软质检输出。"""

    model_config = ConfigDict(extra="ignore")

    segments: list[QASegmentResult] = Field(default_factory=list)

    @field_validator("segments", mode="before")
    @classmethod
    def _coerce_segments(cls, value: Any) -> list:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]


class WriterOutputSchema(BaseModel):
    """Writer 结构化 JSON 输出（正文与图表分字段）。"""

    model_config = ConfigDict(extra="ignore")

    markdown_content: str = ""
    content: str = ""
    embedded_charts: list[dict[str, Any]] = Field(default_factory=list)
    charts: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("embedded_charts", "charts", mode="before")
    @classmethod
    def _coerce_chart_list(cls, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    def resolved_markdown(self) -> str:
        return (self.markdown_content or self.content or "").strip()

    def resolved_charts_raw(self) -> list[dict[str, Any]]:
        charts = self.embedded_charts or self.charts or []
        return [c for c in charts if isinstance(c, dict)]

    @model_validator(mode="after")
    def _require_non_empty_markdown(self) -> "WriterOutputSchema":
        if not self.resolved_markdown():
            raise ValueError("markdown_content 或 content 必须为非空字符串")
        return self
