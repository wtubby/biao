import asyncio
import json
import logging
import time

from fastapi import HTTPException

from config import GENERATION_CONCURRENCY, GENERATION_PARALLEL_SECTIONS
from db.database import SessionLocal
from db.models import Project, TechOutline
from services.chapter_review_errors import dump_review_errors, parse_review_errors
from services.generation_config import get_generation_config
from services.pipeline_runner import GenerationPipeline, StageStatus
from services.project_status import ALLOW_GENERATE, require_status
from services.sse_manager import push_event, reset_queue
from services.writer_service import group_leaves_by_section, write_and_qa_chapter
from services.response_matrix_service import apply_matrix_coverage_to_leaves

logger = logging.getLogger(__name__)


def _mark_leaves_red(db, leaf_ids: list[str], message: str) -> list[str]:
    """将仍卡在 generating 的叶子标为 red，返回实际变更的 chapter_id 列表。"""
    if not leaf_ids:
        return []
    rows = (
        db.query(TechOutline)
        .filter(TechOutline.id.in_(leaf_ids), TechOutline.review_status == "generating")
        .all()
    )
    changed: list[str] = []
    for row in rows:
        row.review_status = "red"
        row.review_errors = dump_review_errors([message])
        changed.append(row.id)
    if rows:
        db.commit()
    return changed


async def _emit_group_failure(project_id: str, group: list[TechOutline], message: str) -> int:
    """组失败时仅对仍 generating 的叶子落库 red 并推送 error，返回 red 增量。"""
    db = SessionLocal()
    try:
        changed_ids = _mark_leaves_red(
            db,
            [leaf.id for leaf in group],
            message,
        )
    finally:
        db.close()
    for chapter_id in changed_ids:
        await push_event(
            project_id,
            {
                "type": "error",
                "chapter_id": chapter_id,
                "message": message,
                "review_status": "red",
            },
        )
    return len(changed_ids)


def _write_chapter_in_thread(
    project_id: str,
    chapter_id: str,
    section_leaf_ids: list[str],
    chat_messages: list[dict] | None,
    entry_summary: str | None = None,
    use_section_summary_pool: bool = False,
) -> tuple[str, str, list[str], list[dict] | None, str | None, str | None, str | None]:
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        chapter = (
            db.query(TechOutline)
            .filter(TechOutline.project_id == project_id, TechOutline.id == chapter_id)
            .first()
        )
        if not project or not chapter:
            raise ValueError("项目或章节不存在")

        section_leaves = (
            db.query(TechOutline)
            .filter(TechOutline.id.in_(section_leaf_ids))
            .order_by(TechOutline.sort_order)
            .all()
        )
        try:
            chapter, messages, retrieval_warning = write_and_qa_chapter(
                db,
                project,
                chapter,
                section_leaves=section_leaves,
                chat_messages=chat_messages,
                entry_summary=entry_summary,
                use_section_summary_pool=use_section_summary_pool,
            )
        except Exception as exc:
            # write_and_qa_chapter 已尽量落库 red；此处兜底再查一次
            db.refresh(chapter)
            if chapter.review_status == "generating":
                chapter.review_status = "red"
                chapter.review_errors = dump_review_errors([f"生成失败：{exc}"])
                db.commit()
            raise
        errors = parse_review_errors(chapter.review_errors)
        return (
            chapter.id,
            chapter.review_status,
            errors,
            messages,
            (chapter.generated_content or "")[:300],
            chapter.last_summary,
            retrieval_warning,
        )
    finally:
        db.close()


