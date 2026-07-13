"""正文/规划 Prompt 与摘要采样单元测试。"""

from prompts.plan_prompt import (
    build_plan_chat_messages,
    build_plan_user_messages,
    build_plan_user_prompt,
)
from prompts.qa_prompt import build_qa_user_prompt
from prompts.writer_prompt import (
    build_writer_chat_messages,
    build_writer_user_messages,
    build_writer_user_prompt,
    sample_content_for_summary,
)


def _base_bundle(**overrides):
    bundle = {
        "global_params": {
            "工程名称": "测试工程",
            "工程领域": "电力工程",
            "电压等级": "220kV",
            "总工期": 180,
            "建设地点": "四川",
        },
        "project_overview": "本工程为四川能源EPC项目，含设计采购施工总承包。",
        "requirements_text": "【施工组织】\n组织设计要求",
        "retrieval_text": "",
        "last_summary": "上章已写主变吊装工艺与控制参数。",
        "chapter_title": "施工进度计划",
        "chapter_level": 2,
        "chapter_path": "施工组织设计 > 施工进度计划",
        "guidance": {
            "brief": "写进度计划",
            "content_boundary": "只写进度，不写质量措施",
            "target_words": 800,
        },
        "global_facts_text": "【合同价】1.2亿元",
        "sibling_leaf_titles": ["施工部署", "施工准备"],
        "other_leaf_titles": [
            "施工部署",
            "施工准备",
            "质量管理体系与措施",
            "安全文明施工措施",
            "环境保护措施",
        ],
        "chart_density_hint": "适中插入甘特图",
        "standards_hint": "按电力EPC写作惯例",
        "reference_bid_text": "参考标书片段：采用三级网络计划控制。",
    }
    bundle.update(overrides)
    return bundle


def test_writer_user_messages_split_for_cache():
    parts = build_writer_user_messages(_base_bundle())
    assert len(parts) >= 3
    assert parts[0].startswith("## 全局工程信息")
    assert "## 检索素材" in parts[2] or any("## 检索素材" in p for p in parts)
    assert parts[-1].startswith("## 本章评分项") or "## 章节定位" in parts[-1]
    chat = build_writer_chat_messages(_base_bundle())
    assert chat[0]["role"] == "system"
    assert sum(1 for m in chat if m["role"] == "user") == len(parts)
    assert build_writer_user_prompt(_base_bundle()) == "\n\n".join(parts)


def test_writer_prompt_includes_other_leaves_and_overview():
    prompt = build_writer_user_prompt(_base_bundle())
    assert "全书其他叶子章节（禁止涉及）" in prompt
    assert "质量管理体系与措施" in prompt
    assert "项目概况（全书背景" in prompt
    assert "四川能源EPC项目" in prompt
    assert "补充说明" not in prompt
    assert "已写内容，本章勿重复展开" in prompt
    assert "适中插入甘特图" in prompt


def test_writer_prompt_includes_immediate_prior_sibling():
    prompt = build_writer_user_prompt(
        _base_bundle(
            immediate_prior_sibling_title="施工流水段划分",
            immediate_prior_sibling_body="A区、B区按流水段组织施工。",
            last_summary="上章已写主变吊装工艺与控制参数。",
        )
    )
    assert "已知前情" in prompt
    assert "施工流水段划分" in prompt
    assert "A区、B区" in prompt
    assert prompt.count("上一章技术摘要") == 0


def test_writer_prompt_dedupes_prior_and_last_summary():
    prompt = build_writer_user_prompt(
        _base_bundle(
            prior_summaries=[
                "「施工部署」已写现场布置",
                "「施工准备」已写临建方案",
            ],
            last_summary="上章已写主变吊装工艺与控制参数。",
        )
    )
    assert "前序章节已写要点" in prompt
    assert "施工部署" in prompt
    assert prompt.count("上一章技术摘要") == 0
    assert "主变吊装" not in prompt


def test_writer_prompt_includes_retrieval_warning():
    prompt = build_writer_user_prompt(
        _base_bundle(
            retrieval_warning="当前项目领域为市政工程，知识库暂无参考资料，建议人工核查",
        )
    )
    assert "检索说明" in prompt
    assert "市政工程" in prompt


def test_writer_prompt_omits_empty_overview():
    prompt = build_writer_user_prompt(_base_bundle(project_overview=None))
    assert "项目概况（全书背景" not in prompt


