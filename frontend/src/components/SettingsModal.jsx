import {
  useState, useEffect, useCallback, useMemo, useRef,
  Card, Button, Table, Form, Input, InputNumber, Select,
  Upload, Tag, Space, message, Spin, Popconfirm, Alert, Typography, Row, Col,
  Modal, Divider, ConfigProvider, Tree, Progress, List, Badge, Popover,
  Menu, Radio, Drawer, Tooltip, Tabs,
  Dragger, Option, Title, Text, Password,
  APP_LOCALE, APP_THEME,
} from '../globals.js';

import { apiFetch } from '../api/client.js';
import { Icon } from './icons.jsx';

function SettingsModal({ open, onClose }) {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [testing, setTesting] = useState(false);
  const [configured, setConfigured] = useState(false);
  const [maskedKey, setMaskedKey] = useState('');

  const loadSettings = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiFetch('/settings');
      setConfigured(data.api_key_configured);
      setMaskedKey(data.api_key_masked);
      form.setFieldsValue({
        base_url: data.base_url,
        model: data.model,
        max_tokens: data.max_tokens,
        temperature: data.temperature,
        api_key: '',
      });
    } catch (e) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  }, [form]);

  useEffect(() => {
    if (open) loadSettings();
  }, [open, loadSettings]);

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      setLoading(true);
      const body = {
        base_url: values.base_url,
        model: values.model,
        max_tokens: values.max_tokens,
        temperature: values.temperature,
      };
      if (values.api_key && values.api_key.trim()) {
        body.api_key = values.api_key.trim();
      }
      const data = await apiFetch('/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      setConfigured(data.api_key_configured);
      setMaskedKey(data.api_key_masked);
      form.setFieldsValue({ api_key: '' });
      message.success('API 设置已保存');
    } catch (e) {
      if (e.message) message.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    try {
      const result = await apiFetch('/settings/test', { method: 'POST' });
      if (result.success) message.success(result.message);
      else message.error(result.message);
    } catch (e) {
      message.error(e.message);
    } finally {
      setTesting(false);
    }
  };

  return (
    <Modal
      title="API 设置"
      open={open}
      onCancel={onClose}
      width={560}
      footer={[
        <Button key="test" loading={testing} onClick={handleTest}>测试连接</Button>,
        <Button key="cancel" onClick={onClose}>取消</Button>,
        <Button key="save" type="primary" loading={loading} onClick={handleSave}>保存</Button>,
      ]}
    >
      <Spin spinning={loading}>
        <Alert
          type={configured ? 'success' : 'warning'}
          showIcon
          style={{ marginBottom: 16 }}
          message={configured ? `API Key 已配置（${maskedKey}）` : '尚未配置 API Key，解析功能将无法使用'}
        />
        <Form form={form} layout="vertical">
          <Form.Item name="api_key" label="API Key" extra="留空则不修改已有 Key">
            <Password placeholder={configured ? `当前：${maskedKey}，输入新 Key 可替换` : 'sk-...'} />
          </Form.Item>
          <Form.Item name="base_url" label="API Base URL" rules={[{ required: true }]}>
            <Input placeholder="https://api.deepseek.com" />
          </Form.Item>
          <Form.Item name="model" label="模型名称" rules={[{ required: true }]}>
            <Select showSearch>
              <Option value="deepseek-chat">deepseek-chat</Option>
              <Option value="deepseek-reasoner">deepseek-reasoner</Option>
            </Select>
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="max_tokens" label="最大 Token" rules={[{ required: true }]}>
                <InputNumber min={256} max={32000} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="temperature" label="Temperature" rules={[{ required: true }]}>
                <InputNumber min={0} max={2} step={0.1} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
        </Form>
        <Divider style={{ margin: '12px 0' }} />
        <Text type="secondary" style={{ fontSize: 12 }}>设置保存至本地 .env，立即生效。</Text>
      </Spin>
    </Modal>
  );
}
export { SettingsModal };
