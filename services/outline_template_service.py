"""内置标准大纲模板库。"""

from pathlib import Path

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "outlines"
_META_PREFIX = "# "


def _parse_meta_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped.startswith(_META_PREFIX):
        return None
    body = stripped[len(_META_PREFIX):]
    if ":" not in body:
        return None
    key, value = body.split(":", 1)
    return key.strip().lower(), value.strip()


def _read_template_meta(path: Path) -> dict[str, str]:
    meta: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            parsed = _parse_meta_line(line)
            if not parsed:
                if line.strip() and not line.strip().startswith("#"):
                    break
                continue
            meta[parsed[0]] = parsed[1]
    except OSError:
        pass
    return meta


def _strip_meta_header(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        if _parse_meta_line(line):
            continue
        if not lines and not line.strip():
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def list_outline_templates() -> list[dict[str, str]]:
    if not _TEMPLATES_DIR.exists():
        return []
    templates: list[dict[str, str]] = []
    for path in sorted(_TEMPLATES_DIR.glob("*.txt")):
        meta = _read_template_meta(path)
        templates.append(
            {
                "id": path.stem,
                "name": meta.get("name") or path.stem,
                "description": meta.get("description", ""),
            }
        )
    return templates


def get_outline_template(template_id: str) -> dict[str, str]:
    safe_id = Path(template_id).stem
    path = _TEMPLATES_DIR / f"{safe_id}.txt"
    if not path.exists():
        raise FileNotFoundError(f"大纲模板不存在：{template_id}")
    raw = path.read_text(encoding="utf-8")
    meta = _read_template_meta(path)
    return {
        "id": safe_id,
        "name": meta.get("name") or safe_id,
        "description": meta.get("description", ""),
        "text": _strip_meta_header(raw),
    }