def test_plan_user_messages_split_for_cache():
    parts = build_plan_user_messages(_base_bundle())
    assert len(parts) >= 3
    assert parts[0].startswith("## 全局工程信息")
    assert any("## 检索素材" in p for p in parts)
    chat = build_plan_chat_messages(_base_bundle())
    assert chat[0]["role"] == "system"
    assert sum(1 for m in chat if m["role"] == "user") == len(parts)
    assert build_plan_user_prompt(_base_bundle()) == "\n\n".join(parts)


def test_plan_prompt_includes_matrix_context():
    prompt = build_plan_user_prompt(
        _base_bundle(
            matrix_context="【本章评分响应矩阵】\n- 「施工组织设计」（15分）；同项还绑定：施工准备"
        )
    )
    assert "本章评分响应矩阵" in prompt
    assert "施工准备" in prompt


def test_plan_prompt_includes_facts_chart_ref_and_scope():
    prompt = build_plan_user_prompt(_base_bundle())
    assert "全局事实变量" in prompt
    assert "合同价" in prompt
    assert "图表要求" in prompt
    assert "写作惯例提示（非标准条文原文）" in prompt
    assert "以标写标参考" in prompt
    assert "范围约束" in prompt
    assert "质量管理体系与措施" in prompt
    assert "项目概况（全书背景）" in prompt
    assert "avoid 字段须据此列出勿重复点" in prompt


def test_plan_prompt_includes_reference_bid_miss():
    prompt = build_plan_user_prompt(
        _base_bundle(reference_bid_text="", reference_bid_miss=True)
    )
    assert "以标写标说明" in prompt
    assert "未检索到相关参考片段" in prompt
    assert "以标写标参考" not in prompt


def test_plan_prompt_dedupes_prior_and_last_summary():
    prompt = build_plan_user_prompt(
        _base_bundle(
            prior_summaries=["「施工部署」已写现场布置"],
            last_summary="上章已写主变吊装工艺",
        )
    )
    assert "前序章节摘要" in prompt
    assert "avoid 必须据此列出勿重复点" in prompt
    assert "上一章技术摘要" not in prompt


def test_qa_prompt_includes_other_leaf_titles():
    prompt = build_qa_user_prompt("正文内容", _base_bundle())
    assert "全书其他叶子章节（不得涉及）" in prompt
    assert "环境保护措施" in prompt


def test_qa_prompt_includes_global_facts():
    prompt = build_qa_user_prompt("正文内容", _base_bundle())
    assert "全局事实变量" in prompt
    assert "合同价" in prompt


def test_qa_prompt_includes_writer_context_blocks():
    prompt = build_qa_user_prompt(
        "正文内容",
        _base_bundle(
            empty_retrieval_hint="本节无检索素材",
            reference_bid_miss=True,
            blind_bid_constraints="## 暗标约束\n- 不得出现公司名",
        ),
    )
    assert "项目概况" in prompt
    assert "四川能源EPC项目" in prompt
    assert "检索说明" in prompt
    assert "图表要求" in prompt
    assert "写作惯例提示" in prompt
    assert "以标写标" in prompt
    assert "暗标约束" in prompt
    assert "全局工程信息" in prompt
    assert "工程名称" in prompt


def test_qa_prompt_includes_descriptive_constraints():
    prompt = build_qa_user_prompt(
        "正文",
        _base_bundle(chapter_title="工程概况", chapter_path="总则 > 工程概况"),
    )
    assert "章节类型：overview" in prompt
    assert "只描述项目客观事实" in prompt or "客观" in prompt


def test_writer_prompt_forbids_fabricated_standards():
    from prompts.writer_prompt import get_writer_system_prompt

    sys_prompt = get_writer_system_prompt("电力工程")
    assert "规范标准号" in sys_prompt or "标准号" in sys_prompt


def test_sample_content_for_summary_short_unchanged():
    text = "短正文" * 10
    assert sample_content_for_summary(text) == text


def test_sample_content_for_summary_long_uses_head_and_tail():
    text = "A" * 3000 + "MID" + "B" * 3000
    sampled = sample_content_for_summary(text, head=2500, tail=1500)
    assert sampled.startswith("A" * 100)
    assert sampled.endswith("B" * 100)
    assert "中间部分省略" in sampled
    assert "MID" not in sampled
    assert len(sampled) < len(text)
