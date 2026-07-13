"""章级/整本质检共享规则（借鉴 tender-writer-v4 compliance_check / check_chapter）。"""

from __future__ import annotations

import re

from services.writing_guidance import get_chapter_type, is_descriptive_chapter

TEMPLATE_RESIDUES = [
    "xxx 公司",
    "XXX公司",
    "XX公司",
    "xxx 项目",
    "XXX项目",
    "XX项目",
    "<甲方单位>",
    "<甲方名称>",
    "<乙方名称>",
    "<项目名称>",
    "<投标人名称>",
    "[甲方单位]",
    "[甲方名称]",
    "[乙方名称]",
    "[项目名称]",
    "[投标人名称]",
    "【甲方单位】",
    "【项目名称】",
    "【投标人名称】",
    "【公司名称】",
    "TODO",
    "todo",
    "【待补充】",
    "【待填写】",
    "【待人工确认】",
    "示例文本",
]

SUBSTANTIAL_KEYWORDS = [
    "完全响应",
    "完全满足",
    "实质性响应",
    "无偏离",
    "满足要求",
    "符合要求",
    "不低于",
]

NORMALIZE_PATTERN = re.compile(r"[\s\u3000，,。；;：:（）()\[\]【】\-—_/]")

_CHINESE_CANONICAL: dict[str, list[str]] = {
    "宋体": ["宋体", "SimSun", "宋体-简", "NSimSun", "STSong", "宋体-繁"],
    "黑体": ["黑体", "SimHei", "STHeiti"],
    "仿宋": ["仿宋", "FangSong", "仿宋_GB2312", "STFangsong"],
    "微软雅黑": ["微软雅黑", "Microsoft YaHei", "Microsoft YaHei UI"],
}
_FONT_ALLOWED = frozenset(
    list(_CHINESE_CANONICAL.keys()) + ["Times New Roman", "Arial", "Calibri", "Cambria"]
)
_FONT_BOILERPLATE = frozenset({"Symbol", "Courier", "ＭＳ 明朝", "ＭＳ ゴシック"})


def normalize_for_match(text: str) -> str:
    return NORMALIZE_PATTERN.sub("", text or "")


def split_keywords(field: str | None) -> list[str]:
    if not field:
        return []
    return [p.strip() for p in re.split(r"[,，;；、/]+", field) if p.strip()]


def split_mandatory_elements(field: str | None) -> list[str]:
    if not field:
        return []
    return [p.strip() for p in re.split(r"[,，;；、/|]+", field) if p.strip()]


# 响应类必备要素：允许动词同义替换与核心词覆盖
_COMPLIANCE_VERBS = (
    "完全响应",
    "实质性响应",
    "完全满足",
    "满足",
    "符合",
    "响应",
)
_DOC_NOUNS = (
    "竞争性谈判文件",
    "谈判文件",
    "招标文件",
    "采购文件",
    "询价文件",
    "招标要求",
)
_HEADING_PREFIXES = ("工程", "项目", "施工", "本工程", "本项目")
_HEADING_SUFFIXES = ("保障", "措施", "方案", "评价", "管理", "控制", "要求", "体系")


def _is_compliance_phrase(element: str) -> bool:
    n = normalize_for_match(element)
    if len(n) < 6:
        return False
    has_verb = any(normalize_for_match(v) in n for v in _COMPLIANCE_VERBS)
    has_anchor = "要求" in n or "规定" in n or "文件" in n
    return has_verb and has_anchor


def phrase_covered_in_text(text: str, phrase: str) -> bool:
    """必备要素/短语覆盖：归一化子串 + 响应类同义放宽。"""
    raw = (phrase or "").strip()
    if not raw:
        return True
    content = text or ""
    if raw in content:
        return True
    normalized_phrase = normalize_for_match(raw)
    normalized_content = normalize_for_match(content)
    if normalized_phrase and normalized_phrase in normalized_content:
        return True
    if not _is_compliance_phrase(raw):
        return False
    # 动词同义替换：满足↔符合↔响应↔完全响应…
    for v_from in _COMPLIANCE_VERBS:
        nf = normalize_for_match(v_from)
        if not nf or nf not in normalized_phrase:
            continue
        for v_to in _COMPLIANCE_VERBS:
            if v_to == v_from:
                continue
            variant = normalized_phrase.replace(nf, normalize_for_match(v_to), 1)
            if variant and variant in normalized_content:
                return True
    # 核心：响应动词 + 文件类名词（或要素去动词后的核心）同时出现
    noun = ""
    for doc in sorted(_DOC_NOUNS, key=len, reverse=True):
        nd = normalize_for_match(doc)
        if nd and nd in normalized_phrase:
            noun = nd
            break
    if not noun:
        core = normalized_phrase
        for v in sorted(_COMPLIANCE_VERBS, key=len, reverse=True):
            core = core.replace(normalize_for_match(v), "")
        core = core.replace("要求", "").replace("规定", "")
        if len(core) >= 4:
            noun = core
    if not noun:
        return False
    has_verb = any(normalize_for_match(v) in normalized_content for v in _COMPLIANCE_VERBS)
    has_verb = has_verb or any(k in content for k in SUBSTANTIAL_KEYWORDS)
    return has_verb and noun in normalized_content


def mandatory_element_covered(content: str, element: str) -> bool:
    return phrase_covered_in_text(content, element)


