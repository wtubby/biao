import { STEP_ORDER } from '../constants/workflow.js';

const STEP_SET = new Set(STEP_ORDER);

function normalizeHash(hash) {
  const raw = String(hash || '').trim();
  if (!raw || raw === '#') return '#/projects';
  return raw.startsWith('#') ? raw : `#${raw}`;
}

/** @returns {{ view: 'list' } | { view: 'project', projectId: string, step: string|null }} */
export function parseHashRoute(hash = window.location.hash) {
  const normalized = normalizeHash(hash).slice(1); // drop #
  const path = normalized.startsWith('/') ? normalized : `/${normalized}`;
  const parts = path.split('/').filter(Boolean);

  if (parts.length === 0 || (parts[0] === 'projects' && parts.length === 1)) {
    return { view: 'list' };
  }

  if (parts[0] === 'projects' && parts[1]) {
    const projectId = decodeURIComponent(parts[1]);
    const step = parts[2] && STEP_SET.has(parts[2]) ? parts[2] : null;
    return { view: 'project', projectId, step };
  }

  return { view: 'list' };
}

export function buildHashRoute(route = {}) {
  if (route.view === 'project' && route.projectId) {
    const id = encodeURIComponent(route.projectId);
    if (route.step && STEP_SET.has(route.step)) {
      return `#/projects/${id}/${route.step}`;
    }
    return `#/projects/${id}`;
  }
  return '#/projects';
}

export function getCurrentHashRoute() {
  return parseHashRoute(window.location.hash);
}

export function replaceHashRoute(route) {
  const next = buildHashRoute(route);
  if (normalizeHash(window.location.hash) === next) return;
  const url = `${window.location.pathname}${window.location.search}${next}`;
  window.history.replaceState(null, '', url);
}

export function pushHashRoute(route) {
  const next = buildHashRoute(route);
  if (normalizeHash(window.location.hash) === next) return;
  window.location.hash = next;
}

export function isWorkflowStepKey(step) {
  return STEP_SET.has(step);
}
