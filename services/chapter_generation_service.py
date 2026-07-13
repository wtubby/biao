"""章节内容规划与 LLM 生成。"""

import logging
import re

from config import (
    KEY_CHAPTER_MIN_SCORE,
    LONG_CHAPTER_MIN_KEY_POINTS,
    LONG_CHAPTER_WORD_THRESHOLD,
    SKIP_CONTENT_PLAN_WORD_THRESHOLD,
)
from domains.registry import DEFAULT_DOMAIN
from llm.llm_client import call_llm_json, call_llm_text
from prompts.plan_prompt import build_plan_user_prompt, get_plan_system_prompt
from prompts.writer_prompt import (
    SUMMARY_SYSTEM_PROMPT,
    build_writer_user_prompt,
    get_writer_system_prompt,
    sample_content_for_summary,
)
from services.qa_rules import (
    check_segment_stitch_quality,
    fallback_content_plan,
    validate_content_plan,
)
from services.retrieval_service import retrieve_detailed
from services.writing_guidance import should_skip_content_plan

logger = logging.getLogger(__name__)


def generate_content_plan(bundle: dict) -> dict:
    domain = bundle.get("engineering_domain") or DEFAULT_DOMAIN
    try:
        plan = call_llm_json(
            [
                {"role": "system", "content": get_plan_system_prompt(domain)},
                {"role": "user", "content": build_plan_user_prompt(bundle)},
            ]
        )
        if not isinstance(plan, dict):
            plan = {}
    except Exception as exc:
        logger.warning("写作规划生成失败: %s", exc)
        plan = {}

    issues = validate_content_plan(plan, bundle)
    if issues:
        logger.info("写作规划校验未通过，尝试重试: %s", issues)
        try:
            retry_prompt = (
                build_plan_user_prompt(bundle)
                + "\n\n上次规划问题：\n"
                + "\n".join(f"- {x}" for x in issues)
                + "\n请输出修正后的完整 JSON。"
            )
            plan2 = call_llm_json(
                [
                    {"role": "system", "content": get_plan_system_prompt(domain)},
                    {"role": "user", "content": retry_prompt},
                ]
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


def _generate_once(
    bundle: dict,
    user_prompt: str,
    *,
    max_tokens: int,
    chat_messages: list[dict] | None,
    use_chat: bool,
) -> tuple[str, list[dict] | None]:
    domain = bundle.get("engineering_domain") or DEFAULT_DOMAIN
    if use_chat:
        messages = list(chat_messages or [])
        messages.append({"role": "user", "content": user_prompt})
        content = call_llm_text(messages, max_tokens=max_tokens)
        messages.append({"role": "assistant", "content": content})
        return content, messages
    content = call_llm_text(
        [
            {"role": "system", "content": get_writer_system_prompt(domain)},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=max_tokens,
    )
    return content, chat_messages


def generate_chapter_content(
    bundle: dict,
    fix_instructions: str | None = None,
    chat_messages: list[dict] | None = None,
    use_chat: bool = False,
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
        )
        return content, messages

    user_prompt = build_writer_user_prompt(bundle)
    if fix_instructions:
        user_prompt += f"\n\n## 修改要求\n{fix_instructions}"
    return _generate_once(
        bundle,
        user_prompt,
        max_tokens=max_tokens,
        chat_messages=chat_messages,
        use_chat=use_chat,
    )


def _generate_segmented_chapter(
    bundle: dict,
    *,
    chat_messages: list[dict] | None,
    use_chat: bool,
    total_max_tokens: int,
    fix_instructions: str | None = None,
) -> tuple[str, list[dict] | None]:
    """长章按规划要点分组撰写，降低后半段空洞与跑题。"""
    plan = dict(bundle.get("content_plan") or {})
    key_points = [str(p).strip() for p in (plan.get("key_points") or []) if str(p).strip()]
    groups = _chunk_key_points(key_points)
    if len(groups) < 2:
        user_prompt = build_writer_user_prompt(bundle)
        if fix_instructions:
            user_prompt += f"\n\n## 修改要求\n{fix_instructions}"
        return _generate_once(
            bundle,
            user_prompt,
            max_tokens=total_max_tokens,
            chat_messages=chat_messages,
            use_chat=use_chat,
        )

    target_words = int((bundle.get("guidance") or {}).get("target_words") or 0)
    per_group_words = max(400, target_words // len(groups)) if target_words else 600
    per_tokens = max(1200, total_max_tokens // len(groups) + 400)
    messages = chat_messages
    parts: list[str] = []
    written: list[str] = []

    for idx, group in enumerate(groups):
        remaining = [p for g in groups[idx + 1:] for p in g]
        seg_plan = dict(plan)
        seg_plan["key_points"] = group
        seg_plan["word_count_target"] = per_group_words
        # 后续段不再重复要求全章图表/方法清单，避免堆砌与复读
        if idx > 0:
            seg_plan["charts_needed"] = []
            seg_plan["technical_methods"] = []
            seg_plan["data_to_include"] = []
            # 后续段 avoid 加上已写要点，强化勿重复
            prev_avoid = list(plan.get("avoid") or [])
            seg_plan["avoid"] = list(dict.fromkeys(prev_avoid + written))
        else:
            # 首段只保留前半方法/数据，其余留给后文自然展开
            methods = list(plan.get("technical_methods") or [])
            data_items = list(plan.get("data_to_include") or [])
            mid_m = max(1, (len(methods) + 1) // 2) if methods else 0
            mid_d = max(1, (len(data_items) + 1) // 2) if data_items else 0
            if methods:
                seg_plan["technical_methods"] = methods[:mid_m]
            if data_items:
                seg_plan["data_to_include"] = data_items[:mid_d]

        seg_bundle = dict(bundle)
        # 与 seg_plan.word_count_target 对齐，避免 prompt 里「篇幅要求」与「本章目标字数」矛盾
        seg_bundle["guidance"] = {
            **(bundle.get("guidance") or {}),
            "target_words": per_group_words,
        }
        seg_bundle["content_plan"] = seg_plan
        # 非首段去掉整章图表密度提示，避免每段都插 1~2 处导致堆砌
        if idx > 0:
            seg_bundle["chart_density_hint"] = ""
        seg_bundle["_segment_mode"] = True
        seg_bundle["_segment_index"] = idx + 1
        seg_bundle["_segment_total"] = len(groups)
        seg_bundle["_segment_written"] = list(written)
        seg_bundle["_segment_remaining"] = remaining

        user_prompt = build_writer_user_prompt(seg_bundle)
        # QA 重试时每段都带完整修复清单，避免非首段“盲修”
        if fix_instructions:
            user_prompt += (
                f"\n\n## 修改要求（整章修复，各段均需落实）\n{fix_instructions}"
            )
        content, messages = _generate_once(
            seg_bundle,
            user_prompt,
            max_tokens=per_tokens,
            chat_messages=messages,
            use_chat=use_chat,
        )
        part = (content or "").strip()
        if part:
            parts.append(part)
            written.extend(group)

    stitch_issues = check_segment_stitch_quality(parts)
    if stitch_issues and len(parts) >= 2:
        # 按检出的段落下标重写对应段（可能是中间段，也可能多段）
        by_idx: dict[int, list[str]] = {}
        for issue in stitch_issues:
            idx = int(issue.get("index", -1))
            msg = str(issue.get("message") or "").strip()
            if idx < 0 or not msg:
                continue
            by_idx.setdefault(idx, []).append(msg)

        for fix_idx in sorted(by_idx.keys()):
            if fix_idx <= 0 or fix_idx >= len(parts) or fix_idx >= len(groups):
                continue
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
            # 非首段不带整章图表密度提示
            seg_bundle["chart_density_hint"] = ""
            seg_bundle["_segment_mode"] = True
            seg_bundle["_segment_index"] = fix_idx + 1
            seg_bundle["_segment_total"] = len(groups)
            seg_bundle["_segment_written"] = prior_points
            seg_bundle["_segment_remaining"] = remaining
            user_prompt = (
                build_writer_user_prompt(seg_bundle) + f"\n\n## 修改要求\n{fix_seg}"
            )
            rewritten, messages = _generate_once(
                seg_bundle,
                user_prompt,
                max_tokens=per_tokens,
                chat_messages=messages,
                use_chat=use_chat,
            )
            if (rewritten or "").strip():
                parts[fix_idx] = rewritten.strip()

    return "\n\n".join(parts), messages if use_chat else chat_messages


def generate_summary(content: str) -> str:
    sampled = sample_content_for_summary(content)
    return call_llm_text(
        [
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": sampled},
        ],
        max_tokens=300,
    ).strip()[:150]


def _count_chinese_chars(content: str) -> int:
    return len(re.sub(r"\s+", "", content))


