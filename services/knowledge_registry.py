"""知识库文件夹注册表：从 knowledge/_registry.yaml 加载，按 mtime 热更新。"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from config import KNOWLEDGE_ROOT

logger = logging.getLogger(__name__)

_REGISTRY_NAME = "_registry.yaml"
_cache: dict[str, list[str]] | None = None
_cache_mtime: float | None = None

_FALLBACK: dict[str, list[str]] = {
    "default": ["主变安装", "GIS安装", "继保调试", "接地网敷设", "电缆敷设"],
    "线路工程": ["电缆敷设", "接地网敷设"],
    "电缆工程": ["电缆敷设", "接地网敷设"],
}


def registry_path() -> Path:
    return Path(KNOWLEDGE_ROOT) / _REGISTRY_NAME


def knowledge_root() -> Path:
    return Path(KNOWLEDGE_ROOT)


def clear_registry_cache() -> None:
    global _cache, _cache_mtime
    _cache = None
    _cache_mtime = None


def _normalize(raw: object) -> dict[str, list[str]]:
    if not isinstance(raw, dict):
        return dict(_FALLBACK)
    result: dict[str, list[str]] = {}
    for key, folders in raw.items():
        name = str(key).strip()
        if not name:
            continue
        if isinstance(folders, list):
            result[name] = [str(x).strip() for x in folders if str(x).strip()]
        elif folders is None:
            result[name] = []
        else:
            result[name] = [str(folders).strip()] if str(folders).strip() else []
    if "default" not in result:
        result["default"] = list(_FALLBACK["default"])
    return result


def load_registry() -> dict[str, list[str]]:
    """读取注册表；文件未变则返回缓存。"""
    global _cache, _cache_mtime
    path = registry_path()
    if not path.is_file():
        logger.warning("知识库注册表不存在: %s，使用内置回退列表", path)
        return dict(_FALLBACK)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return dict(_FALLBACK)
    if _cache is not None and _cache_mtime == mtime:
        return _cache
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("读取知识库注册表失败: %s，使用内置回退列表", exc)
        return dict(_FALLBACK)
    _cache = _normalize(raw)
    _cache_mtime = mtime
    return _cache


def get_knowledge_folders(
    project_type: str | None = None,
    engineering_domain: str | None = None,
) -> list[str]:
    """按项目类型匹配知识文件夹；匹配不到时按工程领域回退。

    与 get_reference_structure 对齐：电力子类型（线路工程/电缆工程等）优先；
    非电力领域若 registry 无对应条目则返回空列表——宁缺毋错，避免把电力工艺
    知识绑到市政/建筑/水利项目。
    """
    from domains.registry import DEFAULT_DOMAIN, resolve_domain

    folders_map = load_registry()
    if project_type:
        for key, folders in folders_map.items():
            if key != "default" and key in project_type:
                return list(folders)
    spec = resolve_domain(engineering_domain)
    if spec.key in folders_map and spec.key != "default":
        return list(folders_map[spec.key])
    if spec.key != DEFAULT_DOMAIN:
        return []
    return list(folders_map["default"])


def registered_folder_names() -> set[str]:
    """注册表中出现过的全部文件夹名（去重）。"""
    names: set[str] = set()
    for folders in load_registry().values():
        names.update(folders)
    return names


def disk_knowledge_folders() -> set[str]:
    """knowledge/ 下的知识分类目录（排除隐藏目录与非目录）。"""
    root = knowledge_root()
    if not root.is_dir():
        return set()
    result: set[str] = set()
    for p in root.iterdir():
        if not p.is_dir():
            continue
        if p.name.startswith("."):
            continue
        result.add(p.name)
    return result
