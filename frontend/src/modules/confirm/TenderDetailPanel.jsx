import {
  useState, useEffect, useCallback, useMemo,
  Button, Form, Input, InputNumber, Select, Table, Tabs, Tag, Space,
  message, Spin, Alert, Row, Col, Radio, Option, Text,
} from '../../globals.js';

import { apiFetch } from '../../api/client.js';
import { fetchTenderDetail, updateTenderDetail } from '../../api/tenderDetail.js';
import { fetchDomains } from '../../api/domains.js';
import { PROJECT_TYPES, ENGINEERING_DOMAINS, CONTRACT_MODES } from '../../constants/project.js';
import { ContradictionsAlert } from './ContradictionsAlert.jsx';
import { RequirementsTable } from './RequirementsTable.jsx';
import { fetchParseSummary } from '../../api/parse.js';

const QUALIFICATION_TABS = [
  { key: '资格性审查', label: '资格性审查' },
  { key: '符合性审查', label: '符合性审查' },
  { key: '废标项', label: '废标项' },
];

const EDIT_TIP = 'AI 分析结果可手动修改。请逐条对照招标文件原文核对、补充遗漏条款、修正表述偏差，避免影响最终生成结果。';

function SectionTitle({ children }) {
  return (
    <div className="tender-section-title">
      <div className="tender-section-bar" />
      <div className="tender-section-heading">{children}</div>
    </div>
  );
}

function EditTip() {
  return (
    <div className="tender-edit-tip">
      <span className="tender-edit-tip-star">*</span>
      <span>{EDIT_TIP}</span>
    </div>
  );
}

function filterQualificationItems(items, tab) {
  if (tab === '资格性审查') {
    return items.filter((i) => (i.item_label || '').includes('资格'));
  }
  if (tab === '符合性审查') {
    return items.filter((i) => (i.item_label || '').includes('符合'));
  }
  if (tab === '废标项') {
    return items.filter(
      (i) => !(i.item_label || '').includes('资格') && !(i.item_label || '').includes('符合'),
    );
  }
  return items;
}

