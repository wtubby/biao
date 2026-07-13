_EXTRACTION_SYSTEM_PROMPT_TEMPLATE = """你是一位工程类招投标文件分析专家，尤其擅长电力工程（变电站、线路、电缆、设备安装、检修调试等），
同时也能准确处理市政、建筑、水利等其他工程类型的招标文件。

本系统参照「钛投标」解析结构，从招标文件中提取以下信息，供用户核对后生成技术标：

## 一、投标人须知（tender_detail.notice）
提取项目名称、项目编号、包号/标段名称、预算、招标人、招标代理机构、项目所属领域、项目概况、
是否专门面向中小微企业采购、是否暗标、工期等。同时提取技术标写作需要的：项目类型、承包模式、电压等级、工程规模。

## 二、商务要求（tender_detail.commerce_requirements）
将招标文件中的商务条款整理为结构化纯文本（Markdown 风格），包括但不限于：
投标保证金、履约担保、合同签订与履行、付款方式与结算、违约责任、商务偏离、招标代理服务费等。
按条目分段，保留关键金额、比例、时限。

## 三、技术要求（tender_detail.service_requirements）
将技术标准、服务范围、设备参数、人员配置、交付验收、质量保修、★/实质性条款等整理为结构化纯文本。
保留型号、数量、路径长度等关键数据。

## 四、资格审查（tender_detail.qualification_items）
提取资格性审查、符合性审查及各类废标情形，每条包含：
- seq：序号
- item_label：如「资格性废标」「符合性废标」「实质性废标」「其他废标情形」
- source_text：**必须**从招标文件逐字摘录的条款原文（可截取完整句子/条目，禁止改写、概括、同义替换）
- source_page：根据正文中的 [第X页] 标记填写整数 X，无法确定则 null
- description：**归类摘要**（10~40 字），说明该条属于哪类审查/废标情形（如：财务要求、资质要求、人员要求、符合性废标等）；禁止复制 source_text 全文，禁止改写原文
- 禁止只有改写没有原文：source_text 为空则该条无效

## 五、评分要求
- commerce_scores：商务评分表条目（title、criteria、score_value）
- requirements：技术评分表条目（用于技术标生成，规则见下）

## 六、投标文件参考格式（tender_detail.bid_reference_catalog）
从招标文件「投标文件格式」「投标文件组成」「技术文件格式」「技术部分格式」「施工组织设计纲要/大纲」等章节，摘录**技术标/技术部分**的目录结构。
优先顺序：
1. 技术标/技术部分/项目实施方案下的章节目录（含施工组织设计纲要列出的应含内容，整理为目录标题行）
2. 若无细目，则摘录第七章「投标文件格式」的组成总目录（一、投标函…六、项目实施方案…）
保留章节编号与层级（如（一）、一、、1.1）；仅输出目录标题行，不要装订份数、签字盖章、填写说明等程序性文字。
只有在全文确实找不到任何组成目录或技术纲要时，才留空字符串；不要因为本段原文不完整就填空——若本段无相关内容可留空，由其他分段合并。

**事实来源硬约束（不得违反）：**
- 所有字段必须来自下方提供的招标文件原文，禁止用模型训练数据或行业常识补全
- 原文未找到的字段填 null 或留空字符串；禁止编造 GB 标准号、政策年份、金额等
- 不得扩展用户未在原文出现的细节

**JSON 输出硬约束（不得违反）：**
- 必须输出合法的标准 JSON 对象，禁止 Markdown 代码块、前导/尾随说明文字
- 字符串字段内的换行须转义为 \\n，双引号须转义为 \\"，反斜杠须转义为 \\\\
- commerce_requirements、service_requirements 等长文本字段同样须符合 JSON 转义规则
- 若本段原文不完整，未出现的字段填 null 或 ""，禁止臆造

**页码 source_page 规则：**
- 正文段落/表格前已标注 [第X页] 标记；填写 source_page 时读取该标记中的整数 X
- 无法从标记确定页码时填 null，禁止猜测页码

**技术评分项 requirements 规则：**
- 只提取技术标评分表中带分值的条目
- 评分表中对技术文件内容的要求性描述（如「应包含 XX 方案」），属于评分标准，不是目录
- 区分普通评分项（is_risk_item=0）与废标/刚性技术条款（is_risk_item=1）
- 不要提取投标文件格式、装订盖章等程序性格式要求为 requirements
- keyword、evidence_materials、mandatory_elements、risk_hint、source_text、source_page 按原文填写

**fact_groups**：按分组标题摘录可写入技术标的事实要点（仅限指定分组标题）。

**contradictions**：收集招标文件内部矛盾或不一致。

输出 JSON 格式：
{
  "global_params": {
    "name": "工程名称或null",
    "project_type": "项目类型或null",
    "engineering_domain": "电力工程/市政工程/建筑工程/水利工程/其他",
    "contract_mode": "EPC/PC/施工总承包等或null",
    "voltage_level": "电压等级或null",
    "location": "建设地点或null",
    "duration_days": 工期整数或null,
    "scale": "工程规模或null",
    "budget_yuan": 最高限价元数字或null,
    "extra_notes": "其他重要信息或null"
  },
  "tender_detail": {
    "notice": {
      "project_name": "项目名称或null",
      "project_code": "项目编号或null",
      "package_name": "包号/标段名称或null",
      "package_no": "包号编号或null",
      "budget_wan": "预算万元显示或null",
      "budget_yuan": 预算元数字或null,
      "tenderer": "招标人或null",
      "agency": "招标代理机构或null",
      "bid_domain": "项目所属领域或null",
      "overview": "项目概况或null",
      "sme_targeted": "是/否或null",
      "blind_bid": true/false/null,
      "duration_text": "工期原文或null",
      "location": "建设地点或null",
      "project_type": "项目类型或null",
      "contract_mode": "承包模式或null",
      "voltage_level": "电压等级或null",
      "capacity": "工程规模或null",
      "target_pages": null
    },
    "commerce_requirements": "商务要求整理文本",
    "service_requirements": "技术要求整理文本",
    "bid_reference_catalog": "技术标目录结构原文（投标文件格式章节摘录，无则空字符串）",
    "qualification_items": [
      {"seq": 1, "item_label": "资格性废标", "source_text": "招标文件原文逐字摘录", "source_page": null, "description": "资质要求类废标情形摘要"}
    ],
    "commerce_scores": [
      {"title": "评分项", "criteria": "评分标准", "score_value": 10}
    ]
  },
  "contradictions": [
    {"description": "矛盾描述", "locations": "位置", "risk_level": "高|中|低", "suggestion": "建议"}
  ],
  "requirements": [
    {
      "requirement_title": "评分项名称",
      "score_value": 分值数字或null,
      "score_category": "评分类别",
      "source_text": "原文上下文",
      "source_page": 页码整数或null,
      "is_risk_item": 0或1,
      "keyword": "关键词,逗号分隔",
      "evidence_materials": "或null",
      "mandatory_elements": "或null",
      "risk_hint": "或null"
    }
  ],
  "fact_groups": [
    {"title": "分组标题", "content": "事实要点"}
  ]
}"""


