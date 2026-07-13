import json

from services.generation_mode import GENERATION_MODE_FULL, branch_mode_hint, skeleton_mode_hint

# ---------------------------------------------------------------------------
# 行业参考结构 — 骨架生成时供模型参考，非强制模板
# ---------------------------------------------------------------------------

_OUTLINE_REFERENCE_STRUCTURES: dict[str, str] = {
    "变电站新建": """
- 土建工程：地基基础、构支架及设备基础、主控通信楼及辅助建筑、站区道路及围墙、防洪排水
- 电气一次安装：主变压器安装、GIS/HGIS 或敞开式配电装置安装、无功补偿装置、站用电系统
- 电气二次安装：继电保护及安全自动装置、监控自动化系统、通信系统、直流电源系统
- 调试：分系统调试、整套启动调试
- 接地与防雷：接地网施工、防雷装置
""",
    "变电站改造": """
- 拆除及旧设备处理：旧设备拆除、迁移、场地清理
- 土建改造：基础加固或新建、构支架改造
- 电气一次改造：新旧设备切改、母线及一次设备安装
- 电气二次改造：保护及自动化系统改造、通信系统改造
- 调试与切改：新旧系统并网调试、停电切改方案
""",
    "线路工程": """
- 基础工程：杆塔基础施工（含特殊地形基础）
- 杆塔工程：铁塔组立、杆塔组装
- 架线工程：导地线展放、紧线、附件安装
- 接地工程：接地装置施工
- 跨越工程：交叉跨越（道路、河流、既有线路）施工方案
""",
    "电缆工程": """
- 电缆通道工程：电缆沟、排管、隧道施工
- 电缆敷设：电缆牵引敷设、接头制作
- 电缆终端及附件安装
- 接地及等电位连接
- 电缆试验：交接试验、耐压试验
""",
    "设备安装": """
- 设备开箱与验收
- 设备就位与安装
- 电气连接与调试
- 分系统及整体调试
""",
    "检修调试": """
- 检修前准备：停电方案、安全措施
- 分部检修：一次设备检修、二次设备检修
- 调试与试验：交接试验、启动调试
- 验收与投运
""",
    "default": """
- 土建/基础工程
- 设备安装（一次/二次）
- 系统调试
- 质量与安全保障措施
""",
}

_GENERIC_REFERENCE_STRUCTURE = """
- 施工准备与总体部署
- 主体工程施工（按专业工作面拆分）
- 质量与安全保障措施
- 竣工验收与交付
"""


def get_reference_structure(project_type: str | None, engineering_domain: str | None = None) -> str:
    from domains.registry import DEFAULT_DOMAIN, resolve_domain

    if project_type:
        for key, text in _OUTLINE_REFERENCE_STRUCTURES.items():
            if key != "default" and key in project_type:
                return text
    spec = resolve_domain(engineering_domain)
    if spec.key != DEFAULT_DOMAIN:
        return _GENERIC_REFERENCE_STRUCTURE
    return _OUTLINE_REFERENCE_STRUCTURES["default"]