def keyword_core_variants(keyword: str) -> list[str]:
    """标题关键词变体：去常见前缀/后缀，便于「进度保障」命中「工程进度保障」。"""
    raw = (keyword or "").strip()
    if not raw:
        return []
    variants = [raw]
    stems = [raw]
    for prefix in _HEADING_PREFIXES:
        if raw.startswith(prefix) and len(raw) - len(prefix) >= 2:
            stems.append(raw[len(prefix) :])
    expanded = list(stems)
    for stem in stems:
        for suffix in _HEADING_SUFFIXES:
            if stem.endswith(suffix) and len(stem) - len(suffix) >= 2:
                expanded.append(stem[: -len(suffix)])
    variants.extend(expanded)
    unique: list[str] = []
    seen: set[str] = set()
    for item in variants:
        n = normalize_for_match(item)
        if len(n) < 2 or n in seen:
            continue
        seen.add(n)
        unique.append(item)
    return unique


def keyword_covered_in_headings(headings: list[str], keyword: str) -> bool:
    norms = [normalize_for_match(h) for h in headings if h]
    if not norms:
        return False
    for variant in keyword_core_variants(keyword):
        nv = normalize_for_match(variant)
        if len(nv) < 2:
            continue
        for h in norms:
            if nv in h:
                return True
            # 标题比关键词更长或略短时允许互相包含，避免短噪声误命中
            if len(h) >= 4 and h in nv:
                return True
    return False


def extract_coverage_candidates(requirement_title: str, keyword: str | None) -> list[str]:
    candidates: list[str] = []
    item = (requirement_title or "").strip()
    if item:
        candidates.append(item)
    candidates.extend(split_keywords(keyword))
    for token in re.split(r"[（）()\[\]【】、，,；;：:\s]+", item):
        token = token.strip()
        if 2 <= len(token) <= 10:
            candidates.append(token)
    unique: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = normalize_for_match(candidate)
        if len(normalized) < 2 or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(candidate)
    return unique


def match_coverage_candidates(content: str, candidates: list[str]) -> list[str]:
    """在正文中匹配评分关键词候选（精确 + 核心变体）。"""
    normalized_content = normalize_for_match(content)
    matched: list[str] = []
    for candidate in candidates:
        normalized = normalize_for_match(candidate)
        if normalized and normalized in normalized_content:
            matched.append(candidate)
            continue
        if any(
            normalize_for_match(v) in normalized_content
            for v in keyword_core_variants(candidate)
            if len(normalize_for_match(v)) >= 2
        ):
            matched.append(candidate)
    return matched


_DESCRIPTIVE_MEASURE_MARKERS = (
    "具体措施",
    "主要措施",
    "保证措施",
    "拟采取",
    "为实现上述目标",
    "为实现本工程",
    "针对上述特点",
    "针对本工程",
    "针对上述难点",
    "我方将",
    "我们将",
    "组织保障",
    "技术保障",
    "管理保障",
    "检验频次",
    "施工步骤",
    "施工工艺",
    "施工组织",
    "专项方案",
    "质量保证体系",
    "质量管理体系",
)


def check_descriptive_chapter_measures(content: str, chapter_title: str) -> list[str]:
    """概况/特点/目标类章节不应混入方案、措施或工艺细节。"""
    if not is_descriptive_chapter(chapter_title):
        return []
    hits = [m for m in _DESCRIPTIVE_MEASURE_MARKERS if m in content]
    if hits:
        label = "目标" if get_chapter_type(chapter_title) == "goal" else "概况/特点"
        return [f"{label}章节不应写措施/方案，检测到：{', '.join(hits[:5])}"]
    return []


def check_template_residues(text: str) -> list[str]:
    hits: list[str] = []
    for marker in TEMPLATE_RESIDUES:
        if marker in text:
            hits.append(f"模板残留：{marker}")
    for marker in ("XXX", "待定", "TBD", "○○○"):
        if marker in text:
            hits.append(f"未替换标记：{marker}")
    return hits


def check_blind_bid_residues(text: str, *, enabled: bool = False) -> list[str]:
    """暗标模式下检测公司名等身份信息（委托 blind_bid_service）。"""
    if not enabled:
        return []
    from services.blind_bid_service import check_blind_bid_violations

    return check_blind_bid_violations(text)


def check_mandatory_elements(content: str, mandatory_elements: str | None) -> list[str]:
    elements = split_mandatory_elements(mandatory_elements)
    if not elements:
        return []
    missing = [e for e in elements if not mandatory_element_covered(content, e)]
    if missing:
        return [f"必备要素未覆盖：{', '.join(missing)}"]
    return []


_HEADING_LINE_RE = re.compile(
    r"^(?:"
    r"第[一二三四五六七八九十百零\d]+[章节篇部]"
    r"|[（(]?[一二三四五六七八九十百零\d]+[）)、\.．、]"
    r"|\d+(?:\.\d+){1,3}[\s、.．]"
    r")"
)


def _line_as_heading(stripped: str) -> str | None:
    """若该行是标题则返回标题文本，否则 None（与 check_chapter_scope 同一标准）。"""
    if stripped.startswith("#"):
        return stripped.lstrip("#").strip() or None
    if (
        stripped
        and len(stripped) < 60
        and not stripped.endswith(("。", "；", ";", "！", "!"))
        and _HEADING_LINE_RE.match(stripped)
    ):
        return stripped
    return None


def _collect_headings(text: str) -> list[str]:
    headings: list[str] = []
    for line in text.splitlines():
        heading = _line_as_heading(line.strip())
        if heading:
            headings.append(heading)
    return headings