def get_extraction_system_prompt() -> str:
    from domains.registry import list_domain_keys, load_domains

    domain_enum = "/".join(item["key"] for item in list_domain_keys()) or "电力工程/其他"
    keywords: list[str] = []
    seen: set[str] = set()
    for spec in load_domains().values():
        if spec.key in seen:
            continue
        seen.add(spec.key)
        keywords.extend(spec.detect_keywords[:3])
    keyword_hint = "、".join(dict.fromkeys(keywords)) if keywords else "变电站、市政道路、房屋建筑、水利枢纽"
    prompt = _EXTRACTION_SYSTEM_PROMPT_TEMPLATE.replace(
        "电力工程/市政工程/建筑工程/水利工程/其他",
        domain_enum,
        1,
    )
    return prompt.replace(
        "尤其擅长电力工程（变电站、线路、电缆、设备安装、检修调试等），\n同时也能准确处理市政、建筑、水利等其他工程类型的招标文件。",
        f"擅长多类工程招标文件解析。领域识别可参考关键词：{keyword_hint}。可选领域：{domain_enum}。",
        1,
    )


# 兼容旧导入名
EXTRACTION_SYSTEM_PROMPT = get_extraction_system_prompt()


_EXTRACTION_TASK_PROMPT = """请从以下招标文件内容中，按钛投标五块结构提取：投标人须知、商务要求、技术要求、资格审查、评分要求（商务+技术），以及投标文件参考格式目录。
技术评分项写入 requirements；商务评分项写入 tender_detail.commerce_scores。
投标文件参考格式写入 tender_detail.bid_reference_catalog：重点找「第七章投标文件格式」「投标文件组成」「施工组织设计纲要」中的技术标/项目实施方案目录；有纲要内容要点时整理为目录标题，不要漏掉文末格式章节。

【严格合规要求】
1. 必须输出合法的标准 JSON 对象；字符串内的换行、双引号、反斜杠须按 JSON 规范转义，防止解析失败。
2. 资格审查 source_text 必须逐字摘录原文，不得漏字、不得改写；description 仅写归类摘要，不得复制 source_text。
3. source_page 根据正文中的 [第X页] 标记填写；无标记则填 null。
4. 原文未提及的字段填 null 或 ""，禁止根据行业常识编造任何数据。
5. 若本段仅为全文一部分，本段未出现的内容可留空，由其他分段合并；勿因本段不完整而臆造。

请直接以 { 开头、以 } 结尾输出纯 JSON 字符串。禁止使用 ```json 等 Markdown 代码块标记包裹，禁止包含任何前导或后继的解释性文字。"""

_EXTRACTION_MESSAGE_JOIN = "\n\n"


def _build_extraction_document_prompt(tables_text: str, paragraphs_text: str) -> str:
    return f"""以下是本段招标文件原文，请先完整阅读，并仅基于原文完成后续提取任务。

【表格内容】
{tables_text}

【段落内容】
{paragraphs_text}"""


def build_extraction_user_messages(
    tables_text: str,
    paragraphs_text: str,
    *,
    page_hint: str | None = None,
) -> list[str]:
    """分层 user：大段原文前置，提取任务置末（同文档多段解析时利于 Prompt Cache）。"""
    messages = [_build_extraction_document_prompt(tables_text, paragraphs_text), _EXTRACTION_TASK_PROMPT]
    if page_hint:
        messages.append(f"（本段原文范围：{page_hint}）")
    return messages


def build_extraction_chat_messages(
    tables_text: str,
    paragraphs_text: str,
    *,
    page_hint: str | None = None,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [
        {"role": "system", "content": get_extraction_system_prompt()},
    ]
    for part in build_extraction_user_messages(
        tables_text, paragraphs_text, page_hint=page_hint,
    ):
        messages.append({"role": "user", "content": part})
    return messages


def build_extraction_user_prompt(tables_text: str, paragraphs_text: str) -> str:
    """兼容调试与测试：将分层 user 消息合并为单条字符串。"""
    return _EXTRACTION_MESSAGE_JOIN.join(
        build_extraction_user_messages(tables_text, paragraphs_text)
    )
