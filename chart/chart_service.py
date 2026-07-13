import json
import logging
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from services.env_check import check_chinese_font, check_graphviz

logger = logging.getLogger(__name__)

_font = check_chinese_font()
if _font:
    plt.rcParams["font.family"] = _font

CHART_CAPTIONS: dict[str, tuple[str, str]] = {
    "GANTT_DATA": ("图", "施工进度横道图"),
    "TIMELINE_DATA": ("图", "里程碑时间轴"),
    "FLOW_DATA": ("图", "工艺流程图"),
    "ORG_DATA": ("图", "组织架构图"),
    "SMART_DATA": ("表", "要点对照表"),
}

_GANTT_MAX_HEIGHT = 12.0
_CHART_TYPES = "ORG_DATA|GANTT_DATA|TIMELINE_DATA|FLOW_DATA|SMART_DATA"
_CHART_HEADER_RE = re.compile(
    rf"\[({_CHART_TYPES}):",
    re.IGNORECASE,
)
# 兼容模型常写的块格式：[GANTT_DATA]\n{{...}}\n[/GANTT_DATA]
_CHART_BLOCK_HEADER_RE = re.compile(
    rf"\[({_CHART_TYPES})\]",
    re.IGNORECASE,
)
_CHART_CLOSE_RE = re.compile(
    rf"\[/({_CHART_TYPES})\]",
    re.IGNORECASE,
)
_DAY_LABEL_RE = re.compile(r"第\s*(\d+)\s*天")
_FENCE_OPEN_LINE_RE = re.compile(r"^```[\w-]*[ \t]*$")
_FENCE_CLOSE_LINE_RE = re.compile(r"^[ \t]*```[ \t]*$")


def _expand_markdown_fence(content: str, start: int, end: int) -> tuple[int, int]:
    """若图表被包在 ``` / ```json 代码块中，把匹配范围扩到整个 fence。"""
    # 回看上一非空行是否为开 fence
    i = start
    while i > 0 and content[i - 1] in " \t":
        i -= 1
    if i <= 0 or content[i - 1] not in "\r\n":
        return start, end
    line_end = i - 1
    if line_end > 0 and content[line_end] == "\n" and content[line_end - 1] == "\r":
        line_end -= 1
    line_start = content.rfind("\n", 0, line_end) + 1
    prev_line = content[line_start:line_end].strip()
    if not _FENCE_OPEN_LINE_RE.match(prev_line):
        return start, end

    new_start = line_start
    j = end
    length = len(content)
    while j < length and content[j] in " \t":
        j += 1
    if j < length and content[j] == "\r":
        j += 1
    if j < length and content[j] == "\n":
        j += 1
    # 下一行应为闭 fence
    close_start = j
    close_end = content.find("\n", close_start)
    line = content[close_start:] if close_end < 0 else content[close_start:close_end]
    if line.endswith("\r"):
        line = line[:-1]
    if not _FENCE_CLOSE_LINE_RE.match(line):
        return new_start, end
    new_end = length if close_end < 0 else close_end + 1
    return new_start, new_end


def _close_fig(fig) -> None:
    plt.close(fig)


def _temp_png_path(prefix: str = "tbe") -> Path:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png", prefix=f"{prefix}_")
    tmp.close()
    return Path(tmp.name)


def next_caption(counters: dict, chart_type: str) -> str:
    """按图表类型生成「图n / 表n」编号文案，counters 在全文/全章内共享。"""
    kind, label = CHART_CAPTIONS.get(chart_type, ("图", chart_type))
    counter_key = "table" if kind == "表" else "figure"
    counters[counter_key] = counters.get(counter_key, 0) + 1
    return f"{kind}{counters[counter_key]} {label}"


def render_warning_image(chart_type: str) -> Path:
    fig, ax = plt.subplots(figsize=(8, 1.2))
    try:
        ax.axis("off")
        ax.text(
            0.5, 0.5,
            f"【注意】此处为【{chart_type}】图表，解析异常，请人工补充",
            ha="center", va="center", fontsize=11, color="#666",
            bbox=dict(boxstyle="round", facecolor="#f0f0f0", edgecolor="#ccc"),
        )
        path = _temp_png_path("tbe_warn")
        fig.savefig(path, dpi=120, bbox_inches="tight")
        return path
    finally:
        _close_fig(fig)


