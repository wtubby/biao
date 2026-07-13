import json
from functools import lru_cache
from pathlib import Path

from config import BASE_DIR, WRITING_GUIDE_PATH
from domains.registry import DEFAULT_DOMAIN, resolve_domain
from prompts.bundle_blocks import (
    format_immediate_prior_sibling_block,
    format_prior_chapters_block,
    format_retrieval_notes,
)
from prompts.project_context import build_cacheable_project_prefix
from prompts.context_blocks import format_scope_constraints
from services.writing_guidance import get_chapter_constraints, is_descriptive_chapter

_WRITER_RULES = """每次只撰写**一个叶子章节**的正文，严格聚焦于当前章节内容，不得穿插、预写或概括其他章节。

【输出格式要求】
1. 直接从正文第一段开始输出，**严禁输出任何 # 标题行**，严禁带有任何客套话或导言。
2. 方案/措施类章节：必须包含具体施工步骤与可量化控制指标。关键参数必须采用 **[参数] 数值+单位** 格式。
3. 需要插入图表处，请直接嵌入以下格式的单行 JSON 占位符（切勿单独换行）：
   [GANTT_DATA: [{"工序": "基础施工", "开始第几天": 1, "持续天数": 10}]]
   [TIMELINE_DATA: [...]] [FLOW_DATA: [...]] [ORG_DATA: {...}]

【材料真实性底线】
1. 坚决杜绝宏观宣誓套话。
2. 凡涉及品牌、设备型号、具体的规范标准号（如 GB/T、DL/T），必须完全以本标书提供的「检索素材」或「全局事实」为准。若素材中未提及，则只做通用技术描述，**绝对不得凭空编造任何型号或标准号**！"""

_WRITER_RULES_COMPACT = """单章 Markdown 正文，严禁输出 # 标题行。
凡涉及标准号、品牌型号，必须有据可查，无依据时只做通用工艺描述，严禁凭空虚构。
方案类须有量化步骤与 **[参数] 数值+单位**。
概况/目标类只写客观描述或承诺，不写具体对策措施。"""

_WRITER_RULES_STRUCTURED = """每次只撰写**一个叶子章节**的正文，严格聚焦于当前章节内容，不得穿插、预写或概括其他章节。

【输出格式要求】
1. 按系统提示的 JSON 格式输出，markdown_content 为纯正文，严禁 # 标题行与客套话。
2. 方案/措施类：须含量化步骤与 **[参数] 数值+单位**；图表写入 embedded_charts，正文用 [[CHART:n]] 标记插入位置。

【材料真实性底线】
1. 坚决杜绝宏观宣誓套话。
2. 品牌、设备型号、规范标准号须以「检索素材」或「全局事实」为准；无依据时只做通用描述，严禁编造。"""

_WRITER_RULES_COMPACT_STRUCTURED = """单章 JSON 输出：markdown_content 纯正文（无 # 标题），图表放 embedded_charts。
标准号/品牌须有依据；方案类须 **[参数] 数值+单位**；概况类只写客观描述。"""


def _writer_identity(domain: str | None) -> str:
    return resolve_domain(domain).identity_prompt


@lru_cache(maxsize=1)
def load_writing_guide() -> str:
    path = Path(WRITING_GUIDE_PATH)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


@lru_cache(maxsize=8)
def load_domain_writing_guide(domain: str | None) -> str:
    """按工程领域加载写作指南。"""
    spec = resolve_domain(domain)
    if not spec.guide_file:
        if spec.key == DEFAULT_DOMAIN:
            return load_writing_guide()
        return ""
    path = Path(BASE_DIR) / "templates" / spec.guide_file
    if not path.exists():
        if spec.key == DEFAULT_DOMAIN:
            return load_writing_guide()
        return ""
    return path.read_text(encoding="utf-8").strip()


