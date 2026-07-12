import { useState, useEffect } from '../../globals.js';
import { Button } from '../../globals.js';
import { fetchKnowledgeItems } from '../../api/knowledge.js';
import { KnowledgeStatusBadge } from './KnowledgeStatusBadge.jsx';

export function KnowledgeFolderActions({
  folder,
  projectId,
  onProcess,
  onView,
  style,
}) {
  const [refreshKey, setRefreshKey] = useState(0);
  const [status, setStatus] = useState('pending');

  useEffect(() => {
    if (!folder) return;
    fetchKnowledgeItems(projectId, folder)
      .then((data) => setStatus(data.status || 'pending'))
      .catch(() => {});
  }, [folder, projectId, refreshKey]);

  if (!folder) return null;

  const handleProcess = (e) => {
    e.stopPropagation();
    onProcess(folder);
    setStatus('processing');
    setRefreshKey((k) => k + 1);
  };

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6, paddingLeft: '28%', ...style }}>
      <KnowledgeStatusBadge folder={folder} projectId={projectId} refreshKey={refreshKey} />
      {status === 'failed' ? (
        <Button type="link" size="small" danger onClick={handleProcess}>
          重试
        </Button>
      ) : (
        <Button type="link" size="small" onClick={handleProcess}>
          提取条目
        </Button>
      )}
      <Button
        type="link"
        size="small"
        onClick={(e) => { e.stopPropagation(); onView(folder); }}
      >
        查看条目
      </Button>
    </div>
  );
}
