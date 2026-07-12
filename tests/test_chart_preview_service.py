from services.chart_preview_service import render_chart_previews


def test_render_chart_previews_returns_gantt_with_caption_and_image():
    content = '[GANTT_DATA: [{"工序": "基础施工", "开始第几天": 1, "持续天数": 5}]]'
    charts = render_chart_previews(content, duration_days=30)
    assert len(charts) == 1
    assert charts[0]["chart_type"] == "GANTT_DATA"
    assert charts[0]["caption"] == "图1 施工进度横道图"
    assert charts[0]["image_base64"]
    assert charts[0]["start"] == 0


def test_render_chart_previews_skips_smart_data():
    content = '[SMART_DATA: [{"title": "A", "desc": "B"}]]'
    assert render_chart_previews(content) == []


def test_render_chart_previews_uses_cache_for_identical_chart():
    content = '[TIMELINE_DATA: [{"第几天": 1, "节点": "开工"}]]'
    first = render_chart_previews(content)
    second = render_chart_previews(content)
    assert first[0]["image_base64"] == second[0]["image_base64"]