def compact_writing_guide(domain: str | None, max_chars: int = 600) -> str:
    """从领域写作指南提取要点摘要，供 compact system 模式注入 user prompt。"""
    guide = load_domain_writing_guide(domain)
    if not guide:
        return ""
    lines: list[str] = []
    for line in guide.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("|"):
            if "---" in stripped:
                continue
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if len(cells) >= 2 and cells[0] not in ("章节类型", ""):
                lines.append(f"- {cells[0]}：{cells[1]}")
            continue
        if stripped.startswith("-"):
            lines.append(stripped)
        else:
            lines.append(f"- {stripped}")
    text = "\n".join(lines)
    if len(text) <= max_chars:
        return text
    trimmed = text[:max_chars]
    if "\n" in trimmed:
        trimmed = trimmed.rsplit("\n", 1)[0]
    return trimmed.rstrip()


def should_attach_guide_to_user(bundle: dict) -> bool:
    """compact system 模式下，施工类章在 user prompt 附带领域要点。"""
    from config import WRITER_SYSTEM_COMPACT

    if not WRITER_SYSTEM_COMPACT:
        return False
    return not is_descriptive_chapter(bundle.get("chapter_title"))


def get_writer_system_prompt(
    domain: str | None = None,
    *,
    compact: bool | None = None,
    structured: bool | None = None,
) -> str:
    from config import WRITER_STRUCTURED_OUTPUT, WRITER_SYSTEM_COMPACT
    from services.writer_output import writer_output_json_hint

    if compact is None:
        compact = WRITER_SYSTEM_COMPACT
    if structured is None:
        structured = WRITER_STRUCTURED_OUTPUT
    spec = resolve_domain(domain)
    if structured:
        rules = _WRITER_RULES_COMPACT_STRUCTURED if compact else _WRITER_RULES_STRUCTURED
    else:
        rules = _WRITER_RULES_COMPACT if compact else _WRITER_RULES
    prompt = f"{spec.identity_prompt}\n\n{rules}"
    if structured:
        prompt = f"{prompt}\n\n{writer_output_json_hint()}"
    if compact:
        return prompt
    guide = load_domain_writing_guide(domain)
    if not guide:
        return prompt
    return f"{prompt}\n\n## {spec.label}技术标写作规范\n{guide}"


_OTHER_LEAF_PROMPT_LIMIT = 40

_WRITER_MESSAGE_JOIN = "\n\n"


def _writer_project_context(bundle: dict) -> str:
    """同项目各章共享的稳定上下文（前置以利于 Prompt Cache）。"""
    return build_cacheable_project_prefix(bundle)


def _writer_continuity_context(bundle: dict) -> str:
    """前序章节与同级衔接（按撰写顺序变化）。"""
    sibling_block = format_immediate_prior_sibling_block(bundle, style="writer")
    prior_block = format_prior_chapters_block(bundle, style="writer")
    return (sibling_block + prior_block).strip()


def _writer_retrieval_context(bundle: dict) -> str:
    retrieval_text = bundle.get("retrieval_text") or "（无检索素材）"
    empty_retrieval_block = format_retrieval_notes(bundle)
    body = f"## 检索素材\n{retrieval_text}"
    if empty_retrieval_block:
        body = f"{body}\n{empty_retrieval_block}"
    return body.strip()


