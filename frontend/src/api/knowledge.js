import { apiFetch } from './client.js';

export function fetchKnowledgeFolders(projectId) {
  return apiFetch(`/projects/${projectId}/knowledge-folders`);
}

export function fetchKnowledgeItems(projectId, folderPath) {
  return apiFetch(
    `/projects/${projectId}/knowledge/items?folder_path=${encodeURIComponent(folderPath)}`,
  );
}

export function processKnowledgeFolder(projectId, folderPath) {
  return apiFetch(`/projects/${projectId}/knowledge/process-folder`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ folder_path: folderPath }),
  });
}

export function deleteKnowledgeItem(itemId) {
  return apiFetch(`/knowledge-items/${itemId}`, { method: 'DELETE' });
}
