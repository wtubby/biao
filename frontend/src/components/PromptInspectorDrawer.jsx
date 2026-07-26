import {
  useState, useEffect,
  Button, Space, message, Spin, Alert, Typography, Radio, Drawer, Tabs, Input, Tag,
  Text,
} from '../globals.js';

import { apiFetch } from '../api/client.js';

function formatMessagesCopy(messages) {
  return (messages || [])
    .map((m, i) => `[${i + 1}] ${String(m.role || 'user').toUpperCase()}\n${m.content || ''}`)
    .join('\n\n==========\n\n');
}

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
  const exportPayload = sourceKey === 'last' && data?.last_generation
    ? data.last_generation
    : data;
  const stageMessages = activeStage?.messages?.length ? activeStage.messages : null;

  const copyText = async (text) => {
    try {
      await navigator.clipboard.writeText(text || '');
      message.success('已复制到剪贴板');
    } catch {
      message.error('复制失败');
    }
  };

  const downloadJson = () => {
    if (!exportPayload) {
      message.warning('暂无可下载数据');
      return;
    }
    const blob = new Blob([JSON.stringify(exportPayload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    const chapterPart = data?.chapter_id || data?.chapter_title || 'prompt';
    a.href = url;
    a.download = `prompt_${chapterPart}_${sourceKey}.json`;
    a.click();
    URL.revokeObjectURL(url);
    message.success('已下载提示词 JSON');
  };

  return (
    <Drawer
      title={title}
      open={open}
      onClose={onClose}
      width={820}
      destroyOnClose
      extra={(
        <Button size="small" onClick={downloadJson} disabled={!exportPayload}>
          下载 JSON
        </Button>
      )}
    >
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
        {data?.last_captured_at && sourceKey === 'last' && (
          <Alert
            type="success"
            showIcon
            style={{ marginBottom: 12 }}
            message={`上次生成快照时间：${data.last_captured_at}`}
            description={data.last_generation?.log_path
              ? `服务端日志：${data.last_generation.log_path}`
              : '可切换「当前预览」对比实时组装结果'}
          />
        )}
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
                {activeStage.metrics.user_message_count != null
                  ? ` · ${activeStage.metrics.message_count || 0} 条消息（user ×${activeStage.metrics.user_message_count}）`
                  : ''}
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
            {stageMessages ? (
              <>
                <Space style={{ marginBottom: 8 }}>
                  <Text strong>真实 Messages</Text>
                  <Button size="small" onClick={() => copyText(formatMessagesCopy(stageMessages))}>
                    复制全部
                  </Button>
                  <Button size="small" onClick={() => copyText(JSON.stringify(stageMessages, null, 2))}>
                    复制 JSON
                  </Button>
                </Space>
                {stageMessages.map((m, idx) => (
                  <div key={`${m.role}-${idx}`} className="prompt-message-block">
                    <div className="prompt-message-role">
                      <Tag color={m.role === 'system' ? 'purple' : m.role === 'user' ? 'blue' : 'default'}>
                        #{idx + 1} {String(m.role || 'user').toUpperCase()}
                      </Tag>
                      <Button size="small" type="link" onClick={() => copyText(m.content || '')}>
                        复制
                      </Button>
                    </div>
                    <Input.TextArea
                      readOnly
                      value={m.content}
                      rows={m.role === 'system' ? 8 : 12}
                      className="prompt-textarea"
                    />
                  </div>
                ))}
              </>
            ) : (
              <>
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
          </>
        )}
        {!loading && !stagesSource?.length && <Text type="secondary">暂无提示词数据</Text>}
      </Spin>
    </Drawer>
  );
}
export { PromptInspectorDrawer };