_LEAF_NODE_RULES = """### 叶子节点字段
- writing_guidance：写作要点，≤30 字，动词短语，说明「写什么」而非「怎么写」
- content_boundary：80~200 字，说明本节写什么、不写什么、须回应的评分关注点
- bound_folder：从提供的知识库文件夹中选最匹配项，无匹配填 null

### 章节类型与 content_boundary（按标题选用，勿混用）

| 类型 | 识别特征 | content_boundary 应写 | 禁止写 |
|------|----------|----------------------|--------|
| 项目目标 | 含「目标」且涉及质量/工期/造价/安全，不含「措施」「保证」「方案」 | 概括性目标承诺；回应评分项中的目标要求 | 保证措施、工艺细节、组织机构、检验频次 |
| 工程概况 | 概况、简介、项目特点、工程特点、现场条件 | 建设规模、电压等级、主要工程量、地形交通、工程显著特征；可描述重难点现象 | 施工方案、保证措施、组织设计、进度计划、「我方将采取」类对策 |
| 施工组织 | 组织、部署、平面布置 | 组织机构、劳动力、机具、临设布置原则 | 具体安装工序参数 |
| 专项方案 | 安装、敷设、调试、专项 | 工序流程、关键参数、质量控制点、须回应的评分关注点 | 其他专业方案、宏观口号 |
| 进度计划 | 进度、工期计划 | 里程碑、关键路径、与总工期关系 | 详细工艺 |
| 质量安全 | 质量/安全/文明（非「目标」类） | 引用规程、控制要点、检验原则 | 与标题无关的专业方案 |

### content_boundary 对照示例（仅供理解，勿照抄）

项目目标类（好）：
「写质量、工期、造价三方面概括性目标承诺，与全局工期一致；回应评分项中的目标要求；不写保证措施与工艺细节。」

工程概况/项目特点类（好）：
「写本工程规模、电压等级、主变台数、站址地形及交通条件；归纳迁改交叉、狭小场地等显著特点；可点出施工难点现象；不写施工方案与保证措施。」

专项方案类（好）：
「写 GIS 就位与安装工序、允许偏差、气室充气及试验项目；回应评分项关键词；不写土建与二次接线内容。」"""

SKELETON_SYSTEM_PROMPT = """## TASK
你是工程投标技术方案大纲策划专家（EPC、PC、施工承包等）。
本次只生成大纲的"骨架"：一级章节 + 二级章节，不涉及评分项绑定、不涉及具体写作指导，这些留给下一步逐支展开处理。
推理在内部完成，只输出 JSON，不输出解释或 Markdown。

## RULES

### 一级章节
- 必须与用户目录中的一级标题完全一致，不得删改、合并、调换顺序

### 二级章节
- 若用户目录中某一级章节下已经给出了二级（或更细）标题，原样保留这些二级标题作为本章的二级节点，不得删除、替换
- 对用户目录中还没有给出二级标题的一级章节，参考<行业参考结构>和项目基本信息，提出 2~6 个二级子节标题，
  体现专业、系统的技术方案结构；结合本项目实际规模、类型判断哪些子项适用，不要生搬硬套参考结构，不要照抄参考结构原文
- 二级标题 8~16 字为宜，能准确指向一个专业方向或工作面即可，不需要过长
- 所有输出节点的 is_leaf 统一填 0（叶子层级由下一步生成），writing_guidance / content_boundary / requirement_ids 留空
- id 格式："1"、"2"（一级），"1.1"、"2.3"（二级）；parent_id 与 level 保持一致

## OUTPUT FORMAT
仅输出一个 JSON 对象：
{"nodes": [
  {"id": "1", "title": "章节标题", "parent_id": null, "level": 1, "is_leaf": 0, "sort_order": 1},
  {"id": "1.1", "title": "二级子节标题", "parent_id": "1", "level": 2, "is_leaf": 0, "sort_order": 1}
]}"""


def get_skeleton_system_prompt(engineering_domain: str | None = None) -> str:
    from domains.registry import resolve_domain

    identity = resolve_domain(engineering_domain).identity_prompt
    # 将写作人设改写为大纲策划语境，保留领域专业性
    expert = identity.replace("技术方案撰写专家", "投标技术方案大纲策划专家")
    if expert == identity:
        expert = f"{identity.rstrip('。')}；同时擅长技术方案大纲策划。"
    return SKELETON_SYSTEM_PROMPT.replace(
        "你是工程投标技术方案大纲策划专家（EPC、PC、施工承包等）。",
        f"{expert}（EPC、PC、施工承包等）。",
        1,
    )


