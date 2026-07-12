import { apiFetch, API } from './client.js';

export function getGenerationStreamUrl(projectId) {
  return `${API}/projects/${projectId}/stream`;
}

export function startBatchGenerate(projectId, resume = false) {
  const path = resume
    ? `/projects/${projectId}/generate/resume`
    : `/projects/${projectId}/generate`;
  return apiFetch(path, { method: 'POST' });
}

export function pauseBatchGenerate(projectId) {
  return apiFetch(`/projects/${projectId}/generate/pause`, { method: 'POST' });
}

export function generateChapter(projectId, chapterId) {
  return apiFetch(`/projects/${projectId}/chapters/${chapterId}/generate`, { method: 'POST' });
}
