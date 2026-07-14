import {
  useState, useEffect, useCallback, useMemo, useRef,
  Card, Button, Input, Tag, Space, message, Spin, Alert, Row, Col,
  Modal, Tree, List, Radio, Dropdown,
  Text,
} from '../../globals.js';

import { apiFetch } from '../../api/client.js';
import {
  detectAiCliches,
  saveChapterContent,
  reviewChapter,
  regenerateChapter,
  selectionRewrite,
} from '../../api/chapter.js';
import { fetchOutline } from '../../api/outline.js';
import { downloadFromApi } from '../../api/download.js';
import { ChapterStatusIcon } from '../../components/icons.jsx';
import { PromptInspectorDrawer } from '../../components/PromptInspectorDrawer.jsx';
import { ComplianceReportDrawer } from '../compliance/ComplianceReportDrawer.jsx';
import { ResponseMatrixDrawer } from '../confirm/ResponseMatrixDrawer.jsx';
import { ChapterVersionDrawer } from './ChapterVersionDrawer.jsx';
import { buildOutlineTreeData } from '../outline/helpers.jsx';
import { useChartPreviews, renderMarkdownPreview } from '../chart/preview.js';
import { getReviewStatusTagColor, formatReviewErrorsText } from '../../lib/chapterStatus.js';

