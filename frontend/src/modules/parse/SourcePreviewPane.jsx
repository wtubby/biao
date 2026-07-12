import {
  useEffect, useMemo, useRef, useState,
  Button, Spin, Text, message,
} from '../../globals.js';
import { getSourceFileUrl } from '../../api/parse.js';
import { Icon } from '../../components/icons.jsx';

const HIGHLIGHT_CLASS = 'source-locate-mark';
const MIN_MATCH_LEN = 6;
const BLOCK_SELECTOR = 'p,td,th,li,h1,h2,h3,h4,h5,h6';

/** docx-preview / Word 常见不可见字符 */
const INVISIBLE_RE = /[\u00AD\u200B\u200C\u200D\u2060\uFEFF\u200E\u200F\u180E\u034F]/;

const PUNCT_SET = new Set(
  Array.from('，。、；：！？""\'\'‘’“”（）【】《》〈〉,.!?;:\'"()[]{}<>·…—_-/\\|=+*&^%$#@~`•·‧'),
);

/** 统一 DOCX→HTML 后的字符形态，便于与摘录比对 */
function unifyChar(ch) {
  if (!ch) return '';
  if (INVISIBLE_RE.test(ch)) return '';
  if (ch === '\u00A0' || ch === '\u3000') return ' ';
  const code = ch.charCodeAt(0);
  // 全角 ASCII → 半角
  if (code >= 0xFF01 && code <= 0xFF5E) {
    return String.fromCharCode(code - 0xFEE0);
  }
  if (code === 0xFF0C) return ',';
  const map = {
    '“': '"', '”': '"', '„': '"', '‟': '"',
    '‘': "'", '’': "'", '‚': "'",
    '—': '-', '–': '-', '−': '-', '─': '-',
    '…': '...',
    '×': 'x',
  };
  return map[ch] || ch;
}

function normalizeWs(s) {
  let out = '';
  for (const ch of String(s || '')) {
    const u = unifyChar(ch);
    if (!u) continue;
    out += u;
  }
  return out.replace(/\s+/g, ' ').trim();
}

/** 紧凑串：去掉空白/标点/不可见字符，并统一全角 */
function compactText(s) {
  let out = '';
  for (const ch of String(s || '')) {
    const u = unifyChar(ch);
    if (!u) continue;
    for (const c of u) {
      if (/\s/.test(c) || PUNCT_SET.has(c)) continue;
      out += c;
    }
  }
  return out;
}

function clearHighlights(root) {
  if (!root) return;
  root.querySelectorAll(`mark.${HIGHLIGHT_CLASS}`).forEach((mark) => {
    const parent = mark.parentNode;
    if (!parent) return;
    while (mark.firstChild) parent.insertBefore(mark.firstChild, mark);
    parent.removeChild(mark);
    parent.normalize();
  });
}

/** 空白折叠索引（已 unify） */
function buildWsIndex(haystack) {
  const map = [];
  let norm = '';
  let prevSpace = true;
  for (let i = 0; i < haystack.length; i += 1) {
    const unified = unifyChar(haystack[i]);
    if (!unified) continue;
    for (const ch of unified) {
      if (/\s/.test(ch)) {
        if (!prevSpace && norm.length > 0) {
          norm += ' ';
          map.push(i);
        }
        prevSpace = true;
      } else {
        norm += ch;
        map.push(i);
        prevSpace = false;
      }
    }
  }
  return { norm: norm.trimEnd(), map };
}

/** 紧凑索引：跳过 DOCX HTML 噪声，映射回 haystack 下标 */
function buildCompactIndex(haystack) {
  const map = [];
  let norm = '';
  for (let i = 0; i < haystack.length; i += 1) {
    const unified = unifyChar(haystack[i]);
    if (!unified) continue;
    for (const ch of unified) {
      if (/\s/.test(ch) || PUNCT_SET.has(ch)) continue;
      norm += ch;
      map.push(i);
    }
  }
  return { norm, map };
}

function rangeFromIndex(index, idx, matchLen) {
  if (idx < 0 || !index.map.length || matchLen <= 0) return null;
  const endPos = Math.min(idx + matchLen, index.map.length) - 1;
  const start = index.map[idx];
  const endIdx = index.map[endPos];
  if (start == null || endIdx == null) return null;
  return { start, end: endIdx + 1, score: matchLen };
}

