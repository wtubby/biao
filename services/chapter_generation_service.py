"""章节内容规划与 LLM 生成。"""

import logging
import re
from typing import TYPE_CHECKING, Any

from config import (
    ENABLE_SEGMENT_QA,
    LONG_CHAPTER_MIN_KEY_POINTS,
    LONG_CHAPTER_WORD_THRESHOLD,
    MAX_SEGMENT_QA_RETRY,
    SKIP_CONTENT_PLAN_WORD_THRESHOLD,
    WRITER_STRUCTURED_OUTPUT,
)
from llm.llm_client import call_llm_json, call_llm_text
from llm.schemas import WriterOutputSchema
from prompts.plan_prompt import build_plan_chat_messages
from prompts.writer_prompt import (
    SUMMARY_SYSTEM_PROMPT,
    build_writer_chat_messages,
    build_writer_user_messages,
    sample_content_for_summary,
)
from services.qa_rules import (
    check_segment_stitch_quality,
    fallback_content_plan,
    validate_content_plan,
)
from services.writer_output import structured_output_to_content
from services.writing_guidance import should_skip_content_plan

if TYPE_CHECKING:
    from db.models import Project, TechOutline

logger = logging.getLogger(__name__)

_ANCHOR_STANDARD_RE = re.compile(
    r"(?:GB/?T?|CJJ|JGJ|JTG|DL/?T?|NB/?T?|Q/?GDW)[A-Z0-9/\-]{2,}",
    re.I,
)
_ANCHOR_QUOTED_RE = re.compile(r"[「『\"“](.{2,40}?)[」』\"”]")


def generate_content_plan(bundle: dict) -> dict:
    try:
        plan = call_llm_json(build_plan_chat_messages(bundle), role="writer")
        if not isinstance(plan, dict):
            plan = {}
    except Exception as exc:
        logger.warning("写作规划生成失败: %s", exc)
        plan = {}

    issues = validate_content_plan(plan, bundle)
    if issues:
        logger.info("写作规划校验未通过，尝试重试: %s", issues)
        try:
            plan2 = call_llm_json(
                build_plan_chat_messages(bundle, retry_issues=issues),
                role="writer",
            )
            if isinstance(plan2, dict) and not validate_content_plan(plan2, bundle):
                return plan2
            if isinstance(plan2, dict) and len(validate_content_plan(plan2, bundle)) < len(issues):
                plan = plan2
        except Exception as exc:
            logger.warning("写作规划重试失败: %s", exc)

    if validate_content_plan(plan, bundle):
        logger.warning("写作规划仍不可用，启用规则兜底")
        return fallback_content_plan(bundle)
    return plan


def resolve_content_plan(bundle: dict) -> dict:
    """生成写作规划：描述类/低分短章跳过 LLM，直接规则兜底。"""
    if should_skip_content_plan(bundle, word_threshold=SKIP_CONTENT_PLAN_WORD_THRESHOLD):
        logger.info(
            "跳过 LLM 写作规划（描述类或目标字数<%d）：%s",
            SKIP_CONTENT_PLAN_WORD_THRESHOLD,
            bundle.get("chapter_title"),
        )
        return fallback_content_plan(bundle)
    return generate_content_plan(bundle)


def estimate_chapter_max_tokens(target_words: int | None) -> int:
    """根据目标字数估算本章需要的 max_tokens，带缓冲并夹在 [默认值, 上限] 之间。"""
    import config as cfg

    if not target_words:
        return cfg.LLM_MAX_TOKENS
    estimated = int(target_words / cfg.CHARS_PER_TOKEN_CN) + 500
    return min(max(estimated, cfg.LLM_MAX_TOKENS), cfg.LLM_MAX_TOKENS_CEILING)


