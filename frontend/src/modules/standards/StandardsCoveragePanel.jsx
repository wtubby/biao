import { useCallback, useEffect, useState } from '../../globals.js';
import { Alert, Table, Tag, message } from '../../globals.js';
import { fetchStandardCoverage } from '../../api/standards.js';

const ACTIVE_THRESHOLD = 5;

export function StandardsCoveragePanel({ refreshKey = 0 }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchStandardCoverage();
      setRows(data.domains || []);
    } catch (e) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load, refreshKey]);

  const columns = [
    {
      title: '领域',
      dataIndex: 'label',
      render: (v, row) => v || row.domain,
    },
    {
      title: '现行 (active)',
      dataIndex: 'active',
      width: 140,
      render: (v) => (
        <Tag color={v < ACTIVE_THRESHOLD ? 'error' : 'success'}>{v}</Tag>
      ),
    },
    {
      title: '草稿 (draft)',
      dataIndex: 'draft',
      width: 120,
      render: (v) => <Tag>{v}</Tag>,
    },
    {
      title: '提示',
      key: 'hint',
      render: (_, row) => (
        row.active < ACTIVE_THRESHOLD
          ? <span style={{ color: '#cf1322' }}>需要补录（现行 &lt; {ACTIVE_THRESHOLD}）</span>
          : '—'
      ),
    },
  ];

  const needFill = rows.filter((r) => r.active < ACTIVE_THRESHOLD);

  return (
    <div style={{ marginBottom: 16 }}>
      {needFill.length > 0 && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message={`${needFill.length} 个领域现行标准不足 ${ACTIVE_THRESHOLD} 条，建议补录`}
        />
      )}
      <Table
        size="small"
        rowKey="domain"
        loading={loading}
        columns={columns}
        dataSource={rows}
        pagination={false}
      />
    </div>
  );
}
