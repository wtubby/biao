import { useEffect, useState } from '../../globals.js';
import {
  Drawer, Form, Input, Select, Button, Space, List, Typography, message, Spin,
} from '../../globals.js';
import { fetchStandard, upsertStandard } from '../../api/standards.js';
import { StandardStatusBadge } from './StandardStatusBadge.jsx';

const { TextArea } = Input;
const { Text } = Typography;

const STATUS_OPTIONS = [
  { value: 'draft', label: '草稿' },
  { value: 'active', label: '现行' },
  { value: 'superseded', label: '被替代' },
  { value: 'withdrawn', label: '废止' },
];

export function StandardDetailDrawer({
  open,
  code,
  domainOptions = [],
  onClose,
  onSaved,
}) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [detail, setDetail] = useState(null);
  const [form] = Form.useForm();

  useEffect(() => {
    if (!open || !code) return undefined;
    let cancelled = false;
    setLoading(true);
    fetchStandard(code)
      .then((data) => {
        if (cancelled) return;
        setDetail(data);
        form.setFieldsValue({
          title: data.title || '',
          category: data.category || '国标',
          status: data.status || 'draft',
          summary: data.summary || '',
          key_clauses: data.key_clauses || '',
          domains: data.domains || [],
          superseded_by: data.superseded_by || '',
        });
      })
      .catch((e) => message.error(e.message))
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [open, code, form]);

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      await upsertStandard(code, {
        title: values.title,
        category: values.category,
        status: values.status,
        summary: values.summary,
        key_clauses: values.key_clauses,
        superseded_by: values.superseded_by || null,
        domains: values.domains || [],
      });
      message.success('已保存');
      onSaved?.();
      onClose?.();
    } catch (e) {
      if (e?.errorFields) return;
      message.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Drawer
      title={detail ? `标准详情 · ${detail.raw_code || detail.code}` : '标准详情'}
      open={open}
      onClose={onClose}
      width={560}
      destroyOnClose
      extra={(
        <Space>
          {detail && <StandardStatusBadge status={detail.status} />}
          <Button type="primary" loading={saving} onClick={handleSave}>保存</Button>
        </Space>
      )}
    >
      <Spin spinning={loading}>
        <Form form={form} layout="vertical">
          <Form.Item name="title" label="标题" rules={[{ required: true, message: '请填写标题' }]}>
            <Input placeholder="标准全称" />
          </Form.Item>
          <Form.Item name="category" label="类别">
            <Input placeholder="国标 / 行标 / 企标" />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select options={STATUS_OPTIONS} />
          </Form.Item>
          <Form.Item name="domains" label="适用领域">
            <Select
              mode="multiple"
              allowClear
              placeholder="选择适用领域"
              options={domainOptions.map((d) => ({ value: d.key, label: d.label || d.key }))}
            />
          </Form.Item>
          <Form.Item name="superseded_by" label="替代标准编号">
            <Input placeholder="被替代时填写" />
          </Form.Item>
          <Form.Item name="summary" label="摘要">
            <TextArea rows={3} placeholder="标准摘要" />
          </Form.Item>
          <Form.Item name="key_clauses" label="关键条款">
            <TextArea rows={4} placeholder="关键条款摘录" />
          </Form.Item>
        </Form>

        <Text strong style={{ display: 'block', marginBottom: 8 }}>关联知识库片段</Text>
        <List
          size="small"
          locale={{ emptyText: '暂无关联片段' }}
          dataSource={detail?.chunks || []}
          renderItem={(item) => (
            <List.Item>
              <div>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {item.folder_path}/{item.source_file}
                </Text>
                <div style={{ marginTop: 4, whiteSpace: 'pre-wrap' }}>{item.text}</div>
              </div>
            </List.Item>
          )}
        />
      </Spin>
    </Drawer>
  );
}
