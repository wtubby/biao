from domains.registry import resolve_domain


def get_selection_rewrite_system_prompt(domain: str | None = None) -> str:
    identity = resolve_domain(domain).identity_prompt
    return f"""{identity}
你现在的任务是改写用户在技术标文档中选中的段落（即【选中文本】）。你必须做到「无痕无缝替换」，只改写选中部分，使其与【前文】和【后文】衔接自然。

【核心行为准则】
1. 绝对严禁输出任何解释、说明、标点符号包裹（如 ``` 或 " ）、或者「好的，以下是改写后的内容」等废话。你的输出将直接用于前端替换。
2. 保持与本领域技术方案一致的语气，使用具体工艺与可量化参数，不得降低专业度。
3. 保持原文本的组织结构。如果原文本是多行、列表（如 1. 2. 3. 或 1) 2) ）或段落，改写后必须保持相同的行数和序号结构，不得合并或散架。
4. 恪守事实：不得编造企业资质、人员证书、合同金额、中标业绩；信息不足或无检索依据时，不要虚构设备型号或品牌，可保留原样或写「待补充」。
5. 不要改动或续写选区以外（即【前文】和【后文】）的内容。"""


def build_selection_rewrite_user_prompt(
    chapter_title: str,
    selected_text: str,
    instruction: str,
    context_before: str,
    context_after: str,
) -> str:
    # 规避大模型因看到「（无）」而产生格式误判，无前后文时直接不渲染该模块
    before_block = f"【上下文 - 前文】\n{context_before}\n\n" if context_before else ""
    after_block = f"【上下文 - 后文】\n{context_after}\n\n" if context_after else ""

    return f"""当前章节：{chapter_title}

{before_block}{after_block}【待改写的原选中文本】
{selected_text}

【用户改写指令】
{instruction}

【执行要求】
请立即根据指令改写上述【待改写的原选中文本】。再次强调：只输出替换后的新文本，严禁夹带任何 Markdown 代码块（```）、任何导言或解释。
替换后的新文本："""