def render_timeline(data: list[dict]) -> Path:
    fig, ax = plt.subplots(figsize=(10, 2.5))
    try:
        days = [d.get("第几天", i + 1) for i, d in enumerate(data)]
        labels = [d.get("节点", "") for d in data]
        ax.plot(days, [1] * len(days), "o-", color="#1890ff", markersize=8)
        for x, label in zip(days, labels):
            ax.annotate(label, (x, 1), textcoords="offset points", xytext=(0, 10), ha="center", fontsize=9)
        ax.set_yticks([])
        ax.set_xlabel("天数")
        ax.set_title("里程碑时间轴")
        path = _temp_png_path("tbe_timeline")
        fig.savefig(path, dpi=120, bbox_inches="tight")
        return path
    finally:
        _close_fig(fig)


def _parse_date(value) -> datetime | None:
    if value is None:
        return None
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(s[:10], fmt)
        except ValueError:
            continue
    return None


def _extract_day_label(value) -> int | None:
    if value is None or isinstance(value, (int, float)):
        return None
    m = _DAY_LABEL_RE.search(str(value))
    return int(m.group(1)) if m else None


def _gantt_span(
    start, end, duration, base_date: datetime | None
) -> tuple[int, int]:
    """把多种 start/end/duration 写法统一为 (开始第几天, 持续天数)。"""
    start_day = _extract_day_label(start)
    end_day = _extract_day_label(end)
    if start_day is not None:
        if end_day is not None:
            return max(start_day, 1), max(end_day - start_day, 1)
        if duration is not None:
            return max(start_day, 1), max(int(duration), 1)
        return max(start_day, 1), 1

    start_date = _parse_date(start)
    end_date = _parse_date(end)
    if start_date is not None:
        origin = base_date or start_date
        s = (start_date - origin).days + 1
        if end_date is not None:
            d = max((end_date - start_date).days, 1)
        elif duration is not None:
            d = max(int(duration), 1)
        else:
            d = 1
        if duration is not None and end_date is not None:
            d = max(int(duration), 1)
        return max(s, 1), d

    if isinstance(start, (int, float)):
        # 模型常用 0-based 天偏移
        s = int(start) + 1
        if isinstance(end, (int, float)):
            return max(s, 1), max(int(end) - int(start), 1)
        if duration is not None:
            return max(s, 1), max(int(duration), 1)
        return max(s, 1), 1

    if duration is not None:
        return 1, max(int(duration), 1)
    return 1, 1


def normalize_gantt_data(data) -> list[dict]:
    """统一为 [{工序, 开始第几天, 持续天数}, ...]，兼容 LLM 常见英文/块结构。"""
    base_date: datetime | None = None
    if isinstance(data, dict):
        base_date = _parse_date(data.get("startDate") or data.get("start_date"))
        items = data.get("tasks") or data.get("items") or data.get("data") or []
        if not isinstance(items, list):
            items = []
        if not items and ("工序" in data or "开始第几天" in data):
            items = [data]
    elif isinstance(data, list):
        items = data
    else:
        return []

    if base_date is None:
        for t in items:
            if isinstance(t, dict):
                d = _parse_date(t.get("start") or t.get("开始日期"))
                if d is not None:
                    base_date = d
                    break

    out: list[dict] = []
    for i, t in enumerate(items):
        if not isinstance(t, dict):
            continue
        if "工序" in t or "开始第几天" in t or "持续天数" in t:
            name = str(t.get("工序") or f"工序{i + 1}")
            start_day = int(t.get("开始第几天") or 1)
            dur = max(int(t.get("持续天数") or 1), 1)
            out.append({"工序": name, "开始第几天": start_day, "持续天数": dur})
            continue
        name = str(t.get("name") or t.get("title") or f"工序{i + 1}")
        start_day, dur = _gantt_span(
            t.get("start"),
            t.get("end"),
            t.get("duration") or t.get("持续天数"),
            base_date,
        )
        out.append({"工序": name, "开始第几天": start_day, "持续天数": dur})
    return out


