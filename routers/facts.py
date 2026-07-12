from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import GlobalFact, Project
from services.facts_service import init_default_facts

router = APIRouter(prefix="/api", tags=["facts"])


class FactCreate(BaseModel):
    title: str
    content: str = ""


class FactUpdate(BaseModel):
    title: str | None = None
    content: str | None = None


class FactReorder(BaseModel):
    orders: list[dict]


def _fact_out(f: GlobalFact) -> dict:
    return {
        "id": f.id,
        "project_id": f.project_id,
        "title": f.title,
        "content": f.content,
        "sort_order": f.sort_order,
    }


@router.get("/projects/{project_id}/facts")
def list_facts(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    facts = db.query(GlobalFact).filter(GlobalFact.project_id == project_id).order_by(GlobalFact.sort_order).all()
    if not facts:
        facts = init_default_facts(db, project)
    return [_fact_out(f) for f in facts]


@router.post("/projects/{project_id}/facts")
def create_fact(project_id: str, body: FactCreate, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    max_order = (
        db.query(GlobalFact.sort_order)
        .filter(GlobalFact.project_id == project_id)
        .order_by(GlobalFact.sort_order.desc())
        .first()
    )
    sort_order = (max_order[0] + 1) if max_order else 0
    fact = GlobalFact(project_id=project_id, title=body.title.strip(), content=body.content, sort_order=sort_order)
    db.add(fact)
    db.commit()
    db.refresh(fact)
    return _fact_out(fact)


@router.put("/facts/{fact_id}")
def update_fact(fact_id: str, body: FactUpdate, db: Session = Depends(get_db)):
    fact = db.query(GlobalFact).filter(GlobalFact.id == fact_id).first()
    if not fact:
        raise HTTPException(404, "事实分组不存在")
    if body.title is not None:
        fact.title = body.title.strip()
    if body.content is not None:
        fact.content = body.content
    fact.updated_at = datetime.now(timezone.utc)
    db.commit()
    return _fact_out(fact)


@router.delete("/facts/{fact_id}")
def delete_fact(fact_id: str, db: Session = Depends(get_db)):
    fact = db.query(GlobalFact).filter(GlobalFact.id == fact_id).first()
    if not fact:
        raise HTTPException(404, "事实分组不存在")
    db.delete(fact)
    db.commit()
    return {"success": True}


@router.post("/projects/{project_id}/facts/reorder")
def reorder_facts(project_id: str, body: FactReorder, db: Session = Depends(get_db)):
    for item in body.orders:
        fact = db.query(GlobalFact).filter(
            GlobalFact.id == item.get("id"),
            GlobalFact.project_id == project_id,
        ).first()
        if fact and "sort_order" in item:
            fact.sort_order = item["sort_order"]
    db.commit()
    return {"success": True}