def _should_segment_chapter(bundle: dict) -> bool:
    """长章节是否走内存分段续写。

    结构拆分产生的子叶子（guidance.split_origin）已由大纲拆成短章，跳过内存分段；
    普通大纲里同级多叶子是默认形态，不得据此禁用分段。
    """
    guidance = bundle.get("guidance") or {}
    if guidance.get("split_origin"):
        return False
    target_words = int(guidance.get("target_words") or 0)
    plan = bundle.get("content_plan") or {}
    key_points = [p for p in (plan.get("key_points") or []) if str(p).strip()]
    return (
        target_words >= LONG_CHAPTER_WORD_THRESHOLD
        and len(key_points) >= LONG_CHAPTER_MIN_KEY_POINTS
        and not bundle.get("_segment_mode")
    )


def _chunk_key_points(key_points: list[str], max_groups: int = 3) -> list[list[str]]:
    points = [p.strip() for p in key_points if str(p).strip()]
    if len(points) <= 2:
        return [points] if points else []
    group_count = min(max_groups, max(2, (len(points) + 1) // 2))
    group_count = min(group_count, len(points))
    size = (len(points) + group_count - 1) // group_count
    return [points[i:i + size] for i in range(0, len(points), size)]


def build_directed_fix_instructions(
    issues: list[str] | str,
    *,
    previous_draft: str | None = None,
    draft_label: str = "内容",
) -> str:
    """组装质检重试修改要求；有上一版草稿时改为「定向修正」而非从零盲写。"""
    issue_block = issues.strip() if isinstance(issues, str) else "\n".join(issues)
    draft = (previous_draft or "").strip()
    if draft:
        return (
            f"你上一版写的{draft_label}如下（供参考，不要简单照抄，但要在此基础上定向修正）：\n"
            f"```\n{draft}\n```\n\n"
            "存在以下问题，请针对性修改，不要改动跟这些问题无关的内容：\n"
            f"{issue_block}"
        )
    return "修复以下问题：\n" + issue_block


def _writer_budget_remaining(qa_context: dict[str, Any] | None) -> int | None:
    if not qa_context:
        return None
    budget = qa_context.get("writer_llm_budget")
    if budget is None:
        return None
    calls = int(qa_context.get("writer_llm_calls") or 0)
    return max(0, int(budget) - calls)


def _consume_writer_budget(qa_context: dict[str, Any] | None) -> bool:
    """消耗一次 Writer 预算；无预算限制时恒为 True。触顶返回 False。"""
    if not qa_context:
        return True
    budget = qa_context.get("writer_llm_budget")
    if budget is None:
        return True
    calls = int(qa_context.get("writer_llm_calls") or 0)
    if calls >= int(budget):
        qa_context["writer_budget_exhausted"] = True
        return False
    qa_context["writer_llm_calls"] = calls + 1
    return True


def _localize_fix_to_segments(
    parts: list[str],
    *,
    anchors: list[str] | None = None,
    fix_instructions: str | None = None,
) -> list[int]:
    """用 evidence 锚点（优先）或 fix 文案弱回退，定位需重写的段落下标。"""
    hit: set[int] = set()
    for anchor in anchors or []:
        a = (anchor or "").strip()
        if len(a) < 2:
            continue
        for i, part in enumerate(parts):
            if a in (part or ""):
                hit.add(i)
    if hit:
        return sorted(hit)

    text = fix_instructions or ""
    candidates: list[str] = []
    candidates.extend(_ANCHOR_STANDARD_RE.findall(text))
    candidates.extend(m.group(1).strip() for m in _ANCHOR_QUOTED_RE.finditer(text))
    for cand in candidates:
        c = (cand or "").strip()
        if len(c) < 2:
            continue
        for i, part in enumerate(parts):
            if c in (part or ""):
                hit.add(i)
    return sorted(hit)


def _generate_once(
    bundle: dict,
    *,
    max_tokens: int,
    chat_messages: list[dict] | None,
    use_chat: bool,
    fix_instructions: str | None = None,
    structured: bool | None = None,
    qa_context: dict[str, Any] | None = None,
) -> tuple[str, list[dict] | None]:
    if not _consume_writer_budget(qa_context):
        logger.warning("Writer LLM 预算已耗尽，跳过本次生成")
        return "", chat_messages

    if structured is None:
        structured = WRITER_STRUCTURED_OUTPUT

    if structured:
        return _generate_once_structured(
            bundle,
            max_tokens=max_tokens,
            chat_messages=chat_messages,
            use_chat=use_chat,
            fix_instructions=fix_instructions,
        )

    if use_chat:
        messages = _append_writer_chat_turn(
            bundle,
            chat_messages=chat_messages,
            fix_instructions=fix_instructions,
            structured=False,
        )
        content = call_llm_text(messages, max_tokens=max_tokens, role="writer")
        messages.append({"role": "assistant", "content": content})
        return content, messages
    content = call_llm_text(
        build_writer_chat_messages(bundle, fix_instructions=fix_instructions, structured=False),
        max_tokens=max_tokens,
        role="writer",
    )
    return content, chat_messages


def _append_writer_chat_turn(
    bundle: dict,
    *,
    chat_messages: list[dict] | None,
    fix_instructions: str | None,
    structured: bool,
) -> list[dict]:
    """关键章节多轮：首轮与普通章节同构（system + 稳定前缀）；续轮只追加非项目块。"""
    is_first_turn = not chat_messages
    if is_first_turn:
        return build_writer_chat_messages(
            bundle,
            fix_instructions=fix_instructions,
            structured=structured,
        )
    messages = list(chat_messages)
    for part in build_writer_user_messages(
        bundle,
        fix_instructions=fix_instructions,
        include_project_context=False,
    ):
        messages.append({"role": "user", "content": part})
    return messages


def _generate_once_structured(
    bundle: dict,
    *,
    max_tokens: int,
    chat_messages: list[dict] | None,
    use_chat: bool,
    fix_instructions: str | None = None,
) -> tuple[str, list[dict] | None]:
    """结构化 JSON 输出，组装为带图表占位符的正文。"""
    if use_chat:
        messages = _append_writer_chat_turn(
            bundle,
            chat_messages=chat_messages,
            fix_instructions=fix_instructions,
            structured=True,
        )
        try:
            raw = call_llm_json(
                messages, max_tokens=max_tokens, role="writer", schema=WriterOutputSchema,
            )
            content = structured_output_to_content(raw)
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("结构化撰写失败，降级纯文本: %s", exc)
            content = call_llm_text(messages, max_tokens=max_tokens, role="writer")
        messages.append({"role": "assistant", "content": content})
        return content, messages

    messages = build_writer_chat_messages(
        bundle, fix_instructions=fix_instructions, structured=True,
    )
    try:
        raw = call_llm_json(
            messages, max_tokens=max_tokens, role="writer", schema=WriterOutputSchema,
        )
        return structured_output_to_content(raw), chat_messages
    except (ValueError, KeyError, TypeError) as exc:
        logger.warning("结构化撰写失败，降级纯文本: %s", exc)
        return call_llm_text(
            build_writer_chat_messages(bundle, fix_instructions=fix_instructions, structured=False),
            max_tokens=max_tokens,
            role="writer",
        ), chat_messages


def generate_chapter_content(
    bundle: dict,
    fix_instructions: str | None = None,
    chat_messages: list[dict] | None = None,
    use_chat: bool = False,
    qa_context: dict[str, Any] | None = None,
) -> tuple[str, list[dict] | None]:
    target_words = (bundle.get("guidance") or {}).get("target_words")
    max_tokens = estimate_chapter_max_tokens(target_words)

    # 长章优先分段；修复重试时若仍满足分段条件则继续分段，避免整章单轮回退
    if _should_segment_chapter(bundle):
        content, messages = _generate_segmented_chapter(
            bundle,
            chat_messages=chat_messages,
            use_chat=use_chat,
            total_max_tokens=max_tokens,
            fix_instructions=fix_instructions,
            qa_context=qa_context,
        )
        return content, messages

    return _generate_once(
        bundle,
        max_tokens=max_tokens,
        chat_messages=chat_messages,
        use_chat=use_chat,
        fix_instructions=fix_instructions,
        qa_context=qa_context,
    )


def _build_segment_bundle(
    bundle: dict,
    *,
    plan: dict,
    group: list[str],
    idx: int,
    groups: list[list[str]],
    per_group_words: int,
    written: list[str],
) -> dict:
    remaining = [p for g in groups[idx + 1:] for p in g]
    seg_plan = dict(plan)
    seg_plan["key_points"] = group
    seg_plan["word_count_target"] = per_group_words
    if idx > 0:
        seg_plan["charts_needed"] = []
        seg_plan["technical_methods"] = []
        seg_plan["data_to_include"] = []
        prev_avoid = list(plan.get("avoid") or [])
        seg_plan["avoid"] = list(dict.fromkeys(prev_avoid + written))
    else:
        methods = list(plan.get("technical_methods") or [])
        data_items = list(plan.get("data_to_include") or [])
        mid_m = max(1, (len(methods) + 1) // 2) if methods else 0
        mid_d = max(1, (len(data_items) + 1) // 2) if data_items else 0
        if methods:
            seg_plan["technical_methods"] = methods[:mid_m]
        if data_items:
            seg_plan["data_to_include"] = data_items[:mid_d]

    seg_bundle = dict(bundle)
    seg_bundle["guidance"] = {
        **(bundle.get("guidance") or {}),
        "target_words": per_group_words,
    }
    seg_bundle["content_plan"] = seg_plan
    if idx > 0:
        seg_bundle["chart_density_hint"] = ""
    seg_bundle["_segment_mode"] = True
    seg_bundle["_segment_index"] = idx + 1
    seg_bundle["_segment_total"] = len(groups)
    seg_bundle["_segment_written"] = list(written)
    seg_bundle["_segment_remaining"] = remaining
    return seg_bundle


def _generate_one_segment(
    *,
    seg_bundle: dict,
    group: list[str],
    segment_label: str,
    per_tokens: int,
    messages: list[dict] | None,
    use_chat: bool,
    fix_seg: str | None,
    max_attempts: int,
    qa_context: dict[str, Any] | None,
    chapter_bundle: dict,
) -> tuple[str, list[dict] | None]:
    from services.chapter_qa_orchestrator import _soft_issue_list, run_segment_qa

    part = ""
    for seg_attempt in range(max_attempts):
        remaining = _writer_budget_remaining(qa_context)
        if remaining is not None and remaining <= 0:
            if qa_context is not None:
                qa_context["writer_budget_exhausted"] = True
            break
        content, messages = _generate_once(
            seg_bundle,
            max_tokens=per_tokens,
            chat_messages=messages,
            use_chat=use_chat,
            fix_instructions=fix_seg,
            qa_context=qa_context,
        )
        part = (content or "").strip()
        if not part:
            if seg_attempt < max_attempts - 1 and not (qa_context or {}).get(
                "writer_budget_exhausted"
            ):
                logger.warning(
                    "分段 %s 生成为空，重试（%d/%d）",
                    segment_label,
                    seg_attempt + 1,
                    max_attempts - 1,
                )
                continue
            points_preview = "；".join(group[:3])
            if len(group) > 3:
                points_preview += "…"
            logger.warning(
                "分段 %s 生成为空，已跳过（要点：%s）",
                segment_label,
                points_preview,
            )
            if qa_context is not None:
                qa_context.setdefault("segment_warnings", []).append(
                    f"分段 {segment_label} 生成为空已跳过，对应要点未写入正文"
                )
            break

        if (
            ENABLE_SEGMENT_QA
            and max_attempts > 1
            and qa_context
            and qa_context.get("project")
            and qa_context.get("chapter")
        ):
            hard_errors, soft = run_segment_qa(
                part,
                qa_context["project"],
                qa_context["chapter"],
                chapter_bundle,
                segment_label=segment_label,
                content_plan=seg_bundle.get("content_plan"),
            )
            soft_issues = _soft_issue_list(soft) if soft else []
            retry_issues = list(hard_errors) + soft_issues
            if retry_issues and seg_attempt < max_attempts - 1:
                remaining = _writer_budget_remaining(qa_context)
                if remaining is not None and remaining <= 0:
                    break
                fix_seg = "修复以下问题：\n" + "\n".join(retry_issues)
                logger.info(
                    "分段 QA 未通过，重写 %s（%d/%d）: %s",
                    segment_label,
                    seg_attempt + 1,
                    max_attempts - 1,
                    retry_issues[:2],
                )
                continue
            leftover = (
                list(hard_errors)
                + soft_issues
                + [m for m in ((soft or {}).get("extra_warn_issues") or []) if m]
            )
            if leftover:
                warnings = qa_context.setdefault("segment_warnings", [])
                for msg in leftover:
                    warnings.append(f"[{segment_label}] {msg}")
        break
    return part, messages


def _generate_segmented_chapter(
    bundle: dict,
    *,
    chat_messages: list[dict] | None,
    use_chat: bool,
    total_max_tokens: int,
    fix_instructions: str | None = None,
    qa_context: dict[str, Any] | None = None,
) -> tuple[str, list[dict] | None]:
    """长章按规划要点分组撰写，降低后半段空洞与跑题。"""
    plan = dict(bundle.get("content_plan") or {})
    key_points = [str(p).strip() for p in (plan.get("key_points") or []) if str(p).strip()]
    groups = _chunk_key_points(key_points)
    if len(groups) < 2:
        return _generate_once(
            bundle,
            max_tokens=total_max_tokens,
            chat_messages=chat_messages,
            use_chat=use_chat,
            fix_instructions=fix_instructions,
            qa_context=qa_context,
        )

    target_words = int((bundle.get("guidance") or {}).get("target_words") or 0)
    per_group_words = max(400, target_words // len(groups)) if target_words else 600
    per_tokens = max(1200, total_max_tokens // len(groups) + 400)
    messages = chat_messages

    cached_parts = list((qa_context or {}).get("segment_parts") or [])
    reuse_mode = bool(
        fix_instructions
        and cached_parts
        and len(cached_parts) == len(groups)
        and all(isinstance(p, str) and p.strip() for p in cached_parts)
    )

    if reuse_mode:
        parts = list(cached_parts)
        indices_to_regen = _localize_fix_to_segments(
            parts,
            anchors=(qa_context or {}).get("fix_anchors"),
            fix_instructions=fix_instructions,
        )
        if indices_to_regen:
            max_attempts = MAX_SEGMENT_QA_RETRY + 1
            logger.info(
                "整章修复按段复用：仅重写段落下标 %s",
                indices_to_regen,
            )
        else:
            # 无锚点：全量重跑，但每段只生成 1 次，避免外层×段内再乘积
            indices_to_regen = list(range(len(groups)))
            max_attempts = 1
            logger.info("整章修复无文本锚点，全量重跑分段（每段 1 次）")
    else:
        parts = [""] * len(groups)
        indices_to_regen = list(range(len(groups)))
        max_attempts = MAX_SEGMENT_QA_RETRY + 1

    written: list[str] = []
    for idx, group in enumerate(groups):
        if idx not in indices_to_regen:
            written.extend(group)
            continue

        seg_bundle = _build_segment_bundle(
            bundle,
            plan=plan,
            group=group,
            idx=idx,
            groups=groups,
            per_group_words=per_group_words,
            written=written,
        )
        fix_seg = None
        if fix_instructions:
            prev_part = (parts[idx] or "").strip() if reuse_mode else ""
            if prev_part:
                # 按段复用重写：只喂本段原文，避免整章正文重复进 prompt
                directed = build_directed_fix_instructions(
                    fix_instructions,
                    previous_draft=prev_part,
                    draft_label="本段内容",
                )
                fix_seg = f"## 修改要求（本段定向修正）\n{directed}"
            else:
                fix_seg = f"## 修改要求（整章修复，各段均需落实）\n{fix_instructions}"

        segment_label = f"第{idx + 1}/{len(groups)}段"
        part, messages = _generate_one_segment(
            seg_bundle=seg_bundle,
            group=group,
            segment_label=segment_label,
            per_tokens=per_tokens,
            messages=messages,
            use_chat=use_chat,
            fix_seg=fix_seg,
            max_attempts=max_attempts,
            qa_context=qa_context,
            chapter_bundle=bundle,
        )
        if part:
            parts[idx] = part
        written.extend(group)

    # 过滤空段再拼接；保留下标对应关系供缓存
    non_empty_parts = [p for p in parts if (p or "").strip()]
    stitch_issues = check_segment_stitch_quality(non_empty_parts)
    # stitch 基于 non_empty 下标；映射回 parts 原下标
    nonempty_indices = [i for i, p in enumerate(parts) if (p or "").strip()]
    if stitch_issues and len(non_empty_parts) >= 2:
        by_idx: dict[int, list[str]] = {}
        for issue in stitch_issues:
            local_idx = int(issue.get("index", -1))
            msg = str(issue.get("message") or "").strip()
            if local_idx < 0 or local_idx >= len(nonempty_indices) or not msg:
                continue
            real_idx = nonempty_indices[local_idx]
            by_idx.setdefault(real_idx, []).append(msg)

        for fix_idx in sorted(by_idx.keys()):
            if fix_idx <= 0 or fix_idx >= len(parts) or fix_idx >= len(groups):
                continue
            remaining_budget = _writer_budget_remaining(qa_context)
            if remaining_budget is not None and remaining_budget <= 0:
                break
            fix_seg = (
                "修复段首问题：\n"
                + "\n".join(by_idx[fix_idx])
                + "\n直接输出本段正文，不要过渡套话。"
            )
            prior_points = [p for g in groups[:fix_idx] for p in g]
            remaining = [p for g in groups[fix_idx + 1:] for p in g]
            seg_bundle = dict(bundle)
            seg_bundle["guidance"] = {
                **(bundle.get("guidance") or {}),
                "target_words": per_group_words,
            }
            seg_bundle["content_plan"] = {
                **plan,
                "key_points": groups[fix_idx],
                "word_count_target": per_group_words,
                "avoid": list(dict.fromkeys(
                    list(plan.get("avoid") or []) + prior_points
                )),
                "charts_needed": [],
                "technical_methods": [],
                "data_to_include": [],
            }
            seg_bundle["chart_density_hint"] = ""
            seg_bundle["_segment_mode"] = True
            seg_bundle["_segment_index"] = fix_idx + 1
            seg_bundle["_segment_total"] = len(groups)
            seg_bundle["_segment_written"] = prior_points
            seg_bundle["_segment_remaining"] = remaining
            rewritten, messages = _generate_once(
                seg_bundle,
                max_tokens=per_tokens,
                chat_messages=messages,
                use_chat=use_chat,
                fix_instructions=fix_seg,
                qa_context=qa_context,
            )
            if (rewritten or "").strip():
                parts[fix_idx] = rewritten.strip()

    final_parts = [p.strip() for p in parts if (p or "").strip()]
    if qa_context is not None:
        # 与 groups 等长，供外层重试按段复用
        qa_context["segment_parts"] = [(p or "").strip() for p in parts]
        qa_context["segment_groups"] = groups

    return "\n\n".join(final_parts), messages if use_chat else chat_messages


def generate_summary(content: str) -> str:
    sampled = sample_content_for_summary(content)
    return call_llm_text(
        [
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": sampled},
        ],
        max_tokens=300,
        role="writer",
    ).strip()[:150]


def _count_chinese_chars(content: str) -> int:
    return len(re.sub(r"\s+", "", content))