function PreviewExport({ projectId, durationDays, onGoGenerate }) {
  const [nodes, setNodes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [selected, setSelected] = useState(null);
  const [content, setContent] = useState('');
  const [savedContent, setSavedContent] = useState('');
  const [contentMode, setContentMode] = useState('edit');
  const [splitView, setSplitView] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [exportingDebug, setExportingDebug] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [complianceOpen, setComplianceOpen] = useState(false);
  const [matrixOpen, setMatrixOpen] = useState(false);
  const [selection, setSelection] = useState({ text: '', start: 0, end: 0 });
  const [rewriteOpen, setRewriteOpen] = useState(false);
  const [rewriteInstruction, setRewriteInstruction] = useState('');
  const [rewriting, setRewriting] = useState(false);
  const [promptOpen, setPromptOpen] = useState(false);
  const [aiHits, setAiHits] = useState([]);
  const [detectingAi, setDetectingAi] = useState(false);
  const [versionOpen, setVersionOpen] = useState(false);
  const textAreaRef = useRef(null);
  const chartPreviews = useChartPreviews(content, durationDays);
  const isDirty = content !== savedContent;

  const getTextAreaEl = useCallback(
    () => textAreaRef.current?.resizableTextArea?.textArea || textAreaRef.current,
    [],
  );

  const captureSelection = useCallback(() => {
    const el = getTextAreaEl();
    if (!el) return;
    const { selectionStart, selectionEnd, value } = el;
    if (selectionStart == null || selectionEnd == null || selectionStart === selectionEnd) {
      setSelection({ text: '', start: 0, end: 0 });
      return;
    }
    setSelection({
      text: value.substring(selectionStart, selectionEnd),
      start: selectionStart,
      end: selectionEnd,
    });
  }, [getTextAreaEl]);

  const applyChapterContent = useCallback((chapter) => {
    const next = chapter?.generated_content || '';
    setContent(next);
    setSavedContent(next);
    setSelection({ text: '', start: 0, end: 0 });
    setAiHits([]);
  }, []);

  const load = useCallback(async ({ preserveSelection = true, silent = false } = {}) => {
    if (!silent) setLoading(true);
    setLoadError(null);
    try {
      const outline = await fetchOutline(projectId);
      setNodes(outline);
      const leaves = outline.filter((n) => n.is_leaf === 1);
      setSelected((prev) => {
        if (preserveSelection && prev && outline.some((n) => n.id === prev && n.is_leaf === 1)) {
          return prev;
        }
        return leaves[0]?.id || null;
      });
      return outline;
    } catch (e) {
      setLoadError(e.message || '加载失败');
      return null;
    } finally {
      if (!silent) setLoading(false);
    }
  }, [projectId]);

  useEffect(() => { load({ preserveSelection: false }); }, [load]);

  // 选中章节变化时加载正文（忽略同章 nodes 刷新，避免覆盖未保存编辑）
  const prevSelectedRef = useRef(null);
  useEffect(() => {
    if (selected === prevSelectedRef.current) return;
    prevSelectedRef.current = selected;
    const ch = nodes.find((c) => c.id === selected);
    applyChapterContent(ch);
  }, [selected, nodes, applyChapterContent]);

  const treeData = useMemo(() => buildOutlineTreeData(nodes, (n) => (
    <Space size="small">
      {n.is_leaf === 1 && <ChapterStatusIcon status={n.review_status} />}
      <Text ellipsis style={{ maxWidth: 180 }}>{n.title}</Text>
      {n.is_leaf === 1 && n.review_status === 'yellow' && (
        <Tag color="orange" style={{ margin: 0, fontSize: 11 }}>待优化</Tag>
      )}
      {n.is_leaf === 1 && n.review_status === 'red' && (
        <Tag color="red" style={{ margin: 0, fontSize: 11 }}>失败</Tag>
      )}
      {n.is_leaf === 1 && !(n.generated_content || '').trim() && n.review_status !== 'red' && (
        <Tag style={{ margin: 0, fontSize: 11 }}>未生成</Tag>
      )}
      {isDirty && n.id === selected && (
        <Tag color="orange" style={{ margin: 0, fontSize: 11 }}>未保存</Tag>
      )}
    </Space>
  )), [nodes, selected, isDirty]);

  const selectedChapter = nodes.find((n) => n.id === selected);
  const leafCount = useMemo(() => nodes.filter((n) => n.is_leaf === 1).length, [nodes]);
  const generatedCount = useMemo(
    () => nodes.filter((n) => n.is_leaf === 1 && (n.generated_content || '').trim()).length,
    [nodes],
  );

  const yellowChapters = useMemo(
    () => nodes.filter((n) => n.is_leaf === 1 && n.review_status === 'yellow'),
    [nodes],
  );
  const redChapters = useMemo(
    () => nodes.filter((n) => n.is_leaf === 1 && n.review_status === 'red'),
    [nodes],
  );
  const emptyChapters = useMemo(
    () => nodes.filter((n) => n.is_leaf === 1 && !(n.generated_content || '').trim()),
    [nodes],
  );

  const doExport = async ({
    allowYellow = false,
    allowIncomplete = false,
  } = {}) => {
    setExporting(true);
    try {
      const params = new URLSearchParams();
      if (allowYellow) params.set('allow_yellow', 'true');
      if (allowIncomplete) params.set('allow_incomplete', 'true');
      const query = params.toString() ? `?${params.toString()}` : '';
      const res = await downloadFromApi(
        `/projects/${projectId}/export${query}`,
        `${projectId}.docx`,
      );
      const compliancePassed = res.headers.get('X-Compliance-Passed') === 'true';
      const warnCount = Number(res.headers.get('X-Compliance-Warnings') || 0);
      const yellowCount = Number(res.headers.get('X-Yellow-Chapters') || 0);
      if (!compliancePassed || warnCount > 0) {
        message.warning(`Word 已导出；合规检查有 ${warnCount} 条提示，可在「合规报告」中查看`);
        setComplianceOpen(true);
      } else if (yellowCount > 0) {
        message.warning(`Word 已导出；${yellowCount} 个章节标题已标注【待优化】`);
        setComplianceOpen(true);
      } else if (allowIncomplete) {
        message.warning('Word 已导出；未生成正文的章节仅保留标题');
      } else {
        message.success('Word 文档已导出');
      }
    } catch (e) {
      message.error(e.message || '导出失败');
    } finally {
      setExporting(false);
    }
  };

  const confirmYellowThenExport = async (allowIncomplete = false) => {
    if (yellowChapters.length === 0) {
      doExport({ allowYellow: false, allowIncomplete });
      return;
    }
    let riskItems = yellowChapters.map((c) => ({
      id: c.id,
      title: c.title,
      errors: [],
    }));
    try {
      const data = await apiFetch(`/projects/${projectId}/export/yellow-risks`);
      if (Array.isArray(data.chapters) && data.chapters.length) {
        riskItems = data.chapters;
      }
    } catch {
      /* 回退本地黄章列表 */
    }
    Modal.confirm({
      title: '存在待优化章节（导出风险）',
      width: 560,
      content: (
        <div>
          <Text>
            以下 {riskItems.length} 个章节质检未完全通过，导出后标题将标注【待优化】，请确认风险：
          </Text>
          <ul style={{ marginTop: 8, paddingLeft: 20, maxHeight: 280, overflow: 'auto' }}>
            {riskItems.map((c) => (
              <li key={c.id} style={{ marginBottom: 6 }}>
                <Text strong>{c.title}</Text>
                {c.errors?.length > 0 && (
                  <div style={{ color: '#8c8c8c', fontSize: 12 }}>
                    {c.errors.slice(0, 3).join('；')}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      ),
      okText: '仍然导出 Word',
      cancelText: '取消',
      onOk: () => doExport({ allowYellow: true, allowIncomplete }),
    });
  };

  const confirmIncompleteThenExport = async () => {
    if (emptyChapters.length === 0) {
      await confirmYellowThenExport(false);
      return;
    }
    Modal.confirm({
      title: '仍有章节未生成正文',
      width: 560,
      content: (
        <div>
          <Text>
            以下 {emptyChapters.length} 个章节尚无正文，导出后将仅保留标题（正文为空）。确认仍要导出？
          </Text>
          <ul style={{ marginTop: 8, paddingLeft: 20, maxHeight: 280, overflow: 'auto' }}>
            {emptyChapters.slice(0, 20).map((c) => (
              <li key={c.id} style={{ marginBottom: 6 }}>
                <Text strong>{c.title}</Text>
              </li>
            ))}
            {emptyChapters.length > 20 && (
              <li style={{ color: '#8c8c8c' }}>…另有 {emptyChapters.length - 20} 章未列出</li>
            )}
          </ul>
        </div>
      ),
      okText: '仍然导出 Word',
      cancelText: '取消',
      onOk: () => confirmYellowThenExport(true),
    });
  };

  const handleExport = async () => {
    if (redChapters.length > 0) {
      const preview = redChapters.slice(0, 5).map((c) => c.title).join('、');
      const more = redChapters.length > 5 ? ` 等 ${redChapters.length} 章` : '';
      message.error(`以下章节生成失败，请先修复后再导出：${preview}${more}`);
      return;
    }

    // 导出前合规终审：有 fail / 评分项 missing 时二次确认，不阻断最终决定权
    let complianceReport = null;
    try {
      complianceReport = await apiFetch(`/projects/${projectId}/compliance/check`, { method: 'POST' });
    } catch {
      /* 检查失败不阻断导出 */
    }
    const failCount = Number(complianceReport?.failure_count || 0);
    const missingItems = (complianceReport?.coverage || []).filter((c) => c.status === 'missing');
    if (failCount > 0 || missingItems.length > 0) {
      const missingPreview = missingItems.slice(0, 5).map((c) => c.title);
      Modal.confirm({
        title: '合规终审未通过（导出风险）',
        width: 560,
        content: (
          <div>
            <Text>
              发现 {failCount} 项严重问题
              {missingItems.length > 0 ? `（含 ${missingItems.length} 条评分项完全未响应）` : ''}
              。未实质性响应可能导致该项失分甚至废标，请确认风险后再导出：
            </Text>
            {missingPreview.length > 0 && (
              <ul style={{ marginTop: 8, paddingLeft: 20, maxHeight: 280, overflow: 'auto' }}>
                {missingPreview.map((title) => (
                  <li key={title} style={{ marginBottom: 6 }}>
                    <Text strong>{title}</Text>
                    <div style={{ color: '#8c8c8c', fontSize: 12 }}>评分项覆盖：missing</div>
                  </li>
                ))}
                {missingItems.length > 5 && (
                  <li style={{ color: '#8c8c8c' }}>…另有 {missingItems.length - 5} 条未列出</li>
                )}
              </ul>
            )}
            <Text type="secondary" style={{ fontSize: 12 }}>
              完整明细可在导出后于「合规报告」中查看。
            </Text>
          </div>
        ),
        okText: '我知道风险，仍要导出 Word',
        cancelText: '取消',
        onOk: () => confirmIncompleteThenExport(),
      });
      return;
    }

    await confirmIncompleteThenExport();
  };

  const handleTreeSelect = (keys) => {
    const id = keys[0];
    if (!id || id === selected) return;
    const node = nodes.find((n) => n.id === id);
    if (node?.is_leaf !== 1) return;

    if (isDirty) {
      Modal.confirm({
        title: '有未保存的修改',
        content: '当前章节内容已修改但尚未保存，切换后将丢失这些修改。',
        okText: '放弃修改并切换',
        cancelText: '继续编辑',
        okButtonProps: { danger: true },
        onOk: () => setSelected(id),
      });
      return;
    }
    setSelected(id);
  };

  const handleDetectAiCliches = async () => {
    if (!selected || !content.trim()) {
      message.warning('章节正文为空，无法检测');
      return;
    }
    setDetectingAi(true);
    try {
      const result = await detectAiCliches(selected, content);
      const hits = result.hits || [];
      setAiHits(hits);
      if (hits.length === 0) {
        message.success('未检测到明显 AI 套话');
      } else {
        message.warning(`检测到 ${hits.length} 处疑似 AI 套话，点击下方条目可定位`);
      }
    } catch (e) {
      message.error(e.message);
    } finally {
      setDetectingAi(false);
    }
  };

  const jumpToAiHit = (hit) => {
    const el = getTextAreaEl();
    if (!el || hit.start == null || hit.end == null) return;
    el.focus();
    el.setSelectionRange(hit.start, hit.end);
    el.scrollTop = Math.max(0, (hit.start / Math.max(content.length, 1)) * el.scrollHeight - 80);
  };

  const handleSave = async () => {
    try {
      await saveChapterContent(selected, content);
      setSavedContent(content);
      message.success('已保存');
      await load({ silent: true });
    } catch (e) {
      message.error(e.message);
    }
  };

  const handleReview = async () => {
    if (!content.trim()) {
      message.warning('章节正文为空，无法验章');
      return;
    }
    setReviewing(true);
    try {
      if (isDirty) {
        await saveChapterContent(selected, content);
        setSavedContent(content);
      }
      const result = await reviewChapter(selected);
      const next = result.generated_content || content;
      setContent(next);
      setSavedContent(next);
      if (next !== content) setAiHits([]);
      if (result.review_status === 'green') {
        message.success('验章通过，本章可参与导出');
      } else {
        message.warning(`验章未通过：${formatReviewErrorsText(result.review_errors)}`);
      }
      await load({ silent: true });
    } catch (e) {
      message.error(e.message);
    } finally {
      setReviewing(false);
    }
  };

  const handleRegenerate = async () => {
    const run = async () => {
      try {
        const result = await regenerateChapter(selected);
        const next = result.generated_content || '';
        setContent(next);
        setSavedContent(next);
        setAiHits([]);
        message.success('重新生成完成');
        await load({ silent: true });
      } catch (e) {
        message.error(e.message);
      }
    };
    if (isDirty) {
      Modal.confirm({
        title: '有未保存的修改',
        content: '重新生成将覆盖当前编辑内容，是否继续？',
        okText: '继续生成',
        cancelText: '取消',
        okButtonProps: { danger: true },
        onOk: run,
      });
      return;
    }
    await run();
  };

  const openRewriteModal = () => {
    captureSelection();
    const el = getTextAreaEl();
    if (!el || el.selectionStart === el.selectionEnd || !el.value.substring(el.selectionStart, el.selectionEnd).trim()) {
      message.warning('请先在正文中拖选要改写的段落');
      return;
    }
    setRewriteInstruction('');
    setRewriteOpen(true);
  };

  const handleSelectionRewrite = async () => {
    if (!selection.text.trim()) {
      message.warning('请先选中要改写的文本');
      return;
    }
    if (!rewriteInstruction.trim()) {
      message.warning('请填写改写指令');
      return;
    }
    setRewriting(true);
    try {
      const result = await selectionRewrite(selected, {
        selected_text: selection.text,
        instruction: rewriteInstruction.trim(),
        context_before: content.substring(0, selection.start),
        context_after: content.substring(selection.end),
        selection_start: selection.start,
        selection_end: selection.end,
      });
      const next = result.generated_content || content;
      setContent(next);
      setSavedContent(next);
      if (next !== content) setAiHits([]);
      setRewriteOpen(false);
      setRewriteInstruction('');
      setSelection({ text: '', start: 0, end: 0 });
      if (result.review_status === 'green') {
        message.success('选区改写完成，验章通过');
      } else if (result.review_status === 'yellow') {
        message.warning(`改写完成，但验章未通过：${formatReviewErrorsText(result.review_errors, '请修改后点击「重新验章」')}`);
      } else {
        message.success('选区改写完成');
      }
      await load({ silent: true });
    } catch (e) {
      message.error(e.message);
    } finally {
      setRewriting(false);
    }
  };

  const handleExportDebug = async () => {
    setExportingDebug(true);
    try {
      await downloadFromApi(`/projects/${projectId}/export-debug`, `${projectId}_debug.zip`);
      message.success('调试包已导出');
    } catch (e) {
      message.error(e.message || '导出调试包失败');
    } finally {
      setExportingDebug(false);
    }
  };

  return (
    <Card title="预览与导出" className="section-card" variant="borderless" style={{ marginTop: 0 }}>
      {loading && nodes.length === 0 ? (
        <div className="preview-page-state">
          <Spin tip="加载章节…" />
        </div>
      ) : loadError ? (
        <Alert
          type="error"
          showIcon
          message="加载失败"
          description={loadError}
          action={<Button size="small" onClick={() => load({ preserveSelection: false })}>重试</Button>}
        />
      ) : leafCount === 0 ? (
        <Alert
          type="info"
          showIcon
          message="暂无可生成章节"
          description="请先返回大纲策划，完成章节结构后再生成正文。"
        />
      ) : generatedCount === 0 ? (
        <Alert
          type="info"
          showIcon
          message="尚未生成正文"
          description="当前只有章节目录，请先在内容生成页生成正文，再进行编辑和 Word 导出。"
          action={onGoGenerate ? (
            <Button size="small" type="primary" onClick={onGoGenerate}>前往内容生成</Button>
          ) : null}
        />
      ) : (
      <Row gutter={16} className="preview-page-layout">
        <Col xs={24} md={7}>
          <div className="preview-tree-panel">
            <Text type="secondary" className="preview-pane-label">章节目录</Text>
            <Tree
              treeData={treeData}
              defaultExpandAll
              selectedKeys={selected ? [selected] : []}
              onSelect={handleTreeSelect}
            />
          </div>
        </Col>
        <Col xs={24} md={17}>
          {!selected || !selectedChapter ? (
            <div className="preview-page-state preview-page-state--muted">
              <Text type="secondary">请从左侧目录选择一个叶子章节</Text>
            </div>
          ) : (
            <>
              <div className="preview-chapter-header">
                <div>
                  <Text strong style={{ fontSize: 15 }}>{selectedChapter.title}</Text>
                  <Space size="middle" style={{ marginTop: 6 }} wrap>
                    <ChapterStatusIcon status={selectedChapter.review_status} />
                    <Tag color={getReviewStatusTagColor(selectedChapter.review_status)}>
                      {selectedChapter.review_status || '未生成'}
                    </Tag>
                    <Text type="secondary">{content.length} 字</Text>
                    {isDirty && <Tag color="orange">未保存</Tag>}
                  </Space>
                </div>
                <Radio.Group
                  size="small"
                  value={splitView ? 'split' : contentMode}
                  onChange={(e) => {
                    if (e.target.value === 'split') {
                      setSplitView(true);
                    } else {
                      setSplitView(false);
                      setContentMode(e.target.value);
                    }
                  }}
                >
                  <Radio.Button value="split">分栏</Radio.Button>
                  <Radio.Button value="edit">仅编辑</Radio.Button>
                  <Radio.Button value="preview">仅预览</Radio.Button>
                </Radio.Group>
              </div>

              {selectedChapter.retrieval_warning && (
                <Alert
                  type="warning"
                  showIcon
                  message="知识库参考不足"
                  description={selectedChapter.retrieval_warning}
                  style={{ marginBottom: 12 }}
                />
              )}

              {aiHits.length > 0 && (
                <Alert
                  type="warning"
                  showIcon
                  style={{ marginBottom: 12 }}
                  message={`检测到 ${aiHits.length} 处疑似 AI 套话`}
                  description={(
                    <List
                      size="small"
                      dataSource={aiHits}
                      renderItem={(hit) => (
                        <List.Item style={{ padding: '4px 0' }}>
                          <Button type="link" size="small" style={{ padding: 0, height: 'auto' }} onClick={() => jumpToAiHit(hit)}>
                            「{hit.phrase}」
                          </Button>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {hit.category}{hit.suggestion ? ` · ${hit.suggestion}` : ''}
                          </Text>
                        </List.Item>
                      )}
                    />
                  )}
                />
              )}

              {(() => {
                const editor = (
                  <Input.TextArea
                    ref={textAreaRef}
                    rows={18}
                    value={content}
                    onChange={(e) => {
                      setContent(e.target.value);
                      setAiHits([]);
                    }}
                    onSelect={captureSelection}
                    onMouseUp={captureSelection}
                    onKeyUp={captureSelection}
                    className="preview-editor"
                  />
                );
                const preview = (
                  <div
                    className={`markdown-preview md-preview preview-pane-preview${splitView ? '' : ' preview-pane-preview--full'}`}
                    dangerouslySetInnerHTML={renderMarkdownPreview(content, chartPreviews)}
                  />
                );
                if (splitView) {
                  return (
                    <Row gutter={12} className="preview-split-row">
                      <Col span={12}>
                        <Text type="secondary" className="preview-pane-label">编辑</Text>
                        {editor}
                      </Col>
                      <Col span={12}>
                        <Text type="secondary" className="preview-pane-label">预览</Text>
                        {preview}
                      </Col>
                    </Row>
                  );
                }
                return contentMode === 'edit' ? editor : preview;
              })()}

              {selection.text ? (
                <Text type="secondary" style={{ display: 'block', marginTop: 8, fontSize: 12 }}>
                  已选中 {selection.text.length} 字
                </Text>
              ) : null}

              <div className="preview-toolbar">
                <div className="preview-toolbar-section">
                  <Text type="secondary" className="preview-toolbar-label">内容编辑</Text>
                  <div className="preview-toolbar-group">
                    <Button type="primary" ghost={isDirty} onClick={handleSave} disabled={!isDirty}>
                      {isDirty ? '保存修改' : '已保存'}
                    </Button>
                    <Button onClick={openRewriteModal} disabled={!content.trim()}>选区改写</Button>
                    <Dropdown
                      menu={{
                        items: [
                          {
                            key: 'regenerate',
                            label: '单章重新生成',
                            onClick: handleRegenerate,
                          },
                          {
                            key: 'version',
                            label: '版本历史',
                            disabled: !selected,
                            onClick: () => setVersionOpen(true),
                          },
                          {
                            key: 'prompt',
                            label: '查看提示词',
                            disabled: !selected,
                            onClick: () => setPromptOpen(true),
                          },
                          { type: 'divider' },
                          {
                            key: 'debug',
                            label: '导出调试包',
                            onClick: handleExportDebug,
                          },
                        ],
                      }}
                    >
                      <Button loading={exportingDebug}>更多</Button>
                    </Dropdown>
                  </div>
                </div>

                <div className="preview-toolbar-section">
                  <Text type="secondary" className="preview-toolbar-label">质量检查</Text>
                  <div className="preview-toolbar-group">
                    <Button loading={reviewing} onClick={handleReview} disabled={!content.trim()}>
                      重新验章
                    </Button>
                    <Dropdown
                      menu={{
                        items: [
                          {
                            key: 'ai',
                            label: '检测 AI 痕迹',
                            disabled: !content.trim(),
                            onClick: handleDetectAiCliches,
                          },
                          {
                            key: 'matrix',
                            label: '响应矩阵',
                            onClick: () => setMatrixOpen(true),
                          },
                          {
                            key: 'compliance',
                            label: '合规报告',
                            onClick: () => setComplianceOpen(true),
                          },
                        ],
                      }}
                    >
                      <Button loading={detectingAi}>检查报告</Button>
                    </Dropdown>
                  </div>
                </div>

                <div className="preview-toolbar-section preview-toolbar-section--export">
                  <Text type="secondary" className="preview-toolbar-label">文档导出</Text>
                  <div className="preview-toolbar-group">
                    <Button type="primary" loading={exporting} onClick={handleExport}>
                      导出 Word
                      {emptyChapters.length > 0
                        ? `（${emptyChapters.length} 章未生成）`
                        : yellowChapters.length > 0
                          ? `（${yellowChapters.length} 章待优化）`
                          : ''}
                    </Button>
                  </div>
                </div>
              </div>
              <Modal
                title="选区改写"
                open={rewriteOpen}
                onCancel={() => setRewriteOpen(false)}
                onOk={handleSelectionRewrite}
                confirmLoading={rewriting}
                okText="开始改写"
                destroyOnClose
              >
                <Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>
                  将只改写选中段落，不会重写整章。
                </Text>
                <Input.TextArea
                  rows={4}
                  value={selection.text}
                  readOnly
                  style={{ marginBottom: 12, background: '#fafafa' }}
                />
                <Input.TextArea
                  rows={3}
                  value={rewriteInstruction}
                  onChange={(e) => setRewriteInstruction(e.target.value)}
                  placeholder="例如：补充主变就位工序细节；改为更规范的电力术语；增加质量控制指标"
                />
              </Modal>
            </>
          )}
        </Col>
      </Row>
      )}

      <PromptInspectorDrawer
        open={promptOpen}
        onClose={() => setPromptOpen(false)}
        title={selectedChapter ? `《${selectedChapter.title}》生成提示词` : '章节生成提示词'}
        fetchPath={selected ? `/projects/${projectId}/chapters/${selected}/prompts` : null}
        hint="查看各阶段完整提示词，便于调整 writing_guidance、content_boundary 与全局事实变量。"
      />
      <ComplianceReportDrawer
        open={complianceOpen}
        onClose={() => setComplianceOpen(false)}
        projectId={projectId}
      />
      <ResponseMatrixDrawer
        open={matrixOpen}
        onClose={() => setMatrixOpen(false)}
        projectId={projectId}
      />
      <ChapterVersionDrawer
        open={versionOpen}
        chapterId={selected}
        chapterTitle={selectedChapter?.title}
        onClose={() => setVersionOpen(false)}
        onRestored={(result) => {
          const next = result.generated_content || '';
          setContent(next);
          setSavedContent(next);
          setAiHits([]);
          load({ silent: true });
        }}
      />
    </Card>
  );
}
export { PreviewExport };
