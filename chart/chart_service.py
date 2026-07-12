import logging
import re
import tempfile
from dataclasses import dataclass
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
_CHART_HEADER_RE = re.compile(
    r"\[(ORG_DATA|GANTT_DATA|TIMELINE_DATA|FLOW_DATA|SMART_DATA):",
    re.IGNORECASE,
)


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


def render_gantt(data: list[dict], duration: int | None = None) -> Path:
    """把工序列表渲染成横道图（甘特图）。data 每项含「工序」「开始第几天」「持续天数」。"""
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


def iter_chart_matches(content: str):
    """扫描正文中的图表占位符，用括号计数提取 JSON，避免嵌套 ] 被正则截断。"""
    i = 0
    length = len(content)
    while i < length:
        if content[i] != "[":
            i += 1
            continue
        header = _CHART_HEADER_RE.match(content, i)
        if not header:
            i += 1
            continue
        chart_type = header.group(1).upper()
        j = header.end()
        while j < length and content[j].isspace():
            j += 1
        if j >= length:
            break
        open_ch, close_ch = ("{", "}") if chart_type == "ORG_DATA" else ("[", "]")
        if content[j] != open_ch:
            i += 1
            continue
        extracted = _extract_balanced(content, j, open_ch, close_ch)
        if not extracted:
            i += 1
            continue
        raw_json, json_end = extracted
        if json_end >= length or content[json_end] != "]":
            i += 1
            continue
        yield ChartMatch(i, json_end + 1, chart_type, raw_json)
        i = json_end + 1


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
