import { apiFetch } from './client.js';

export async function fetchCommercialStatus(projectId) {
  return apiFetch(`/projects/${projectId}/commercial/status`);
}

export async function toggleCommercialScope(projectId, enabled) {
  return apiFetch(`/projects/${projectId}/commercial/toggle`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  });
}

export async function regenerateCommercial(projectId) {
  return apiFetch(`/projects/${projectId}/commercial/regenerate`, {
    method: 'POST',
  });
}

export async function updateCommercialSection(projectId, sectionId, patch) {
  return apiFetch(`/projects/${projectId}/commercial/sections/${sectionId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  });
}
