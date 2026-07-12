import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Windows 上 Graphviz 常见安装路径（PATH 没配对时兜底）
_WINDOWS_GRAPHVIZ_FALLBACK_PATHS = [
    r"C:\Program Files\Graphviz\bin\dot.exe",
    r"C:\Program Files (x86)\Graphviz\bin\dot.exe",
]


def check_ghostscript() -> bool:
    return shutil.which("gswin64c") is not None or shutil.which("gs") is not None


def _find_dot_executable() -> str | None:
    found = shutil.which("dot")
    if found:
        return found
    for candidate in _WINDOWS_GRAPHVIZ_FALLBACK_PATHS:
        if Path(candidate).exists():
            return candidate
    return None


def check_graphviz() -> bool:
    """检测 Graphviz 是否可用（PATH + Windows 常见安装路径兜底）。"""
    dot_path = _find_dot_executable()
    if not dot_path:
        return False
    try:
        result = subprocess.run([dot_path, "-V"], capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def check_ocr() -> bool:
    """检测扫描件 OCR 依赖是否可用。"""
    try:
        from rapidocr_onnxruntime import RapidOCR  # noqa: F401
        return True
    except ImportError:
        return False


def check_chinese_font() -> str | None:
    try:
        import matplotlib.font_manager as fm
    except ImportError:
        return None
    candidates = ["SimHei", "Microsoft YaHei", "SimSun", "FangSong"]
    available = {f.name for f in fm.fontManager.ttflist}
    for name in candidates:
        if name in available:
            return name
    return None


GRAPHVIZ_INSTALL_HINT = (
    "未检测到 Graphviz，工艺流程图/组织架构图将退化为「解析异常，请人工补充」的警示图片，"
    "会直接出现在导出的 Word 文档中。"
    "Windows 安装：winget install Graphviz.Graphviz（或前往 https://graphviz.org/download/ 下载安装包），"
    "安装完成后需要重启本程序（如果安装程序没自动配置 PATH，需重启电脑或手动把 Graphviz\\bin 加入系统 PATH）。"
)


# ---- 启动时计算一次，缓存供 API / 前端复用，避免每次请求都起子进程 ----
_env_status_cache: dict | None = None


def run_env_checks(force: bool = False) -> dict:
    """启动时环境检查，返回检查结果摘要；结果会缓存，force=True 可强制重新检测。"""
    global _env_status_cache
    if _env_status_cache is not None and not force:
        return _env_status_cache

    gs_ok = check_ghostscript()
    gv_ok = check_graphviz()
    font = check_chinese_font()
    ocr_ok = check_ocr()

    if not gs_ok:
        logger.warning("Ghostscript 未安装，Camelot 将降级为 pdfplumber 全量解析")
    if not gv_ok:
        logger.warning(GRAPHVIZ_INSTALL_HINT)
    if not font:
        logger.warning("未检测到中文字体，图表文字将使用英文/拼音兜底")
    if not ocr_ok:
        logger.warning("rapidocr-onnxruntime 未安装，扫描件 PDF 将无法 OCR 解析")

    _env_status_cache = {
        "ghostscript": gs_ok,
        "graphviz": gv_ok,
        "graphviz_hint": GRAPHVIZ_INSTALL_HINT if not gv_ok else None,
        "chinese_font": font,
        "ocr": ocr_ok,
        "ocr_hint": (
            "未安装 rapidocr-onnxruntime，扫描件 PDF 无法自动识别。"
            "请执行：pip install rapidocr-onnxruntime"
        ) if not ocr_ok else None,
    }
    return _env_status_cache
