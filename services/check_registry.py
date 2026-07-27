"""可插拔检查注册表：Finding 协议 + 章级/项目级运行器。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from services.check_catalog import category_default_severity, category_label


Severity = str  # info | warn | block


@dataclass
class Finding:
    check_id: str
    category: str
    severity: Severity
    message: str
    evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_error_string(self) -> str:
        """兼容现有 review_errors 字符串列表。"""
        label = category_label(self.category)
        if self.message.startswith(f"[{label}]"):
            return self.message
        return f"[{label}] {self.message}"


@dataclass
class ChapterCheckContext:
    content: str
    project: Any
    requirements: list = field(default_factory=list)
    guidance: dict | None = None
    chapter_title: str | None = None
    other_leaf_titles: list[str] | None = None
    allowed_standard_sources: str | None = None
    content_plan: dict | None = None
    facts_text: str | None = None
    global_params: dict | None = None
    prior_contents: list[str] | None = None
    scope: str = "chapter"  # chapter | segment


@dataclass
class ProjectCheckContext:
    project: Any
    chapters: list
    requirements: list
    docx_text: str
    meta: dict[str, Any] = field(default_factory=dict)
    docx_path: Any = None
    format_info: dict[str, Any] = field(default_factory=dict)
    qualification_items: list[dict[str, Any]] = field(default_factory=list)


ChapterCheckFn = Callable[[ChapterCheckContext], list[Finding]]
ProjectCheckFn = Callable[[ProjectCheckContext], list[Finding]]


@dataclass
class CheckSkill:
    check_id: str
    category: str
    severity: Severity
    scopes: tuple[str, ...]
    run_chapter: ChapterCheckFn | None = None
    run_project: ProjectCheckFn | None = None
    description: str = ""


_REGISTRY: dict[str, CheckSkill] = {}


def register_check(skill: CheckSkill) -> CheckSkill:
    _REGISTRY[skill.check_id] = skill
    return skill


def get_check(check_id: str) -> CheckSkill | None:
    return _REGISTRY.get(check_id)


def list_checks(*, scope: str | None = None) -> list[CheckSkill]:
    ensure_builtin_checks_registered()
    skills = list(_REGISTRY.values())
    if scope:
        skills = [s for s in skills if scope in s.scopes]
    return skills


def _messages_to_findings(
    messages: list[str],
    *,
    check_id: str,
    category: str,
    severity: Severity | None = None,
) -> list[Finding]:
    sev = severity or category_default_severity(category)
    return [
        Finding(
            check_id=check_id,
            category=category,
            severity=sev,
            message=str(msg),
        )
        for msg in messages
        if msg
    ]


def wrap_message_check(
    check_id: str,
    category: str,
    *,
    severity: Severity | None = None,
    scopes: tuple[str, ...] = ("chapter",),
    description: str = "",
):
    """把返回 list[str] 或 list[Finding] 的规则函数注册为章级 CheckSkill。"""

    def decorator(fn: Callable[[ChapterCheckContext], list]):
        sev = severity or category_default_severity(category)

        def _run(ctx: ChapterCheckContext) -> list[Finding]:
            raw = fn(ctx) or []
            if raw and isinstance(raw[0], Finding):
                out: list[Finding] = []
                for item in raw:
                    if not isinstance(item, Finding):
                        continue
                    out.append(
                        Finding(
                            check_id=item.check_id or check_id,
                            category=item.category or category,
                            severity=item.severity or sev,
                            message=item.message,
                            evidence=item.evidence or "",
                        )
                    )
                return out
            return _messages_to_findings(
                raw,
                check_id=check_id,
                category=category,
                severity=sev,
            )

        return register_check(
            CheckSkill(
                check_id=check_id,
                category=category,
                severity=sev,
                scopes=scopes,
                run_chapter=_run,
                description=description or fn.__doc__ or "",
            )
        )

    return decorator


def run_chapter_checks(ctx: ChapterCheckContext) -> list[Finding]:
    ensure_builtin_checks_registered()
    findings: list[Finding] = []
    for skill in list_checks(scope=ctx.scope):
        if not skill.run_chapter:
            continue
        try:
            findings.extend(skill.run_chapter(ctx) or [])
        except Exception as exc:  # noqa: BLE001 — 单条检查失败不阻断整轮
            findings.append(
                Finding(
                    check_id=skill.check_id,
                    category=skill.category,
                    severity="warn",
                    message=f"检查执行异常：{exc}",
                )
            )
    return dedupe_findings(findings)


def run_project_checks(ctx: ProjectCheckContext) -> list[Finding]:
    ensure_builtin_checks_registered()
    findings: list[Finding] = []
    for skill in list_checks(scope="project"):
        if not skill.run_project:
            continue
        try:
            findings.extend(skill.run_project(ctx) or [])
        except Exception as exc:  # noqa: BLE001
            findings.append(
                Finding(
                    check_id=skill.check_id,
                    category=skill.category,
                    severity="warn",
                    message=f"检查执行异常：{exc}",
                )
            )
    return dedupe_findings(findings)


def dedupe_findings(findings: list[Finding]) -> list[Finding]:
    seen: set[str] = set()
    unique: list[Finding] = []
    for item in findings:
        key = f"{item.check_id}|{item.message}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def findings_to_messages(findings: list[Finding], *, with_label: bool = False) -> list[str]:
    if with_label:
        return [f.as_error_string() for f in findings]
    return [f.message for f in findings]


def summarize_findings(findings: list[Finding]) -> dict[str, Any]:
    by_category: dict[str, list[dict[str, Any]]] = {}
    block = warn = info = 0
    for f in findings:
        by_category.setdefault(f.category, []).append(f.to_dict())
        if f.severity == "block":
            block += 1
        elif f.severity == "info":
            info += 1
        else:
            warn += 1
    return {
        "total": len(findings),
        "block_count": block,
        "warn_count": warn,
        "info_count": info,
        "by_category": {
            cat: {
                "label": category_label(cat),
                "count": len(items),
                "items": items,
            }
            for cat, items in by_category.items()
        },
    }


_BUILTINS_LOADED = False


def ensure_builtin_checks_registered() -> None:
    global _BUILTINS_LOADED
    if _BUILTINS_LOADED:
        return
    # 延迟导入，避免循环依赖
    from services import check_skills as _check_skills  # noqa: F401

    _check_skills.register_builtin_checks()
    _BUILTINS_LOADED = True


def reset_registry_for_tests() -> None:
    """仅测试用：清空并允许重新注册。"""
    global _BUILTINS_LOADED
    _REGISTRY.clear()
    _BUILTINS_LOADED = False
    try:
        from services import check_skills

        check_skills._REGISTERED = False
    except Exception:  # noqa: BLE001
        pass
