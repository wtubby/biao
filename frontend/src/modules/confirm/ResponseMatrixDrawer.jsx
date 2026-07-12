import {
  useState, useEffect, useCallback,
  Button, Table, Tag, Space, message, Spin, Alert, Drawer, Text,
} from '../../globals.js';

import { apiFetch } from '../../api/client.js';
import { MetricCard } from '../../components/MetricCard.jsx';

function ResponseMatrixDrawer({ open, onClose, projectId }) {
  const [loading, setLoading] = useState(false);
  const [matrix, setMatrix] = useState(null);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      setMatrix(await apiFetch(`/projects/${projectId}/response-matrix`));
    } catch (e) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  const rows = matrix?.rows || [];
  const summary = matrix?.summary || {};
  const statusMeta = {
    covered: { color: 'green', text: '已覆盖' },
    partial: { color: 'orange', text: '部分覆盖' },
    bound_pending: { color: 'blue', text: '已绑定待生成' },
    unbound: { color: 'red', text: '未绑定' },
    ignored: { color: 'default', text: '已忽略' },
  };

  const columns = [
    {
      title: '评分项',
      dataIndex: 'title',
      width: 260,
      render: (text, record) => (
        <Space direction="vertical" size={2}>
          <Space wrap>
            {record.is_risk_item === 1 && <Tag color="red">刚性</Tag>}
            <Text strong>{text}</Text>
          </Space>
          <Text type="secondary">{record.score_category || '未分类'} · {record.score_value ?? '—'} 分</Text>
        </Space>
      ),
    },
    {
      title: '响应状态',
      dataIndex: 'status',
      width: 120,
      render: (status) => {
        const meta = statusMeta[status] || { color: 'default', text: status || '未知' };
        return <Tag color={meta.color}>{meta.text}</Tag>;
      },
    },
    {
      title: '绑定章节与证据',
      dataIndex: 'bound_chapters',
      render: (chapters) => {
        if (!chapters?.length) return <Text type="danger">尚未绑定到叶子章节</Text>;
        return (
          <Space direction="vertical" size={6}>
            {chapters.map((ch) => (
              <div key={ch.id}>
                <Space wrap>
                  <Tag color={ch.review_status === 'green' ? 'green' : ch.review_status === 'yellow' ? 'orange' : 'default'}>
                    {ch.review_status || 'init'}
                  </Tag>
                  <Text>{ch.title}</Text>
                  {ch.matched_keywords?.length ? (
                    <Text type="secondary">命中：{ch.matched_keywords.slice(0, 4).join('、')}</Text>
                  ) : (
                    <Text type="warning">未命中关键词</Text>
                  )}
                </Space>
                {ch.evidence && <div className="matrix-evidence">{ch.evidence}</div>}
              </div>
            ))}
          </Space>
        );
      },
    },
    {
      title: '缺失要素',
      dataIndex: 'missing_elements',
      width: 180,
      render: (items) => items?.length
        ? <Text type="danger">{items.join('、')}</Text>
        : <Text type="secondary">—</Text>,
    },
  ];

  return (
    <Drawer
      title="评分项响应矩阵"
      open={open}
      onClose={onClose}
      width={980}
      destroyOnClose
      extra={<Button size="small" onClick={load} loading={loading}>刷新</Button>}
    >
      <Spin spinning={loading}>
        {matrix && (
          <>
            <div className="metric-cards matrix-summary">
              <MetricCard accent="blue" label="评分项总数" value={summary.total || 0} sub={`刚性 ${summary.risk_total || 0} 项`} />
              <MetricCard accent="green" label="已覆盖" value={summary.covered || 0} sub="绑定章节且正文命中" />
              <MetricCard accent="red" label="未充分覆盖" value={(summary.unbound || 0) + (summary.partial || 0) + (summary.bound_pending || 0)} sub={`刚性未覆盖 ${summary.risk_uncovered || 0} 项`} />
            </div>
            {matrix.contradictions?.length > 0 && (
              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 12 }}
                message={`解析阶段存在 ${matrix.contradictions.length} 条招标文件矛盾，请结合响应矩阵人工复核。`}
              />
            )}
            <Table
              rowKey="requirement_id"
              columns={columns}
              dataSource={rows}
              size="small"
              pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 条` }}
              scroll={{ x: 920 }}
            />
          </>
        )}
        {!loading && !matrix && <Text type="secondary">暂无响应矩阵数据</Text>}
      </Spin>
    </Drawer>
  );
}
export { ResponseMatrixDrawer };