def _title_scope_match(heading: str, title: str) -> bool:
    h = normalize_for_match(heading)
    t = normalize_for_match(title)
    if not h or not t or len(t) < 3:
        return False
    return t in h or h in t


def check_chapter_scope(
    content: str,
    chapter_title: str,
    other_leaf_titles: list[str],
) -> list[str]:
    """检测正文是否出现其他叶子章节标题（超范围撰写）。"""
    if not other_leaf_titles:
        return []
    errors: list[str] = []
    for heading in _collect_headings(content):
        if _title_scope_match(heading, chapter_title):
            continue
        for other in other_leaf_titles:
            if _title_scope_match(heading, other):
                errors.append(
                    f"正文出现其他章节标题「{heading}」，超出本章「{chapter_title}」范围"
                )
                break
    return errors


def trim_out_of_scope_content(
    content: str,
    chapter_title: str,
    other_leaf_titles: list[str],
) -> str:
    """从首个其他章节标题处截断，防止一次生成多章内容。"""
    if not content or not other_leaf_titles:
        return content
    kept: list[str] = []
    for line in content.splitlines():
        heading = _line_as_heading(line.strip())
        if heading and not _title_scope_match(heading, chapter_title):
            for other in other_leaf_titles:
                if _title_scope_match(heading, other):
                    return "\n".join(kept).rstrip()
        kept.append(line)
    return content


def check_heading_keyword_coverage(
    content: str,
    chapter_title: str,
    keywords: list[str],
) -> list[str]:
    if not keywords:
        return []
    headings = _collect_headings(content)
    if chapter_title:
        headings.append(chapter_title)
    hit = [kw for kw in keywords if keyword_covered_in_headings(headings, kw)]
    if not hit:
        return [f"标题未覆盖关键词：{'/'.join(keywords)}"]
    return []


def check_stitch_cheat(text: str, keywords: list[str], *, window: int = 30, min_hits: int = 3) -> list[str]:
    """检测标题/正文中关键词堆叠作弊。"""
    if len(keywords) < min_hits:
        return []
    errors: list[str] = []
    blocks: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            blocks.append(stripped.lstrip("#").strip())
        elif len(stripped) <= 80:
            blocks.append(stripped)
    blocks.extend(re.split(r"[。；\n]", text))
    for block in blocks:
        b = block.strip()
        if len(b) < 8:
            continue
        matched: list[tuple[int, str]] = []
        for kw in keywords:
            idx = b.find(kw)
            if idx >= 0:
                matched.append((idx, kw))
        if len(matched) < min_hits:
            continue
        matched.sort()
        span_start = matched[0][0]
        span_end = matched[-1][0] + len(matched[-1][1])
        if span_end - span_start <= window:
            errors.append(f"疑似缝合句作弊（{len(matched)} 个关键词挤在 {span_end - span_start} 字内）：{b[:40]}…")
            break
    return errors


_SENTENCE_END_CHARS = ("。", "！", "？", "]]", "}]", "）", ")")
_TABLE_ROW_RE = re.compile(r"^\|.*\|$")


def check_truncation_risk(content: str) -> list[str]:
    """检测正文结尾是否疑似被截断（无标点收尾、占位符未闭合等）。"""
    text = (content or "").rstrip()
    if not text:
        return []
    if text.endswith(_SENTENCE_END_CHARS):
        return []
    # 以合法 Markdown 表格行收尾是正常结束，不算截断
    last_line = text.rsplit("\n", 1)[-1].strip()
    if _TABLE_ROW_RE.match(last_line):
        return []
    if text.endswith(("，", "、", "：", "；", "-", "—")):
        return ["正文结尾疑似被截断（以逗号/顿号等非结束标点收尾）"]
    if len(text) > 200:
        return ["正文结尾疑似被截断（未以句号等结束标点收尾）"]
    return []


def check_chart_renderability(content: str) -> list[str]:
    """检测正文中图表占位符是否可正常渲染（避免警示图进入正式稿）。"""
    import json

    from chart.chart_service import CHART_PATTERN, parse_chart_match
    from services.env_check import check_graphviz

    errors: list[str] = []
    for match in CHART_PATTERN.finditer(content or ""):
        chart_type, raw_json = parse_chart_match(match)
        try:
            json.loads(raw_json)
        except json.JSONDecodeError:
            errors.append(f"图表占位符 {chart_type} 的 JSON 格式无效")
            continue
        if chart_type in ("FLOW_DATA", "ORG_DATA") and not check_graphviz():
            errors.append(
                f"正文含 {chart_type} 流程/组织图，但 Graphviz 未安装；"
                "请安装 Graphviz 或删除该占位符后再导出"
            )
    return errors


def check_ai_spacing(text: str) -> list[str]:
    errors: list[str] = []
    if "\u3000" in text:
        errors.append("存在全角空格（应使用半角或删除）")
    # Markdown 表格行常含列宽对齐空格，排除后再查连续半角空格
    non_table = "\n".join(
        line
        for line in (text or "").splitlines()
        if not _TABLE_ROW_RE.match(line.strip())
    )
    if re.search(r"  +", non_table):
        errors.append("存在连续多个半角空格")
    return errors


_TABLE_SEP_RE = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$")
_OPENING_PREFIX_RE = re.compile(
    r"^([针对为按照根据结合通过采用将本工程本项目本章本节本文][^，,。；;：:\n]{0,6})[，,：:；;]"
)
_OPENING_PREFIX_LEN = 5