def build_skeleton_user_prompt(global_info: dict, catalog: list[dict], reference_text: str, *, generation_mode: str | None = None) -> str:
    mode = generation_mode or GENERATION_MODE_FULL
    catalog_text = _format_catalog(catalog)
    mode_hint = skeleton_mode_hint(mode)
    return f"""请为下方项目生成大纲骨架（一级 + 二级）。

<generation_mode>
{mode_hint}
</generation_mode>

<project_info>
{json.dumps(global_info, ensure_ascii=False, indent=2)}
</project_info>

<catalog>
{catalog_text}
</catalog>

一级标题约束：nodes 中 level=1 的 title 必须与 catalog 内【一级标题锁定清单】中的文本逐字一致，不得附加序号前缀（如「1.」）或 level 后缀（如「（level=1）」）。

<行业参考结构（仅供参考，按实际项目取舍增删，不要照抄）>
{reference_text}
</行业参考结构>

仅输出 JSON。"""


BRANCH_SYSTEM_PROMPT = """## TASK
你是工程投标技术方案大纲策划专家。你会收到大纲树中**一个二级章节分支**，需要判断：
1. 该分支内容是否单薄、无需再拆——若是，把它自己标记为叶子节点直接返回（不新增子节点）；
2. 或者需要向下拆到三级（必要时四级）叶子节点，使相关评分项都能被清晰覆盖、专业内容划分合理。
只输出这一个分支自身（不拆分时）或它的下级节点（拆分时），不要输出其他分支、不要输出整棵树。
推理在内部完成，只输出 JSON，不输出解释或 Markdown。

## RULES

### 是否需要向下拆分
- 若该分支只对应 1 项评分项、内容单一、不需要再分专业工作面：直接返回**这一个节点自身**（id/parent_id/level/title 不变），
  is_leaf 改为 1，并补齐 requirement_ids、writing_guidance、content_boundary、bound_folder
- 若该分支对应多项评分项，或按行业惯例应包含多个专业工作面/工序：向下拆到三级（必要时四级）叶子节点，
  新节点 id 以本分支 id 为前缀（如本分支为 "2.1"，子节点为 "2.1.1"、"2.1.2"），本分支自身不要出现在输出里
  （分支本身作为容器节点由上层处理）。如需要四级，三级节点可以是非叶子容器（is_leaf=0），四级为叶子。
- 若用户原始目录中该分支下已经给出了更细的标题，必须保留这些标题，可在此基础上补充

### 评分项绑定
- 每个叶子节点（is_leaf=1）的 requirement_ids 优先绑定与本分支专业内容语义相关的评分项，不要为凑绑定关系而勉强关联无关评分项
- 若该分支确实没有匹配的评分项，requirement_ids 可为空列表，但仍需体现专业方案内容
- requirement_ids 只能使用用户消息中列出的 ID，禁止编造
- 同一评分项允许绑定多个叶子节点（不同分支各自需要时）
- 你只看到当前分支，但 all_requirements 列出了全部评分项；若某评分项与当前分支内容勉强相关，且在大纲中无更合适的章节承载，请在本分支下建立对应子节予以覆盖，避免标书漏项
- 优先绑定与本分支语义强相关的评分项；不要为了独占绑定而与其他分支争抢同一 requirement_id

### 跨分支去重
- 用户消息中的 `<other_branches>` 列出同级其他二级分支，其主题已由并行展开任务占用
- 本分支子节点标题与 content_boundary 不得复述、抢占这些分支的专业范围

%LEAF_RULES%

### 篇幅控制
- 单个分支通常节点不多，无需为了省 token 压缩深度，按专业逻辑正常拆分即可
- content_boundary 仍控制在 200 字以内，一句一事

## OUTPUT FORMAT
仅输出一个 JSON 对象：
{"nodes": [ ... ]}"""


def get_branch_system_prompt(engineering_domain: str | None = None) -> str:
    from domains.registry import resolve_domain

    identity = resolve_domain(engineering_domain).identity_prompt
    expert = identity.replace("技术方案撰写专家", "投标技术方案大纲策划专家")
    if expert == identity:
        expert = f"{identity.rstrip('。')}；同时擅长技术方案大纲策划。"
    return (
        BRANCH_SYSTEM_PROMPT.replace(
            "你是工程投标技术方案大纲策划专家。",
            f"{expert}。",
            1,
        )
        .replace("%LEAF_RULES%", _LEAF_NODE_RULES)
    )


