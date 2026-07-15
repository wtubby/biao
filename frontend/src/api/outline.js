import { apiFetch } from './client.js';

/** 兼容旧版数组响应与新版 { nodes, warnings } 包装。 */
export function normalizeOutlineNodes(data) {
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.nodes)) return data.nodes;
  return [];
}

/** @param {string} projectId @param {{ includeWarnings?: boolean }} [options] */
export async function fetchOutline(projectId, options = {}) {
  const data = await apiFetch(`/projects/${projectId}/outline`);
  const includeWarnings = options.includeWarnings === true;
  const nodes = normalizeOutlineNodes(data);
  const warnings = Array.isArray(data?.warnings) ? data.warnings : [];
  if (includeWarnings) {
    return { nodes, warnings };
  }
  return nodes;
}

/** 返回大纲节点与持久化的深化警告列表。 */
export async function fetchOutlineBundle(projectId) {
  return fetchOutline(projectId, { includeWarnings: true });
}

export function fetchOutlineCatalog(projectId) {
  return apiFetch(`/projects/${projectId}/outline-catalog`);
}

export function fetchOutlineTemplates() {
  return apiFetch('/outline/templates');
}

export function fetchOutlineTemplate(templateId) {
  return apiFetch(`/outline/templates/${templateId}`);
}

export function saveOutlineCatalog(projectId, text) {
  return apiFetch(`/projects/${projectId}/outline-catalog`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
}

export function setOutlineCatalogSource(projectId, source) {
  return apiFetch(`/projects/${projectId}/outline-catalog/source`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source }),
  });
}

export function setGenerationMode(projectId, mode) {
  return apiFetch(`/projects/${projectId}/generation-mode`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode }),
  });
}

/**
 * 切换生成档位的统一入口。
 * @param {{ projectId: string, mode: string, currentMode?: string, locked?: boolean, reload?: () => Promise<void> }} opts
 */
export async function changeGenerationMode({
  projectId,
  mode,
  currentMode,
  locked = false,
  reload,
}) {
  if (mode === currentMode || locked) return null;
  const result = await setGenerationMode(projectId, mode);
  if (result.outline_updated && reload) {
    await reload();
  }
  return result;
}

export function generateOutline(projectId) {
  return apiFetch(`/projects/${projectId}/outline/generate`, { method: 'POST' });
}

/** 单章重新生成编写思路（写作要点 + 内容边界） */
export function regenerateLeafGuidance(projectId, leafId, options = {}) {
  const body = {};
  if (options.styleTier) body.style_tier = options.styleTier;
  return apiFetch(`/projects/${projectId}/outline/leaves/${encodeURIComponent(leafId)}/regenerate-guidance`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export function saveOutline(projectId, nodes) {
  return apiFetch(`/projects/${projectId}/outline`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nodes }),
  });
}

export function validateOutline(projectId) {
  return apiFetch(`/projects/${projectId}/outline/validate`, { method: 'POST' });
}

export function lockOutline(projectId) {
  return apiFetch(`/projects/${projectId}/outline/lock`, { method: 'POST' });
}

export function previewSplitLongLeaves(projectId) {
  return apiFetch(`/projects/${projectId}/outline/split-long-leaves/preview`);
}

/** @param {string} projectId @param {{ leafId?: string }} [options] */
export function splitLongLeaves(projectId, options = {}) {
  const body = options.leafId ? { leaf_id: options.leafId } : {};
  return apiFetch(`/projects/${projectId}/outline/split-long-leaves`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}