def _parse_table_cells(row: str) -> list[str]:
    from services.markdown_utils import parse_table_cells

    return parse_table_cells(row)


def _extract_body_paragraphs(content: str) -> list[str]:
    paragraphs: list[str] = []
    for block in re.split(r"\n\s*\n", content or ""):
        text = block.strip()
        if not text:
            continue
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            continue
        if all(line.startswith("#") for line in lines):
            continue
        body_lines = [line.lstrip("#").strip() for line in lines if not line.startswith("#")]
        if body_lines:
            paragraphs.append("\n".join(body_lines))
        else:
            paragraphs.append(lines[0].lstrip("#").strip())
    return paragraphs


def _paragraph_opening(text: str) -> str:
    stripped = text.strip()
    stripped = re.sub(r"^[-*+]\s+", "", stripped)
    stripped = re.sub(r"^\d+[.、]\s+", "", stripped)
    match = _OPENING_PREFIX_RE.match(stripped)
    if match:
        opening = normalize_for_match(match.group(1))
        if len(opening) >= 3:
            return opening
    opening = normalize_for_match(stripped[:_OPENING_PREFIX_LEN])
    return opening if len(opening) >= 3 else ""


def check_first_paragraph_repeats_title(content: str, chapter_title: str) -> list[str]:
    """首段不应直接重复章节标题。"""
    if not content or not chapter_title:
        return []
    paragraphs = _extract_body_paragraphs(content)
    if not paragraphs:
        return []
    first = normalize_for_match(paragraphs[0])
    title = normalize_for_match(chapter_title)
    if len(title) < 4:
        return []
    if first == title or (first.startswith(title) and len(first) <= len(title) + 8):
        return [f"首段不应重复章节标题「{chapter_title}」"]
    return []


def check_paragraph_opening_repetition(content: str, *, min_repeat: int = 3) -> list[str]:
    """检测连续多段以相同句式开头。"""
    paragraphs = _extract_body_paragraphs(content)
    if len(paragraphs) < min_repeat:
        return []
    openings = [_paragraph_opening(p) for p in paragraphs]
    streak = 1
    for idx in range(1, len(openings)):
        current = openings[idx]
        previous = openings[idx - 1]
        if current and current == previous:
            streak += 1
            if streak >= min_repeat:
                return [f"连续 {streak} 段以相同句式开头「{current}」，建议调整表达方式"]
        else:
            streak = 1
    return []


def check_markdown_table_integrity(content: str) -> list[str]:
    """检测 Markdown 表格列数不一致或空行断裂。"""
    lines = (content or "").splitlines()
    errors: list[str] = []
    idx = 0
    while idx < len(lines):
        line = lines[idx].strip()
        if not _TABLE_ROW_RE.match(line):
            idx += 1
            continue
        if idx + 1 >= len(lines) or not _TABLE_SEP_RE.match(lines[idx + 1].strip()):
            idx += 1
            continue

        header_cols = len(_parse_table_cells(line))
        if header_cols == 0:
            errors.append(f"表格表头无效（第 {idx + 1} 行）")
            idx += 1
            continue

        row_idx = idx + 2
        while row_idx < len(lines) and _TABLE_ROW_RE.match(lines[row_idx].strip()):
            row = lines[row_idx].strip()
            cells = _parse_table_cells(row)
            if not cells or all(not cell for cell in cells):
                errors.append(f"表格存在空行或无效行（第 {row_idx + 1} 行）")
            elif len(cells) != header_cols:
                errors.append(
                    f"表格列数不一致：表头 {header_cols} 列，第 {row_idx + 1} 行为 {len(cells)} 列"
                )
            row_idx += 1
        idx = row_idx
    return errors


def _check_trailing_incomplete_table(lines: list[str]) -> list[str]:
    """正文末尾表格仅有表头/分隔线、无数据行。"""
    if not lines:
        return []
    last = lines[-1].strip()
    if not _TABLE_ROW_RE.match(last):
        return []
    start = len(lines) - 1
    while start > 0 and _TABLE_ROW_RE.match(lines[start - 1].strip()):
        start -= 1
    if start > 0 and _TABLE_SEP_RE.match(lines[start - 1].strip()):
        start -= 1
    block = [lines[i].strip() for i in range(start, len(lines))]
    if len(block) == 1:
        return ["正文以不完整表格行结尾，须在本节点内输出完整表格（含表头与至少一行数据）"]
    if len(block) == 2 and _TABLE_ROW_RE.match(block[0]) and _TABLE_SEP_RE.match(block[1]):
        return ["表格仅有表头与分隔线，缺少数据行，须在本节点内完整输出"]
    return []


def check_atomic_markdown_closure(content: str) -> list[str]:
    """独立节点 Markdown 须自包含闭合，禁止留续写尾巴。"""
    text = (content or "").strip()
    if not text:
        return []
    errors: list[str] = []

    open_charts = len(re.findall(r"\[(GANTT|TIMELINE|FLOW|ORG|SMART)_DATA:", text, re.I))
    close_brackets = text.count("]]") + text.count("}]")
    if open_charts > close_brackets:
        errors.append("存在未闭合的图表占位符，须在本节点内完整输出后再结束")
    if re.search(r"\[(GANTT|TIMELINE|FLOW|ORG|SMART)_DATA:[^\]]*$", text, re.I | re.MULTILINE):
        errors.append("正文末尾存在未闭合的图表占位符")

    lines = text.splitlines()
    errors.extend(_check_trailing_incomplete_table(lines))
    return errors[:3]