async def _process_section_group(
    project_id: str,
    section_leaves: list[TechOutline],
    semaphore: asyncio.Semaphore,
    entry_summary: str | None = None,
    use_section_summary_pool: bool = False,
) -> tuple[list[tuple[str, str, list[str], str | None, str | None, str | None, float]], bool]:
    section_ids = [leaf.id for leaf in section_leaves]
    chat_messages: list[dict] | None = None
    results: list[tuple[str, str, list[str], str | None, str | None, str | None, float]] = []

    for leaf in section_leaves:
        started_at = time.perf_counter()
        await push_event(
            project_id,
            {"type": "start", "chapter_id": leaf.id, "title": leaf.title},
        )
        async with semaphore:
            try:
                chapter_id, status, errors, chat_messages, preview, last_summary, retrieval_warning = await asyncio.to_thread(
                    _write_chapter_in_thread,
                    project_id,
                    leaf.id,
                    section_ids,
                    chat_messages,
                    entry_summary if leaf.id == section_leaves[0].id else None,
                    use_section_summary_pool,
                )
            except Exception as exc:
                logger.exception("单章生成失败 chapter=%s: %s", leaf.id, exc)
                db = SessionLocal()
                try:
                    _mark_leaves_red(db, [leaf.id], f"生成失败：{exc}")
                finally:
                    db.close()
                # 记入 results，由 _emit 推送 done(red)，避免与 error 事件重复计数
                results.append(
                    (leaf.id, "red", [f"生成失败：{exc}"], None, None, None, round(time.perf_counter() - started_at, 1))
                )
                chat_messages = None
                continue

            duration_seconds = round(time.perf_counter() - started_at, 1)
            results.append(
                (chapter_id, status, errors, preview, last_summary, retrieval_warning, duration_seconds)
            )

        db = SessionLocal()
        try:
            project = db.query(Project).filter(Project.id == project_id).first()
            if project and project.pause_requested:
                project.pause_requested = 0
                db.commit()
                await push_event(
                    project_id,
                    {"type": "paused", "chapter_id": chapter_id},
                )
                return results, True
        finally:
            db.close()
    return results, False


async def _emit_chapter_results(
    project_id: str,
    output: list[tuple[str, str, list[str], str | None, str | None, str | None, float]],
) -> tuple[int, int, int]:
    green = yellow = red = 0
    for chapter_id, status, errors, preview, _last_summary, retrieval_warning, duration_seconds in output:
        if status == "green":
            green += 1
        elif status == "yellow":
            yellow += 1
        else:
            red += 1
        event: dict = {
            "type": "done",
            "chapter_id": chapter_id,
            "review_status": status,
            "preview": preview,
            "errors": errors,
            "duration_seconds": duration_seconds,
        }
        if retrieval_warning:
            event["retrieval_warning"] = retrieval_warning
        await push_event(project_id, event)
    return green, yellow, red


async def _run_generation_groups(
    project_id: str,
    groups: list[list[TechOutline]],
    semaphore: asyncio.Semaphore,
) -> tuple[int, int, int, bool]:
    green = yellow = red = 0
    entry_summary: str | None = None
    paused = False

    if GENERATION_PARALLEL_SECTIONS and len(groups) > 1:
        async def run_one(group: list[TechOutline]) -> tuple[list[tuple[str, str, list[str], str | None, str | None, str | None, float]], bool]:
            return await _process_section_group(
                project_id,
                group,
                semaphore,
                use_section_summary_pool=True,
            )

        gathered = await asyncio.gather(*[run_one(g) for g in groups], return_exceptions=True)
        for group, output in zip(groups, gathered):
            if isinstance(output, Exception):
                logger.exception("章节组生成失败: %s", output)
                red += await _emit_group_failure(
                    project_id, group, f"章节组生成失败：{output}",
                )
                continue
            result_list, group_paused = output
            if group_paused:
                paused = True
            g, y, r = await _emit_chapter_results(project_id, result_list)
            green += g
            yellow += y
            red += r
            if paused:
                break
    else:
        for group in groups:
            try:
                output, group_paused = await _process_section_group(
                    project_id,
                    group,
                    semaphore,
                    entry_summary=entry_summary,
                    use_section_summary_pool=False,
                )
            except Exception as exc:
                logger.exception("章节组生成失败: %s", exc)
                red += await _emit_group_failure(
                    project_id, group, f"章节组生成失败：{exc}",
                )
                continue

            if group_paused:
                paused = True
            g, y, r = await _emit_chapter_results(project_id, output)
            green += g
            yellow += y
            red += r
            if output:
                entry_summary = output[-1][4]
            if paused:
                break

    return green, yellow, red, paused