/** 从摘录生成多个候选（适配改写/截断；长度按紧凑串） */
function buildNeedleCandidates(raw) {
  const full = normalizeWs(raw);
  if (!full) return [];

  const seen = new Set();
  const out = [];
  const push = (s) => {
    const t = normalizeWs(s);
    if (!t || compactText(t).length < MIN_MATCH_LEN || seen.has(t)) return;
    seen.add(t);
    out.push(t);
  };

  push(full);

  const quoteMatch = full.match(/[「『"“](.{6,160})[」』"”]/);
  if (quoteMatch) push(quoteMatch[1]);

  push(full.replace(/^(若|如|凡|投标人|申请人|响应文件|招标文件)[^，。；]{0,16}[，：:]/, ''));

  // 按句号/分号切开，取较长子句
  full.split(/[。；;！？\n]/).forEach((part) => push(part));

  const prefixLens = [80, 64, 48, 36, 28, 20, 16, 12, 8];
  prefixLens.forEach((len) => {
    if (full.length > len) push(full.slice(0, len));
  });

  const compact = compactText(full);
  const winLens = [24, 18, 14, 10];
  winLens.forEach((win) => {
    if (compact.length <= win) return;
    const step = Math.max(4, Math.floor(win / 2));
    for (let i = 0; i + win <= Math.min(compact.length, 240); i += step) {
      // 用紧凑窗口反查不到原文位置，直接把窗口当候选（走 compact 匹配）
      push(compact.slice(i, i + win));
    }
  });

  out.sort((a, b) => compactText(b).length - compactText(a).length);
  return out;
}

/**
 * 在扁平文本中找 needle（面向 docx-preview HTML）。
 * 返回原始 haystack 起止下标。
 */
function findNormalizedRange(haystack, needle) {
  const candidates = buildNeedleCandidates(needle);
  if (!candidates.length) return null;

  const wsIndex = buildWsIndex(haystack);
  const compactIndex = buildCompactIndex(haystack);
  const needleCompactFull = compactText(needle);

  let best = null;

  for (const cand of candidates) {
    const candWs = normalizeWs(cand);
    const candCompact = compactText(cand);
    if (candCompact.length < MIN_MATCH_LEN) continue;

    // 1) 空白折叠子串
    let idx = wsIndex.norm.indexOf(candWs);
    if (idx >= 0) {
      const hit = rangeFromIndex(wsIndex, idx, candWs.length);
      if (hit && (!best || hit.score > best.score)) {
        const exact = candCompact === needleCompactFull;
        best = { ...hit, fuzzy: !exact };
        if (exact) return best;
      }
    }

    // 2) 紧凑串（忽略标点/不可见字符/全角差异）——DOCX→HTML 主路径
    idx = compactIndex.norm.indexOf(candCompact);
    if (idx >= 0) {
      const hit = rangeFromIndex(compactIndex, idx, candCompact.length);
      if (hit && (!best || hit.score > best.score)) {
        best = { ...hit, fuzzy: candCompact !== needleCompactFull };
        if (candCompact === needleCompactFull && hit.score >= needleCompactFull.length) {
          return best;
        }
      }
    }
  }

  return best;
}

function isBlockBoundary(node) {
  const el = node.parentElement;
  if (!el) return null;
  return el.closest(BLOCK_SELECTOR);
}

/**
 * 收集 docx-preview DOM 文本：块级边界插入换行，避免段落粘连；
 * ranges 映射到真实 Text 节点（用于 splitText 高亮）。
 */
function collectDocxFlatText(root) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      if (!node.nodeValue) return NodeFilter.FILTER_REJECT;
      const parent = node.parentElement;
      if (parent && parent.closest('script, style, mark.source-locate-mark')) {
        return NodeFilter.FILTER_REJECT;
      }
      // 页眉页脚里的重复条款易误匹配，仍保留（招标文件正文为主）；不排除
      return NodeFilter.FILTER_ACCEPT;
    },
  });

  let full = '';
  const ranges = [];
  let prevBlock = null;

  while (walker.nextNode()) {
    const node = walker.currentNode;
    const block = isBlockBoundary(node);
    if (full.length > 0 && block && prevBlock && block !== prevBlock) {
      full += '\n';
    }
    if (block) prevBlock = block;

    const start = full.length;
    full += node.nodeValue;
    ranges.push({ node, start, end: full.length });
  }

  return { full, ranges };
}

