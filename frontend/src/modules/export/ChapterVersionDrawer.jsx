import { useState, useEffect, useCallback } from '../../globals.js';
import {
  Alert, Button, Drawer, List, Popconfirm, Select, Space, Spin, Tag, Text, message,
} from '../../globals.js';
import {
  compareChapterVersions,
  fetchChapterVersions,
  restoreChapterVersion,
} from '../../api/chapter.js';

function formatVersionTime(value) {
  if (!value) return '未知时间';
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

export function ChapterVersionDrawer({
  open,
  chapterId,
  chapterTitle,
  onClose,
  onRestored,
}) {
  const [versions, setVersions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [compareFrom, setCompareFrom] = useState('');
  const [compareTo, setCompareTo] = useState('');
  const [diffText, setDiffText] = useState('');
  const [comparing, setComparing] = useState(false);
  const [restoring, setRestoring] = useState('');

  const loadVersions = useCallback(async () => {
    if (!chapterId) return;
    setLoading(true);
    try {
      const data = await fetchChapterVersions(chapterId);
      const items = data.versions || [];
      setVersions(items);
      if (items.length > 0) {
        setCompareFrom(items[0].id);
        setCompareTo('');
      } else {
        setCompareFrom('');
        setDiffText('');
      }
    } catch (e) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  }, [chapterId]);

  useEffect(() => {
    if (open) loadVersions();
  }, [open, loadVersions]);

  const handleCompare = async () => {
    if (!compareFrom) return;
    setComparing(true);
    try {
      const data = await compareChapterVersions(chapterId, compareFrom, compareTo || null);
      setDiffText(data.diff || '（无差异）');
    } catch (e) {
      message.error(e.message);
    } finally {
      setComparing(false);
    }
  };

  const handleRestore = async (versionId) => {
    setRestoring(versionId);
    try {
      const result = await restoreChapterVersion(chapterId, versionId);
      message.success('已恢复到选定版本');
      onRestored?.(result);
      await loadVersions();
    } catch (e) {
      message.error(e.message);
    } finally {
      setRestoring('');
    }
  };

  return (
    <Drawer
      title={`版本历史：${chapterTitle || ''}`}
      open={open}
      onClose={onClose}
      width={720}
    >
      <Spin spinning={loading}>
        {versions.length === 0 ? (
          <Text type="secondary">暂无历史版本。保存、生成或改写章节后会自动存档。</Text>
        ) : (
          <>
            <List
              size="small"
              dataSource={versions}
              renderItem={(item) => (
                <List.Item
                  actions={[
                    <Button
                      key="compare-from"
                      type="link"
                      size="small"
                      onClick={() => setCompareFrom(item.id)}
                    >
                      作对比基准
                    </Button>,
                    <Popconfirm
                      key="restore"
                      title="恢复此版本？当前正文会先存档。"
                      onConfirm={() => handleRestore(item.id)}
                    >
                      <Button type="link" size="small" loading={restoring === item.id}>
                        恢复
                      </Button>
                    </Popconfirm>,
                  ]}
                >
                  <List.Item.Meta
                    title={(
                      <Space size="small">
                        <Text>{formatVersionTime(item.created_at)}</Text>
                        <Tag>{item.source_label || item.source}</Tag>
                        {item.review_status && <Tag color="blue">{item.review_status}</Tag>}
                      </Space>
                    )}
                    description={`${item.char_count || 0} 字 · ${item.preview || ''}`}
                  />
                </List.Item>
              )}
            />

            <div style={{ marginTop: 16 }}>
              <Text strong>版本对比</Text>
              <Space wrap style={{ marginTop: 8, marginBottom: 8 }}>
                <Select
                  style={{ minWidth: 220 }}
                  placeholder="选择基准版本"
                  value={compareFrom || undefined}
                  onChange={setCompareFrom}
                  options={versions.map((v) => ({
                    value: v.id,
                    label: formatVersionTime(v.created_at),
                  }))}
                />
                <Select
                  allowClear
                  style={{ minWidth: 220 }}
                  placeholder="对比版本（空=当前正文）"
                  value={compareTo || undefined}
                  onChange={(v) => setCompareTo(v || '')}
                  options={versions.map((v) => ({
                    value: v.id,
                    label: formatVersionTime(v.created_at),
                  }))}
                />
                <Button loading={comparing} onClick={handleCompare} disabled={!compareFrom}>
                  对比
                </Button>
              </Space>
              {diffText ? (
                <pre
                  style={{
                    maxHeight: 320,
                    overflow: 'auto',
                    background: '#fafafa',
                    padding: 12,
                    borderRadius: 6,
                    fontSize: 12,
                    lineHeight: 1.5,
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  {diffText}
                </pre>
              ) : null}
            </div>
          </>
        )}
      </Spin>
    </Drawer>
  );
}
