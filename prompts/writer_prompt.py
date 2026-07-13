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
from prompts.context_blocks import (
    format_contradictions_block,
    format_facts_block,
    format_generation_extras,
    format_overview_block,
    format_scope_constraints,
)
from services.writing_guidance import get_chapter_constraints, is_descriptive_chapter

_WRITER_RULES = """每次只撰写**一个叶子章节**的正文，不得穿插、预写或概括其他章节内容。

输出 Markdown 正文，直接从正文段落开始，不要输出本章或其他章节的 # 标题行，不要前置客套话。

禁止：宏观宣誓套话、与上一章摘要完全重复的工艺、无单位孤立数字、无检索依据的品牌型号、编造未在检索素材/全局事实中出现的规范标准号、为其他章节写小节标题或正文。

概况/特点/目标类章节：只写客观描述或目标承诺，不写施工方案与保证措施（以本章定位中的专项约束为准）。

施工方案/措施类章节必须：具体施工步骤与可量化控制指标；关键参数用 **[参数] 数值+单位** 格式；需要图表处输出 JSON 占位符（冒号后紧跟 JSON，禁止写成 [GANTT_DATA] 单独一行再另起 JSON）：
[GANTT_DATA: [{"工序": "基础施工", "开始第几天": 1, "持续天数": 10}]] [TIMELINE_DATA: [...]] [FLOW_DATA: [...]] [ORG_DATA: {...}] [SMART_DATA: [...]]"""

_WRITER_RULES_COMPACT = """单章 Markdown 正文，无 # 标题行。禁止套话、无依据的品牌型号与标准号、跨章内容。
方案类须有步骤与 **[参数] 数值+单位**；图表用 [GANTT_DATA]/[FLOW_DATA]/[ORG_DATA] 等 JSON 占位符。
概况/目标类只写客观描述或承诺，不写措施。"""


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
        # 电力默认指南路径兼容：registry 中电力有 guide_file；无文件时再试 WRITING_GUIDE_PATH
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


def get_writer_system_prompt(domain: str | None = None, *, compact: bool | None = None) -> str:
    from config import WRITER_SYSTEM_COMPACT

    if compact is None:
        compact = WRITER_SYSTEM_COMPACT
    spec = resolve_domain(domain)
    rules = _WRITER_RULES_COMPACT if compact else _WRITER_RULES
    prompt = f"{spec.identity_prompt}\n\n{rules}"
    if compact:
        return prompt
    guide = load_domain_writing_guide(domain)
    if not guide:
        return prompt
    return f"{prompt}\n\n## {spec.label}技术标写作规范\n{guide}"


_OTHER_LEAF_PROMPT_LIMIT = 40


