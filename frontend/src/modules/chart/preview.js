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

function _jsonBracketsFor(chartType, ch) {
  if (chartType === 'ORG_DATA') return ch === '{' ? ['{', '}'] : null;
  if (chartType === 'FLOW_DATA') return ch === '[' ? ['[', ']'] : null;
  if (ch === '[') return ['[', ']'];
  if (ch === '{') return ['{', '}'];
  return null;
}

function _expandMarkdownFence(text, start, end) {
  let i = start;
  while (i > 0 && /[ \t]/.test(text[i - 1])) i -= 1;
  if (i <= 0 || (text[i - 1] !== '\n' && text[i - 1] !== '\r')) return { start, end };
  let lineEnd = i - 1;
  if (lineEnd > 0 && text[lineEnd] === '\n' && text[lineEnd - 1] === '\r') lineEnd -= 1;
  const lineStart = text.lastIndexOf('\n', lineEnd - 1) + 1;
  const prevLine = text.slice(lineStart, lineEnd).trim();
  if (!/^```[\w-]*[ \t]*$/.test(prevLine)) return { start, end };

  let j = end;
  while (j < text.length && /[ \t]/.test(text[j])) j += 1;
  if (text[j] === '\r') j += 1;
  if (text[j] === '\n') j += 1;
  const closeEnd = text.indexOf('\n', j);
  const closeLine = (closeEnd < 0 ? text.slice(j) : text.slice(j, closeEnd)).replace(/\r$/, '');
  if (!/^[ \t]*```[ \t]*$/.test(closeLine)) return { start: lineStart, end };
  return { start: lineStart, end: closeEnd < 0 ? text.length : closeEnd + 1 };
}

function* iterChartMatches(text) {
  const colonRe = /\[(ORG_DATA|GANTT_DATA|TIMELINE_DATA|FLOW_DATA|SMART_DATA):/gi;
  const blockRe = /\[(ORG_DATA|GANTT_DATA|TIMELINE_DATA|FLOW_DATA|SMART_DATA)\]/gi;
  const closeRe = /\[\/(ORG_DATA|GANTT_DATA|TIMELINE_DATA|FLOW_DATA|SMART_DATA)\]/gi;
  let i = 0;
  while (i < text.length) {
    if (text[i] !== '[') {
      i += 1;
      continue;
    }
    colonRe.lastIndex = i;
    let header = colonRe.exec(text);
    let requireOuterClose = true;
    let chartType;
    let j;
    if (header && header.index === i) {
      chartType = header[1].toUpperCase();
      j = colonRe.lastIndex;
    } else {
      blockRe.lastIndex = i;
      header = blockRe.exec(text);
      if (!header || header.index !== i) {
        i += 1;
        continue;
      }
      chartType = header[1].toUpperCase();
      j = blockRe.lastIndex;
      requireOuterClose = false;
    }
    while (j < text.length && /\s/.test(text[j])) j += 1;
    if (j >= text.length) break;
    const brackets = _jsonBracketsFor(chartType, text[j]);
    if (!brackets) {
      i += 1;
      continue;
    }
    const [openCh, closeCh] = brackets;
    const extracted = _extractBalanced(text, j, openCh, closeCh);
    if (!extracted) {
      i += 1;
      continue;
    }
    let end;
    if (requireOuterClose) {
      if (extracted.end >= text.length || text[extracted.end] !== ']') {
        i += 1;
        continue;
      }
      end = extracted.end + 1;
    } else {
      end = extracted.end;
      let k = end;
      while (k < text.length && /\s/.test(text[k])) k += 1;
      closeRe.lastIndex = k;
      const closeM = closeRe.exec(text);
      if (closeM && closeM.index === k && closeM[1].toUpperCase() === chartType) {
        end = closeM.index + closeM[0].length;
      }
    }
    const expanded = _expandMarkdownFence(text, i, end);
    yield {
      index: expanded.start,
      end: expanded.end,
      chartType,
      rawJson: extracted.json,
    };
    i = expanded.end;
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

function _chartHtml(chartType, rawJson, caption, preview) {
  if (chartType === 'SMART_DATA') {
    try {
      return _smartTableHtml(JSON.parse(rawJson)) + _captionHtml(caption);
    } catch {
      return _chartPlaceholderHtml(chartType, true);
    }
  }
  if (preview && preview.image_base64) {
    return (
      `<div style="text-align:center"><img src="data:image/png;base64,${preview.image_base64}" style="max-width:100%;border:1px solid #eee;border-radius:4px" /></div>`
      + _captionHtml(caption)
    );
  }
  if (preview && !preview.image_base64) {
    return _chartPlaceholderHtml(chartType, true);
  }
  return _chartPlaceholderHtml(chartType, false);
}

function useChartPreviews(content, durationDays, delay = 700) {
  const [previews, setPreviews] = useState([]);
  const timerRef = useRef(null);
  const requestIdRef = useRef(0);

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    if (!content || !/\[\/?(ORG_DATA|GANTT_DATA|TIMELINE_DATA|FLOW_DATA)/i.test(content)) {
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

function _resolvePreview(chartPreviews, matchIndex, order) {
  const list = chartPreviews || [];
  return list.find((p) => p.start === matchIndex) || list[order] || null;
}

function _parseMarkdownSegment(segment) {
  if (!segment) return '';
  const highlighted = segment.replace(
    /\*\*\[参数\]\s*(.+?)\*\*/g,
    '<span style="background:#fffbe6;border:1px solid #ffe58f;padding:0 4px;border-radius:2px;font-weight:bold">$1</span>',
  );
  if (window.marked) return window.marked.parse(highlighted);
  return highlighted
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\n/g, '<br>');
}

function renderMarkdownPreview(text, chartPreviews) {
  if (!text) return { __html: '<p style="color:#999">暂无内容</p>' };

  const matches = [...iterChartMatches(text)];
  if (!matches.length) {
    const html = _parseMarkdownSegment(text);
    return { __html: html || '<p style="color:#999">暂无内容</p>' };
  }

  const captionCounters = {};
  let html = '';
  let lastEnd = 0;
  matches.forEach((m, idx) => {
    html += _parseMarkdownSegment(text.slice(lastEnd, m.index));
    const preview = _resolvePreview(chartPreviews, m.index, idx);
    const caption = preview?.caption || formatCaption(m.chartType, captionCounters);
    html += _chartHtml(m.chartType, m.rawJson, caption, preview);
    lastEnd = m.end;
  });
  html += _parseMarkdownSegment(text.slice(lastEnd));
  return { __html: html };
}
export {
  CHART_CAPTIONS,
  CHART_LABELS,
  useChartPreviews,
  renderMarkdownPreview,
};
