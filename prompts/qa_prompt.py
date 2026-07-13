import json

from prompts.bundle_blocks import (
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

QA_SYSTEM_PROMPT = """你是技术方案质检专家。检查正文是否完整回应评分项、品牌型号与规范标准号是否有检索素材/全局事实依据，以及是否超出当前章节范围（写了其他章节标题或内容）。

概况/特点/目标类章节：只应有客观描述或目标承诺，不得含施工方案、保证措施、「我方将采取」等对策表述。

【检查核心要点】
1. faithfulness_issues: 正文出现的品牌型号、具体规范标准号（如 GB/T、DL/T），若检索素材与评分项原文均未出现，则记为忠实度问题；常见通用表述可不报。
2. coverage_issues: 是否按评分项/写作规划要点逐条回应；是否仅有口号无参数；是否遗漏必备要素或量化要求；是否重复前序章节已写工艺。
3. scope_issues: 正文是否跨越边界写了其他章节的内容。
4. specificity_issues: 正文是否体现本项目特征（工程名称、电压等级、地点、工期、合同范围等全局信息，或检索素材中的项目细节）；若大量段落替换为任意同类工程仍成立、看不出针对本标书，则记为针对性不足。

请直接输出 JSON 字符串，不要包含 ```json 标记或任何前后导言。结构如下：
{
  "passed": true,
  "coverage_issues": ["问题1"],
  "faithfulness_issues": ["问题1"],
  "scope_issues": ["问题1"],
  "specificity_issues": ["问题1"]
}"""

_OTHER_LEAF_QA_LIMIT = 40
QA_SEGMENT_THRESHOLD = 8000
QA_SEGMENT_SIZE = 2800


def sample_content_windows_for_qa(
    content: str,
    *,
    threshold: int = QA_SEGMENT_THRESHOLD,
    window: int = QA_SEGMENT_SIZE,
) -> list[tuple[str, str]]:
    """返回 [(标签, 正文片段), ...]。短文单窗；长文头/中/尾三窗。"""
    text = (content or "").strip()
    if not text:
        return [("全文", "")]

    if len(text) <= threshold:
        return [("全文", text)]

    mid_start = max(0, (len(text) - window) // 2)
    windows = [
        ("开头", text[:window]),
        ("中段", text[mid_start:mid_start + window]),
        ("结尾", text[-window:]),
    ]

    # 去重完全相同的窗
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for label, body in windows:
        if body in seen:
            continue
        seen.add(body)
        unique.append((label, body))

    # 如果去重后意外为空（极端情况），做安全兜底
    return unique or [("全文片段", text[:window])]


def build_qa_user_prompt(
    content: str,
    bundle: dict,
    *,
    segment_label: str | None = None,
) -> str:
    from services.writing_guidance import get_chapter_constraints, get_chapter_type

    chapter_title = bundle.get("chapter_title", "未命名章节")
    chapter_path = bundle.get("chapter_path", "未知路径")

    # 1. 范围约束与章节属性
    scope_block = format_scope_constraints(bundle, style="qa", limit=_OTHER_LEAF_QA_LIMIT)
    type_block = ""
    constraints = get_chapter_constraints(chapter_title)
    if constraints:
        ctype = get_chapter_type(chapter_title)
        type_block = f"\n章节类型：{ctype}\n章节硬性约束：{constraints}\n"

    # 2. 正文片段处理
    if segment_label:
        body = content
        segment_line = (
            f"抽检片段标签：【{segment_label}】"
            "（注意：请仅基于本片段内容判断，勿臆测片段外未给出的部分）\n"
        )
    else:
        # 兼容旧调用：单次头尾拼接
        if len(content) <= QA_SEGMENT_THRESHOLD:
            body = content
        else:
            half = QA_SEGMENT_SIZE // 2
            body = f"{content[:half]}\n\n……（此处省略中间内容）……\n\n{content[-half:]}"
        segment_line = "抽检片段标签：【全文/头尾拼窗】\n"

    # 3. 全局事实与项目输入
    global_params = bundle.get("global_params") or {}
    global_block = ""
    if global_params:
        global_block = f"\n全局工程信息：\n{json.dumps(global_params, ensure_ascii=False, indent=2)}\n"

    overview_block = format_overview_block(bundle.get("project_overview") or "", style="qa")
    empty_hint = format_retrieval_notes(bundle, inline=False)
    facts_block = format_facts_block(bundle.get("global_facts_text") or "", style="qa")

    # 4. 写作规划响应要求
    plan = bundle.get("content_plan") or {}
    plan_block = ""
    key_points = [str(p).strip() for p in (plan.get("key_points") or []) if str(p).strip()]
    if key_points:
        plan_block = "\n本章写作规划预期覆盖要点：\n" + "\n".join(f"- {p}" for p in key_points) + "\n"
        avoid = [str(a).strip() for a in (plan.get("avoid") or []) if str(a).strip()]
        if avoid:
            plan_block += (
                "规划注明的规避内容（本章不应重复阐述）：\n"
                + "\n".join(f"- {a}" for a in avoid[:6])
                + "\n"
            )

    # 5. 上下文与矩阵细则
    prior_block = format_prior_chapters_block(bundle, style="qa")
    if prior_block and not prior_block.startswith("\n"):
        prior_block = "\n" + prior_block

    contra_block = format_contradictions_block(
        bundle.get("contradictions") or [], style="qa", max_items=4,
    )
    extras_block = format_generation_extras(bundle, style="qa")

    req_hint = (bundle.get("requirements_hint") or "").strip()
    req_hint_block = f"\n{req_hint}\n" if req_hint else ""

    matrix_context = (bundle.get("matrix_context") or "").strip()
    matrix_block = f"\n评分响应矩阵细则：\n{matrix_context}\n" if matrix_context else ""
    evaluation_focus = (bundle.get("evaluation_focus") or "").strip()
    focus_block = f"\n{evaluation_focus}\n" if evaluation_focus else ""

    requirements_text = bundle.get("requirements_text") or "（无明确评分项要求）"
    retrieval_text = bundle.get("retrieval_text") or "（无检索素材）"

    return f"""当前章节：{chapter_title}
章节路径：{chapter_path}
{segment_line}{scope_block}
{type_block}{global_block}{overview_block}
评分项：
{requirements_text}{req_hint_block}{matrix_block}{focus_block}
检索素材与事实依据：
{retrieval_text}
{empty_hint}{facts_block}{plan_block}{prior_block}{contra_block}{extras_block}
待质检正文片段：
{body}
"""
