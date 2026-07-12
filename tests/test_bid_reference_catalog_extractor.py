"""投标文件参考格式启发式提取测试。"""

from services.bid_reference_catalog_extractor import extract_bid_reference_catalog_from_items
from services.document_parser import ParsedItem
from services.parser_service import (
    _chunk_for_extraction,
    _ensure_bid_reference_catalog,
    CHUNK_MAX_CHARS,
)


def _paras(*texts: str) -> list[ParsedItem]:
    return [ParsedItem(text=t, page=1, kind="paragraph") for t in texts]


def test_extract_bid_composition_toc():
    items = _paras(
        "其他说明文字",
        "一、投标函及投标函附录………………………（）",
        "二、法定代表人身份证明………………………（）",
        "三、授权委托书………………………………（）",
        "四、投标保证金………………………………（）",
        "五、报价清单………………………………（）",
        "六、项目实施方案……………………………（）",
        "七、资格审查资料……………………………（）",
        "八、其他材料…………………………………（）",
        "1.我方已仔细研究了…",
    )
    text = extract_bid_reference_catalog_from_items(items)
    assert "一、投标函及投标函附录" in text
    assert "六、项目实施方案" in text
    assert "七、资格审查资料" in text


def test_extract_prefers_construction_outline_under_tech_parent():
    items = _paras(
        "一、投标函及投标函附录",
        "二、授权委托书",
        "三、投标保证金",
        "六、项目实施方案",
        "七、资格审查资料",
        "施工组织设计纲要是投标书的重要组成部分，是评标、定标的重要因素。",
        "工程简述，工程规模，工程承包范围，地质及地貌状况，自然环境，交通情况等。",
        "设计特点、工程特点、影响施工的主要和特殊环节分析等。",
        "平面布置要求内容全面，充分利用现场条件，合理布置施工队。",
        "4.3主要工序和特殊工序的施工方法和施工效率估计，潜在问题的分析。",
        "（6）质量目标、质量保证体系及技术组织措施",
        "（7）安全目标、安全保证体系及技术组织措施",
        "9.3文明施工的目标、组织机构和实施方案",
    )
    text = extract_bid_reference_catalog_from_items(items)
    assert text.startswith("六、项目实施方案")
    assert "工程简述" in text
    assert "质量目标" in text
    assert "安全目标" in text
    assert "主要工序和特殊工序的施工方法" in text
    # 不应把 4.3 拆成「4.」+「3…」
    assert "3主要工序" not in text


def test_chunk_for_extraction_splits_single_page_long_doc():
    items = [
        ParsedItem(text=("段落内容" * 200), page=1, kind="paragraph")
        for _ in range(20)
    ]
    chunks = _chunk_for_extraction(items, max_chars=5000)
    assert len(chunks) >= 2
    assert sum(len(c) for c in chunks) == len(items)


def test_ensure_bid_reference_catalog_fills_when_empty():
    items = _paras(
        "一、投标函及投标函附录",
        "二、授权委托书",
        "三、投标保证金",
        "四、报价清单",
        "五、项目实施方案",
        "六、资格审查资料",
    )
    result = {"tender_detail": {"bid_reference_catalog": ""}}
    _ensure_bid_reference_catalog(result, items)
    assert "项目实施方案" in result["tender_detail"]["bid_reference_catalog"]


def test_ensure_bid_reference_catalog_keeps_llm_result():
    items = _paras("一、投标函", "二、授权委托书", "三、投标保证金", "四、报价清单")
    result = {"tender_detail": {"bid_reference_catalog": "（一）工程概况\n（二）施工方案"}}
    _ensure_bid_reference_catalog(result, items)
    assert result["tender_detail"]["bid_reference_catalog"] == "（一）工程概况\n（二）施工方案"


def test_chunk_max_chars_constant_under_annotate_budget():
    # 保证分块预算小于单块 annotate 截断阈值，避免块内再次被硬截断丢尾
    assert CHUNK_MAX_CHARS < 20000