def _writer_chapter_task_body(bundle: dict) -> str:
    """本章任务与规划（每章/每段不同，置末）。"""
    requirements_text = bundle.get("requirements_text") or "（无相关评分项要求）"
    chapter_title = bundle.get("chapter_title") or "未命名章节"
    chapter_level = bundle.get("chapter_level") or "未知"
    chapter_path = bundle.get("chapter_path") or "未知路径"

    guidance = bundle.get("guidance") or {}
    brief = guidance.get("brief") or "无"
    boundary = guidance.get("content_boundary") or "无"
    target_words = guidance.get("target_words")
    word_hint = f"建议篇幅约 {target_words} 字（允许 ±25%）" if target_words else "篇幅与绑定评分项分值匹配"

    scope_block = format_scope_constraints(bundle, style="writer", limit=_OTHER_LEAF_PROMPT_LIMIT)

    req_hint = (bundle.get("requirements_hint") or "").strip()
    req_hint_block = f"\n\n{req_hint}" if req_hint else ""
    matrix_context = (bundle.get("matrix_context") or "").strip()
    matrix_block = f"\n\n## 本章评分响应矩阵\n{matrix_context}\n" if matrix_context else ""
    evaluation_focus = (bundle.get("evaluation_focus") or "").strip()
    focus_block = f"\n\n{evaluation_focus}\n" if evaluation_focus else ""

    base = f"""## 本章评分项
{requirements_text}{req_hint_block}{matrix_block}{focus_block}

## 章节定位
标题：{chapter_title}
层级：第 {chapter_level} 级
路径：{chapter_path}
写作要点：{brief}
内容边界：{boundary}
篇幅要求：{word_hint}

## 撰写范围（必须遵守）
{scope_block}"""

    plan = bundle.get("content_plan")
    if plan and isinstance(plan, dict):
        kp_list = plan.get("key_points") or []
        tm_list = plan.get("technical_methods") or []
        di_list = plan.get("data_to_include") or []
        ch_list = plan.get("charts_needed") or []
        av_list = plan.get("avoid") or []

        kp_str = "\n".join(f"- {p}" for p in kp_list) if kp_list else "- 无"
        tm_str = "\n".join(f"- {m}" for m in tm_list) if tm_list else "- 无"
        di_str = "\n".join(f"- {d}" for d in di_list) if di_list else "- 无"
        ch_str = (
            "\n".join(
                f"- [{c.get('type', '')}] {c.get('purpose', '')}"
                for c in ch_list
                if isinstance(c, dict)
            )
            if ch_list
            else "- 无"
        )
        av_str = "; ".join(av_list) if av_list else "无"

        base += f"""

【本章写作规划（请严格按规划撰写，不得遗漏关键要点）】
必须覆盖的要点：
{kp_str}

拟采用的技术方法：
{tm_str}

需包含的关键数据：
{di_str}

建议插入的图表：
{ch_str}

本章目标字数：约 {plan.get('word_count_target', 1000)} 字

【不要重复上章内容】：{av_str}"""

    if bundle.get("_segment_mode"):
        seg_i = bundle.get("_segment_index") or 1
        seg_n = bundle.get("_segment_total") or 1
        written = bundle.get("_segment_written") or []
        remaining = bundle.get("_segment_remaining") or []
        base += f"""

## 分段撰写（第 {seg_i}/{seg_n} 段）
- 只写本段「必须覆盖的要点」，不要写其他段要点
- 不要输出本章 # 标题，不要写「接上文」等过渡套话
- 已写要点（勿重复）：{'；'.join(written) if written else '（无）'}
- 后续段将写（本段勿抢写）：{'；'.join(remaining) if remaining else '（本段为最后一段）'}"""

    chapter_constraints = get_chapter_constraints(chapter_title)
    if chapter_constraints:
        base += f"\n\n{chapter_constraints}"

    chart_hint = bundle.get("chart_density_hint")
    if chart_hint:
        base += f"\n\n## 图表要求\n{chart_hint}"

    ref_bid = (bundle.get("reference_bid_text") or "").strip()
    if ref_bid:
        base += (
            "\n\n## 以标写标参考（仅结构与表述风格参考；禁止逐句照抄；与本章无关内容忽略）\n"
            f"{ref_bid}"
        )
    elif bundle.get("reference_bid_miss"):
        base += (
            "\n\n## 以标写标说明\n"
            "已启用以标写标，但本章未检索到相关参考片段，请勿臆造参考内容，按评分项与工程参数正常撰写。"
        )

    if should_attach_guide_to_user(bundle):
        excerpt = (bundle.get("writing_guide_excerpt") or "").strip()
        if not excerpt:
            from config import WRITER_GUIDE_USER_MAX_CHARS

            excerpt = compact_writing_guide(
                bundle.get("engineering_domain"),
                WRITER_GUIDE_USER_MAX_CHARS,
            )
        if excerpt:
            base += f"\n\n## 领域写作要点\n{excerpt}"

    from config import WRITER_STRUCTURED_OUTPUT

    if WRITER_STRUCTURED_OUTPUT:
        return base + "\n\n请按 JSON 格式输出本章正文（markdown_content + embedded_charts）。"
    return base + "\n\n请撰写本章正文。"


