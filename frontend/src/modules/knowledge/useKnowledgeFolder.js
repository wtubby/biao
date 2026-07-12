import { useState, useCallback } from '../../globals.js';
import { message } from '../../globals.js';
import {
  deleteKnowledgeItem as apiDeleteItem,
  fetchKnowledgeItems,
  processKnowledgeFolder as apiProcessFolder,
} from '../../api/knowledge.js';

export function useKnowledgeFolder(projectId) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [folder, setFolder] = useState('');
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState('pending');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const loadItems = useCallback(async (folderPath) => {
    if (!folderPath) return;
    setLoading(true);
    try {
      const data = await fetchKnowledgeItems(projectId, folderPath);
      setItems(data.items || []);
      setStatus(data.status || 'pending');
      setError(data.error || '');
    } catch (e) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  const openDrawer = useCallback((folderPath) => {
    setFolder(folderPath);
    setDrawerOpen(true);
    loadItems(folderPath);
  }, [loadItems]);

  const closeDrawer = useCallback(() => setDrawerOpen(false), []);

  const processFolder = useCallback(async (folderPath) => {
    if (!folderPath) return;
    try {
      await apiProcessFolder(projectId, folderPath);
      message.success('知识条目提取任务已启动');
      setStatus('processing');
      setError('');
      setTimeout(() => loadItems(folderPath), 3000);
    } catch (e) {
      message.error(e.message);
    }
  }, [projectId, loadItems]);

  const deleteItem = useCallback(async (itemId) => {
    try {
      await apiDeleteItem(itemId);
      loadItems(folder);
    } catch (e) {
      message.error(e.message);
    }
  }, [folder, loadItems]);

  return {
    drawerOpen,
    folder,
    items,
    status,
    error,
    loading,
    openDrawer,
    closeDrawer,
    processFolder,
    deleteItem,
  };
}
