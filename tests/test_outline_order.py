"""大纲树形排序。"""

from types import SimpleNamespace

from services.outline_order import sort_outline_tree_dfs


def _node(id_, parent_id, sort_order, title=""):
    return SimpleNamespace(
        id=id_, parent_id=parent_id, sort_order=sort_order, title=title or id_,
    )


def test_sort_outline_tree_dfs_interleaves_parent_and_children():
    """一级章与其子节应交错排列，而非先全部一级再全部叶子。"""
    chapters = [
        _node("1", None, 1, "概述"),
        _node("2", None, 2, "总体方案"),
        _node("1.1", "1", 1, "工程概况"),
        _node("1.2", "1", 2, "建设必要性"),
        _node("2.1", "2", 1, "质量目标"),
    ]
    ordered = sort_outline_tree_dfs(chapters)
    assert [c.id for c in ordered] == ["1", "1.1", "1.2", "2", "2.1"]


def test_sort_outline_tree_dfs_respects_sibling_sort_order():
    chapters = [
        _node("1", None, 2),
        _node("2", None, 1),
        _node("2.2", "2", 2),
        _node("2.1", "2", 1),
    ]
    ordered = sort_outline_tree_dfs(chapters)
    assert [c.id for c in ordered] == ["2", "2.1", "2.2", "1"]
