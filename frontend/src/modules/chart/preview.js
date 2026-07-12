import {
  useState, useEffect, useRef,
} from '../../globals.js';

import { apiFetch } from '../../api/client.js';
const CHART_CAPTIONS = {
  GANTT_DATA: ['图', '施工进度横道图'],
  TIMELINE_DATA: ['图', '里程碑时间轴'],
  FLOW_DATA: ['图', '工艺流程图'],
  ORG_DATA: ['图', '组织架构图'],
  SMART_DATA: ['表', '要点对照表'],
};

function formatCaption(chartType, counters) {
  const [kind, label] = CHART_CAPTIONS[chartType] || ['图', chartType];
  const key = kind === '表' ? 'table' : 'figure';
  counters[key] = (counters[key] || 0) + 1;
  return `${kind}${counters[key]} ${label}`;
}

function _captionHtml(text) {
  return `<p style="text-align:center;font-size:12px;color:#595959;margin:4px 0 12px">${text}</p>`;
}

function _extractBalanced(text, start, openCh, closeCh) {
  let depth = 0;
  let inString = false;
  let escape = false;
  let stringQuote = '';
  for (let i = start; i < text.length; i += 1) {
    const ch = text[i];
    if (inString) {
      if (escape) escape = false;
      else if (ch === '\\') escape = true;
      else if (ch === stringQuote) inString = false;
      continue;
    }
    if (ch === '"' || ch === "'") {
      inString = true;
      stringQuote = ch;
      continue;
    }
    if (ch === openCh) depth += 1;
    else if (ch === closeCh) {
      depth -= 1;
      if (depth === 0) return { json: text.slice(start, i + 1), end: i + 1 };
    }
  }
  return null;
}

function* iterChartMatches(text) {
  const headerRe = /\[(ORG_DATA|GANTT_DATA|TIMELINE_DATA|FLOW_DATA|SMART_DATA):/gi;
  let i = 0;
  while (i < text.length) {
    if (text[i] !== '[') {
      i += 1;
      continue;
    }
    headerRe.lastIndex = i;
    const header = headerRe.exec(text);
    if (!header || header.index !== i) {
      i += 1;
      continue;
    }
    const chartType = header[1].toUpperCase();
    let j = headerRe.lastIndex;
    while (j < text.length && /\s/.test(text[j])) j += 1;
    if (j >= text.length) break;
    const openCh = chartType === 'ORG_DATA' ? '{' : '[';
    const closeCh = chartType === 'ORG_DATA' ? '}' : ']';
    if (text[j] !== openCh) {
      i += 1;
      continue;
    }
    const extracted = _extractBalanced(text, j, openCh, closeCh);
    if (!extracted) {
      i += 1;
      continue;
    }
    if (extracted.end >= text.length || text[extracted.end] !== ']') {
      i += 1;
      continue;
    }
    yield {
      index: i,
      end: extracted.end + 1,
      chartType,
      rawJson: extracted.json,
    };
    i = extracted.end + 1;
  }
}

const CHART_LABELS = {
  GANTT_DATA: '施工进度横道图',
  TIMELINE_DATA: '里程碑时间轴',
  FLOW_DATA: '工艺流程图',
  ORG_DATA: '组织架构图',
  SMART_DATA: '并列要点块',
};

function _chartPlaceholderHtml(chartType, failed) {
  const style = failed
    ? 'background:#fff2f0;border:1px dashed #ffccc7;color:#cf1322'
    : 'background:#f5f5f5;border:1px dashed #ccc;color:#888';
  const text = failed ? `${CHART_LABELS[chartType] || chartType} 数据解析失败，请检查格式` : `${CHART_LABELS[chartType] || chartType}（渲染中…）`;
  return `<div style="${style};padding:12px;border-radius:4px;text-align:center">${text}</div>`;
}

function _smartTableHtml(data) {
  if (!Array.isArray(data) || !data.length) return _chartPlaceholderHtml('SMART_DATA', true);
  const heads = data.map((d) => `<th>${d.title || ''}</th>`).join('');
  const cells = data.map((d) => `<td>${d.desc || ''}</td>`).join('');
  return `<table><thead><tr>${heads}</tr></thead><tbody><tr>${cells}</tr></tbody></table>`;
}

function useChartPreviews(content, durationDays, delay = 700) {
  const [previews, setPreviews] = useState([]);
  const timerRef = useRef(null);
  const requestIdRef = useRef(0);

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    if (!content || !/\[(ORG_DATA|GANTT_DATA|TIMELINE_DATA|FLOW_DATA):/i.test(content)) {
      setPreviews([]);
      return;
    }
    timerRef.current = setTimeout(async () => {
      const requestId = ++requestIdRef.current;
      try {
        const data = await apiFetch('/chart-preview', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            content,
            duration_days: durationDays ?? null,
          }),
        });
        if (requestId === requestIdRef.current) {
          setPreviews(data.charts || []);
        }
      } catch {
        if (requestId === requestIdRef.current) setPreviews([]);
      }
    }, delay);
    return () => clearTimeout(timerRef.current);
  }, [content, durationDays]);

  return previews;
}

function renderMarkdownPreview(text, chartPreviews) {
  if (!text) return { __html: '<p style="color:#999">暂无内容</p>' };

  const previewByStart = new Map((chartPreviews || []).map((p) => [p.start, p]));
  const captionByIndex = new Map();
  const captionCounters = {};
  for (const m of iterChartMatches(text)) {
    captionByIndex.set(m.index, formatCaption(m.chartType, captionCounters));
  }
  let result = '';
  let lastEnd = 0;
  for (const m of iterChartMatches(text)) {
    result += text.slice(lastEnd, m.index);
    const { chartType, rawJson } = m;
    const caption = previewByStart.get(m.index)?.caption || captionByIndex.get(m.index);

    if (chartType === 'SMART_DATA') {
      try {
        const data = JSON.parse(rawJson);
        result += _smartTableHtml(data);
        result += _captionHtml(caption);
      } catch {
        result += _chartPlaceholderHtml(chartType, true);
      }
    } else {
      const preview = previewByStart.get(m.index);
      if (preview && preview.image_base64) {
        result += `<div style="text-align:center"><img src="data:image/png;base64,${preview.image_base64}" style="max-width:100%;border:1px solid #eee;border-radius:4px" /></div>`;
        result += _captionHtml(caption);
      } else if (preview && !preview.image_base64) {
        result += _chartPlaceholderHtml(chartType, true);
      } else {
        result += _chartPlaceholderHtml(chartType, false);
      }
    }
    lastEnd = m.end;
  }
  result += text.slice(lastEnd);

  const highlighted = result.replace(
    /\*\*\[参数\]\s*(.+?)\*\*/g,
    '<span style="background:#fffbe6;border:1px solid #ffe58f;padding:0 4px;border-radius:2px;font-weight:bold">$1</span>'
  );
  if (window.marked) {
    return { __html: window.marked.parse(highlighted) };
  }
  const escaped = highlighted
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\n/g, '<br>');
  return { __html: escaped };
}
export {
  CHART_CAPTIONS,
  CHART_LABELS,
  useChartPreviews,
  renderMarkdownPreview,
};
