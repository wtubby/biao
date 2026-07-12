from fastapi import APIRouter
from pydantic import BaseModel

from services.chart_preview_service import render_chart_previews

router = APIRouter(prefix="/api", tags=["chart-preview"])


class ChartPreviewRequest(BaseModel):
    content: str
    duration_days: int | None = None


@router.post("/chart-preview")
def chart_preview(body: ChartPreviewRequest):
    return {"charts": render_chart_previews(body.content, body.duration_days)}
