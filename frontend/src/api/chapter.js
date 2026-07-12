import { apiFetch } from './client.js';

export function detectAiCliches(chapterId, content) {
  return apiFetch(`/chapters/${chapterId}/detect-ai-cliches`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  });
}

export function saveChapterContent(chapterId, content) {
  return apiFetch(`/chapters/${chapterId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ generated_content: content }),
  });
}

export function reviewChapter(chapterId) {
  return apiFetch(`/chapters/${chapterId}/review`, { method: 'POST' });
}

export function regenerateChapter(chapterId) {
  return apiFetch(`/chapters/${chapterId}/regenerate`, { method: 'POST' });
}

export function selectionRewrite(chapterId, body) {
  return apiFetch(`/chapters/${chapterId}/selection-rewrite`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export function fetchChapterVersions(chapterId) {
  return apiFetch(`/chapters/${chapterId}/versions`);
}

export function compareChapterVersions(chapterId, fromVersionId, toVersionId) {
  const params = new URLSearchParams({ from_version_id: fromVersionId });
  if (toVersionId) params.set('to_version_id', toVersionId);
  return apiFetch(`/chapters/${chapterId}/versions/compare?${params.toString()}`);
}

export function restoreChapterVersion(chapterId, versionId) {
  return apiFetch(`/chapters/${chapterId}/versions/${versionId}/restore`, { method: 'POST' });
}
