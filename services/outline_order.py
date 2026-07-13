"""大纲节点树形遍历顺序（读取 / 落库 / 导出）。"""

from __future__ import annotations

from db.models import TechOutline


def reorder_outline_dict_nodes(nodes: list[dict]) -> list[dict]:
    """按父子关系 DFS 遍历 dict 节点，并重赋全局唯一的 sort_order（1..n）。"""
    if not nodes:
        return []

    id_map = {str(n["id"]): dict(n) for n in nodes}
    children: dict[str | None, list[str]] = {}
    for n in nodes:
        pid = n.get("parent_id")
        if pid and str(pid) not in id_map:
            pid = None
        children.setdefault(pid, []).append(str(n["id"]))
    for ids in children.values():
        ids.sort(key=lambda i: (id_map[i].get("sort_order") or 0, i))

    ordered: list[dict] = []

    def visit(parent_id: str | None, level: int) -> None:
        for nid in children.get(parent_id, []):
            node = id_map[nid]
            node["level"] = level
            ordered.append(node)
            if not node.get("is_leaf"):
                visit(nid, level + 1)

    visit(None, 1)
    for i, node in enumerate(ordered, start=1):
        node["sort_order"] = i
    return ordered


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


def sort_leaves_by_dfs(
    leaves: list[TechOutline],
    all_nodes: list[TechOutline],
) -> list[TechOutline]:
    """在完整大纲树 DFS 序中排列叶子子集（跨分支全局顺序）。"""
    rank = {n.id: i for i, n in enumerate(sort_outline_tree_dfs(all_nodes))}
    return sorted(leaves, key=lambda x: rank.get(x.id, x.sort_order or 0))