function TenderDetailPanel({
  projectId, project, onProjectSaved, onStatsChange, onLocateSource, activeLocateKey,
}) {
  const [loading, setLoading] = useState(true);
  const [savingSection, setSavingSection] = useState('');
  const [detail, setDetail] = useState(null);
  const [parseSummary, setParseSummary] = useState(null);
  const [qualTab, setQualTab] = useState('废标项');
  const [scoreTab, setScoreTab] = useState('tech');
  const [domainOptions, setDomainOptions] = useState(
    ENGINEERING_DOMAINS.map((d) => ({ key: d, label: d })),
  );
  const [editingQualIndexes, setEditingQualIndexes] = useState(() => new Set());
  const [noticeForm] = Form.useForm();
  const bidDomain = Form.useWatch('bid_domain', noticeForm);
  const voltageRequired = !bidDomain || bidDomain === '电力工程';

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [data, summary, domainsRes] = await Promise.all([
        fetchTenderDetail(projectId),
        fetchParseSummary(projectId).catch(() => null),
        fetchDomains().catch(() => null),
      ]);
      setDetail(data);
      setParseSummary(summary);
      if (domainsRes?.domains?.length) {
        setDomainOptions(domainsRes.domains);
      }
      noticeForm.setFieldsValue({
        ...data.notice,
        blind_bid: data.notice?.blind_bid === true ? 'true' : data.notice?.blind_bid === false ? 'false' : undefined,
        sme_targeted: data.notice?.sme_targeted || undefined,
      });
    } catch (e) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  }, [projectId, noticeForm]);

  useEffect(() => { load(); }, [load]);

  const saveNotice = async () => {
    try {
      const values = await noticeForm.validateFields();
      setSavingSection('notice');
      const body = {
        notice: {
          ...values,
          blind_bid: values.blind_bid === 'true' ? true : values.blind_bid === 'false' ? false : null,
        },
      };
      const updated = await updateTenderDetail(projectId, body);
      setDetail(updated);
      // 以服务端 Project 为准刷新门禁字段（含 duration_days / target_pages 解析结果）
      if (onProjectSaved) {
        const refreshed = await apiFetch(`/projects/${projectId}`);
        onProjectSaved(refreshed);
      }
      message.success('工程信息与投标人须知已保存');
    } catch (e) {
      if (e.message) message.error(e.message);
    } finally {
      setSavingSection('');
    }
  };

  const saveTextSection = async (field) => {
    setSavingSection(field);
    try {
      const payload = field === 'bid_reference_catalog'
        ? { bid_reference_catalog: detail.bid_reference_catalog }
        : { [field]: detail[field] };
      const updated = await updateTenderDetail(projectId, payload);
      setDetail(updated);
      message.success('已保存');
    } catch (e) {
      message.error(e.message);
    } finally {
      setSavingSection('');
    }
  };

  const saveQualification = async () => {
    setSavingSection('qualification');
    try {
      const updated = await updateTenderDetail(projectId, {
        qualification_items: detail.qualification_items,
      });
      setDetail(updated);
      message.success('资格审查已保存');
    } catch (e) {
      message.error(e.message);
    } finally {
      setSavingSection('');
    }
  };

  const saveCommerceScores = async () => {
    setSavingSection('commerce_scores');
    try {
      const updated = await updateTenderDetail(projectId, {
        commerce_scores: detail.commerce_scores,
      });
      setDetail(updated);
      message.success('商务评分已保存');
    } catch (e) {
      message.error(e.message);
    } finally {
      setSavingSection('');
    }
  };

  const qualItems = detail?.qualification_items || [];
  const commerceScores = detail?.commerce_scores || [];

  // 废标项数量 = 总数 − 资格性 − 符合性
  const qualTabCounts = useMemo(() => {
    const ziGe = filterQualificationItems(qualItems, '资格性审查').length;
    const fuHe = filterQualificationItems(qualItems, '符合性审查').length;
    return {
      资格性审查: ziGe,
      符合性审查: fuHe,
      废标项: Math.max(0, qualItems.length - ziGe - fuHe),
    };
  }, [qualItems]);

  const qualDisplay = useMemo(() => {
    const filtered = filterQualificationItems(qualItems, qualTab);
    return filtered.map((item) => ({
      ...item,
      _origIndex: qualItems.findIndex(
        (q) => q.seq === item.seq && q.description === item.description && q.item_label === item.item_label,
      ),
    }));
  }, [qualItems, qualTab]);

  const updateQualItem = (origIndex, patch) => {
    setDetail((d) => {
      const next = [...(d.qualification_items || [])];
      if (origIndex < 0 || origIndex >= next.length) return d;
      next[origIndex] = { ...next[origIndex], ...patch };
      return { ...d, qualification_items: next };
    });
  };

  const locateQual = (record) => {
    if (!onLocateSource) return;
    const text = (record.source_text || record.description || record.item_label || '').trim();
    if (!text) return;
    onLocateSource({
      key: `qual-${record._origIndex}`,
      nonce: Date.now(),
      text,
      page: record.source_page || null,
      title: record.item_label,
    });
  };

  const startEditQual = (origIndex, e) => {
    e?.stopPropagation();
    setEditingQualIndexes((prev) => new Set(prev).add(origIndex));
  };

  const finishEditQual = (origIndex, e) => {
    e?.stopPropagation();
    setEditingQualIndexes((prev) => {
      const next = new Set(prev);
      next.delete(origIndex);
      return next;
    });
  };

  const qualColumns = [
    { title: '序号', dataIndex: 'seq', width: 72, render: (v, _, idx) => v ?? idx + 1 },
    {
      title: '废标项',
      dataIndex: 'item_label',
      width: 140,
      render: (text, record) => {
        if (editingQualIndexes.has(record._origIndex)) {
          return (
            <Input
              value={text}
              size="small"
              onClick={(e) => e.stopPropagation()}
              onChange={(e) => updateQualItem(record._origIndex, { item_label: e.target.value })}
            />
          );
        }
        return <span className="qual-item-label">{text || '—'}</span>;
      },
    },
    {
      title: '具体表现',
      dataIndex: 'description',
      render: (text, record) => {
        const sourceText = (record.source_text || '').trim();
        const desc = (text || '').trim();
        const showContrast = sourceText && desc && sourceText !== desc;

        if (editingQualIndexes.has(record._origIndex)) {
          return (
            <div className="qual-edit-fields" onClick={(e) => e.stopPropagation()}>
              <div className="qual-edit-label">说明</div>
              <Input.TextArea
                value={text}
                autoSize={{ minRows: 1, maxRows: 4 }}
                placeholder="可读说明（可与原文相同）"
                onChange={(e) => updateQualItem(record._origIndex, { description: e.target.value })}
              />
              <div className="qual-edit-label">原文摘录（定位用）</div>
              <Input.TextArea
                value={record.source_text || ''}
                autoSize={{ minRows: 1, maxRows: 4 }}
                placeholder="招标文件逐字原文"
                onChange={(e) => updateQualItem(record._origIndex, { source_text: e.target.value })}
              />
            </div>
          );
        }

        if (!desc && !sourceText) return <Text type="secondary">—</Text>;

        return (
          <button
            type="button"
            className="score-locate-link qual-desc-locate"
            title="点击在原文中高亮"
            onClick={(e) => {
              e.stopPropagation();
              locateQual(record);
            }}
          >
            <span className="qual-desc-main">{desc || sourceText}</span>
            {showContrast && (
              <span className="qual-source-contrast">
                <span className="qual-source-contrast-label">原文</span>
                {sourceText}
              </span>
            )}
          </button>
        );
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 88,
      render: (_, record) => (
        editingQualIndexes.has(record._origIndex) ? (
          <Button type="link" size="small" onClick={(e) => finishEditQual(record._origIndex, e)}>
            完成
          </Button>
        ) : (
          <Button type="link" size="small" onClick={(e) => startEditQual(record._origIndex, e)}>
            编辑
          </Button>
        )
      ),
    },
  ];

  const locateCommerce = (record, idx) => {
    if (!onLocateSource) return;
    onLocateSource({
      key: `commerce-${idx}`,
      nonce: Date.now(),
      text: record.criteria || record.title || '',
      page: record.source_page || null,
      title: record.title,
    });
  };

  const commerceColumns = [
    {
      title: '评分项',
      dataIndex: 'title',
      width: 160,
      render: (text, record, idx) => (
        <Input
          value={text}
          size="small"
          onChange={(e) => {
            const next = [...commerceScores];
            next[idx] = { ...record, title: e.target.value };
            setDetail((d) => ({ ...d, commerce_scores: next }));
          }}
        />
      ),
    },
    {
      title: '评分标准',
      dataIndex: 'criteria',
      render: (text, record, idx) => (
        <div>
          <Input.TextArea
            value={text}
            autoSize={{ minRows: 2, maxRows: 8 }}
            onChange={(e) => {
              const next = [...commerceScores];
              next[idx] = { ...record, criteria: e.target.value };
              setDetail((d) => ({ ...d, commerce_scores: next }));
            }}
          />
          {onLocateSource && (text || record.title) && (
            <Button
              type="link"
              size="small"
              className="score-locate-link"
              style={{ padding: '4px 0 0', height: 'auto' }}
              onClick={(e) => { e.stopPropagation(); locateCommerce(record, idx); }}
            >
              在原文中定位
            </Button>
          )}
        </div>
      ),
    },
    {
      title: '分数',
      dataIndex: 'score_value',
      width: 90,
      align: 'center',
      render: (val, record, idx) => (
        <InputNumber
          value={val}
          size="small"
          min={0}
          style={{ width: 72 }}
          onChange={(v) => {
            const next = [...commerceScores];
            next[idx] = { ...record, score_value: v };
            setDetail((d) => ({ ...d, commerce_scores: next }));
          }}
        />
      ),
    },
  ];

  if (loading || !detail) {
    return <Spin tip="加载解析结果..." style={{ display: 'block', margin: '48px auto' }} />;
  }

  const packageLabel = detail.notice?.package_name || project?.name || '当前标段';

  return (
    <div className="tender-detail-panel">
      {parseSummary?.parse_error && (
        <Alert type="warning" showIcon message="解析提示" description={parseSummary.parse_error} style={{ marginBottom: 16 }} />
      )}
      {parseSummary?.blind_bid_auto_detected && (
        <Alert
          type="warning"
          showIcon
          message="检测到本项目可能为暗标，请确认"
          description="招标文件中出现暗标相关表述，已预勾选「暗标=是」。请核对后保存；若误判可改为「否」。"
          style={{ marginBottom: 16 }}
        />
      )}
      <ContradictionsAlert projectId={projectId} />

      <div className="tender-detail-block">
        <SectionTitle>投标人须知</SectionTitle>
        <Form form={noticeForm} layout="vertical" className="tender-notice-form">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="project_name" label="项目名称" rules={[{ required: true, message: '请填写项目名称' }]}>
                <Input placeholder="项目名称" maxLength={100} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="project_code" label="项目编号">
                <Input placeholder="项目编号" maxLength={100} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="package_name" label="包号">
                <Input placeholder="标段/包号名称" maxLength={100} />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="budget_wan" label="预算（万元）">
                <Input placeholder="如 359.3026" />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="package_no" label="包号编号">
                <Input placeholder="选填" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="tenderer" label="招标人">
                <Input placeholder="招标人" maxLength={100} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="agency" label="招标代理机构">
                <Input placeholder="招标代理机构" maxLength={100} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="bid_domain"
                label="项目所属领域"
                rules={[{ required: true, message: '请选择工程领域' }]}
                extra="影响后续正文撰写的专业身份设定"
              >
                <Select placeholder="请输入或选择" showSearch optionFilterProp="children">
                  {domainOptions.map((d) => (
                    <Option key={d.key || d} value={d.key || d}>{d.label || d}</Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="location" label="建设地点" rules={[{ required: true, message: '请填写建设地点' }]}>
                <Input placeholder="省市区或具体地址" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="sme_targeted" label="是否专门面向中小微企业采购">
                <Select allowClear placeholder="请选择">
                  <Option value="是">是</Option>
                  <Option value="否">否</Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="blind_bid"
                label="暗标"
                extra={
                  parseSummary?.blind_bid_auto_detected
                    ? '已根据招标文件关键词预勾选，请核对确认'
                    : undefined
                }
              >
                <Radio.Group>
                  <Radio.Button value="true">是</Radio.Button>
                  <Radio.Button value="false">否</Radio.Button>
                </Radio.Group>
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="duration_text"
                label="工期"
                rules={[{ required: true, message: '请填写工期，如 60个日历天' }]}
              >
                <Input placeholder="如 60个日历天" maxLength={50} />
              </Form.Item>
            </Col>
          </Row>
          <div className="tender-subsection-label">技术标写作参数（全书一致，仅在此维护）</div>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="project_type" label="项目类型" rules={[{ required: true, message: '请选择' }]}>
                <Select placeholder="项目类型">
                  {PROJECT_TYPES.map((t) => <Option key={t} value={t}>{t}</Option>)}
                </Select>
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="contract_mode" label="承包模式">
                <Select placeholder="承包模式" allowClear>
                  {CONTRACT_MODES.map((t) => <Option key={t} value={t}>{t}</Option>)}
                </Select>
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="voltage_level"
                label="电压等级"
                rules={voltageRequired ? [{ required: true, message: '请填写' }] : []}
                extra={voltageRequired ? undefined : '非电力工程可不填'}
              >
                <Input placeholder={voltageRequired ? '如 10kV' : '非电力工程可不填'} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="capacity" label="工程规模">
                <Input placeholder="线路长度、容量等" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="target_pages" label="技术标目标页数">
                <InputNumber min={10} max={1200} style={{ width: '100%' }} placeholder="默认 40" />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item
                name="overview"
                label="项目概况"
                extra="作为全书写作背景，生成正文时注入全局上下文"
              >
                <Input.TextArea rows={4} maxLength={1000} placeholder="项目概况" />
              </Form.Item>
            </Col>
          </Row>
          <Button type="primary" onClick={saveNotice} loading={savingSection === 'notice'}>
            保存工程信息与投标人须知
          </Button>
        </Form>
      </div>

      <div className="tender-detail-block">
        <SectionTitle>商务要求</SectionTitle>
        <Input.TextArea
          className="tender-rich-text"
          rows={16}
          value={detail.commerce_requirements}
          onChange={(e) => setDetail((d) => ({ ...d, commerce_requirements: e.target.value }))}
          placeholder="商务条款整理内容..."
        />
        <EditTip />
        <Button
          style={{ marginTop: 12 }}
          onClick={() => saveTextSection('commerce_requirements')}
          loading={savingSection === 'commerce_requirements'}
        >
          保存商务要求
        </Button>
      </div>

      <div className="tender-detail-block">
        <SectionTitle>技术要求</SectionTitle>
        <Input.TextArea
          className="tender-rich-text"
          rows={16}
          value={detail.service_requirements}
          onChange={(e) => setDetail((d) => ({ ...d, service_requirements: e.target.value }))}
          placeholder="技术标准与服务需求整理内容..."
        />
        <EditTip />
        <Button
          style={{ marginTop: 12 }}
          onClick={() => saveTextSection('service_requirements')}
          loading={savingSection === 'service_requirements'}
        >
          保存技术要求
        </Button>
      </div>

      <div className="tender-detail-block">
        <SectionTitle>投标文件参考格式（技术部分目录）</SectionTitle>
        <Input.TextArea
          className="tender-rich-text"
          rows={10}
          value={detail.bid_reference_catalog || ''}
          onChange={(e) => setDetail((d) => ({ ...d, bid_reference_catalog: e.target.value }))}
          placeholder={'从招标文件「投标文件格式 / 技术文件组成」摘录目录，例如：\n（一）工程概况\n（二）施工组织设计\n  1. 施工部署'}
        />
        <EditTip />
        <Button
          style={{ marginTop: 12 }}
          onClick={() => saveTextSection('bid_reference_catalog')}
          loading={savingSection === 'bid_reference_catalog'}
        >
          保存参考格式目录
        </Button>
      </div>

      <div className="tender-detail-block">
        <SectionTitle>资格审查</SectionTitle>
        <Tabs
          activeKey={qualTab}
          onChange={setQualTab}
          items={QUALIFICATION_TABS.map((tab) => ({
            key: tab.key,
            label: (
              <span>
                {tab.label}
                <Tag style={{ marginLeft: 6 }}>{qualTabCounts[tab.key] ?? 0}</Tag>
              </span>
            ),
          }))}
        />
        <Table
          className="tender-qual-table"
          size="small"
          rowKey={(r, i) => `${r.seq}-${i}`}
          columns={qualColumns}
          dataSource={qualDisplay}
          pagination={{ pageSize: 15, showTotal: (t) => `共 ${t} 条` }}
          scroll={{ x: 800 }}
          rowClassName={(record) => (
            activeLocateKey === `qual-${record._origIndex}` ? 'score-row-active' : ''
          )}
          onRow={(record) => ({
            onClick: () => {
              if (editingQualIndexes.has(record._origIndex)) return;
              locateQual(record);
            },
            style: editingQualIndexes.has(record._origIndex) ? undefined : { cursor: 'pointer' },
          })}
        />
        <Space style={{ marginTop: 12 }}>
          <Button
            onClick={() => {
              const newIndex = qualItems.length;
              const next = [...qualItems, {
                seq: qualItems.length + 1,
                item_label: '废标项',
                description: '',
                source_text: '',
                source_page: null,
              }];
              setDetail((d) => ({ ...d, qualification_items: next }));
              setEditingQualIndexes((prev) => new Set(prev).add(newIndex));
              setQualTab('废标项');
            }}
          >
            新增一行
          </Button>
          <Button type="primary" onClick={saveQualification} loading={savingSection === 'qualification'}>
            保存资格审查
          </Button>
        </Space>
      </div>

      <div className="tender-detail-block">
        <SectionTitle>评分要求</SectionTitle>
        <Tabs
          activeKey={scoreTab}
          onChange={setScoreTab}
          items={[
            { key: 'commerce', label: '商务评分' },
            { key: 'tech', label: '技术评分' },
          ]}
        />
        {scoreTab === 'commerce' ? (
          <>
            <Table
              className="tender-score-table"
              size="small"
              rowKey={(r, i) => `c-${i}`}
              columns={commerceColumns}
              dataSource={commerceScores}
              pagination={false}
              scroll={{ x: 700 }}
              rowClassName={(_, idx) => (
                activeLocateKey === `commerce-${idx}` ? 'score-row-active' : ''
              )}
            />
            <Space style={{ marginTop: 12 }}>
              <Button
                onClick={() => {
                  setDetail((d) => ({
                    ...d,
                    commerce_scores: [...commerceScores, { title: '', criteria: '', score_value: null }],
                  }));
                }}
              >
                新增商务评分项
              </Button>
              <Button type="primary" onClick={saveCommerceScores} loading={savingSection === 'commerce_scores'}>
                保存商务评分
              </Button>
            </Space>
            <div className="tender-package-hint">当前包号：{packageLabel}</div>
          </>
        ) : (
          <>
            <RequirementsTable
              projectId={projectId}
              onStatsChange={onStatsChange}
              onLocateSource={onLocateSource}
              activeLocateKey={activeLocateKey}
            />
            <div className="tender-package-hint">当前包号：{packageLabel}</div>
          </>
        )}
      </div>
    </div>
  );
}

export { TenderDetailPanel };
