import { apiFetch, API } from './client.js';

export function fetchParseSummary(projectId) {
  return apiFetch(`/projects/${projectId}/parse/summary`);
}

export function getSourceFileUrl(projectId) {
  return `${API}/projects/${projectId}/source`;
}

export function fetchSourceMeta(projectId) {
  return apiFetch(`/projects/${projectId}/source/meta`);
}
