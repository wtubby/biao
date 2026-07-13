"""自适应 RAG 路由单元测试。"""

from types import SimpleNamespace

from services.retrieval_router import resolve_retrieval_route


def _req(score: float):
    return SimpleNamespace(score_value=score)


def test_descriptive_chapter_uses_light_bm25_only():
    route = resolve_retrieval_route(chapter_title="工程概况")
    assert route.mode == "light"
    assert route.top_k == 3
    assert route.use_vector is False


def test_complex_chapter_by_score_uses_deep():
    route = resolve_retrieval_route(
        chapter_title="GIS安装专项方案",
        requirements=[_req(6.0)],
        guidance={"target_words": 800},
    )
    assert route.mode == "deep"
    assert route.top_k == 8
    assert route.use_vector is True


def test_complex_chapter_by_long_target_words():
    route = resolve_retrieval_route(
        chapter_title="施工技术措施",
        requirements=[_req(1.0)],
        guidance={"target_words": 2000},
    )
    assert route.mode == "deep"


def test_standard_technical_chapter():
    route = resolve_retrieval_route(
        chapter_title="文明施工措施",
        requirements=[_req(2.0)],
        guidance={"target_words": 600},
    )
    assert route.mode == "standard"
    assert route.top_k == 5
    assert route.use_vector is True


def test_plan_followup_route():
    route = resolve_retrieval_route(
        chapter_title="施工方案",
        is_plan_followup=True,
    )
    assert route.mode == "plan_followup"
    assert route.top_k == 4


def test_route_to_dict():
    route = resolve_retrieval_route(chapter_title="项目目标")
    data = route.to_dict()
    assert data["mode"] == "light"
    assert "top_k" in data