function applyHighlightMarks(ranges, match, scrollRoot, root) {
  const touches = ranges.filter((r) => r.node && r.end > match.start && r.start < match.end);
  for (let i = touches.length - 1; i >= 0; i -= 1) {
    const { node, start } = touches[i];
    if (!node.parentNode) continue;
    const localStart = Math.max(0, match.start - start);
    const localEnd = Math.min(node.nodeValue.length, match.end - start);
    if (localStart >= localEnd) continue;

    try {
      const after = node.splitText(localEnd);
      const mid = node.splitText(localStart);
      const mark = document.createElement('mark');
      mark.className = HIGHLIGHT_CLASS;
      mid.parentNode.insertBefore(mark, mid);
      mark.appendChild(mid);
      void after;
    } catch {
      // 节点已被拆分时忽略
    }
  }

  const firstMark = root.querySelector(`mark.${HIGHLIGHT_CLASS}`);
  if (firstMark && scrollRoot) {
    const markRect = firstMark.getBoundingClientRect();
    const scrollRect = scrollRoot.getBoundingClientRect();
    const offset = markRect.top - scrollRect.top + scrollRoot.scrollTop - scrollRoot.clientHeight * 0.25;
    scrollRoot.scrollTo({ top: Math.max(0, offset), behavior: 'smooth' });
  }
}

function blockMightContain(blockCompact, needleCompact) {
  if (!blockCompact || !needleCompact) return false;
  if (blockCompact.includes(needleCompact)) return true;
  const probe = Math.min(12, needleCompact.length);
  if (probe >= MIN_MATCH_LEN && blockCompact.includes(needleCompact.slice(0, probe))) return true;
  for (let i = 0; i + MIN_MATCH_LEN <= Math.min(needleCompact.length, 120); i += 5) {
    const frag = needleCompact.slice(i, i + Math.min(12, needleCompact.length - i));
    if (frag.length >= MIN_MATCH_LEN && blockCompact.includes(frag)) return true;
  }
  return false;
}

/**
 * 在 DOCX 预览 DOM 中按原文摘录高亮并滚入视口。
 * 先按段落/单元格匹配（贴合 docx-preview 块结构），再回退全文。
 * @returns {{ ok: boolean, fuzzy?: boolean }}
 */
function highlightInDocx(root, scrollRoot, rawText) {
  clearHighlights(root);
  const needle = normalizeWs(rawText);
  const needleCompact = compactText(needle);
  if (!needle || needleCompact.length < MIN_MATCH_LEN) return { ok: false };

  let best = null;
  let bestPack = null;

  const blocks = root.querySelectorAll(BLOCK_SELECTOR);
  for (let b = 0; b < blocks.length; b += 1) {
    const block = blocks[b];
    const blockCompact = compactText(block.textContent || '');
    if (blockCompact.length < MIN_MATCH_LEN) continue;
    if (!blockMightContain(blockCompact, needleCompact)) continue;

    const pack = collectDocxFlatText(block);
    const match = findNormalizedRange(pack.full, needle);
    if (
      match
      && (
        !best
        || match.score > best.score
        || (match.score === best.score && !match.fuzzy && best.fuzzy)
      )
    ) {
      best = match;
      bestPack = pack;
      if (!match.fuzzy && match.score >= needleCompact.length) break;
    }
  }

  if (!best || best.fuzzy || best.score < Math.min(needleCompact.length, 24)) {
    const pack = collectDocxFlatText(root);
    const match = findNormalizedRange(pack.full, needle);
    if (match && (!best || match.score > best.score)) {
      best = match;
      bestPack = pack;
    }
  }

  if (!best || !bestPack) return { ok: false };

  applyHighlightMarks(bestPack.ranges, best, scrollRoot, root);
  return { ok: true, fuzzy: !!best.fuzzy };
}

/**
 * 左侧/右侧：招标原文预览（PDF iframe；DOCX 用 docx-preview）
 * highlightTarget: { text, page, key } — 点击评分项时定位高亮
 */