def build_writer_user_messages(
    bundle: dict,
    *,
    fix_instructions: str | None = None,
) -> list[str]:
    """分层 user 消息：稳定上下文前置，本章任务置末（利于 Prompt Cache 前缀命中）。"""
    messages: list[str] = []
    for part in (
        _writer_project_context(bundle),
        _writer_continuity_context(bundle),
        _writer_retrieval_context(bundle),
        _writer_chapter_task_body(bundle),
    ):
        text = (part or "").strip()
        if text:
            messages.append(text)
    if fix_instructions:
        messages.append(f"## 修改要求\n{fix_instructions.strip()}")
    return messages


def build_writer_chat_messages(
    bundle: dict,
    *,
    fix_instructions: str | None = None,
    include_system: bool = True,
    structured: bool | None = None,
) -> list[dict[str, str]]:
    domain = bundle.get("engineering_domain") or DEFAULT_DOMAIN
    messages: list[dict[str, str]] = []
    if include_system:
        messages.append({
            "role": "system",
            "content": get_writer_system_prompt(domain, structured=structured),
        })
    for part in build_writer_user_messages(bundle, fix_instructions=fix_instructions):
        messages.append({"role": "user", "content": part})
    return messages


def build_writer_user_prompt(
    bundle: dict,
    *,
    fix_instructions: str | None = None,
) -> str:
    """兼容调试预览：将分层 user 消息合并为单条字符串。"""
    return _WRITER_MESSAGE_JOIN.join(
        build_writer_user_messages(bundle, fix_instructions=fix_instructions)
    )


def build_key_chapter_init_prompt(
    project, requirements: list, outline_titles: list[str], domain: str | None = None,
    overview: str | None = None,
) -> str:
    spec = resolve_domain(domain)
    domain_label = spec.label
    req_lines = "\n".join(f"- {r.requirement_title}" for r in requirements) if requirements else "（无）"
    titles = "\n".join(f"- {t}" for t in outline_titles) if outline_titles else "（无）"

    voltage_line = ""
    if spec.key == DEFAULT_DOMAIN:
        voltage_line = f"电压等级：{getattr(project, 'voltage_level', '未填')}\n"

    overview_block = ""
    if (overview or "").strip():
        overview_block = f"\n项目概况：\n{overview.strip()}\n"

    return f"""请记住以下{domain_label}技术标项目背景，后续将逐章请你撰写正文。

工程名称：{getattr(project, 'name', '未填')}
{voltage_line}工程规模：{getattr(project, 'capacity', '未填')}
总工期：{getattr(project, 'duration_days', '未填')} 日历天
建设地点：{getattr(project, 'location', '未填')}
{overview_block}
评分项：
{req_lines}

大纲结构：
{titles}

请确认已理解。后续每次只撰写指定的一章正文，不得提前撰写或穿插其他章节内容。"""


SUMMARY_SYSTEM_PROMPT = (
    "将以下技术方案章节压缩为150字以内技术摘要。"
    "必须保留：已写工艺/方法、设备规格、控制参数、工序顺序。"
    "摘要末尾用一句话列出「勿重复要点」（供下一章避让）。"
    "只输出摘要文本，不要标题或解释。"
)


def sample_content_for_summary(content: str, head: int = 2500, tail: int = 1500) -> str:
    """长章取头尾，避免摘要只覆盖前半段导致跨章重复。"""
    text = (content or "").strip()
    if len(text) <= head + tail:
        return text
    return text[:head] + "\n\n……（中间部分省略）……\n\n" + text[-tail:]