def merge_gantt_payloads(payloads: list) -> list[dict]:
    """合并多章甘特数据为一份整体工序列表（按工序名去重，保留先出现的）。"""
    merged: list[dict] = []
    seen: set[str] = set()
    for payload in payloads:
        for row in normalize_gantt_data(payload):
            name = str(row.get("工序") or "")
            if not name or name in seen:
                continue
            seen.add(name)
            merged.append(row)
    return merged


def collect_gantt_payloads_from_text(content: str) -> list:
    """从正文中提取全部 GANTT JSON 载荷。"""
    payloads: list = []
    for match in iter_chart_matches(content or ""):
        if match.chart_type != "GANTT_DATA":
            continue
        try:
            payloads.append(json.loads(match.raw_json))
        except json.JSONDecodeError:
            continue
    return payloads


def render_gantt(data: list[dict] | dict | None, duration: int | None = None) -> Path:
    """把工序列表渲染成横道图（甘特图）。data 每项含「工序」「开始第几天」「持续天数」。"""
    data = normalize_gantt_data(data)
    if not data:
        return render_warning_image("GANTT_DATA")

    tasks = [str(d.get("工序") or f"工序{i + 1}") for i, d in enumerate(data)]
    starts = [int(d.get("开始第几天") or 1) for d in data]
    durations = [max(int(d.get("持续天数") or 1), 1) for d in data]
    ends = [s + d for s, d in zip(starts, durations)]
    max_day = max(duration or 0, max(ends, default=1))

    n = len(tasks)
    fig_height = min(max(2.0, 0.45 * n + 1), _GANTT_MAX_HEIGHT)
    fig, ax = plt.subplots(figsize=(10, fig_height))
    try:
        y_positions = list(range(n))
        ax.barh(y_positions, durations, left=starts, height=0.5, color="#1890ff", edgecolor="#0b5fb0")
        min_label_width = max(max_day * 0.06, 2)
        for y, s, dur in zip(y_positions, starts, durations):
            label = f"{dur}天"
            if dur >= min_label_width:
                ax.text(s + dur / 2, y, label, ha="center", va="center", fontsize=8, color="white")
            else:
                ax.text(s + dur + 0.3, y, label, ha="left", va="center", fontsize=8, color="#333")
        ax.set_yticks(y_positions)
        ax.set_yticklabels(tasks, fontsize=9)
        ax.invert_yaxis()
        ax.set_xlim(0, max_day + 2)
        ax.set_xlabel("天数")
        ax.set_title("施工进度横道图")
        ax.grid(axis="x", linestyle="--", alpha=0.4)
        path = _temp_png_path("tbe_gantt")
        fig.savefig(path, dpi=120, bbox_inches="tight")
        return path
    finally:
        _close_fig(fig)


def render_flow(data: list[str]) -> Path | None:
    if not check_graphviz():
        return None
    try:
        import graphviz

        dot = graphviz.Digraph(format="png")
        dot.attr(rankdir="LR")
        prev = None
        for i, step in enumerate(data):
            node_id = f"n{i}"
            dot.node(node_id, step)
            if prev:
                dot.edge(prev, node_id)
            prev = node_id
        path = _temp_png_path("tbe_flow")
        rendered = dot.render(filename=str(path.with_suffix("")), cleanup=True)
        return Path(f"{rendered}.png") if not str(rendered).endswith(".png") else Path(rendered)
    except Exception as exc:
        logger.warning("流程图渲染失败: %s", exc)
        return None


def render_org(data: dict) -> Path | None:
    if not check_graphviz():
        return None
    try:
        import graphviz

        dot = graphviz.Digraph(format="png")
        dot.attr(rankdir="TB")

        def walk(node, parent=None):
            nid = str(id(node))
            dot.node(nid, node.get("name", ""))
            if parent:
                dot.edge(parent, nid)
            for child in node.get("children") or []:
                walk(child, nid)

        walk(data)
        path = _temp_png_path("tbe_org")
        rendered = dot.render(filename=str(path.with_suffix("")), cleanup=True)
        return Path(f"{rendered}.png") if not str(rendered).endswith(".png") else Path(rendered)
    except Exception as exc:
        logger.warning("组织架构图渲染失败: %s", exc)
        return None


