import { useState, useEffect } from '../../globals.js';
import { Text } from '../../globals.js';
import { Icon } from '../../components/icons.jsx';
import { fetchKnowledgeItems } from '../../api/knowledge.js';

export function KnowledgeStatusBadge({ folder, projectId, refreshKey = 0 }) {
  const [status, setStatus] = useState('pending');
  const [count, setCount] = useState(0);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!folder) return undefined;

    let cancelled = false;
    let timer;

    const load = () => {
      fetchKnowledgeItems(projectId, folder)
        .then((data) => {
          if (cancelled) return;
          const nextStatus = data.status || 'pending';
          setStatus(nextStatus);
          setCount(data.count || 0);
          setError(data.error || '');
          if (nextStatus === 'processing') {
            timer = setTimeout(load, 3000);
          }
        })
        .catch(() => {});
    };

    load();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [folder, projectId, refreshKey]);

  if (status === 'processing') {
    return (
      <Text type="warning" style={{ fontSize: 12 }}>
        <Icon name="loading" size={12} style={{ verticalAlign: '-2px', marginRight: 4 }} />
        处理中...
      </Text>
    );
  }
  if (status === 'failed') {
    return (
      <Text type="danger" style={{ fontSize: 12 }} title={error || undefined}>
        <Icon name="warning" size={12} style={{ verticalAlign: '-2px', marginRight: 4 }} />
        处理失败{error ? `：${error}` : ''}
      </Text>
    );
  }
  if (count > 0) {
    return (
      <Text type="success" style={{ fontSize: 12 }}>
        <Icon name="success" size={12} style={{ verticalAlign: '-2px', marginRight: 4 }} />
        已提取 {count} 个条目
      </Text>
    );
  }
  return (
    <Text type="secondary" style={{ fontSize: 12 }}>
      <Icon name="pending" size={12} style={{ verticalAlign: '-2px', marginRight: 4 }} />
      未处理
    </Text>
  );
}
