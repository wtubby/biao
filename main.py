import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import get_cors_origins
from db.database import init_db
from routers import chart_preview, commercial, export, facts, generate, knowledge, outline, parse, project, prompts, settings
from services.env_check import run_env_checks

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Tech-Bid-Engine",
    description="工程技术方案自动生成系统",
    version="5.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(project.router)
app.include_router(parse.router)
app.include_router(settings.router)
app.include_router(outline.router)
app.include_router(prompts.router)
app.include_router(generate.router)
app.include_router(export.router)
app.include_router(commercial.router)
app.include_router(facts.router)
app.include_router(knowledge.router)
app.include_router(chart_preview.router)


@app.on_event("startup")
def on_startup():
    init_db()
    checks = run_env_checks()
    logger.info("环境检查完成: %s", checks)


@app.get("/api/domains")
def api_domains():
    from domains.registry import list_domain_keys
    return {"domains": list_domain_keys()}


@app.get("/api/env-status")
def env_status(recheck: bool = False):
    """返回环境依赖检测结果（Graphviz/Ghostscript/中文字体）。
    recheck=true 时强制重新探测（用户安装完 Graphviz 后不用重启程序就能刷新状态）。"""
    return run_env_checks(force=recheck)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "version": "5.0.0",
        "api_features": [
            "outline-catalog",
            "project-knowledge-folders",
            "contradictions",
            "mandatory-elements",
        ],
        "global_params_required": ["工程名称", "项目类型", "电压等级", "建设地点", "总工期"],
    }


frontend_dir = Path(__file__).parent / "frontend"
vendor_dir = frontend_dir / "vendor"
if vendor_dir.exists():
    app.mount("/vendor", StaticFiles(directory=str(vendor_dir)), name="vendor")
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="root")