@dataclass
class ChartMatch:
    start_pos: int
    end_pos: int
    chart_type: str
    raw_json: str

    def start(self) -> int:
        return self.start_pos

    def end(self) -> int:
        return self.end_pos

    def group(self, n: int):
        if n == 1 and self.chart_type == "ORG_DATA":
            return self.raw_json
        if n == 2 and self.chart_type != "ORG_DATA":
            return self.chart_type
        if n == 3 and self.chart_type != "ORG_DATA":
            return self.raw_json
        return None


def _extract_balanced(text: str, start: int, open_ch: str, close_ch: str) -> tuple[str, int] | None:
    depth = 0
    in_string = False
    escape = False
    string_quote = ""
    i = start
    while i < len(text):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == string_quote:
                in_string = False
            i += 1
            continue
        if ch in ('"', "'"):
            in_string = True
            string_quote = ch
            i += 1
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start : i + 1], i + 1
        i += 1
    return None


def _json_brackets_for(chart_type: str, ch: str) -> tuple[str, str] | None:
    """根据图表类型与首字符决定 JSON 括号对。GANTT 等允许数组或对象。"""
    if chart_type == "ORG_DATA":
        return ("{", "}") if ch == "{" else None
    if chart_type == "FLOW_DATA":
        return ("[", "]") if ch == "[" else None
    if ch == "[":
        return ("[", "]")
    if ch == "{":
        return ("{", "}")
    return None


def iter_chart_matches(content: str):
    """扫描正文中的图表占位符，用括号计数提取 JSON，避免嵌套 ] 被正则截断。

    支持两种写法：
    - 标准：`[GANTT_DATA: [...]]`
    - 块格式：`[GANTT_DATA]\\n{...}\\n[/GANTT_DATA]`（模型常用）
    """
    i = 0
    length = len(content)
    while i < length:
        if content[i] != "[":
            i += 1
            continue

        header = _CHART_HEADER_RE.match(content, i)
        require_outer_close = True
        if header:
            chart_type = header.group(1).upper()
            j = header.end()
        else:
            header = _CHART_BLOCK_HEADER_RE.match(content, i)
            if not header:
                i += 1
                continue
            # 避免把 [/GANTT_DATA] 收尾标签当成开标签
            if content[i + 1 : i + 2] == "/":
                i += 1
                continue
            chart_type = header.group(1).upper()
            j = header.end()
            require_outer_close = False

        while j < length and content[j].isspace():
            j += 1
        if j >= length:
            break

        brackets = _json_brackets_for(chart_type, content[j])
        if not brackets:
            i += 1
            continue
        open_ch, close_ch = brackets
        extracted = _extract_balanced(content, j, open_ch, close_ch)
        if not extracted:
            i += 1
            continue
        raw_json, json_end = extracted

        if require_outer_close:
            if json_end >= length or content[json_end] != "]":
                i += 1
                continue
            end = json_end + 1
        else:
            end = json_end
            k = end
            while k < length and content[k].isspace():
                k += 1
            close_m = _CHART_CLOSE_RE.match(content, k)
            if close_m and close_m.group(1).upper() == chart_type:
                end = close_m.end()

        start, end = _expand_markdown_fence(content, i, end)
        yield ChartMatch(start, end, chart_type, raw_json)
        i = end


# 兼容旧代码与测试：保留 CHART_PATTERN 名称，实际走括号计数扫描
class _ChartPattern:
    @staticmethod
    def finditer(content: str):
        return iter_chart_matches(content or "")


CHART_PATTERN = _ChartPattern()


def parse_chart_match(match: ChartMatch | re.Match) -> tuple[str, str]:
    if isinstance(match, ChartMatch):
        return match.chart_type, match.raw_json.strip()
    if match.group(2):
        return match.group(2).upper(), match.group(3).strip()
    return "ORG_DATA", match.group(1).strip()
