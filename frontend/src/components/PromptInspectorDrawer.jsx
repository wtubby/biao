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
function PromptInspectorDrawer({ open, onClose, title, fetchPath, hint }) {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [sourceKey, setSourceKey] = useState('preview');
  const [stageId, setStageId] = useState('0');

  useEffect(() => {
    if (!open || !fetchPath) return undefined;
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const payload = await apiFetch(fetchPath);
        if (!cancelled) {
          setData(payload);
          setSourceKey(payload.last_generation ? 'last' : 'preview');
          setStageId('0');
        }
      } catch (e) {
        if (!cancelled) message.error(e.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [open, fetchPath]);

  const stagesSource = sourceKey === 'last' && data?.last_generation
    ? data.last_generation.stages
    : data?.stages;
  const promptMetrics = sourceKey === 'last' && data?.last_generation?.prompt_metrics
    ? data.last_generation.prompt_metrics
    : data?.prompt_metrics;
  const activeStage = stagesSource?.[Number(stageId)];
  const guidance = sourceKey === 'last' && data?.last_generation?.guidance
    ? data.last_generation.guidance
    : data?.guidance;

  const copyText = async (text) => {
    try {
      await navigator.clipboard.writeText(text || '');
      message.success('已复制到剪贴板');
    } catch {
      message.error('复制失败');
    }
  };

  return (
    <Drawer title={title} open={open} onClose={onClose} width={820} destroyOnClose>
      <Spin spinning={loading}>
        {promptMetrics && (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
            message={`预估输入约 ${promptMetrics.total_tokens_est?.toLocaleString?.() ?? promptMetrics.total_tokens_est} tokens（${promptMetrics.stage_count} 个阶段）`}
          />
        )}
        {hint && <Alert type="info" showIcon message={hint} style={{ marginBottom: 12 }} />}
        {guidance && (
          <div className="prompt-guidance-box">
            <div><Text type="secondary">写作要点：</Text>{guidance.brief || '—'}</div>
            <div><Text type="secondary">内容边界：</Text>{guidance.content_boundary || '—'}</div>
            {data?.chapter_type && (
              <div><Text type="secondary">章节类型：</Text>{data.chapter_type}</div>
            )}
          </div>
        )}
        {data?.last_generation && (
          <Radio.Group
            value={sourceKey}
            onChange={(e) => { setSourceKey(e.target.value); setStageId('0'); }}
            style={{ marginBottom: 12 }}
            optionType="button"
            buttonStyle="solid"
            options={[
              { label: '当前预览', value: 'preview' },
              { label: '上次生成快照', value: 'last' },
            ]}
          />
        )}
        {stagesSource?.length > 0 && (
          <Tabs
            activeKey={stageId}
            onChange={setStageId}
            style={{ marginBottom: 8 }}
            items={stagesSource.map((s, i) => ({ key: String(i), label: s.label }))}
          />
        )}
        {activeStage && (
          <>
            {activeStage.note && <Alert type="warning" message={activeStage.note} showIcon style={{ marginBottom: 8 }} />}
            {activeStage.metrics && (
              <Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>
                本阶段预估：System {activeStage.metrics.system_tokens_est} + User {activeStage.metrics.user_tokens_est} ≈ {activeStage.metrics.total_tokens_est} tokens
              </Text>
            )}
            {data?.last_generation?.fix_instructions && sourceKey === 'last' && (
              <Alert
                type="error"
                showIcon
                message="质检修复要求"
                description={data.last_generation.fix_instructions}
                style={{ marginBottom: 8 }}
              />
            )}
            <Text strong>System 提示词</Text>
            <Input.TextArea
              readOnly
              value={activeStage.system}
              rows={8}
              className="prompt-textarea"
            />
            <Space style={{ margin: '8px 0' }}>
              <Text strong>User 提示词</Text>
              <Button size="small" onClick={() => copyText(activeStage.user)}>复制 User</Button>
              <Button size="small" onClick={() => copyText(`[System]\n${activeStage.system}\n\n[User]\n${activeStage.user}`)}>
                复制全部
              </Button>
            </Space>
            <Input.TextArea
              readOnly
              value={activeStage.user}
              rows={22}
              className="prompt-textarea"
            />
          </>
        )}
        {!loading && !stagesSource?.length && <Text type="secondary">暂无提示词数据</Text>}
      </Spin>
    </Drawer>
  );
}
export { PromptInspectorDrawer };
