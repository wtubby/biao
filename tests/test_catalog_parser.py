"""目录文本多级编号层级识别。"""

from services.catalog_parser import parse_catalog_text


def test_parse_catalog_numeric_levels():
    text = """第一章 工程概况
1.1 项目背景
1.1.1 建设规模
1. 总体部署
1.1 施工安排"""
    items = parse_catalog_text(text)
    assert [item["level"] for item in items] == [1, 2, 3, 2, 2]
    assert [item["title"] for item in items] == [
        "工程概况",
        "项目背景",
        "建设规模",
        "总体部署",
        "施工安排",
    ]


def test_parse_catalog_cn_level1():
    text = "（一）施工组织设计\n（二）质量保证措施"
    items = parse_catalog_text(text)
    assert all(item["level"] == 1 for item in items)
