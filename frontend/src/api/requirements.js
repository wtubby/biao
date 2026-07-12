import { apiFetch } from './client.js';

export function fetchRequirements(projectId) {
  return apiFetch(`/projects/${projectId}/requirements`);
}

export function updateRequirement(id, fields) {
  return apiFetch(`/requirements/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(fields),
  });
}

export function confirmAllRequirements(projectId) {
  return apiFetch(`/projects/${projectId}/requirements/confirm-all`, { method: 'POST' });
}

export function computeRequirementStats(reqs = []) {
  const riskItems = reqs.filter((r) => r.is_risk_item === 1);
  return {
    total: reqs.length,
    confirmed: reqs.filter((r) => r.status === 'confirmed').length,
    risk: riskItems.length,
    riskConfirmed: riskItems.filter((r) => r.status === 'confirmed').length,
  };
}
