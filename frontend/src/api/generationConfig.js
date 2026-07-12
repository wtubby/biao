import { API, apiFetch, formatApiError } from './client.js';

export function fetchGenerationConfig(projectId) {
  return apiFetch(`/projects/${projectId}/generation-config`);
}

export function updateGenerationConfig(projectId, body) {
  return apiFetch(`/projects/${projectId}/generation-config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export function confirmBidFormat(projectId) {
  return apiFetch(`/projects/${projectId}/generation-config/confirm-format`, {
    method: 'POST',
  });
}

export async function uploadReferenceBid(projectId, file) {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${API}/projects/${projectId}/reference-bid/upload`, {
    method: 'POST',
    body: form,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(formatApiError(data) || '上传参考标书失败');
  }
  return data;
}
