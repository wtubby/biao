import {
  useState, useEffect, useCallback, useMemo,
  Button, Table, Input, Dropdown, Space, message, Spin, Popconfirm, Progress, Tooltip,
  Title, Text,
} from '../../globals.js';

import { apiFetch } from '../../api/client.js';
import { downloadFromApi } from '../../api/download.js';
import { PageHeader, getWorkflowProgressByStatus } from '../../components/layout.jsx';
import { Icon } from '../../components/icons.jsx';
import { PROJECT_STATUS_LABELS, PROJECT_STATUS_BADGES } from '../../constants/project.js';

const STATUS_FILTER_ITEMS = [
  { key: 'all', label: '全部' },
  ...Object.keys(PROJECT_STATUS_LABELS).map((key) => ({
    key,
    label: PROJECT_STATUS_LABELS[key],
  })),
];

function projectSummary(p) {
  const parts = [p.project_type, p.voltage_level, p.capacity, p.location].filter(Boolean);
  return parts.length ? parts.join(' · ') : '尚未填写工程信息';
}

function ProjectList({ onSelect, onCreate }) {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [selectedRowKeys, setSelectedRowKeys] = useState([]);
  const [batchDeleting, setBatchDeleting] = useState(false);
  const [downloadingId, setDownloadingId] = useState(null);
  const [pageSize, setPageSize] = useState(10);
  const [currentPage, setCurrentPage] = useState(1);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setProjects(await apiFetch('/projects'));
    } catch (e) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const filteredProjects = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return projects.filter((p) => {
      if (statusFilter !== 'all' && p.status !== statusFilter) return false;
      if (!keyword) return true;
      const haystack = [
        p.name,
        p.project_type,
        p.voltage_level,
        p.capacity,
        p.location,
      ].filter(Boolean).join(' ').toLowerCase();
      return haystack.includes(keyword);
    });
  }, [projects, search, statusFilter]);

  useEffect(() => {
    setCurrentPage(1);
  }, [search, statusFilter]);

  const handleCreate = async () => {
    setCreating(true);
    try {
      const p = await apiFetch('/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: '新项目' }),
      });
      onCreate(p);
    } catch (e) {
      message.error(e.message);
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (id) => {
    try {
      await apiFetch(`/projects/${id}`, { method: 'DELETE' });
      message.success('已删除');
      setSelectedRowKeys((keys) => keys.filter((k) => k !== id));
      load();
    } catch (err) {
      message.error(err.message);
    }
  };

  const handleBatchDelete = async () => {
    if (!selectedRowKeys.length) return;
    setBatchDeleting(true);
    try {
      await Promise.all(
        selectedRowKeys.map((id) => apiFetch(`/projects/${id}`, { method: 'DELETE' })),
      );
      message.success(`已删除 ${selectedRowKeys.length} 个项目`);
      setSelectedRowKeys([]);
      load();
    } catch (err) {
      message.error(err.message);
    } finally {
      setBatchDeleting(false);
    }
  };

  const handleDownload = async (project, e) => {
    e.stopPropagation();
    if (project.status !== 'done') return;
    setDownloadingId(project.id);
    try {
      await downloadFromApi(
        `/projects/${project.id}/export`,
        `${project.name || project.id}.docx`,
      );
      message.success('Word 文档已导出');
    } catch (err) {
      message.error(err.message);
    } finally {
      setDownloadingId(null);
    }
  };

  const statusFilterLabel = statusFilter === 'all'
    ? '状态'
    : (PROJECT_STATUS_LABELS[statusFilter] || '状态');

  const columns = [
    {
      title: '文件名称',
      dataIndex: 'name',
      ellipsis: true,
      render: (name) => (
        <span className="project-list-name">{name || '未命名项目'}</span>
      ),
    },
    {
      title: (
        <Dropdown
          menu={{
            items: STATUS_FILTER_ITEMS,
            selectedKeys: [statusFilter],
            onClick: ({ key }) => setStatusFilter(key),
          }}
          trigger={['click']}
        >
          <button type="button" className="project-list-status-filter">
            {statusFilterLabel}
            <Icon name="chevronDown" size={12} />
          </button>
        </Dropdown>
      ),
      dataIndex: 'status',
      width: 100,
      render: (status) => {
        const st = {
          badge: PROJECT_STATUS_BADGES[status] || 'default',
          text: PROJECT_STATUS_LABELS[status] || status,
        };
        return (
          <span className={`project-status-badge project-status-badge--${st.badge}`}>
            {st.text}
          </span>
        );
      },
    },
    {
      title: '进度',
      dataIndex: 'status',
      width: 140,
      render: (status) => {
        const wf = getWorkflowProgressByStatus(status);
        return (
          <div className="project-list-progress">
            <Progress
              percent={wf.percent}
              size="small"
              showInfo={false}
              strokeColor={status === 'done' ? '#16a34a' : '#2563eb'}
            />
            <span className="project-list-progress-label">{wf.label}</span>
          </div>
        );
      },
    },
    {
      title: '工程摘要',
      key: 'summary',
      ellipsis: true,
      render: (_, p) => (
        <span className="project-list-summary" title={projectSummary(p)}>
          {projectSummary(p)}
        </span>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 200,
      render: (t) => (t ? dayjs(t).format('YYYY-MM-DD HH:mm') : '—'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_, p) => (
        <Space size={4} onClick={(e) => e.stopPropagation()}>
          <Tooltip title={p.status === 'done' ? '下载 Word' : '生成完成后可下载'}>
            <Button
              type="link"
              size="small"
              disabled={p.status !== 'done'}
              loading={downloadingId === p.id}
              onClick={(e) => handleDownload(p, e)}
            >
              下载
            </Button>
          </Tooltip>
          <Popconfirm
            title="确认删除此项目？"
            okText="删除"
            cancelText="取消"
            onConfirm={() => handleDelete(p.id)}
          >
            <Button type="link" size="small" danger>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const showEmpty = !loading && projects.length === 0;
  const showFilteredEmpty = !loading && projects.length > 0 && filteredProjects.length === 0;

  return (
    <div className="project-list-page">
      <PageHeader
        title="项目列表"
        description="管理电力工程 EPC 招投标技术方案生成任务"
      />

      <div className="project-panel">
        <div className="project-list-toolbar">
          <Space size={8}>
            <Button
              type="primary"
              className="btn-cta-primary"
              loading={creating}
              onClick={handleCreate}
            >
              新建项目
            </Button>
            <Popconfirm
              title={`确认删除选中的 ${selectedRowKeys.length} 个项目？`}
              okText="删除"
              cancelText="取消"
              disabled={!selectedRowKeys.length}
              onConfirm={handleBatchDelete}
            >
              <Button disabled={!selectedRowKeys.length} loading={batchDeleting}>
                批量删除
              </Button>
            </Popconfirm>
          </Space>
          <Input
            className="project-list-search"
            allowClear
            maxLength={50}
            placeholder="搜索项目名称或工程信息…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="搜索项目"
          />
        </div>

        <div className="project-list-body">
          <Spin spinning={loading}>
            {showEmpty ? (
              <div className="empty-projects">
                <div className="empty-projects-icon">
                  <Icon name="clipboard" size={48} />
                </div>
                <Title level={4} type="secondary">暂无项目</Title>
                <Text type="secondary">点击「新建项目」上传招标文件，开始生成技术方案</Text>
                <div style={{ marginTop: 16 }}>
                  <Button
                    type="primary"
                    className="btn-cta-primary"
                    loading={creating}
                    onClick={handleCreate}
                  >
                    新建项目
                  </Button>
                </div>
              </div>
            ) : (
              <Table
                className="project-list-table"
                size="middle"
                rowKey="id"
                columns={columns}
                dataSource={filteredProjects}
                locale={{ emptyText: showFilteredEmpty ? '没有匹配的项目' : '暂无数据' }}
                rowSelection={{
                  selectedRowKeys,
                  onChange: setSelectedRowKeys,
                  columnWidth: 40,
                }}
                pagination={{
                  current: currentPage,
                  pageSize,
                  total: filteredProjects.length,
                  showSizeChanger: true,
                  pageSizeOptions: ['10', '20'],
                  showTotal: (total) => `共 ${total} 条`,
                  size: 'small',
                  onChange: (page, size) => {
                    setCurrentPage(page);
                    setPageSize(size);
                  },
                }}
                onRow={(p) => ({
                  onClick: () => onSelect(p),
                  className: 'project-list-row',
                })}
              />
            )}
          </Spin>
        </div>
      </div>
    </div>
  );
}

export { ProjectList };