# 常见标准号形态；年份可选。前缀与 domains.yaml standard_prefixes 对齐（含市政 CJJ 等）
_STANDARD_CODE_RE = re.compile(
    r"(?:"
    r"GB/?T?\s*[\d.]+(?:\s*[-—－]\s*\d{4})?"
    r"|DL/?T?\s*[\d.]+(?:\s*[-—－]\s*\d{4})?"
    r"|JGJ/?T?\s*[\d.]+(?:\s*[-—－]\s*\d{4})?"
    r"|NB/?T?\s*[\d.]+(?:\s*[-—－]\s*\d{4})?"
    r"|Q/?GDW\s*[\d.]+(?:\s*[-—－]\s*\d{4})?"
    r"|SL/?T?\s*[\d.]+(?:\s*[-—－]\s*\d{4})?"
    r"|CJJ/?T?\s*[\d.]+(?:\s*[-—－]\s*\d{4})?"
    r")",
    re.IGNORECASE,
)

# 写作指南与行业常用号：无检索素材时仍允许出现，避免误杀
_COMMON_STANDARD_CORES = frozenset({
    "GB50168", "GB50169", "GB50171", "GB50233", "GB50254", "GB50303",
    "GB50150", "GB50149", "GB50217", "GBT50026",
    "DLT5168", "DLT5210", "DLT596", "DLT572", "DLT574",
    "JGJ46", "QGDW",
})


def normalize_standard_core(code: str) -> str:
    """GB/T 50168-2006 → GB50168；去掉空格、斜杠与年份。"""
    s = re.sub(r"[\s/]", "", (code or "").upper())
    s = s.replace("—", "-").replace("－", "-")
    s = re.sub(r"-\d{4}$", "", s)
    return s


def _prefix_code_pattern(prefix: str) -> str:
    p = re.sub(r"[\s/]", "", (prefix or "").upper())
    if not p:
        return ""
    if p == "QGDW":
        return r"Q/?GDW\s*[\d.]+(?:\s*[-—－]\s*\d{4})?"
    return rf"{re.escape(p)}/?T?\s*[\d.]+(?:\s*[-—－]\s*\d{4})?"


def extract_standard_codes(text: str, extra_prefixes: list[str] | None = None) -> list[str]:
    if not text:
        return []
    found = list(_STANDARD_CODE_RE.findall(text))
    if extra_prefixes:
        for prefix in extra_prefixes:
            pat = _prefix_code_pattern(prefix)
            if pat:
                found.extend(re.findall(pat, text, re.IGNORECASE))
    unique: list[str] = []
    seen: set[str] = set()
    for raw in found:
        core = normalize_standard_core(raw)
        if len(core) < 5 or core in seen:
            continue
        seen.add(core)
        unique.append(re.sub(r"\s+", " ", raw.strip()))
    return unique


def check_fabricated_standards(
    content: str,
    allowed_sources: str | None,
    *,
    max_report: int = 5,
    domain: str | None = None,
) -> list[str]:
    """正文中的规范标准号须出现在检索/事实等来源，或属于常见白名单。

    domain 对齐 domains.yaml 的 standard_prefixes，补充扫描该领域前缀
    （避免市政 CJJ 等漏检）；编造判定仍以来源命中为准，不按前缀白名单放行。
    """
    from domains.registry import resolve_domain

    extra_prefixes = resolve_domain(domain).standard_prefixes if domain else None
    codes = extract_standard_codes(content, extra_prefixes=extra_prefixes)
    if not codes:
        return []
    allowed_compact = re.sub(r"[\s/]", "", (allowed_sources or "")).upper()
    allowed_compact = allowed_compact.replace("—", "-").replace("－", "-")
    fabricated: list[str] = []
    for code in codes:
        core = normalize_standard_core(code)
        if core in _COMMON_STANDARD_CORES:
            continue
        if core.startswith("QGDW") and "QGDW" in allowed_compact:
            continue
        if core and core in allowed_compact:
            continue
        # 允许来源写 GB/T 而正文写 GB（或反之）
        alt = core.replace("GBT", "GB", 1) if core.startswith("GBT") else "GBT" + core[2:]
        if alt in allowed_compact or alt in _COMMON_STANDARD_CORES:
            continue
        fabricated.append(code)
    if not fabricated:
        return []
    shown = fabricated[:max_report]
    extra = f" 等共 {len(fabricated)} 处" if len(fabricated) > max_report else ""
    return [
        f"疑似编造规范标准号（未出现在检索素材/全局事实中）：{', '.join(shown)}{extra}"
    ]


def check_plan_key_points_coverage(
    content: str,
    key_points: list[str] | None,
    *,
    min_ratio: float = 0.7,
) -> list[str]:
    """写作规划要点应在正文中有可识别覆盖（词面命中）。"""
    points = [str(p).strip() for p in (key_points or []) if str(p).strip()]
    if len(points) < 2 or not (content or "").strip():
        return []
    hit = 0
    for point in points:
        # 限制中文块长度，避免整句粘成一词导致误判未覆盖
        raw = re.findall(r"[\u4e00-\u9fff]{2,8}|[A-Za-z0-9]{2,}", point)
        tokens: list[str] = []
        for t in raw:
            tokens.append(t)
            if len(t) >= 6:
                # 再切 2~4 字片段提高召回
                for n in (4, 3, 2):
                    for i in range(0, len(t) - n + 1, n):
                        tokens.append(t[i:i + n])
        tokens = sorted(set(tokens), key=len, reverse=True)[:10]
        if not tokens:
            hit += 1
            continue
        if any(t in content for t in tokens):
            hit += 1
    ratio = hit / len(points)
    if ratio + 1e-9 < min_ratio:
        return [
            f"写作规划要点覆盖不足：仅命中 {hit}/{len(points)}，"
            f"请按规划补写未覆盖要点"
        ]
    return []


