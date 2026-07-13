"""组装各阶段 LLM 提示词，供前端预览与生成后调试。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from config import ENABLE_CONTENT_PLAN, SKIP_CONTENT_PLAN_WORD_THRESHOLD
from db.models import Project, TechOutline, TechRequirement
from domains.registry import DEFAULT_DOMAIN
from prompts.outline_prompt import (
    build_branch_user_prompt,
    build_skeleton_user_prompt,
    get_branch_system_prompt,
    get_reference_structure,
    get_skeleton_system_prompt,
)
from services.knowledge_registry import get_knowledge_folders
from services.outline_order import sort_outline_tree_dfs
from services.outline_service import _other_branches_for_expand
from prompts.plan_prompt import build_plan_user_prompt, get_plan_system_prompt
from prompts.qa_prompt import QA_SYSTEM_PROMPT, build_qa_user_prompt
from prompts.writer_prompt import (
    build_writer_user_prompt,
    get_writer_system_prompt,
)
from services.generation_mode import get_generation_mode
from services.prompt_project_info import build_prompt_global_params
from services.requirement_utils import requirement_dicts
from services.project_meta import get_meta, get_outline_catalog
from services.prompt_metrics import attach_stage_metrics
from services.writing_guidance import get_chapter_type, should_skip_content_plan


def _parse_content_plan(chapter: TechOutline) -> dict | None:
    raw = chapter.content_plan
    if not raw or not str(raw).strip():
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _branch_dict_from_outline(node: TechOutline) -> dict:
    return {
        "id": node.id,
        "title": node.title,
        "parent_id": node.parent_id,
        "level": node.level,
    }


def _first_branch_from_catalog(catalog: list[dict]) -> dict | None:
    """从用户目录推断第一个二级分支（用于大纲尚未 AI 深化时）。"""
    parent_id: str | None = None
    child_count = 0
    for item in sorted(catalog, key=lambda x: x.get("sort_order", 0)):
        level = int(item.get("level") or 1)
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        if level == 1:
            parent_id = str(int(item.get("sort_order") or 1))
            child_count = 0
        elif level == 2 and parent_id:
            child_count += 1
            return {
                "id": f"{parent_id}.{child_count}",
                "title": title,
                "parent_id": parent_id,
                "level": 2,
            }
    return None


def _pick_outline_branch_for_preview(
    db: Session, project: Project, catalog: list[dict]
) -> tuple[dict, str]:
    """选取大纲分支展开预览节点，返回 (branch, stage_label)。"""
    level2_nodes = [
        n for n in sort_outline_tree_dfs(
            db.query(TechOutline).filter(TechOutline.project_id == project.id).all()
        )
        if n.level == 2
    ]
    outline_branch = level2_nodes[0] if level2_nodes else None
    if outline_branch:
        return _branch_dict_from_outline(outline_branch), f"分支展开（{outline_branch.title}）"

    catalog_branch = _first_branch_from_catalog(catalog)
    if catalog_branch:
        return catalog_branch, f"分支展开（{catalog_branch['title']}）"

    return (
        {"id": "1.1", "title": "（目录尚无二级分支）", "parent_id": "1", "level": 2},
        "分支展开（占位）",
    )


def _stage(stage_id: str, label: str, system: str, user: str, **extra: Any) -> dict[str, Any]:
    from services.prompt_metrics import estimate_prompt_stage

    payload: dict[str, Any] = {
        "id": stage_id,
        "label": label,
        "system": system,
        "user": user,
        "metrics": estimate_prompt_stage(system, user),
    }
    payload.update(extra)
    return payload


def build_outline_prompt_preview(db: Session, project: Project) -> dict[str, Any]:
    requirements = (
        db.query(TechRequirement)
        .filter(TechRequirement.project_id == project.id, TechRequirement.status == "confirmed")
        .all()
    )
    global_info = build_prompt_global_params(project)
    catalog = get_outline_catalog(project)
    project_type = global_info.get("项目类型")
    engineering_domain = global_info.get("工程领域") or get_meta(project).get("engineering_domain") or DEFAULT_DOMAIN
    reference_text = get_reference_structure(project_type, engineering_domain)
    knowledge_folders = get_knowledge_folders(project_type, engineering_domain)
    req_dicts = requirement_dicts(requirements)

    generation_mode = get_generation_mode(project)
    domain = (global_info or {}).get("工程领域")
    skeleton_user = build_skeleton_user_prompt(
        global_info, catalog, reference_text, generation_mode=generation_mode,
    )
    preview_branch, branch_label = _pick_outline_branch_for_preview(db, project, catalog)
    level2_nodes = [
        _branch_dict_from_outline(n)
        for n in sort_outline_tree_dfs(
            db.query(TechOutline).filter(TechOutline.project_id == project.id).all()
        )
        if n.level == 2
    ]
    branch_user = build_branch_user_prompt(
        global_info, preview_branch, catalog, req_dicts, knowledge_folders,
        generation_mode=generation_mode,
        other_branches=_other_branches_for_expand(level2_nodes, preview_branch),
    )
    outline_stages = [
        _stage("outline_skeleton", "大纲骨架", get_skeleton_system_prompt(domain), skeleton_user),
        _stage("outline_branch", branch_label, get_branch_system_prompt(domain), branch_user),
    ]
    stages, prompt_metrics = attach_stage_metrics(outline_stages)
    return {
        "project_id": project.id,
        "kind": "outline",
        "stages": stages,
        "prompt_metrics": prompt_metrics,
        "preview_branch": preview_branch,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def build_chapter_prompt_preview(
    db: Session,
    project: Project,
    chapter: TechOutline,
    *,
    content_for_qa: str | None = None,
    fix_instructions: str | None = None,
) -> dict[str, Any]:
    from services.writer_service import build_context_bundle

    bundle = build_context_bundle(db, project, chapter)
    content_plan = _parse_content_plan(chapter)
    if content_plan:
        bundle["content_plan"] = content_plan
    guidance = bundle.get("guidance") or {}
    stages: list[dict[str, Any]] = []

    domain = bundle.get("engineering_domain") or DEFAULT_DOMAIN
    if ENABLE_CONTENT_PLAN:
        if should_skip_content_plan(bundle, word_threshold=SKIP_CONTENT_PLAN_WORD_THRESHOLD):
            from services.qa_rules import fallback_content_plan

            stages.append(
                _stage(
                    "plan",
                    "写作规划（规则兜底）",
                    get_plan_system_prompt(domain),
                    json.dumps(fallback_content_plan(bundle), ensure_ascii=False, indent=2),
                    note=(
                        f"描述类或目标字数<{SKIP_CONTENT_PLAN_WORD_THRESHOLD} 的章节跳过 LLM 规划，"
                        "上列为规则兜底 JSON"
                    ),
                )
            )
        else:
            stages.append(
                _stage(
                    "plan",
                    "写作规划",
                    get_plan_system_prompt(domain),
                    build_plan_user_prompt(bundle),
                    note="实际请求按多条 user 消息分层发送（项目上下文→衔接→检索→本章任务），利于 Prompt Cache",
                )
            )

    writer_user = build_writer_user_prompt(bundle, fix_instructions=fix_instructions)
    stages.append(
        _stage(
            "writer",
            "正文撰写",
            get_writer_system_prompt(domain),
            writer_user,
            note="实际请求按多条 user 消息分层发送（项目上下文→衔接→检索→本章任务），利于 Prompt Cache",
        )
    )

    qa_sample = (content_for_qa or chapter.generated_content or "").strip()
    if not qa_sample:
        qa_sample = "（预览占位：生成正文后将填入本章内容用于软质检）"
    stages.append(
        _stage(
            "qa",
            "软质检",
            QA_SYSTEM_PROMPT,
            build_qa_user_prompt(qa_sample[:6000], bundle),
            note="软质检在正文生成后执行，预览时正文可能为占位或历史版本",
        )
    )

    stages, prompt_metrics = attach_stage_metrics(stages)

    return {
        "project_id": project.id,
        "chapter_id": chapter.id,
        "chapter_title": chapter.title,
        "kind": "chapter",
        "chapter_type": get_chapter_type(chapter.title),
        "guidance": {
            "brief": guidance.get("brief"),
            "content_boundary": guidance.get("content_boundary"),
            "target_words": guidance.get("target_words"),
        },
        "stages": stages,
        "prompt_metrics": prompt_metrics,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def capture_generation_prompt_debug(
    bundle: dict,
    chapter: TechOutline,
    *,
    fix_instructions: str | None = None,
    content_for_qa: str | None = None,
) -> str:
    """生成流程中保存的提示词快照（JSON 字符串）。"""
    guidance = bundle.get("guidance") or {}
    stages: list[dict[str, Any]] = []
    domain = bundle.get("engineering_domain") or DEFAULT_DOMAIN

    if ENABLE_CONTENT_PLAN:
        if should_skip_content_plan(bundle, word_threshold=SKIP_CONTENT_PLAN_WORD_THRESHOLD):
            from services.qa_rules import fallback_content_plan

            stages.append(
                _stage(
                    "plan",
                    "写作规划（规则兜底）",
                    get_plan_system_prompt(domain),
                    json.dumps(fallback_content_plan(bundle), ensure_ascii=False, indent=2),
                    note=f"描述类或目标字数<{SKIP_CONTENT_PLAN_WORD_THRESHOLD}，跳过 LLM 规划",
                )
            )
        else:
            stages.append(
                _stage(
                    "plan",
                    "写作规划",
                    get_plan_system_prompt(domain),
                    build_plan_user_prompt(bundle),
                    note="实际请求按多条 user 消息分层发送（项目上下文→衔接→检索→本章任务），利于 Prompt Cache",
                )
            )

    writer_user = build_writer_user_prompt(bundle, fix_instructions=fix_instructions)
    stages.append(
        _stage(
            "writer",
            "正文撰写",
            get_writer_system_prompt(domain),
            writer_user,
            note="实际请求按多条 user 消息分层发送（项目上下文→衔接→检索→本章任务），利于 Prompt Cache",
        )
    )

    if content_for_qa:
        stages.append(
            _stage(
                "qa",
                "软质检",
                QA_SYSTEM_PROMPT,
                build_qa_user_prompt(content_for_qa[:6000], bundle),
            )
        )

    stages, prompt_metrics = attach_stage_metrics(stages)

    stages, prompt_metrics = attach_stage_metrics(stages)

    payload = {
        "chapter_id": chapter.id,
        "chapter_title": chapter.title,
        "guidance": {
            "brief": guidance.get("brief"),
            "content_boundary": guidance.get("content_boundary"),
            "target_words": guidance.get("target_words"),
        },
        "stages": stages,
        "prompt_metrics": prompt_metrics,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
    if fix_instructions:
        payload["fix_instructions"] = fix_instructions
    warning = bundle.get("retrieval_warning")
    if warning:
        payload["retrieval_warning"] = warning
    route = bundle.get("retrieval_route")
    if isinstance(route, dict) and route:
        payload["retrieval_route"] = route
    return json.dumps(payload, ensure_ascii=False)


def parse_stored_prompt_debug(raw: str | None) -> dict[str, Any] | None:
    if not raw or not str(raw).strip():
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None
