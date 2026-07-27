import { useState } from '../../globals.js';
import {
  Button, Space, Popconfirm, Modal, Input, message, Table,
} from '../../globals.js';
import { StandardStatusBadge } from './StandardStatusBadge.jsx';
import { markSuperseded, markWithdrawn } from '../../api/standards.js';

export function StandardsTable({
  items,
  loading,
  onEdit,
  onChanged,
}) {
  const [supersedeTarget, setSupersedeTarget] = useState(null);
  const [byCode, setByCode] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleWithdrawn = async (record) => {
    try {
      await markWithdrawn(record.code);
      message.success(`已标记 ${record.raw_code || record.code} 为废止`);
      onChanged?.();
    } catch (e) {
      message.error(e.message);
    }
  };

  const handleSupersedeOk = async () => {
    if (!supersedeTarget) return;
    const next = byCode.trim();
    if (!next) {
      message.warning('请填写替代标准编号');
      return;
    }
    setSubmitting(true);
    try {
      await markSuperseded(supersedeTarget.code, next);
      message.success('已标记为被替代');
      setSupersedeTarget(null);
      setByCode('');
      onChanged?.();
    } catch (e) {
      message.error(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  const columns = [
    {
      title: '编号',
      dataIndex: 'raw_code',
      width: 140,
      render: (v, row) => v || row.code,
    },
    {
      title: '标题',
      dataIndex: 'title',
      ellipsis: true,
      render: (v) => v || '—',
    },
    {
      title: '类别',
      dataIndex: 'category',
      width: 90,
      render: (v) => v || '—',
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (v) => <StandardStatusBadge status={v} />,
    },
    {
      title: '适用领域',
      dataIndex: 'domains',
      width: 180,
      render: (domains) => (domains?.length ? domains.join('、') : '—'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 220,
      render: (_, row) => (
        <Space size={4} onClick={(e) => e.stopPropagation()}>
          <Button type="link" size="small" onClick={() => onEdit(row)}>
            编辑
          </Button>
          <Button
            type="link"
            size="small"
            onClick={() => {
              setSupersedeTarget(row);
              setByCode(row.superseded_by || '');
            }}
          >
            标记被替代
          </Button>
          <Popconfirm
            title="确认标记为废止？"
            okText="废止"
            cancelText="取消"
            onConfirm={() => handleWithdrawn(row)}
          >
            <Button type="link" size="small" danger>
              标记废止
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <>
      <Table
        className="project-list-table"
        size="middle"
        rowKey="code"
        loading={loading}
        columns={columns}
        dataSource={items}
        pagination={{ pageSize: 20, showTotal: (total) => `共 ${total} 条`, size: 'small' }}
        onRow={(row) => ({
          onClick: () => onEdit(row),
          className: 'project-list-row',
        })}
      />
      <Modal
        title="标记为被替代"
        open={!!supersedeTarget}
        onCancel={() => { setSupersedeTarget(null); setByCode(''); }}
        onOk={handleSupersedeOk}
        confirmLoading={submitting}
        okText="确认"
        cancelText="取消"
      >
        <p style={{ marginBottom: 8 }}>
          标准 {supersedeTarget?.raw_code || supersedeTarget?.code} 将被谁替代？
        </p>
        <Input
          placeholder="如 GB/T 50233-2015"
          value={byCode}
          onChange={(e) => setByCode(e.target.value)}
        />
      </Modal>
    </>
  );
}