def check_scoring_coverage_in_content(
    content: str,
    requirements: list,
    *,
    require_substantial: bool = True,
) -> list[str]:
    """章级评分覆盖：必备要素 + 关键词；可选实质性响应表述。"""
    text = content or ""
    if not text.strip() or not requirements:
        return []
    errors: list[str] = []
    normalized_content = normalize_for_match(text)
    for req in requirements:
        title = getattr(req, "requirement_title", None) or "评分项"
        is_risk = int(getattr(req, "is_risk_item", 0) or 0) == 1
        missing = [
            e for e in split_mandatory_elements(getattr(req, "mandatory_elements", None))
            if not mandatory_element_covered(text, e)
        ]
        if missing:
            errors.append(f"评分覆盖不足「{title}」：缺少必备要素 {', '.join(missing)}")
            continue
        candidates = extract_coverage_candidates(
            title, getattr(req, "keyword", None)
        )
        matched = match_coverage_candidates(text, candidates)
        if candidates and not matched:
            prefix = "刚性风险项" if is_risk else "评分项"
            errors.append(f"{prefix}「{title}」关键词未在正文中体现")
            continue
        if require_substantial and is_risk and matched:
            # 刚性项：关键词附近应有实质性响应表述
            responded = False
            for cand in matched[:3]:
                pos = text.find(cand)
                if pos < 0:
                    continue
                window = text[max(0, pos - 80): pos + len(cand) + 120]
                if any(k in window for k in SUBSTANTIAL_KEYWORDS):
                    responded = True
                    break
            if not responded and any(k in text for k in SUBSTANTIAL_KEYWORDS):
                responded = True
            if not responded:
                errors.append(
                    f"刚性风险项「{title}」缺少实质性响应表述"
                    f"（如完全响应/满足要求/不低于等）"
                )
    return errors[:10]


_FACT_KV_RE = re.compile(
    r"(?:^|[\n；;。])\s*"
    r"([\u4e00-\u9fffA-Za-z0-9（）()]{2,20})"
    r"\s*[:：为是]\s*"
    r"([^\n；;。]{1,40})"
)
_COUNT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(台|套|基|回|km|公里|米|m|天|日|人)")
# 2~3 字行政名 + 省/市/县/区，避免「类似规模的上海市」这类带前缀垃圾片段
_PLACE_NAME_RE = re.compile(r"([\u4e00-\u9fff]{2,3}(?:省|市|县|区))")
# 明确断言本工程地点的句式；不含「参考XX市」类比
_LOCATION_CLAIM_RE = re.compile(
    r"(?:建设地点|施工地点|工程地点|工程位于|项目位于|本工程位于|本项目位于|"
    r"本工程(?:建设)?地址|项目地址|工程地址|坐落于)"
    r"(?:[：:\s]|为|是)+"
    r"([^。；;，,\n]{2,40})"
)


def extract_fact_kv_pairs(facts_text: str) -> list[tuple[str, str]]:
    """从全局事实文本粗提取「键:值」对。"""
    pairs: list[tuple[str, str]] = []
    for m in _FACT_KV_RE.finditer(facts_text or ""):
        key = m.group(1).strip()
        val = m.group(2).strip()
        if key and val and len(val) <= 40:
            pairs.append((key, val))
    return pairs[:30]


def _location_parts(location: str) -> list[str]:
    """拆出建设地点中的省/市/县/区片段，便于子串兼容。"""
    parts = _PLACE_NAME_RE.findall(location or "")
    loc = (location or "").strip()
    if loc and loc not in parts:
        parts.append(loc)
    return parts


def check_global_fact_consistency(
    content: str,
    *,
    facts_text: str | None = None,
    global_params: dict | None = None,
) -> list[str]:
    """正文与全局事实/工程参数的明显冲突检测。"""
    text = content or ""
    if not text.strip():
        return []
    errors: list[str] = []
    params = global_params or {}

    location = str(params.get("建设地点") or "").strip()
    if location and len(location) >= 2:
        loc_parts = _location_parts(location)
        for m in _LOCATION_CLAIM_RE.finditer(text):
            claim = m.group(1).strip()
            # 声明里已覆盖全局建设地点（含「成都市」对「四川省成都市」）则放过
            if any(p and p in claim for p in loc_parts):
                continue
            places = _PLACE_NAME_RE.findall(claim)
            foreign = [
                p for p in places
                if not any(p in lp or lp in p for lp in loc_parts if lp)
            ]
            if foreign:
                errors.append(
                    f"建设地点疑似不一致：全局为「{location}」，正文出现「{foreign[0]}」"
                )
                break

    voltage = str(params.get("电压等级") or "").strip()
    if voltage:
        mentioned = re.findall(r"(\d+(?:\.\d+)?)\s*[kK][vV]", text)
        # 提取全局电压数字
        gv = re.search(r"(\d+(?:\.\d+)?)", voltage)
        if gv and mentioned:
            expected = gv.group(1)
            for m in mentioned:
                if m != expected and abs(float(m) - float(expected)) > 0.01:
                    # 允许出现更低电压等级（如站用变），仅当出现更高且差一档以上时告警
                    if float(m) > float(expected) * 1.5:
                        errors.append(
                            f"电压等级疑似冲突：全局 {voltage}，正文出现 {m}kV"
                        )
                        break

    for key, val in extract_fact_kv_pairs(facts_text or ""):
        count_m = _COUNT_RE.search(val)
        if not count_m or key not in text:
            continue
        num, unit = count_m.group(1), count_m.group(2)
        # 同键附近出现不同数量
        for m in re.finditer(re.escape(key), text):
            window = text[m.start(): m.start() + 80]
            for cm in _COUNT_RE.finditer(window):
                if cm.group(2) == unit and cm.group(1) != num:
                    errors.append(
                        f"全局事实冲突「{key}」：应为 {num}{unit}，正文出现 {cm.group(0)}"
                    )
                    break
            else:
                continue
            break

    return errors[:6]


