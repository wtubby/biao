from services.humanizer_service import detect_ai_cliches, humanize_content


def test_detect_ai_cliches_finds_common_phrases():
    text = "综上所述，本工程具有重要意义。值得注意的是，我们将采用专项施工方案。"
    hits = detect_ai_cliches(text)
    phrases = {hit["phrase"] for hit in hits}
    assert "综上所述" in phrases
    assert "值得注意的是" in phrases


def test_detect_ai_cliches_returns_positions():
    text = "综上所述，施工组织设计完整。"
    hits = detect_ai_cliches(text)
    assert hits
    assert hits[0]["start"] == 0
    assert hits[0]["end"] == len("综上所述")


def test_humanize_content_still_replaces_phrases():
    text = "本方案通过顶层设计形成闭环管理，助力工程质量提升。" * 5
    result = humanize_content(text)
    assert "顶层设计" not in result
    assert "助力" not in result


def test_humanize_strips_summary_cliches():
    text = (
        "本工程施工组织设计围绕现场条件展开。"
        "综上所述，我们将落实三级质检与旁站监督，确保关键工序受控。"
    ) * 3
    result = humanize_content(text)
    assert "综上所述" not in result
    assert "三级质检" in result