function SourcePreviewPane({ projectId, hasSource, sourceType, highlightTarget = null }) {
  const url = useMemo(
    () => (hasSource && projectId ? getSourceFileUrl(projectId) : null),
    [hasSource, projectId],
  );
  const docxContainerRef = useRef(null);
  const scrollRef = useRef(null);
  const [docxLoading, setDocxLoading] = useState(false);
  const [docxError, setDocxError] = useState(null);
  const [docxReady, setDocxReady] = useState(false);
  const [locateHint, setLocateHint] = useState(null);

  const pdfSrc = useMemo(() => {
    if (!url || sourceType !== 'pdf') return null;
    const page = highlightTarget?.page;
    if (page && Number(page) > 0) {
      return `${url}#page=${Number(page)}`;
    }
    return url;
  }, [url, sourceType, highlightTarget?.page]);

  const pdfFrameKey = highlightTarget
    ? `pdf-${highlightTarget.key}-${highlightTarget.nonce || highlightTarget.page || ''}`
    : 'pdf-default';

  useEffect(() => {
    if (!url || sourceType !== 'docx' || !docxContainerRef.current) {
      setDocxReady(false);
      return undefined;
    }

    let cancelled = false;
    const container = docxContainerRef.current;
    container.innerHTML = '';
    setDocxLoading(true);
    setDocxError(null);
    setDocxReady(false);

    (async () => {
      try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`加载失败（${res.status}）`);
        const buffer = await res.arrayBuffer();
        if (cancelled) return;
        const { renderAsync } = await import('docx-preview');
        await renderAsync(buffer, container, null, {
          className: 'docx',
          inWrapper: true,
          breakPages: true,
          renderHeaders: true,
          renderFooters: true,
          ignoreLastRenderedPageBreak: true,
          useBase64URL: true,
        });
        if (!cancelled) setDocxReady(true);
      } catch (e) {
        if (!cancelled) {
          setDocxError(e.message || 'DOCX 预览失败');
          setDocxReady(false);
        }
      } finally {
        if (!cancelled) setDocxLoading(false);
      }
    })();

    return () => {
      cancelled = true;
      clearHighlights(container);
      container.innerHTML = '';
      setDocxReady(false);
    };
  }, [url, sourceType]);

  useEffect(() => {
    if (!highlightTarget) {
      setLocateHint(null);
      return;
    }

    const text = normalizeWs(highlightTarget.text);
    const page = highlightTarget.page;

    if (sourceType === 'docx' && docxReady && docxContainerRef.current) {
      const result = highlightInDocx(docxContainerRef.current, scrollRef.current, text);
      if (result.ok) {
        setLocateHint({
          ok: true,
          fuzzy: result.fuzzy,
          page,
          preview: text.length > 80 ? `${text.slice(0, 80)}…` : text,
        });
        if (result.fuzzy) {
          message.info('已定位到相近原文片段（摘录可能为摘要改写）');
        }
      } else {
        setLocateHint({
          ok: false,
          page,
          preview: text.length > 80 ? `${text.slice(0, 80)}…` : text,
        });
        if (text) message.warning('未在预览中匹配到原文，请对照摘录人工查找');
      }
      return;
    }

    if (sourceType === 'pdf') {
      setLocateHint({
        ok: !!page,
        page,
        preview: text.length > 120 ? `${text.slice(0, 120)}…` : text,
      });
      if (!page && text) {
        message.info('PDF 暂不支持页内高亮，已展示原文摘录供对照');
      }
    }
  }, [highlightTarget, sourceType, docxReady]);

  return (
    <div className="source-preview-pane">
      <div className="source-preview-header">
        <Text strong>招标原文预览</Text>
        {hasSource && sourceType && (
          <Text type="secondary" style={{ fontSize: 12 }}>
            {sourceType.toUpperCase()}
          </Text>
        )}
        {url && (
          <Button
            type="link"
            size="small"
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            style={{ marginLeft: 'auto', paddingInline: 0 }}
          >
            {sourceType === 'docx' ? '下载原文' : '新窗口打开'}
          </Button>
        )}
      </div>

      {locateHint && (
        <div className={`source-locate-banner${locateHint.ok ? '' : ' source-locate-banner--miss'}`}>
          {locateHint.page ? (
            <span className="source-locate-page">第 {locateHint.page} 页</span>
          ) : null}
          <span className="source-locate-text">{locateHint.preview || '（无原文摘录）'}</span>
        </div>
      )}

      <div className="source-preview-scroll" ref={scrollRef}>
        {!hasSource && (
          <div className="source-preview-empty">
            <Icon name="preview" size={40} />
            <p>上传 PDF / DOCX 后可在此预览原文</p>
          </div>
        )}

        {hasSource && sourceType === 'pdf' && pdfSrc && (
          <iframe
            key={pdfFrameKey}
            className="source-preview-frame"
            title="招标原文 PDF 预览"
            src={pdfSrc}
          />
        )}

        {hasSource && sourceType === 'docx' && url && (
          <Spin spinning={docxLoading} tip="正在渲染 Word 预览…" className="source-preview-docx-spin">
            {docxError ? (
              <div className="source-preview-docx source-preview-docx--error">
                <Icon name="error" size={36} />
                <p>页内预览失败：{docxError}</p>
                <Button type="primary" href={url} download="source.docx">
                  下载原文
                </Button>
              </div>
            ) : (
              <div ref={docxContainerRef} className="source-preview-docx-host" />
            )}
          </Spin>
        )}
      </div>
    </div>
  );
}

export { SourcePreviewPane };
