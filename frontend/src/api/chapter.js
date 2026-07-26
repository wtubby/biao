import { apiFetch } from './client.js';

export function detectAiCliches(projectId, chapterId, content) {
  return apiFetch(`/projects/${projectId}/chapters/${chapterId}/detect-ai-cliches`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  });
}

export function saveChapterContent(projectId, chapterId, content) {
  return apiFetch(`/projects/${projectId}/chapters/${chapterId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ generated_content: content }),
  });
}

export function reviewChapter(projectId, chapterId) {
  return apiFetch(`/projects/${projectId}/chapters/${chapterId}/review`, { method: 'POST' });
}

export function regenerateChapter(projectId, chapterId) {
  return apiFetch(`/projects/${projectId}/chapters/${chapterId}/regenerate`, { method: 'POST' });
}

export function selectionRewrite(projectId, chapterId, body) {
  return apiFetch(`/projects/${projectId}/chapters/${chapterId}/selection-rewrite`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export function fetchChapterVersions(projectId, chapterId) {
  return apiFetch(`/projects/${projectId}/chapters/${chapterId}/versions`);
}

export function compareChapterVersions(projectId, chapterId, fromVersionId, toVersionId) {
  const params = new URLSearchParams({ from_version_id: fromVersionId });
  if (toVersionId) params.set('to_version_id', toVersionId);
  return apiFetch(`/projects/${projectId}/chapters/${chapterId}/versions/compare?${params.toString()}`);
}

export function restoreChapterVersion(projectId, chapterId, versionId) {
  return apiFetch(`/projects/${projectId}/chapters/${chapterId}/versions/${versionId}/restore`, {
    method: 'POST',
  });
}
