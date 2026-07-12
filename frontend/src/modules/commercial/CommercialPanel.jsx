import {
  useState, useEffect, useCallback,
  Button, Card, Input, Space, message, Spin, Tag, Text, Alert,
} from '../../globals.js';

import {
  fetchCommercialStatus,
  regenerateCommercial,
  updateCommercialSection,
} from '../../api/commercial.js';
import { PageHeader } from '../../components/layout.jsx';

const { TextArea } = Input;

function statusTag(status) {
  if (status === 'confirmed') return <Tag color="success">已确认</Tag>;
  return <Tag>草稿</Tag>;
}

function CommercialPanel({ projectId, onStatusChange }) {
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState('');
  const [regenerating, setRegenerating] = useState(false);
  const [status, setStatus] = useState(null);
  const [drafts, setDrafts] = useState({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchCommercialStatus(projectId);
      setStatus(data);
      const next = {};
      (data.sections || []).forEach((s) => {
        next[s.id] = s.content_markdown || '';
      });
      setDrafts(next);
      onStatusChange?.(data);
    } catch (e) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  }, [projectId, onStatusChange]);

  useEffect(() => { load(); }, [load]);

  const handleSave = async (section, { confirm = false } = {}) => {
    setSavingId(section.id);
    try {
      await updateCommercialSection(projectId, section.id, {
        content_markdown: drafts[section.id] ?? section.content_markdown,
        status: confirm ? 'confirmed' : undefined,
      });
      message.success(confirm ? '已确认' : '已保存');
      await load();
    } catch (e) {
      message.error(e.message);
    } finally {
      setSavingId('');
    }
  };

  const handleRegenerate = async () => {
    setRegenerating(true);
    try {
      await regenerateCommercial(projectId);
      message.success('已按最新招标详情重生成草稿（已确认章节保留）');
      await load();
    } catch (e) {
      message.error(e.message);
    } finally {
      setRegenerating(false);
    }
  };

  if (loading && !status) {
    return <Spin tip="加载商务标…" />;
  }

  if (!status?.enabled) {
    return (
      <Alert
        type="info"
        showIcon
        message="尚未开启商务标"
        description="请在「确认评分项」页将生成范围设为「技术标+商务标」。"
      />
    );
  }

  const sections = status.sections || [];

  return (
    <div className="commercial-panel">
      <PageHeader
        title="商务标"
        description="基于招标详情模板生成资格/商务响应草稿，可逐条编辑并确认；导出为独立 Word 分册。"
        extra={(
          <Space>
            <Text type="secondary">
              已确认 {status.confirmed_count || 0}/{status.section_count || 0}
            </Text>
            <Button loading={regenerating} onClick={handleRegenerate}>
              按最新招标详情重生成
            </Button>
          </Space>
        )}
      />

      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        {sections.map((section) => (
          <Card
            key={section.id}
            size="small"
            className="section-card"
            title={(
              <Space>
                <span>{section.title}</span>
                {statusTag(section.status)}
              </Space>
            )}
            extra={(
              <Space>
                <Button
                  size="small"
                  loading={savingId === section.id}
                  onClick={() => handleSave(section)}
                >
                  保存
                </Button>
                <Button
                  size="small"
                  type="primary"
                  loading={savingId === section.id}
                  disabled={section.status === 'confirmed' && drafts[section.id] === section.content_markdown}
                  onClick={() => handleSave(section, { confirm: true })}
                >
                  确认
                </Button>
              </Space>
            )}
          >
            <TextArea
              className="tender-rich-text"
              rows={8}
              value={drafts[section.id] ?? ''}
              onChange={(e) => setDrafts((prev) => ({ ...prev, [section.id]: e.target.value }))}
            />
          </Card>
        ))}
        {!sections.length && (
          <Alert type="warning" showIcon message="暂无商务标章节，请点击「重生成」或检查招标详情是否已解析。" />
        )}
      </Space>
    </div>
  );
}

export { CommercialPanel };
