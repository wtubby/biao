"""为前端交互测试造数据：直接用应用自己的 SQLAlchemy models 建项目，
跳过真实解析/LLM 调用，让 Playwright 能测导航/路由/刷新这类跟内容生成无关的交互路径。

用法：python3 scripts/seed_e2e_fixtures.py
输出：把生成的 project_id 写到 tests/e2e/.fixtures.json，供 Playwright 用例读取。
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.database import SessionLocal, engine  # noqa: E402
from db.models import Base, Project, TechOutline  # noqa: E402
from services.project_meta import set_meta  # noqa: E402

Base.metadata.create_all(bind=engine)


def _base_project(db, *, name: str, status: str) -> Project:
    p = Project(
        name=name,
        voltage_level="110kV",
        capacity="50MVA",
        duration_days=180,
        location="测试市测试区",
        bid_scope="technical",
        status=status,
        pause_requested=0,
    )
    set_meta(p, project_type="变电站工程", engineering_domain="电力工程")
    db.add(p)
    db.flush()
    return p


def _add_outline(db, project_id: str, *, generated: bool) -> None:
    root_id = str(uuid.uuid4())
    root = TechOutline(
        project_id=project_id,
        id=root_id,
        title="施工组织设计",
        parent_id=None,
        sort_order=1,
        level=1,
        is_leaf=0,
        is_locked=1,
        review_status="init",
        retry_count=0,
    )
    db.add(root)
    db.flush()
    leaf = TechOutline(
        project_id=project_id,
        id=str(uuid.uuid4()),
        title="施工总体部署",
        parent_id=root_id,
        sort_order=1,
        level=2,
        is_leaf=1,
        is_locked=1,
        review_status="green" if generated else "init",
        retry_count=0,
        generated_content="本工程施工总体部署如下：……（E2E 测试用桩数据）" if generated else None,
    )
    db.add(leaf)


def main() -> None:
    db = SessionLocal()
    fixtures = {}
    try:
        # 场景 A：confirm 步骤（工程信息已填，用来测子向导 + 浏览器后退）
        p_confirm = _base_project(db, name="E2E-确认向导", status="confirming")
        fixtures["confirm_project_id"] = p_confirm.id

        # 场景 B：generating 状态（用来测刷新页面时的进度条 / SSE 重连，
        # 不会有真实事件推送，但足够验证页面不崩、能正确回连）
        p_generating = _base_project(db, name="E2E-生成中刷新", status="generating")
        _add_outline(db, p_generating.id, generated=False)
        fixtures["generating_project_id"] = p_generating.id

        # 场景 C：done 状态（用来测预览页前进/后退时大纲数据一致性）
        p_done = _base_project(db, name="E2E-预览前进后退", status="done")
        _add_outline(db, p_done.id, generated=True)
        fixtures["done_project_id"] = p_done.id

        db.commit()
    finally:
        db.close()

    out_dir = Path(__file__).resolve().parent.parent / "tests" / "e2e"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / ".fixtures.json").write_text(json.dumps(fixtures, ensure_ascii=False, indent=2))
    print(json.dumps(fixtures, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()