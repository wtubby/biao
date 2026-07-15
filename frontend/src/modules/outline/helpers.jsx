import { Badge } from '../../globals.js';

function reviewStatusToBadgeStatus(status) {
  const map = {
    green: 'success',
    yellow: 'warning',
    red: 'error',
    generating: 'processing',
  };
  return map[status] || null;
}

function OutlineReviewBadge({ status }) {
  const badgeStatus = reviewStatusToBadgeStatus(status);
  if (!badgeStatus) return null;
  return <Badge status={badgeStatus} />;
}

/** 共用父子索引，避免 buildOutlineTreeData / getOrderedLeaves 各建一遍 */
function sortOutlineSiblings(items) {
  return [...items].sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
}

function buildOutlineIndex(nodes) {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const childrenOf = new Map();
  const roots = [];
  nodes.forEach((n) => {
    if (n.parent_id && byId.has(n.parent_id)) {
      if (!childrenOf.has(n.parent_id)) childrenOf.set(n.parent_id, []);
      childrenOf.get(n.parent_id).push(n);
    } else {
      roots.push(n);
    }
  });
  roots.sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
  childrenOf.forEach((kids, parentId) => {
    childrenOf.set(parentId, sortOutlineSiblings(kids));
  });
  return { byId, childrenOf, roots };
}

const CN_DIGITS = '〇一二三四五六七八九';

function cnIndex(n) {
  if (n <= 0) return String(n);
  if (n <= 10) return n === 10 ? '十' : CN_DIGITS[n];
  if (n < 20) return `十${CN_DIGITS[n - 10]}`;
  const tens = Math.floor(n / 10);
  const ones = n % 10;
  const tensPart = tens === 1 ? '' : CN_DIGITS[tens];
  const onesPart = ones ? CN_DIGITS[ones] : '';
  return `${tensPart}十${onesPart}`;
}

/** 与 Word 导出 numbering_service 预设一致 */
function formatOutlineNumberLabel(preset, level, counters) {
  const c = counters;
  switch (preset) {
    case 'chapter_cn':
      if (level === 1) return `第${c[0]}章`;
      if (level === 2) return `第${c[1]}节`;
      if (level === 3) return `${cnIndex(c[2])}、`;
      return `（${c[3]}）`;
    case 'outline_mixed':
      if (level === 1) return `第${c[0]}章`;
      if (level === 2) return `${c[0]}.${c[1]}`;
      if (level === 3) return `${c[0]}.${c[1]}.${c[2]}`;
      return `（${c[3]}）`;
    case 'none':
      return '';
    case 'decimal':
    default:
      return c.slice(0, level).join('.');
  }
}

/** 按树结构生成各节点展示用多级编号（编辑态全量显示，含空容器节点） */
function computeOutlineNumberLabels(nodes, preset = 'decimal') {
  if (!nodes.length || preset === 'none') return new Map();
  const { childrenOf, roots } = buildOutlineIndex(nodes);
  const labels = new Map();
  const counters = [0, 0, 0, 0];

  const walk = (items, depth) => {
    items.forEach((node) => {
      counters[depth - 1] += 1;
      for (let i = depth; i < counters.length; i += 1) counters[i] = 0;
      const label = formatOutlineNumberLabel(preset, depth, counters);
      if (label) labels.set(node.id, label);
      const kids = childrenOf.get(node.id);
      if (kids?.length) walk(kids, depth + 1);
    });
  };

  walk(roots, 1);
  return labels;
}

function buildOutlineTreeData(nodes, renderTitle) {
  const { childrenOf, roots } = buildOutlineIndex(nodes);
  const toTreeNode = (n) => {
    const kids = childrenOf.get(n.id) || [];
    const item = { key: n.id, title: renderTitle(n) };
    if (kids.length) item.children = kids.map(toTreeNode);
    return item;
  };
  return roots.map(toTreeNode);
}

function getOrderedLeaves(nodes) {
  const { childrenOf, roots } = buildOutlineIndex(nodes);
  const leaves = [];
  const walk = (items) => {
    items.forEach((n) => {
      if (n.is_leaf === 1) leaves.push(n);
      else if (childrenOf.has(n.id)) walk(childrenOf.get(n.id));
    });
  };
  walk(roots);
  return leaves;
}

function newOutlineId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return `ch-${crypto.randomUUID()}`;
  }
  return `ch-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function getNodeDescendantIds(nodes, nodeId) {
  const ids = new Set([nodeId]);
  let changed = true;
  while (changed) {
    changed = false;
    nodes.forEach((n) => {
      if (n.parent_id && ids.has(n.parent_id) && !ids.has(n.id)) {
        ids.add(n.id);
        changed = true;
      }
    });
  }
  return ids;
}

function getNextSortOrder(nodes, parentId) {
  const siblings = nodes.filter((n) => (n.parent_id || null) === (parentId || null));
  if (!siblings.length) return 1;
  return Math.max(...siblings.map((n) => n.sort_order || 0)) + 1;
}

function recomputeOutlineStructure(nodes) {
  if (!nodes.length) return [];
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const computeLevel = (id, seen = new Set()) => {
    if (seen.has(id)) return 1;
    seen.add(id);
    const n = byId.get(id);
    if (!n || !n.parent_id || !byId.has(n.parent_id)) return 1;
    return computeLevel(n.parent_id, seen) + 1;
  };
  return nodes.map((n) => {
    const hasChildren = nodes.some((c) => c.parent_id === n.id);
    return {
      ...n,
      level: computeLevel(n.id),
      is_leaf: hasChildren ? 0 : 1,
    };
  });
}

function createOutlineNode({ parentId = null, title = '新章节' }) {
  return {
    id: newOutlineId(),
    title,
    parent_id: parentId,
    sort_order: 0,
    level: 1,
    is_leaf: 1,
    bound_folder: null,
    requirement_ids: [],
    guidance_brief: '',
    content_boundary: '',
    style_tier: 'balanced',
    target_words: 0,
    review_status: 'init',
  };
}

function serializeOutlineNodesForSave(nodes) {
  return recomputeOutlineStructure(nodes).map((n, i) => {
    const item = {
      id: n.id,
      title: (n.title || '').trim() || '未命名章节',
      parent_id: n.parent_id || null,
      sort_order: n.sort_order ?? i + 1,
      level: n.level ?? 1,
      is_leaf: n.is_leaf ?? 0,
      bound_folder: n.bound_folder || null,
      requirement_ids: n.requirement_ids || [],
    };
    if (item.is_leaf === 1) {
      item.guidance_brief = n.guidance_brief || '';
      item.content_boundary = n.content_boundary || '';
      item.style_tier = n.style_tier || 'balanced';
    }
    return item;
  });
}

export {
  reviewStatusToBadgeStatus,
  OutlineReviewBadge,
  buildOutlineIndex,
  buildOutlineTreeData,
  computeOutlineNumberLabels,
  getOrderedLeaves,
  newOutlineId,
  getNodeDescendantIds,
  getNextSortOrder,
  recomputeOutlineStructure,
  createOutlineNode,
  serializeOutlineNodesForSave,
};