def _format_other_branches(other_branches: list[dict] | None) -> str:
    lines: list[str] = []
    for item in other_branches or []:
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        bid = str(item.get("id") or "").strip()
        lines.append(f"- {bid} {title}" if bid else f"- {title}")
    if not lines:
        return "（无其他同级二级分支）"
    return "\n".join(lines)


def build_branch_user_prompt(
    global_info: dict,
    branch: dict,
    catalog: list[dict],
    requirements: list[dict],
    knowledge_folders: list[str] | None = None,
    *,
    generation_mode: str | None = None,
    other_branches: list[dict] | None = None,
) -> str:
    mode = generation_mode or GENERATION_MODE_FULL
    risk_text, req_text = _format_requirements(requirements)
    catalog_text = _format_catalog(catalog)
    other_branches_text = _format_other_branches(other_branches)
    folder_hint = "、".join(knowledge_folders or []) or "无"
    mode_hint = branch_mode_hint(mode)
    return f"""请判断并展开下方分支节点。

<generation_mode>
{mode_hint}
</generation_mode>

<project_info>
{json.dumps(global_info, ensure_ascii=False, indent=2)}
</project_info>

<branch>
id={branch['id']}，标题「{branch['title']}」，parent_id={branch.get('parent_id')}，level={branch.get('level')}
</branch>

<other_branches>
以下同级二级分支已由其他展开任务占用；本分支子节点不得重复其主题或专业范围：
{other_branches_text}
</other_branches>

<原始用户目录（参考，若本分支在其中已有更细标题必须保留）>
{catalog_text}
</原始用户目录>

<risk_requirements>
{risk_text}
</risk_requirements>

<all_requirements>
{req_text}
</all_requirements>

<knowledge_folders>
{folder_hint}
</knowledge_folders>

执行要求：
1. 只判断和展开「{branch['title']}」这一个分支，不要输出其他分支内容
2. 子节点标题与 content_boundary 不得与 <other_branches> 中列出的分支主题重复或抢占
3. 判断该分支是否需要向下拆分（见系统提示规则）
4. 若拆分，新增子节点 id 以 "{branch['id']}." 为前缀
5. 若 all_requirements 中有评分项与当前分支勉强相关且无更合适的章节承载，请在本分支下建立子节覆盖，避免漏项
6. 仅输出 JSON"""


def _format_requirements(requirements: list[dict]) -> tuple[str, str]:
    """分离刚性评分项与全部评分项，便于模型优先覆盖。"""
    risk_lines: list[str] = []
    all_lines: list[str] = []
    for r in requirements:
        line = (
            f"- ID={r['id']} | {r['title']} | 分值={r.get('score_value')} | "
            f"刚性={r.get('is_risk_item')} | 类别={r.get('score_category') or '未分类'}"
        )
        all_lines.append(line)
        if r.get("is_risk_item") == 1:
            risk_lines.append(line)
    risk_block = "\n".join(risk_lines) if risk_lines else "（无刚性评分项）"
    all_block = "\n".join(all_lines)
    return risk_block, all_block


def _format_catalog(catalog: list[dict]) -> str:
    lines: list[str] = []
    level1_titles: list[str] = []
    for i, item in enumerate(catalog):
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        level = int(item.get("level") or 1)
        order = item.get("sort_order", i + 1)
        if level == 1:
            level1_titles.append(title)
        indent = "  " * max(level - 1, 0)
        lines.append(f"{indent}{order}. {title}（level={level}）")
    header = ""
    if level1_titles:
        locked = "\n".join(f"  - {t}" for t in level1_titles)
        header = (
            "【一级标题锁定清单】\n"
            "返回 JSON 时，一级节点的 title 必须与下列文本逐字一致，"
            "不得附加序号前缀（如「1.」）或 level 后缀（如「（level=1）」）。\n"
            f"{locked}\n\n"
        )
    return header + "\n".join(lines)
