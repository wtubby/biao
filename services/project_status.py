"""项目状态机门禁（借鉴 tender-writer-v4 ensure_reviewed 闸门）。"""

from fastapi import HTTPException

# draft → parsing → confirming → planning → outline_locked → generating → done
ALLOW_UPLOAD = frozenset({"draft", "confirming", "planning"})
# 与 SAVE/LOCK 一致：仅 planning。generating/done 下整树删重建会冲掉已写正文。
ALLOW_OUTLINE_GENERATE = frozenset({"planning"})
ALLOW_OUTLINE_SAVE = frozenset({"planning"})
ALLOW_OUTLINE_LOCK = frozenset({"planning"})
ALLOW_GENERATE = frozenset({"outline_locked", "generating", "done"})
ALLOW_EXPORT = frozenset({"generating", "done", "outline_locked"})


def require_status(project, allowed: frozenset[str], action: str) -> None:
    if project.status not in allowed:
        raise HTTPException(
            400,
            f"当前状态为「{project.status}」，不允许{action}。"
            f"请按流程完成前置步骤（评分项确认 → 大纲锁定 → 内容生成）。",
        )

