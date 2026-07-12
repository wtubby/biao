import asyncio

from services.pipeline_runner import GenerationPipeline, StageStatus


def test_pipeline_runs_stages_in_order():
    order: list[str] = []

    async def stage_a(ctx):
        order.append("a")
        return {"a": 1}

    async def stage_b(ctx):
        order.append("b")
        assert ctx.get("a") == 1
        return {}

    async def run():
        pipeline = GenerationPipeline("proj-1")
        pipeline.add_stage("validate", stage_a)
        pipeline.add_stage("generate", stage_b)
        return await pipeline.run()

    results = asyncio.run(run())

    assert order == ["a", "b"]
    assert len(results) == 2
    assert all(r.status == StageStatus.COMPLETED for r in results)


def test_pipeline_stops_on_failure():
    async def ok(ctx):
        return {}

    async def fail(ctx):
        raise RuntimeError("boom")

    async def run():
        pipeline = GenerationPipeline("proj-2")
        pipeline.add_stage("validate", ok)
        pipeline.add_stage("generate", fail)
        pipeline.add_stage("finalize", ok)
        return await pipeline.run()

    results = asyncio.run(run())

    assert len(results) == 2
    assert results[0].status == StageStatus.COMPLETED
    assert results[1].status == StageStatus.FAILED
    assert "boom" in (results[1].error or "")


def test_pipeline_emits_stage_callbacks():
    events: list[tuple[str, str]] = []

    async def on_stage(stage, status, progress, message, data):
        events.append((stage, status))

    async def work(ctx):
        return {"done": True}

    async def run():
        pipeline = GenerationPipeline("proj-3", on_stage=on_stage)
        pipeline.add_stage("validate", work)
        return await pipeline.run()

    asyncio.run(run())

    assert ("validate", "running") in events
    assert ("validate", "completed") in events
