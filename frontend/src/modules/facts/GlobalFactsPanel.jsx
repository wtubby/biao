import {
  useState, useEffect, useCallback,
  Card, Button, Input, Tag, Space, message, Spin, Popconfirm, Alert, Text,
} from '../../globals.js';

import { apiFetch } from '../../api/client.js';
import { Icon } from '../../components/icons.jsx';

function GlobalFactsPanel({ projectId }) {
  const [facts, setFacts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState(null);
  const [editTitle, setEditTitle] = useState('');
  const [editContent, setEditContent] = useState('');
  const [saving, setSaving] = useState(false);

  const loadFacts = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiFetch(`/projects/${projectId}/facts`);
      setFacts(data);
    } catch (e) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => { loadFacts(); }, [loadFacts]);

  const startEdit = (fact) => {
    setEditingId(fact.id);
    setEditTitle(fact.title);
    setEditContent(fact.content || '');
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await apiFetch(`/facts/${editingId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: editTitle, content: editContent }),
      });
      message.success('已保存');
      setEditingId(null);
      loadFacts();
    } catch (e) {
      message.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleAdd = async () => {
    try {
      await apiFetch(`/projects/${projectId}/facts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: '新分组', content: '' }),
      });
      loadFacts();
    } catch (e) {
      message.error(e.message);
    }
  };

  const handleDelete = async (id) => {
    try {
      await apiFetch(`/facts/${id}`, { method: 'DELETE' });
      loadFacts();
    } catch (e) {
      message.error(e.message);
    }
  };

  const moveFact = async (index, direction) => {
    const target = index + direction;
    if (target < 0 || target >= facts.length) return;
    const next = [...facts];
    [next[index], next[target]] = [next[target], next[index]];
    const orders = next.map((f, i) => ({ id: f.id, sort_order: i }));
    try {
      await apiFetch(`/projects/${projectId}/facts/reorder`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ orders }),
      });
      setFacts(next.map((f, i) => ({ ...f, sort_order: i })));
    } catch (e) {
      message.error(e.message);
    }
  };

  return (
    <Card
      title={(
        <Space>
          全局事实变量
          <Tag>可选</Tag>
        </Space>
      )}
      className="section-card"
      variant="borderless"
      extra={<Button type="primary" size="small" onClick={handleAdd}>+ 新增分组</Button>}
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="本步骤为可选"
        description="工程名称、电压等级、工期等核心参数请在「确认评分项」中维护。此处仅补充可扩展事实分组（人名、品牌、关键数字等），生成正文时注入提示词。不需要时可直接点击底部「跳过，进入大纲」。"
      />
      <Spin spinning={loading}>
        {facts.length === 0 && !loading ? (
          <div className="facts-empty-state">
            <Text type="secondary">暂无事实分组。可新增，或跳过本步骤继续大纲策划。</Text>
          </div>
        ) : null}
        {facts.map((fact, index) => (
          <Card
            key={fact.id}
            size="small"
            style={{ marginBottom: 12 }}
            title={<Text strong>{fact.title}</Text>}
            extra={(
              <Space size="small">
                <Button type="link" size="small" disabled={index === 0} onClick={() => moveFact(index, -1)}>
                  <Icon name="chevronUp" size={14} />
                </Button>
                <Button type="link" size="small" disabled={index === facts.length - 1} onClick={() => moveFact(index, 1)}>
                  <Icon name="chevronDown" size={14} />
                </Button>
                <Button type="link" size="small" onClick={() => startEdit(fact)}>编辑</Button>
                <Popconfirm title="确定删除此分组？" onConfirm={() => handleDelete(fact.id)}>
                  <Button type="link" size="small" danger>删除</Button>
                </Popconfirm>
              </Space>
            )}
          >
            {editingId === fact.id ? (
              <div>
                <Input
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  style={{ marginBottom: 8 }}
                  placeholder="分组标题"
                />
                <Input.TextArea
                  value={editContent}
                  onChange={(e) => setEditContent(e.target.value)}
                  autoSize={{ minRows: 3, maxRows: 20 }}
                  style={{ marginBottom: 8 }}
                />
                <Space>
                  <Button type="primary" size="small" loading={saving} onClick={handleSave}>保存</Button>
                  <Button size="small" onClick={() => setEditingId(null)}>取消</Button>
                </Space>
              </div>
            ) : (
              <pre style={{ whiteSpace: 'pre-wrap', margin: 0, fontSize: 13, color: '#555' }}>
                {fact.content || '（尚未填写）'}
              </pre>
            )}
          </Card>
        ))}
      </Spin>
    </Card>
  );
}
export { GlobalFactsPanel };
