import {
  useState, useEffect,
  Alert, List, Space, Tag, Text,
} from '../../globals.js';

import { apiFetch } from '../../api/client.js';

function ContradictionsAlert({ projectId }) {
  const [items, setItems] = useState([]);

  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    apiFetch(`/projects/${projectId}/parse/contradictions`)
      .then((data) => {
        if (!cancelled) setItems(data.items || []);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [projectId]);

  if (!items.length) return null;

  return (
    <Alert
      type="warning"
      showIcon
      style={{ marginBottom: 16 }}
      message={`招标文件解析发现 ${items.length} 条矛盾或风险提示`}
      description={(
        <List
          size="small"
          dataSource={items}
          renderItem={(item) => (
            <List.Item>
              <Space direction="vertical" size={2}>
                <Space wrap>
                  <Tag color={item.risk_level === '高' ? 'red' : item.risk_level === '中' ? 'orange' : 'blue'}>
                    {item.risk_level || '风险'}
                  </Tag>
                  <Text strong>{item.description || '未命名矛盾'}</Text>
                </Space>
                {item.locations && <Text type="secondary">位置：{item.locations}</Text>}
                {item.suggestion && <Text type="secondary">建议：{item.suggestion}</Text>}
              </Space>
            </List.Item>
          )}
        />
      )}
    />
  );
}
export { ContradictionsAlert };