def generate_single_chapter(db, project_id: str, chapter_id: str):
    """生成单个叶子章节（含同 section 上下文）。"""
    ch = (
        db.query(TechOutline)
        .filter(TechOutline.project_id == project_id, TechOutline.id == chapter_id)
        .first()
    )
    if not ch:
        raise HTTPException(404, "章节不存在")
    if ch.is_leaf != 1:
        raise HTTPException(400, "仅支持对叶子章节生成内容")

    project = db.query(Project).filter(Project.id == ch.project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    require_status(project, ALLOW_GENERATE, "生成章节内容")

    if project.status == "generating":
        raise HTTPException(409, "批量生成进行中，请稍后再试")

    locked = (
        db.query(TechOutline)
        .filter(TechOutline.project_id == ch.project_id, TechOutline.is_locked == 1)
        .first()
    )
    if not locked:
        raise HTTPException(400, "请先锁定大纲")

    gen_cfg = get_generation_config(project)
    if not gen_cfg.get("format_confirmed_at"):
        raise HTTPException(
            400,
            "请先确认投标文件格式：在「内容生成」页确认目录与格式后再生成",
        )

    all_nodes = (
        db.query(TechOutline)
        .filter(TechOutline.project_id == ch.project_id)
        .order_by(TechOutline.sort_order)
        .all()
    )
    leaves = [n for n in all_nodes if n.is_leaf == 1]
    groups = group_leaves_by_section(leaves, all_nodes)
    section_leaves = next((g for g in groups if any(l.id == chapter_id for l in g)), [ch])

    ch.retry_count = 0
    ch.review_status = "generating"
    db.commit()

    try:
        chapter, _, _ = write_and_qa_chapter(db, project, ch, section_leaves=section_leaves)
        return chapter
    except Exception as exc:
        db.refresh(ch)
        if ch.review_status == "generating":
            ch.review_status = "red"
            ch.review_errors = dump_review_errors([f"生成失败：{exc}"])
            db.commit()
            db.refresh(ch)
        raise


async def run_generation(project_id: str, resume: bool = False) -> None:
    reset_queue(project_id)

    async def on_stage(stage: str, status: str, progress: float, message: str, data: dict) -> None:
        await push_event(
            project_id,
            {
                "type": "stage",
                "stage": stage,
                "status": status,
                "progress": progress,
                "message": message,
                **data,
            },
        )

    pipeline = GenerationPipeline(project_id, on_stage=on_stage)

    async def stage_validate(ctx: dict) -> dict:
        db = SessionLocal()
        try:
            project = db.query(Project).filter(Project.id == project_id).first()
            if not project:
                raise ValueError("项目不存在")

            locked = (
                db.query(TechOutline)
                .filter(TechOutline.project_id == project_id, TechOutline.is_locked == 1)
                .first()
            )
            if not locked:
                raise ValueError("大纲未锁定")

            all_nodes = (
                db.query(TechOutline)
                .filter(TechOutline.project_id == project_id)
                .order_by(TechOutline.sort_order)
                .all()
            )
            leaves = [n for n in all_nodes if n.is_leaf == 1]
            if resume:
                leaves = [n for n in leaves if n.review_status != "green"]
            if not leaves:
                raise ValueError("无待生成章节")

            project.status = "generating"
            project.pause_requested = 0
            for leaf in leaves:
                if leaf.review_status != "green":
                    leaf.review_status = "generating"
            db.commit()

            ctx["leaves"] = leaves
            ctx["groups"] = group_leaves_by_section(leaves, all_nodes)
            ctx["resume"] = resume
        finally:
            db.close()
        return {}

    async def stage_generate(ctx: dict) -> dict:
        semaphore = asyncio.Semaphore(GENERATION_CONCURRENCY)
        green, yellow, red, paused = await _run_generation_groups(project_id, ctx["groups"], semaphore)
        ctx["green"] = green
        ctx["yellow"] = yellow
        ctx["red"] = red
        ctx["paused"] = paused
        return {}

    async def stage_finalize(ctx: dict) -> dict:
        db = SessionLocal()
        try:
            project = db.query(Project).filter(Project.id == project_id).first()
            if project:
                # 清理仍卡在 generating 的叶子（暂停保留 generating，便于 resume）
                if not ctx.get("paused"):
                    stuck = (
                        db.query(TechOutline)
                        .filter(
                            TechOutline.project_id == project_id,
                            TechOutline.is_leaf == 1,
                            TechOutline.review_status == "generating",
                        )
                        .all()
                    )
                    for leaf in stuck:
                        leaf.review_status = "red"
                        leaf.review_errors = dump_review_errors(["生成未完成或异常中断"])
                    # 批量收尾：评分覆盖缺口回写
                    leaves = (
                        db.query(TechOutline)
                        .filter(TechOutline.project_id == project_id, TechOutline.is_leaf == 1)
                        .all()
                    )
                    apply_matrix_coverage_to_leaves(db, project, leaves)
                    # 以 DB 实况重算，避免 stuck/矩阵降级导致计数漂移
                    ctx["yellow"] = sum(1 for n in leaves if n.review_status == "yellow")
                    ctx["green"] = sum(1 for n in leaves if n.review_status == "green")
                    ctx["red"] = sum(1 for n in leaves if n.review_status == "red")

                if ctx.get("paused"):
                    project.status = "outline_locked"
                else:
                    project.status = "done"
                db.commit()

                # 批量生成完成后自动跑合规（不依赖 docx）
                compliance_summary = None
                if project and not ctx.get("paused"):
                    try:
                        from services.compliance_service import check_compliance_now

                        report = check_compliance_now(db, project)
                        compliance_summary = {
                            "passed": report.get("passed"),
                            "failure_count": report.get("failure_count", 0),
                            "warning_count": report.get("warning_count", 0),
                        }
                        ctx["compliance"] = compliance_summary
                    except Exception as exc:
                        logger.warning("生成后自动合规检查失败 project=%s: %s", project_id, exc)
        finally:
            db.close()

        if ctx.get("paused"):
            return {}

        event = {
            "type": "complete",
            "total": len(ctx.get("leaves", [])),
            "green_count": ctx.get("green", 0),
            "yellow_count": ctx.get("yellow", 0),
            "red_count": ctx.get("red", 0),
        }
        if ctx.get("compliance"):
            event["compliance"] = ctx["compliance"]
        await push_event(project_id, event)
        return {}

    pipeline.add_stage("validate", stage_validate)
    pipeline.add_stage("generate", stage_generate)
    pipeline.add_stage("finalize", stage_finalize)

    results = await pipeline.run()
    failed = next((r for r in results if r.status == StageStatus.FAILED), None)
    if failed:
        db = SessionLocal()
        try:
            project = db.query(Project).filter(Project.id == project_id).first()
            if project and project.status == "generating":
                project.status = "outline_locked"
                project.pause_requested = 0
            # 流水线失败：清理 generating 叶子
            stuck = (
                db.query(TechOutline)
                .filter(
                    TechOutline.project_id == project_id,
                    TechOutline.is_leaf == 1,
                    TechOutline.review_status == "generating",
                )
                .all()
            )
            for leaf in stuck:
                leaf.review_status = "red"
                leaf.review_errors = dump_review_errors(
                    [failed.error or f"流水线阶段 {failed.stage_name} 失败"]
                )
            db.commit()
        finally:
            db.close()
        await push_event(
            project_id,
            {"type": "error", "message": failed.error or f"流水线阶段 {failed.stage_name} 失败"},
        )
