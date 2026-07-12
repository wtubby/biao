import json
from typing import Any

from db.models import Project


def get_meta(project: Project) -> dict[str, Any]:
    if not project.extra_params:
        return {}
    try:
        return json.loads(project.extra_params)
    except json.JSONDecodeError:
        return {}


def set_meta(project: Project, **kwargs) -> None:
    meta = get_meta(project)
    meta.update(kwargs)
    project.extra_params = json.dumps(meta, ensure_ascii=False)


def get_parse_error(project: Project) -> str | None:
    return get_meta(project).get("parse_error")


def set_parse_error(project: Project, error: str | None) -> None:
    meta = get_meta(project)
    if error:
        meta["parse_error"] = error
    else:
        meta.pop("parse_error", None)
    project.extra_params = json.dumps(meta, ensure_ascii=False)


# 解析分阶段进度（供前端轮询展示）
PARSE_STAGE_READING = "reading"
PARSE_STAGE_EXTRACTING = "extracting"
PARSE_STAGE_SAVING = "saving"
PARSE_STAGE_DONE = "done"
PARSE_STAGE_ERROR = "error"

PARSE_STAGE_LABELS = {
    PARSE_STAGE_READING: "阅读文档段落",
    PARSE_STAGE_EXTRACTING: "提取关键信息",
    PARSE_STAGE_SAVING: "写入解析结果",
    PARSE_STAGE_DONE: "解析完成",
    PARSE_STAGE_ERROR: "解析失败",
}

PARSE_STAGE_PERCENT = {
    PARSE_STAGE_READING: 15,
    PARSE_STAGE_EXTRACTING: 55,
    PARSE_STAGE_SAVING: 85,
    PARSE_STAGE_DONE: 100,
    PARSE_STAGE_ERROR: 100,
}


def get_parse_progress(project: Project) -> dict[str, Any] | None:
    progress = get_meta(project).get("parse_progress")
    return progress if isinstance(progress, dict) else None


def set_parse_progress(
    project: Project,
    stage: str,
    message: str | None = None,
    *,
    chunk_index: int | None = None,
    chunk_total: int | None = None,
) -> None:
    """写入解析阶段进度到 project.extra_params。"""
    label = PARSE_STAGE_LABELS.get(stage, stage)
    percent = PARSE_STAGE_PERCENT.get(stage, 0)
    if (
        stage == PARSE_STAGE_EXTRACTING
        and chunk_index is not None
        and chunk_total
        and chunk_total > 0
    ):
        # 阅读 15% → 写入前 85%，按分块线性推进
        base, end = 15, 85
        percent = base + int((end - base) * (chunk_index / chunk_total))
    payload: dict[str, Any] = {
        "stage": stage,
        "label": label,
        "message": message or label,
        "percent": percent,
    }
    if chunk_index is not None:
        payload["chunk_index"] = chunk_index
    if chunk_total is not None:
        payload["chunk_total"] = chunk_total
    set_meta(project, parse_progress=payload)


def clear_parse_progress(project: Project) -> None:
    meta = get_meta(project)
    meta.pop("parse_progress", None)
    project.extra_params = json.dumps(meta, ensure_ascii=False)


def is_valid_outline_catalog(catalog: list) -> bool:
    """至少 1 个有效章节标题（单评分项招标可只生成一条目录骨架）。"""
    titles = [str(item.get("title", "")).strip() for item in catalog if isinstance(item, dict)]
    titles = [t for t in titles if t]
    return len(titles) >= 1


def get_outline_catalog_text(project: Project) -> str:
    return str(get_meta(project).get("outline_catalog_text") or "")


def get_outline_catalog(project: Project) -> list[dict]:
    meta = get_meta(project)
    catalog = meta.get("outline_catalog")
    if not isinstance(catalog, list):
        return []
    return [item for item in catalog if isinstance(item, dict) and str(item.get("title", "")).strip()]


def set_outline_catalog(project: Project, text: str, catalog: list[dict]) -> None:
    set_meta(
        project,
        outline_catalog_text=text,
        outline_catalog=catalog if is_valid_outline_catalog(catalog) else None,
    )
