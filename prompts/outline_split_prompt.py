"""规划期长章节结构化拆分 Prompt。"""

from __future__ import annotations

import json

from prompts.outline_prompt import _LEAF_NODE_RULES

SPLIT_SYSTEM_PROMPT = """## TASK
你是工程投标技术方案大纲策划专家。你会收到**一个偏长的叶子章节**，需要在**不改变专业逻辑**的前提下，将其拆成 3~4 个**可独立生成**的三级/四级子节点。
拆分依据必须是施工组织、工序、工作面、资源配置等业务结构，**禁止**仅按字数机械切分。
推理在内部完成，只输出 JSON，不输出解释或 Markdown。

## RULES

### 拆分原则
- 子节点须顺序承接：前一节点交代的前提/划分，后一节点直接展开，主题不重叠
- 每个子节点是一个完整的技术主题（如流水段划分 → 劳动力配置 → 机械时序）
- 子节点标题 8~16 字，能准确指向一个工作面或工序块
- 父节点目标字数为约束：子节点合计约等于父节点字数，单节点建议 600~900 字技术深度

### 评分项绑定
- 每个子节点只绑定与**本子节点主题**语义相关的评分项（requirement_ids）
- 若某子节点没有匹配的评分项，requirement_ids 可为 []
- requirement_ids 只能使用 `<bound_requirements>` 中列出的 ID，禁止编造
- 同一评分项可绑定多个子节点（仅当多个子节点确实都需要覆盖该评分内容时）
- 禁止把父节点全部评分项原样复制给每一个子节点

### 字段要求
{_LEAF_NODE_RULES}

### 输出 id
- 使用 id_suffix：\"1\"、\"2\"、\"3\"（系统将拼为「父节点 id + . + suffix」）
- 必须输出 3~4 个子节点

## OUTPUT FORMAT
仅输出 JSON：
{{"nodes": [
  {{"id_suffix": "1", "title": "子节标题", "guidance_brief": "写作要点", "content_boundary": "边界说明", "requirement_ids": ["评分项id"]}},
  ...
]}}"""


def get_split_system_prompt(engineering_domain: str | None = None) -> str:
    from domains.registry import resolve_domain

    identity = resolve_domain(engineering_domain).identity_prompt
    expert = identity.replace("技术方案撰写专家", "投标技术方案大纲策划专家")
    if expert == identity:
        expert = f"{identity.rstrip('。')}；同时擅长技术方案大纲策划。"
    return SPLIT_SYSTEM_PROMPT.replace(
        "你是工程投标技术方案大纲策划专家。",
        expert if expert.endswith("。") else f"{expert}。",
        1,
    ).format(_LEAF_NODE_RULES=_LEAF_NODE_RULES)


def build_split_user_prompt(
    *,
    global_info: dict,
    leaf: dict,
    parent_path: str,
    sibling_titles: list[str],
    requirements: list[dict],
    target_words: int,
    per_child_words: int,
) -> str:
    req_lines = []
    for r in requirements:
        kw = (r.get("keyword") or "").strip() or "（无）"
        mandatory = (r.get("mandatory_elements") or "").strip() or "（无）"
        req_lines.append(
            f"- id={r['id']} | {r.get('title') or ''} | {r.get('score_value') or 0}分"
            f" | keyword={kw} | mandatory={mandatory}"
        )
    req_text = "\n".join(req_lines) if req_lines else "（无绑定评分项）"
    siblings = "、".join(sibling_titles) if sibling_titles else "（无）"
    bound = leaf.get("bound_folder") or "null"
    return f"""请将下方叶子章节按**专业结构**拆成 3~4 个可独立撰写的子节点。

<project_info>
{json.dumps(global_info, ensure_ascii=False, indent=2)}
</project_info>

<parent_section>
路径：{parent_path}
</parent_section>

<leaf_to_split>
id={leaf.get('id')}
标题：{leaf.get('title')}
目标字数：约 {target_words} 字（请拆成 3~4 个子节点，每个约 {per_child_words} 字）
写作要点：{leaf.get('guidance_brief') or '（无）'}
内容边界：{leaf.get('content_boundary') or '（无）'}
bound_folder：{bound}
</leaf_to_split>

<bound_requirements>
{req_text}
</bound_requirements>

<同级兄弟章节（子节点不得涉及）>
{siblings}
</同级兄弟章节>

请输出 3~4 个子节点 JSON；为每个子节点分配相关的 requirement_ids（可为空列表）；
子节点 content_boundary 须明确「写什么 / 不写什么 / 与前后子节点如何衔接」。
仅输出 JSON。"""