def build_writer_user_prompt(bundle: dict) -> str:
    guidance = bundle.get("guidance") or {}
    brief = guidance.get("brief") or "无"
    boundary = guidance.get("content_boundary") or "无"
    target_words = guidance.get("target_words")
    word_hint = f"建议篇幅约 {target_words} 字（允许 ±25%）" if target_words else "篇幅与绑定评分项分值匹配"

    scope_block = format_scope_constraints(bundle, style="writer", limit=_OTHER_LEAF_PROMPT_LIMIT)
    overview_block = format_overview_block(bundle.get("project_overview") or "", style="writer")
    empty_retrieval_block = format_retrieval_notes(bundle)
    sibling_block = format_immediate_prior_sibling_block(bundle, style="writer")
    prior_block = format_prior_chapters_block(bundle, style="writer")
    req_hint = (bundle.get("requirements_hint") or "").strip()
    req_hint_block = f"\n\n{req_hint}" if req_hint else ""
    matrix_context = (bundle.get("matrix_context") or "").strip()
    matrix_block = f"\n\n## 本章评分响应矩阵\n{matrix_context}\n" if matrix_context else ""
    evaluation_focus = (bundle.get("evaluation_focus") or "").strip()
    focus_block = f"\n\n{evaluation_focus}\n" if evaluation_focus else ""
    contra_block = format_contradictions_block(bundle.get("contradictions") or [], style="writer")

    base = f"""## 全局工程信息
{json.dumps(bundle['global_params'], ensure_ascii=False, indent=2)}

{overview_block}## 本章评分项
{bundle['requirements_text']}{req_hint_block}{matrix_block}{focus_block}

## 检索素材
{bundle['retrieval_text'] or '（无检索素材）'}
{empty_retrieval_block}
{sibling_block}{prior_block}{contra_block}## 章节定位
标题：{bundle['chapter_title']}
层级：第 {bundle['chapter_level']} 级
路径：{bundle['chapter_path']}
写作要点：{brief}
内容边界：{boundary}
篇幅要求：{word_hint}

## 撰写范围（必须遵守）
{scope_block}"""

    facts_text = (bundle.get("global_facts_text") or "").strip()
    if facts_text:
        base += f"""

【全局事实变量（全书保持一致，涉及时必须使用以下信息，不得自行编造）】
{facts_text}"""

    plan = bundle.get("content_plan")
    if plan:
        base += f"""

【本章写作规划（请严格按规划撰写，不得遗漏关键要点）】
必须覆盖的要点：
{chr(10).join('- ' + p for p in plan.get('key_points', []))}

拟采用的技术方法：
{chr(10).join('- ' + m for m in plan.get('technical_methods', []))}

需包含的关键数据：
{chr(10).join('- ' + d for d in plan.get('data_to_include', []))}

建议插入的图表：
{chr(10).join('- [' + c.get('type', '') + '] ' + c.get('purpose', '') for c in plan.get('charts_needed', []))}

本章目标字数：约 {plan.get('word_count_target', 1000)} 字

【不要重复上章内容】：{'; '.join(plan.get('avoid', []))}"""

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

    chapter_constraints = get_chapter_constraints(bundle.get("chapter_title"))
    if chapter_constraints:
        base += f"\n\n{chapter_constraints}"

    chart_hint = bundle.get("chart_density_hint")
    if chart_hint:
        base += f"\n\n## 图表要求\n{chart_hint}"

    standards_hint = bundle.get("standards_hint")
    if standards_hint:
        base += f"\n\n## 写作惯例提示（非标准条文原文，仅供表述参考）\n{standards_hint}"

    blind_constraints = (bundle.get("blind_bid_constraints") or "").strip()
    if blind_constraints:
        base += f"\n\n{blind_constraints}"

    ref_bid = (bundle.get("reference_bid_text") or "").strip()
    if ref_bid:
        base += f"""

## 以标写标参考（仅结构与表述风格参考；禁止逐句照抄；与本章无关内容忽略）
{ref_bid}"""
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

    return base + "\n\n请撰写本章正文。"


def build_key_chapter_init_prompt(
    project, requirements: list, outline_titles: list[str], domain: str | None = None,
    overview: str | None = None,
) -> str:
    from domains.registry import DEFAULT_DOMAIN, resolve_domain

    spec = resolve_domain(domain)
    domain_label = spec.label
    req_lines = "\n".join(f"- {r.requirement_title}" for r in requirements)
    titles = "\n".join(f"- {t}" for t in outline_titles)
    voltage_line = (
        f"电压等级：{project.voltage_level or '未填'}\n"
        if spec.key == DEFAULT_DOMAIN
        else ""
    )
    overview_block = ""
    if (overview or "").strip():
        overview_block = f"\n项目概况：\n{overview.strip()}\n"
    return f"""请记住以下{domain_label}技术标项目背景，后续将逐章请你撰写正文。

工程名称：{project.name}
{voltage_line}工程规模：{project.capacity or '未填'}
总工期：{project.duration_days or '未填'} 日历天
建设地点：{project.location or '未填'}
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
