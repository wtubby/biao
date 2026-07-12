import {
  useState, useEffect, useCallback, useMemo, useRef,
  Button, Table, Input, InputNumber, Select, Tag, Space, message,
  Alert, List, Popover, Radio, Option, Text,
} from '../../globals.js';

import { fetchParseSummary } from '../../api/parse.js';
import {
  fetchRequirements,
  updateRequirement,
  computeRequirementStats,
} from '../../api/requirements.js';

const CONFIDENCE_LEVEL_META = {
  high: { type: 'success', label: '较高' },
  medium: { type: 'warning', label: '中等' },
  low: { type: 'error', label: '偏低' },
};

function RequirementsTable({ projectId, onStatsChange, onLocateSource, activeLocateKey }) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [parseSummary, setParseSummary] = useState(null);
  const [statusFilter, setStatusFilter] = useState('all');
  const [searchText, setSearchText] = useState('');
  const [selectedRowKeys, setSelectedRowKeys] = useState([]);
  const [batchConfirming, setBatchConfirming] = useState(false);
  const focusValueRef = useRef({});

  const locateRecord = (record) => {
    if (!onLocateSource) return;
    onLocateSource({
      key: `tech-${record.id}`,
      nonce: Date.now(),
      text: record.source_text || record.requirement_title || '',
      page: record.source_page || null,
      title: record.requirement_title,
    });
  };

  const applyStats = useCallback((reqs) => {
    if (onStatsChange) onStatsChange(computeRequirementStats(reqs));
  }, [onStatsChange]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [reqs, summary] = await Promise.all([
        fetchRequirements(projectId),
        fetchParseSummary(projectId).catch(() => null),
      ]);
      setData(reqs);
      setParseSummary(summary);
      applyStats(reqs);
    } catch (e) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  }, [projectId, applyStats]);

  useEffect(() => { load(); }, [load]);

  const showConfidenceAlert = parseSummary
    && parseSummary.confidence != null
    && parseSummary.level !== 'high';

  const patchLocal = (id, fields) => {
    setData((prev) => prev.map((r) => (r.id === id ? { ...r, ...fields } : r)));
  };

  const handleUpdate = async (id, fields) => {
    let snapshot;
    setData((prev) => {
      snapshot = prev;
      const next = prev.map((r) => (r.id === id ? { ...r, ...fields } : r));
      applyStats(next);
      return next;
    });
    try {
      await updateRequirement(id, fields);
    } catch (e) {
      message.error(e.message);
      setData(snapshot);
      applyStats(snapshot);
    }
  };

  const fieldKey = (id, field) => `${id}:${field}`;

  const filteredData = useMemo(() => {
    let rows = data;
    if (statusFilter === 'pending') {
      rows = rows.filter((r) => r.status !== 'confirmed' && r.status !== 'ignored');
    } else if (statusFilter === 'confirmed') {
      rows = rows.filter((r) => r.status === 'confirmed');
    } else if (statusFilter === 'risk') {
      rows = rows.filter((r) => r.is_risk_item === 1);
    } else if (statusFilter === 'ignored') {
      rows = rows.filter((r) => r.status === 'ignored');
    }
    const q = searchText.trim().toLowerCase();
    if (q) {
      rows = rows.filter((r) => (
        (r.requirement_title || '').toLowerCase().includes(q)
        || (r.keyword || '').toLowerCase().includes(q)
        || (r.source_text || '').toLowerCase().includes(q)
      ));
    }
    return rows;
  }, [data, statusFilter, searchText]);

  const confirmRows = async (rows) => {
    const targets = rows.filter((r) => r.status !== 'confirmed');
    if (!targets.length) {
      message.info('没有可确认的评分项');
      return;
    }
    setBatchConfirming(true);
    const snapshot = data;
    const targetIds = new Set(targets.map((r) => r.id));
    const next = data.map((r) => (targetIds.has(r.id) ? { ...r, status: 'confirmed' } : r));
    setData(next);
    applyStats(next);
    try {
      await Promise.all(targets.map((r) => updateRequirement(r.id, { status: 'confirmed' })));
      message.success(`已确认 ${targets.length} 项`);
      setSelectedRowKeys((prev) => prev.filter((id) => !targetIds.has(id)));
    } catch (e) {
      message.error(e.message);
      setData(snapshot);
      applyStats(snapshot);
    } finally {
      setBatchConfirming(false);
    }
  };

  const handleBatchConfirm = () => {
    const rows = data.filter((r) => selectedRowKeys.includes(r.id));
    confirmRows(rows);
  };

  const handleConfirmFiltered = () => confirmRows(filteredData);

  const columns = [
    {
      title: '评分项名称',
      dataIndex: 'requirement_title',
      width: 240,
      render: (text, record) => (
        <Space size={4} wrap>
          {record.is_risk_item === 1 && <Tag color="red">刚性</Tag>}
          <Input
            value={text}
            size="small"
            style={{ minWidth: 140, flex: 1 }}
            onFocus={(e) => { focusValueRef.current[fieldKey(record.id, 'title')] = e.target.value; }}
            onChange={(e) => patchLocal(record.id, { requirement_title: e.target.value })}
            onBlur={(e) => {
              const key = fieldKey(record.id, 'title');
              if (e.target.value !== focusValueRef.current[key]) {
                handleUpdate(record.id, { requirement_title: e.target.value });
              }
            }}
          />
        </Space>
      ),
    },
    {
      title: '分值',
      dataIndex: 'score_value',
      width: 90,
      render: (val, record) => (
        <InputNumber
          value={val}
          size="small"
          min={0}
          style={{ width: 76 }}
          placeholder={val == null ? '需填写' : undefined}
          status={val == null ? 'warning' : undefined}
          onFocus={() => { focusValueRef.current[fieldKey(record.id, 'score')] = val; }}
          onChange={(v) => patchLocal(record.id, { score_value: v })}
          onBlur={() => {
            const key = fieldKey(record.id, 'score');
            if (record.score_value !== focusValueRef.current[key]) {
              handleUpdate(record.id, { score_value: record.score_value });
            }
          }}
        />
      ),
    },
    {
      title: '类别',
      dataIndex: 'score_category',
      width: 120,
      render: (text, record) => (
        <Select
          value={text || '技术方案'}
          size="small"
          style={{ width: 110 }}
          onChange={(v) => handleUpdate(record.id, { score_category: v })}
        >
          <Option value="技术方案">技术方案</Option>
          <Option value="施工组织">施工组织</Option>
          <Option value="质量保证">质量保证</Option>
          <Option value="安全文明">安全文明</Option>
          <Option value="其他">其他</Option>
        </Select>
      ),
    },
    {
      title: '刚性风险',
      dataIndex: 'is_risk_item',
      width: 90,
      render: (val, record) => (
        <Select
          value={val}
          size="small"
          style={{ width: 70 }}
          onChange={(v) => handleUpdate(record.id, { is_risk_item: v })}
        >
          <Option value={0}>否</Option>
          <Option value={1}>是</Option>
        </Select>
      ),
    },
    {
      title: '关键词',
      dataIndex: 'keyword',
      width: 150,
      render: (text, record) => (
        <Input
          value={text || ''}
          size="small"
          placeholder="逗号分隔"
          onFocus={(e) => { focusValueRef.current[fieldKey(record.id, 'keyword')] = e.target.value; }}
          onChange={(e) => patchLocal(record.id, { keyword: e.target.value })}
          onBlur={(e) => {
            const key = fieldKey(record.id, 'keyword');
            if (e.target.value !== (focusValueRef.current[key] || '')) {
              handleUpdate(record.id, { keyword: e.target.value });
            }
          }}
        />
      ),
    },
    {
      title: '页码',
      dataIndex: 'source_page',
      width: 64,
      align: 'center',
      render: (page, record) => (
        page ? (
          <Button
            type="link"
            size="small"
            className="score-locate-link"
            onClick={(e) => { e.stopPropagation(); locateRecord(record); }}
          >
            {page}
          </Button>
        ) : <Text type="secondary">—</Text>
      ),
    },
    {
      title: '原文上下文',
      dataIndex: 'source_text',
      width: 200,
      render: (text, record) => {
        if (!text) return <Text type="secondary">—</Text>;
        const preview = text.length > 40 ? `${text.slice(0, 40)}…` : text;
        return (
          <Popover
            title="原文上下文（点击定位到招标文件）"
            trigger="hover"
            styles={{ root: { maxWidth: 520 } }}
            content={(
              <div>
                <div style={{ maxHeight: 240, overflowY: 'auto', whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.6, marginBottom: 8 }}>
                  {text}
                </div>
                {onLocateSource && (
                  <Button type="primary" size="small" block onClick={() => locateRecord(record)}>
                    在原文中定位
                  </Button>
                )}
              </div>
            )}
          >
            <Button
              type="link"
              size="small"
              className="score-locate-link"
              style={{ padding: 0, height: 'auto', textAlign: 'left' }}
              onClick={(e) => { e.stopPropagation(); locateRecord(record); }}
            >
              <span className="source-text">{preview}</span>
            </Button>
          </Popover>
        );
      },
    },
    {
      title: '操作',
      width: 120,
      fixed: 'right',
      render: (_, record) => (
        <Space>
          {record.status !== 'confirmed' && (
            <Button size="small" type="primary" onClick={() => handleUpdate(record.id, { status: 'confirmed' })}>确认</Button>
          )}
          {record.status !== 'ignored' && record.is_risk_item !== 1 && (
            <Button size="small" onClick={() => handleUpdate(record.id, { status: 'ignored' })}>忽略</Button>
          )}
          {record.status === 'confirmed' && <Tag color="green">已确认</Tag>}
          {record.status === 'ignored' && <Tag>已忽略</Tag>}
        </Space>
      ),
    },
  ];

  const pendingInFilter = filteredData.filter((r) => r.status !== 'confirmed' && r.status !== 'ignored').length;

  return (
    <>
      {showConfidenceAlert && (
        <Alert
          type={CONFIDENCE_LEVEL_META[parseSummary.level]?.type || 'warning'}
          showIcon
          style={{ marginBottom: 16 }}
          message={`解析可信度 ${CONFIDENCE_LEVEL_META[parseSummary.level]?.label || '待评估'}（${Math.round(parseSummary.confidence * 100)}%）`}
          description={(
            <List
              size="small"
              dataSource={parseSummary.warnings || []}
              locale={{ emptyText: '请人工核对评分项与全局参数后再进入大纲' }}
              renderItem={(item) => <List.Item>{item}</List.Item>}
            />
          )}
        />
      )}
      <div className="requirements-toolbar">
        <Input.Search
          placeholder="搜索评分项名称、关键词或原文"
          allowClear
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          style={{ width: 280 }}
        />
        <Radio.Group value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} size="small">
          <Radio.Button value="all">全部 ({data.length})</Radio.Button>
          <Radio.Button value="pending">待确认 ({data.filter((r) => r.status !== 'confirmed' && r.status !== 'ignored').length})</Radio.Button>
          <Radio.Button value="confirmed">已确认 ({data.filter((r) => r.status === 'confirmed').length})</Radio.Button>
          <Radio.Button value="risk">刚性风险 ({data.filter((r) => r.is_risk_item === 1).length})</Radio.Button>
          <Radio.Button value="ignored">已忽略 ({data.filter((r) => r.status === 'ignored').length})</Radio.Button>
        </Radio.Group>
        <Space>
          <Button
            size="small"
            type="primary"
            disabled={!selectedRowKeys.length}
            loading={batchConfirming}
            onClick={handleBatchConfirm}
          >
            批量确认选中
          </Button>
          <Button
            size="small"
            disabled={!pendingInFilter}
            loading={batchConfirming}
            onClick={handleConfirmFiltered}
          >
            确认当前筛选 ({pendingInFilter})
          </Button>
        </Space>
      </div>
      <Table
        columns={columns}
        dataSource={filteredData}
        rowKey="id"
        loading={loading}
        size="small"
        scroll={{ x: 1220 }}
        pagination={{ pageSize: 20, showTotal: (total) => `共 ${total} 条` }}
        rowClassName={(record) => {
          const classes = [];
          if (record.is_risk_item === 1) classes.push('risk-row');
          if (activeLocateKey === `tech-${record.id}`) classes.push('score-row-active');
          return classes.join(' ');
        }}
        rowSelection={{
          selectedRowKeys,
          onChange: setSelectedRowKeys,
          getCheckboxProps: (record) => ({
            disabled: record.status === 'confirmed',
          }),
        }}
      />
    </>
  );
}
export { RequirementsTable };
