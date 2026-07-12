import { apiFetch } from './client.js';

export function fetchTenderDetail(projectId) {
  return apiFetch(`/projects/${projectId}/tender-detail`);
}

export function updateTenderDetail(projectId, body) {
  return apiFetch(`/projects/${projectId}/tender-detail`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}
