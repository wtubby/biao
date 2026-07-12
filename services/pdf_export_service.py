"""Word → PDF 转换（优先 LibreOffice，其次 Word COM）。"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def convert_docx_to_pdf(docx_path: Path, out_dir: Path | None = None) -> Path:
    """将 docx 转为同目录 pdf；失败抛出 ValueError。"""
    src = Path(docx_path)
    if not src.exists():
        raise ValueError(f"Word 文件不存在：{src}")
    target_dir = Path(out_dir) if out_dir else src.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = target_dir / f"{src.stem}.pdf"

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice:
        try:
            subprocess.run(
                [
                    soffice,
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(target_dir),
                    str(src),
                ],
                check=True,
                capture_output=True,
                timeout=180,
            )
            if pdf_path.exists():
                return pdf_path
        except (subprocess.SubprocessError, OSError) as exc:
            logger.warning("LibreOffice 转 PDF 失败: %s", exc)

    # Windows Word COM 回退
    try:
        import win32com.client  # type: ignore

        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        doc = word.Documents.Open(str(src.resolve()))
        # 17 = wdFormatPDF
        doc.SaveAs(str(pdf_path.resolve()), FileFormat=17)
        doc.Close(False)
        word.Quit()
        if pdf_path.exists():
            return pdf_path
    except Exception as exc:
        logger.warning("Word COM 转 PDF 失败: %s", exc)

    raise ValueError(
        "无法导出 PDF：请安装 LibreOffice（soffice）或本机 Microsoft Word 后重试"
    )
