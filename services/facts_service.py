"""全局事实变量：预设分组与项目初始化。"""

from sqlalchemy.orm import Session

from db.models import GlobalFact, Project

DEFAULT_FACT_GROUPS = [
    "项目基本信息",
    "企业资质与人员",
    "主要设备品牌型号",
    "施工组织配置",
    "质量与安全目标",
    "项目里程碑节点",
]


def _basic_info_content(project: Project) -> str:
    lines = []
    if project.name:
        lines.append(f"工程名称：{project.name}")
    if project.voltage_level:
        lines.append(f"电压等级：{project.voltage_level}")
    if project.capacity:
        lines.append(f"工程规模：{project.capacity}")
    if project.duration_days:
        lines.append(f"总工期：{project.duration_days} 日历天")
    if project.transformer_count:
        lines.append(f"主变台数：{project.transformer_count}")
    if project.location:
        lines.append(f"建设地点：{project.location}")
    return "\n".join(lines)


def init_default_facts(db: Session, project: Project) -> list[GlobalFact]:
    existing = db.query(GlobalFact).filter(GlobalFact.project_id == project.id).count()
    if existing:
        return db.query(GlobalFact).filter(GlobalFact.project_id == project.id).order_by(GlobalFact.sort_order).all()

    facts: list[GlobalFact] = []
    for i, title in enumerate(DEFAULT_FACT_GROUPS):
        content = _basic_info_content(project) if title == "项目基本信息" else ""
        fact = GlobalFact(project_id=project.id, title=title, content=content, sort_order=i)
        db.add(fact)
        facts.append(fact)
    db.commit()
    return facts


def sync_basic_info_fact(db: Session, project: Project) -> None:
    fact = (
        db.query(GlobalFact)
        .filter(GlobalFact.project_id == project.id, GlobalFact.title == "项目基本信息")
        .first()
    )
    if fact:
        fact.content = _basic_info_content(project)
        db.commit()


def prefill_facts_from_extraction(
    db: Session,
    project: Project,
    fact_groups: list[dict] | None,
) -> int:
    """解析完成后将事实分组预填入全局事实变量（仅填充空白分组）。"""
    init_default_facts(db, project)
    sync_basic_info_fact(db, project)

    filled = 0
    allowed_titles = set(DEFAULT_FACT_GROUPS)
    for item in fact_groups or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        content = str(item.get("content") or "").strip()
        if not title or not content or title not in allowed_titles:
            continue
        if title == "项目基本信息":
            continue

        fact = (
            db.query(GlobalFact)
            .filter(GlobalFact.project_id == project.id, GlobalFact.title == title)
            .first()
        )
        if not fact:
            continue
        if (fact.content or "").strip():
            continue
        fact.content = content
        filled += 1

    if filled:
        db.commit()
    return filled