def check_cross_chapter_overlap(
    content: str,
    prior_texts: list[str] | None,
    *,
    max_overlap_ratio: float = 0.18,
    min_prior_len: int = 80,
) -> list[str]:
    """检测本章与前序章节正文的长句/短语重叠。"""
    text = (content or "").strip()
    priors = [p.strip() for p in (prior_texts or []) if p and len(p.strip()) >= min_prior_len]
    if len(text) < 120 or not priors:
        return []

    prior_joined = "\n".join(priors)
    # 滑动窗口指纹：连续 10 字，步长 5
    windows: list[str] = []
    pure = re.sub(r"[^\u4e00-\u9fff]", "", text)
    if len(pure) < 40:
        return []
    for i in range(0, len(pure) - 9, 5):
        windows.append(pure[i:i + 10])
    if len(windows) < 8:
        return []
    sample = windows[:: max(1, len(windows) // 50)][:50]
    prior_pure = re.sub(r"[^\u4e00-\u9fff]", "", prior_joined)
    hits = sum(1 for w in sample if w in prior_pure)
    ratio = hits / len(sample)
    if ratio >= max_overlap_ratio:
        return [
            f"与前序章节内容重复偏高（约 {int(ratio * 100)}%），"
            "请删去已写工艺/措施的复述，仅保留本章增量要点"
        ]
    return []


_STITCH_BAD_OPENERS = (
    "综上所述",
    "接上文",
    "如上所述",
    "继续上文",
    "下面继续",
)

_STITCH_NGRAM_N = 8
_STITCH_OVERLAP_RATIO = 0.18


def _chinese_ngrams(text: str, n: int = _STITCH_NGRAM_N) -> set[str]:
    """滑动窗口中文 n-gram；相位无关，能检出偏移后的整句重复。"""
    chars = "".join(re.findall(r"[\u4e00-\u9fff]", text or ""))
    if len(chars) < n:
        return set()
    return {chars[i : i + n] for i in range(len(chars) - n + 1)}


def check_segment_stitch_quality(parts: list[str]) -> list[dict]:
    """长章分段拼接质量：段首套话、相邻段重叠。

    返回 [{"index": int, "message": str}, ...]，index 为需重写段的 0-based 下标
    （接缝问题一律修后一段：去掉段首套话/对上段的复述）。
    """
    indexed = [(i, (p or "").strip()) for i, p in enumerate(parts) if (p or "").strip()]
    if len(indexed) < 2:
        return []
    errors: list[dict] = []
    for j in range(1, len(indexed)):
        prev_i, prev = indexed[j - 1]
        curr_i, part = indexed[j]
        seg_no = curr_i + 1
        head = part[:80]
        for opener in _STITCH_BAD_OPENERS:
            if head.startswith(opener) or opener in head[:40]:
                errors.append({
                    "index": curr_i,
                    "message": f"第 {seg_no} 段段首出现过渡套话「{opener}」，请直接写技术内容",
                })
                break
        prev_tail = prev[-220:]
        curr_head = part[:220]
        prev_grams = _chinese_ngrams(prev_tail)
        curr_grams = _chinese_ngrams(curr_head)
        if prev_grams and curr_grams:
            overlap = len(prev_grams & curr_grams) / max(len(curr_grams), 1)
            if overlap >= _STITCH_OVERLAP_RATIO:
                errors.append({
                    "index": curr_i,
                    "message": (
                        f"第 {prev_i + 1}/{seg_no} 段接缝重复偏高，"
                        "请去掉段首对上段内容的复述"
                    ),
                })
    return errors[:5]


def validate_content_plan(
    plan: dict | None,
    bundle: dict | None = None,
) -> list[str]:
    """写作规划结构校验；返回问题列表（空表示可用）。"""
    if not isinstance(plan, dict) or not plan:
        return ["写作规划为空"]
    issues: list[str] = []
    key_points = [str(p).strip() for p in (plan.get("key_points") or []) if str(p).strip()]
    if len(key_points) < 2:
        issues.append("写作规划 key_points 少于 2 条")
    chapter_title = (bundle or {}).get("chapter_title") or ""
    if not is_descriptive_chapter(chapter_title):
        methods = [m for m in (plan.get("technical_methods") or []) if str(m).strip()]
        if not methods:
            issues.append("施工/方案类章节规划缺少 technical_methods")
    if (bundle or {}).get("last_summary"):
        avoid = [a for a in (plan.get("avoid") or []) if str(a).strip()]
        if not avoid:
            issues.append("存在上一章摘要但规划 avoid 为空，易导致跨章重复")
    target = (bundle or {}).get("guidance", {}).get("target_words") if bundle else None
    plan_words = plan.get("word_count_target")
    if target and plan_words:
        try:
            tw, pw = int(target), int(plan_words)
            if tw > 0 and abs(pw - tw) / tw > 0.35:
                issues.append(f"规划字数 {pw} 与目标 {tw} 偏差过大")
        except (TypeError, ValueError):
            pass
    requirements = (bundle or {}).get("requirements") or []
    if key_points and requirements:
        points_blob = " ".join(key_points)
        missing_mandatory: list[str] = []
        for req in requirements:
            for elem in split_mandatory_elements(getattr(req, "mandatory_elements", None)):
                if not mandatory_element_covered(points_blob, elem):
                    missing_mandatory.append(elem)
        if missing_mandatory:
            shown = "、".join(dict.fromkeys(missing_mandatory[:5]))
            issues.append(f"规划 key_points 未体现必备要素：{shown}")
    return issues


def fallback_content_plan(bundle: dict) -> dict:
    """规划失败时的规则兜底，保证长章仍可分段。"""
    guidance = bundle.get("guidance") or {}
    title = bundle.get("chapter_title") or "本章"
    brief = (guidance.get("brief") or "").strip()
    boundary = (guidance.get("content_boundary") or "").strip()
    req_text = bundle.get("requirements_text") or ""
    points: list[str] = []
    if brief:
        points.append(brief[:80])
    for line in req_text.splitlines():
        line = line.strip().lstrip("【").rstrip("】")
        if 4 <= len(line) <= 40 and not line.startswith("http"):
            points.append(line)
        if len(points) >= 6:
            break
    if len(points) < 2:
        points = [f"{title}总体要求", f"{title}关键措施与控制要点", f"{title}验收与保障"]
    avoid = []
    if bundle.get("last_summary"):
        avoid.append("勿重复上一章已写工艺与参数")
    prior = bundle.get("prior_summaries") or []
    if prior:
        avoid.append("勿展开前序章节已覆盖的同类措施")
    return {
        "key_points": points[:8],
        "technical_methods": [] if is_descriptive_chapter(title) else [f"{title}主要工艺"],
        "data_to_include": [],
        "charts_needed": [],
        "word_count_target": int(guidance.get("target_words") or 1000),
        "avoid": avoid,
        "retrieval_focus": points[:4],
        "_fallback": True,
    }


def check_ai_cliche_residues(content: str, *, max_report: int = 5) -> list[str]:
    """硬质检：残留空泛套话（去痕后仍存在的需改写项）。"""
    from services.humanizer_service import detect_ai_cliches

    hits = detect_ai_cliches(content or "")
    if not hits:
        return []
    phrases = list(dict.fromkeys(h["phrase"] for h in hits))[:max_report]
    return [f"存在空泛套话，请改为具体技术表述：{', '.join(phrases)}"]


def normalize_ai_spacing(text: str) -> str:
    result = text.replace("\u3000", " ")
    result = re.sub(r" {2,}", " ", result)
    result = re.sub(r"([\u4e00-\u9fff]) ([a-zA-Z0-9])", r"\1\2", result)
    result = re.sub(r"([a-zA-Z0-9]) ([\u4e00-\u9fff])", r"\1\2", result)
    return result


def _normalize_font_alias(font_name: str) -> str:
    for canonical, aliases in _CHINESE_CANONICAL.items():
        if font_name in aliases:
            return canonical
    return font_name


def check_font_safety(docx_path) -> list[str]:
    """段落级 + fontTable 级字体白名单检查（warn 级）。"""
    import zipfile
    import xml.etree.ElementTree as ET
    from pathlib import Path

    path = Path(docx_path)
    issues: list[str] = []
    try:
        with zipfile.ZipFile(path) as zf:
            if "word/document.xml" not in zf.namelist():
                return issues
            document_xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
            rfonts = re.findall(r"<w:rFonts\s[^/]*/?>", document_xml)
            bad: dict[str, int] = {}
            for tag in rfonts:
                ea = re.search(r'w:eastAsia="([^"]+)"', tag)
                if ea:
                    font = ea.group(1)
                    norm = _normalize_font_alias(font)
                    if norm not in _FONT_ALLOWED and font not in _FONT_BOILERPLATE:
                        bad[font] = bad.get(font, 0) + 1
            for font, cnt in bad.items():
                issues.append(f"非白名单 eastAsia 字体 {font!r} × {cnt} 处")

            if "word/fontTable.xml" in zf.namelist():
                ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
                root = ET.fromstring(zf.read("word/fontTable.xml"))
                suspicious = []
                for font_el in root.findall(f"{ns}font"):
                    name = font_el.get(f"{ns}name")
                    if not name:
                        continue
                    norm = _normalize_font_alias(name)
                    if norm in _FONT_ALLOWED or name in _FONT_BOILERPLATE:
                        continue
                    suspicious.append(name)
                if suspicious:
                    issues.append(f"fontTable 声明非白名单字体：{sorted(set(suspicious))[:8]}")
    except Exception as exc:
        issues.append(f"字体检查跳过：{exc}")
    return issues
