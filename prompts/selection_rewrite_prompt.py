from domains.registry import resolve_domain


def get_selection_rewrite_system_prompt(domain: str | None = None) -> str:
    identity = resolve_domain(domain).identity_prompt
    return f"""{identity}
你现在的任务是改写用户在技术标文档中选中的段落，只改写选中部分，保持专业、准确、与上下文衔接自然。

要求：
- 只输出替换后的新文本，不要输出解释、标题或 Markdown 代码块
- 保持与本领域技术方案一致的语气，使用具体工艺与可量化参数
- 不得编造企业资质、人员证书、合同金额、中标业绩
- 无依据时不要虚构设备型号或品牌；信息不足可写「待补充」
- 不要改动选区以外的内容"""


# 兼容旧引用（脚本/测试等无 domain 场景）
SELECTION_REWRITE_SYSTEM_PROMPT = get_selection_rewrite_system_prompt()


def build_selection_rewrite_user_prompt(
    chapter_title: str,
    selected_text: str,
    instruction: str,
    context_before: str,
    context_after: str,
) -> str:
    return f"""【章节】
{chapter_title}

【前文】
{context_before or '（无）'}

【后文】
{context_after or '（无）'}

【选中文本】
{selected_text}

【改写指令】
{instruction}

请只输出替换后的新文本。"""
