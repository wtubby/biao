"""大纲节点树形遍历顺序（导出 / 装配用）。"""

from __future__ import annotations

from db.models import TechOutline


def sort_outline_tree_dfs(chapters: list[TechOutline]) -> list[TechOutline]:
    """按父子关系深度优先排序；sort_order 仅在同层兄弟间比较。

    不可单独用全局 sort_order 平面排序（同级兄弟会共用 1、2、3…）。
    """
    if not chapters:
        return []

    by_id = {ch.id: ch for ch in chapters}
    children_of: dict[str | None, list[TechOutline]] = {}

    for ch in chapters:
        parent_id = ch.parent_id
        if not parent_id or parent_id not in by_id:
            parent_id = None
        children_of.setdefault(parent_id, []).append(ch)

    for kids in children_of.values():
        kids.sort(key=lambda c: (c.sort_order or 0, c.id))

    ordered: list[TechOutline] = []

    def walk(parent_id: str | None) -> None:
        for ch in children_of.get(parent_id, []):
            ordered.append(ch)
            walk(ch.id)

    walk(None)
    return ordered
