import {
  useState, useEffect, useCallback, useMemo, useRef,
  Card, Button, Tag, Space, message, Spin, Alert,
  Tree, Progress, Text,
} from '../../globals.js';

import { fetchOutline } from '../../api/outline.js';
import { fetchGenerationConfig, confirmBidFormat } from '../../api/generationConfig.js';
import {
  startBatchGenerate as apiStartBatchGenerate,
  pauseBatchGenerate as apiPauseBatchGenerate,
  generateChapter,
} from '../../api/generation.js';
import { useGenerationStream } from '../../hooks/useGenerationStream.js';
import { ChapterStatusIcon } from '../../components/icons.jsx';
import { PromptInspectorDrawer } from '../../components/PromptInspectorDrawer.jsx';
import { buildOutlineTreeData } from '../outline/helpers.jsx';
import { useChartPreviews, renderMarkdownPreview } from '../chart/preview.js';
import { GenerationConfigPanel } from './GenerationConfigPanel.jsx';
import { FormatConfirmModal } from './FormatConfirmModal.jsx';
import { parseReviewErrors, formatChapterDuration } from '../../lib/chapterStatus.js';

function GenerationPanel({
  projectId,
  projectStatus,
  durationDays,
  generationMode = 'full',
  onDone,
  onPaused,
  onStarted,
  onGenerationModeChange,
  onGoEditOutline,
  onHasGeneratedChapter,
  onGoPreview,
}) {
  const [nodes, setNodes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [batchGenerating, setBatchGenerating] = useState(false);
  const [paused, setPaused] = useState(false);
  const [singleGenerating, setSingleGenerating] = useState(new Set());
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const [chapterDurations, setChapterDurations] = useState({});
  const [outlineLocked, setOutlineLocked] = useState(false);
  const [catalogText, setCatalogText] = useState('');
  const [formatModalOpen, setFormatModalOpen] = useState(false);
  const [pendingSingleChapterId, setPendingSingleChapterId] = useState(null);
  const [formatConfirmed, setFormatConfirmed] = useState(false);
  const streamDisconnectRef = useRef(null);
  const [promptOpen, setPromptOpen] = useState(false);
  const [generationResult, setGenerationResult] = useState(null);

  const isBatchRunning = batchGenerating || projectStatus === 'generating';
  const canGenerateContent = outlineLocked && ['outline_locked', 'generating', 'done'].includes(projectStatus || '');
  const hasDoneChapters = progress.done > 0;
  const leaves = useMemo(() => nodes.filter((n) => n.is_leaf === 1), [nodes]);
  const selected = nodes.find((n) => n.id === selectedId);

  const countDone = useCallback((items) => (
    items.filter((n) => n.generated_content && n.review_status !== 'generating').length
  ), []);

  const loadOutline = useCallback(async () => {
    try {
      const [outline, config] = await Promise.all([
        fetchOutline(projectId),
        fetchGenerationConfig(projectId).catch(() => ({})),
      ]);
      const leafNodes = outline.filter((n) => n.is_leaf === 1);
      setNodes(outline);
      setCatalogText(config.catalog_text || '');
      setFormatConfirmed(!!config.format_confirmed_at);
      setOutlineLocked(outline.some((n) => n.is_locked === 1));
      setProgress({ done: countDone(leafNodes), total: leafNodes.length });
      setSelectedId((prev) => {
        if (prev && outline.some((n) => n.id === prev)) return prev;
        return leafNodes[0]?.id || null;
      });
      setLoadError(null);
      if (leafNodes.some((n) => n.generated_content && n.review_status !== 'generating')) {
        onHasGeneratedChapter?.(true);
      }
    } catch (e) {
      setLoadError(e.message || '加载大纲失败');
    } finally {
      setLoading(false);
    }
  }, [projectId, countDone, onHasGeneratedChapter]);

  useEffect(() => {
    setLoading(true);
    loadOutline();
  }, [loadOutline]);

  // 仅单章生成时轮询；批量生成由 SSE 事件驱动刷新，避免与 loadOutline 叠加
  useEffect(() => {
    if (isBatchRunning || singleGenerating.size === 0) return undefined;
    const timer = setInterval(loadOutline, 3000);
    return () => clearInterval(timer);
  }, [isBatchRunning, singleGenerating, loadOutline]);

  const updateChapter = useCallback((chapterId, fields) => {
    setNodes((prev) => prev.map((n) => (n.id === chapterId ? { ...n, ...fields } : n)));
  }, []);

  const handleStreamEvent = useCallback((data) => {
    if (data.type === 'start') {
      updateChapter(data.chapter_id, { review_status: 'generating' });
    }
    if (data.type === 'done') {
      setProgress((p) => ({ ...p, done: p.done + 1 }));
      if (data.duration_seconds != null) {
        setChapterDurations((prev) => ({
          ...prev,
          [data.chapter_id]: data.duration_seconds,
        }));
      }
      updateChapter(data.chapter_id, {
        review_status: data.review_status,
        review_errors: data.errors?.length ? data.errors : null,
        retrieval_warning: data.retrieval_warning || null,
        ...(data.preview ? { generated_content: data.preview } : {}),
      });
      if (data.review_status === 'green' || data.review_status === 'yellow') {
        onHasGeneratedChapter?.(true);
      }
      if (data.review_status === 'red') {
        const errText = (data.errors || []).slice(0, 2).join('；') || '生成失败';
        message.error(`章节生成失败：${errText}`);
      } else if (data.review_status === 'yellow' && data.errors?.length) {
        message.warning(`章节待优化：${data.errors.slice(0, 2).join('；')}`);
      }
      loadOutline();
    }
    if (data.type === 'error' && data.chapter_id) {
      setProgress((p) => ({ ...p, done: p.done + 1 }));
      updateChapter(data.chapter_id, {
        review_status: data.review_status || 'red',
        review_errors: data.message ? [data.message] : undefined,
      });
      message.error(`章节生成失败：${data.message}`);
      loadOutline();
    }
    if (data.type === 'paused') {
      setBatchGenerating(false);
      setPaused(true);
      streamDisconnectRef.current?.();
      onPaused?.();
      message.warning('生成已暂停，可在预览页修改章节后继续');
      loadOutline();
    }
    if (data.type === 'complete') {
      const compliance = data.compliance;
      let extra = '';
      if (compliance) {
        extra = compliance.passed
          ? '；合规检查已通过'
          : `；合规有 ${compliance.failure_count || 0} 项问题 / ${compliance.warning_count || 0} 条提示，请在预览页查看`;
      }
      const greenCount = data.green_count || 0;
      const yellowCount = data.yellow_count || 0;
      message.success(
        `生成完成：通过 ${greenCount}，待检 ${yellowCount}，失败 ${data.red_count}${extra}`,
      );
      streamDisconnectRef.current?.();
      setBatchGenerating(false);
      if (greenCount + yellowCount > 0) onHasGeneratedChapter?.(true);
      setGenerationResult({
        greenCount,
        yellowCount,
        redCount: data.red_count || 0,
        compliance,
      });
      onDone?.({ greenCount, yellowCount, redCount: data.red_count || 0 });
      loadOutline();
    }
    if (data.type === 'error' && !data.chapter_id) {
      message.error(data.message);
      streamDisconnectRef.current?.();
      setBatchGenerating(false);
    }
  }, [loadOutline, onDone, onPaused, onHasGeneratedChapter, updateChapter]);

  const { connect: connectStream, disconnect: disconnectStream } = useGenerationStream({
    projectId,
    active: batchGenerating && !paused,
    onEvent: handleStreamEvent,
  });
  streamDisconnectRef.current = disconnectStream;

  // 刷新或切回生成页时：服务端仍在 generating，本地 state 已重置，补连 SSE 接管进度
  useEffect(() => {
    if (projectStatus !== 'generating' || batchGenerating || paused) return undefined;
    setBatchGenerating(true);
    connectStream();
    return undefined;
  }, [projectStatus, batchGenerating, paused, connectStream]);

  const runBatchGenerate = async (resume = false) => {
    setBatchGenerating(true);
    setPaused(false);
    setGenerationResult(null);
    if (!resume) {
      setChapterDurations({});
    }
    setProgress({ done: resume ? countDone(leaves) : 0, total: leaves.length });
    try {
      connectStream();
      await apiStartBatchGenerate(projectId, resume);
      onStarted?.();
    } catch (e) {
      message.error(e.message);
      setBatchGenerating(false);
      disconnectStream();
    }
  };

  const requestBatchGenerate = (resume = false) => {
    if (!resume && !formatConfirmed && !hasDoneChapters) {
      setPendingSingleChapterId(null);
      setFormatModalOpen(true);
      return;
    }
    runBatchGenerate(resume);
  };

  const runSingleGenerate = async (chapterId) => {
    if (isBatchRunning) {
      message.warning('批量生成进行中，请稍后再单章生成');
      return;
    }
    const hadContent = !!(leaves.find((n) => n.id === chapterId)?.generated_content || '').trim();
    setSingleGenerating((prev) => new Set(prev).add(chapterId));
    setSelectedId(chapterId);
    updateChapter(chapterId, { review_status: 'generating' });
    try {
      const result = await generateChapter(projectId, chapterId);
      updateChapter(chapterId, {
        review_status: result.review_status,
        generated_content: result.generated_content,
        retrieval_warning: result.retrieval_warning || null,
      });
      setSelectedId(chapterId);
      if (result.review_status === 'green' || result.review_status === 'yellow') {
        onHasGeneratedChapter?.(true);
      }
      await loadOutline();
      message.success(
        hadContent
          ? '章节已重新生成；修改前版本已自动保存，可在「预览与导出 → 版本历史」中恢复'
          : '章节生成完成',
      );
    } catch (err) {
      updateChapter(chapterId, { review_status: 'red' });
      message.error(err.message);
    } finally {
      setSingleGenerating((prev) => {
        const next = new Set(prev);
        next.delete(chapterId);
        return next;
      });
    }
  };

  const handleFormatConfirm = async () => {
    try {
      await confirmBidFormat(projectId);
      setFormatConfirmed(true);
      setFormatModalOpen(false);
      const singleId = pendingSingleChapterId;
      setPendingSingleChapterId(null);
      if (singleId) {
        await runSingleGenerate(singleId);
      } else {
        runBatchGenerate(false);
      }
    } catch (e) {
      message.error(e.message);
    }
  };

  const pauseBatchGenerate = async () => {
    try {
      await apiPauseBatchGenerate(projectId);
      message.info('已请求暂停，当前章节完成后停止');
    } catch (e) {
      message.error(e.message);
    }
  };

  const startSingleGenerate = async (chapterId, e) => {
    e?.stopPropagation();
    if (isBatchRunning) {
      message.warning('批量生成进行中，请稍后再单章生成');
      return;
    }
    if (!formatConfirmed) {
      setPendingSingleChapterId(chapterId);
      setFormatModalOpen(true);
      return;
    }
    await runSingleGenerate(chapterId);
  };

  const statusIcon = (s) => <ChapterStatusIcon status={s} />;

  const handleTreeSelect = (keys) => {
    const id = keys[0];
    if (!id) return;
    const node = nodes.find((n) => n.id === id);
    if (node?.is_leaf === 1) setSelectedId(id);
  };

  const treeData = buildOutlineTreeData(nodes, (n) => (
    <div className="gen-tree-node">
      <Space size="small" style={{ minWidth: 0, flex: 1 }}>
        <span style={{ flexShrink: 0 }}>{statusIcon(n.review_status)}</span>
        <Text ellipsis style={{ maxWidth: 160 }}>{n.title}</Text>
        {chapterDurations[n.id] != null && (
          <Text type="secondary" style={{ fontSize: 11, flexShrink: 0 }}>
            {formatChapterDuration(chapterDurations[n.id])}
          </Text>
        )}
        {n.generated_content && <Tag color="blue" style={{ margin: 0, fontSize: 11 }}>已生成</Tag>}
      </Space>
      {n.is_leaf === 1 && (
        <Button
          type="link"
          size="small"
          style={{ flexShrink: 0, padding: '0 4px' }}
          loading={singleGenerating.has(n.id) || (isBatchRunning && n.review_status === 'generating')}
          disabled={!canGenerateContent || isBatchRunning}
          onClick={(e) => startSingleGenerate(n.id, e)}
        >
          {n.generated_content ? '重新生成' : '生成'}
        </Button>
      )}
    </div>
  ));

  const previewContent = selected?.generated_content || '';
  const chartPreviews = useChartPreviews(previewContent, durationDays);
  const isSelectedGenerating = selected?.review_status === 'generating'
    || singleGenerating.has(selectedId)
    || (isBatchRunning && selected?.review_status === 'generating');

  const statusCounts = useMemo(() => ({
    green: leaves.filter((n) => n.review_status === 'green').length,
    yellow: leaves.filter((n) => n.review_status === 'yellow').length,
    red: leaves.filter((n) => n.review_status === 'red').length,
    pending: leaves.filter((n) => !n.generated_content && n.review_status !== 'generating').length,
  }), [leaves]);
  const completionResult = generationResult || (
    projectStatus === 'done' && !isBatchRunning
      ? {
        greenCount: statusCounts.green,
        yellowCount: statusCounts.yellow,
        redCount: statusCounts.red,
        compliance: null,
      }
      : null
  );

  const selectedReviewErrors = useMemo(
    () => parseReviewErrors(selected?.review_errors),
    [selected?.review_errors],
  );

  return (
    <Card className="section-card gen-page-card" variant="borderless" style={{ marginTop: 0 }}>
      {loading && nodes.length === 0 ? (
        <div className="gen-page-preview-empty">
          <Spin tip="加载大纲…" />
        </div>
      ) : loadError && nodes.length === 0 ? (
        <Alert
          type="error"
          showIcon
          message="加载失败"
          description={loadError}
          action={<Button size="small" onClick={() => { setLoading(true); loadOutline(); }}>重试</Button>}
        />
      ) : (
      <>
      {!canGenerateContent && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message={outlineLocked && projectStatus === 'planning' ? '项目状态未同步，无法生成' : '大纲尚未锁定'}
          description={
            outlineLocked && projectStatus === 'planning'
              ? '章节虽已锁定，但项目仍为 planning。请返回「大纲策划」重新点击「锁定并继续」同步状态。'
              : '请返回「大纲策划」步骤，完成 AI 深化并锁定大纲后再开始生成。'
          }
          action={onGoEditOutline ? (
            <Button size="small" onClick={onGoEditOutline}>去大纲策划</Button>
          ) : null}
        />
      )}

      {completionResult && (
        <Alert
          type={completionResult.redCount > 0 ? 'warning' : 'success'}
          showIcon
          className="generation-result-summary"
          message="正文生成已完成"
          description={`通过 ${completionResult.greenCount} 章，待优化 ${completionResult.yellowCount} 章，失败 ${completionResult.redCount} 章${completionResult.compliance?.passed ? '；合规检查已通过' : ''}`}
          action={(completionResult.greenCount + completionResult.yellowCount > 0) && onGoPreview ? (
            <Button type="primary" onClick={onGoPreview}>进入预览与导出</Button>
          ) : null}
        />
      )}

      {leaves.length === 0 ? (
        <Alert message="暂无叶子章节，请先完成大纲策划" type="info" showIcon />
      ) : (
        <div className="gen-page-layout">
          <div className="gen-page-left">
            <div className="gen-page-section-title">
              <div className="shuxian" />
              <span>生成配置</span>
            </div>
            <GenerationConfigPanel
              projectId={projectId}
              disabled={!canGenerateContent || isBatchRunning}
              generationMode={generationMode}
              onGenerationModeChange={(mode) => {
                onGenerationModeChange?.(mode);
                loadOutline();
              }}
              onConfigUpdated={(_cfg, meta) => {
                // 篇幅滑块静默保存时不重载大纲，避免整块配置区抖动
                if (meta?.quiet) return;
                if (meta?.outlineChanged) loadOutline();
              }}
            />

            <div className="gen-page-control">
              <div className="generation-progress-block generation-progress-block--compact">
                <div className="generation-progress-label">
                  <Text strong>章节进度</Text>
                  <Text type="secondary">{progress.done} / {progress.total}</Text>
                </div>
                <Progress
                  percent={progress.total ? Math.round((progress.done / progress.total) * 100) : 0}
                  status={isBatchRunning ? 'active' : 'normal'}
                  strokeColor="#2563eb"
                  size="small"
                />
                <div className="generation-legend">
                  <span className="generation-legend-item"><ChapterStatusIcon status="green" /> {statusCounts.green}</span>
                  <span className="generation-legend-item"><ChapterStatusIcon status="yellow" /> {statusCounts.yellow}</span>
                  <span className="generation-legend-item"><ChapterStatusIcon status="red" /> {statusCounts.red}</span>
                  <span className="generation-legend-item"><ChapterStatusIcon status="pending" /> {statusCounts.pending}</span>
                </div>
              </div>

              <Space className="gen-page-actions" wrap>
                {!isBatchRunning && !paused && !hasDoneChapters && (
                  <Button
                    type="primary"
                    className="generate-btn-primary"
                    onClick={() => requestBatchGenerate(false)}
                    disabled={!canGenerateContent || leaves.length === 0}
                  >
                    生成标书
                  </Button>
                )}
                {isBatchRunning && (
                  <Button type="primary" danger onClick={pauseBatchGenerate}>暂停生成</Button>
                )}
                {paused && (
                  <Button type="primary" onClick={() => requestBatchGenerate(true)}>继续生成</Button>
                )}
                {!isBatchRunning && !paused && hasDoneChapters && (
                  <Button onClick={() => runBatchGenerate(true)} disabled={!canGenerateContent}>
                    重新生成未完成章节
                  </Button>
                )}
              </Space>
            </div>

            <div className="gen-page-section-title gen-page-section-title--compact">
              <div className="shuxian" />
              <span>生成目录</span>
            </div>
            <div className="gen-page-tree-wrap">
              <Tree
                treeData={treeData}
                defaultExpandAll
                selectedKeys={selectedId ? [selectedId] : []}
                onSelect={handleTreeSelect}
              />
            </div>

            <p className="gen-ai-hint">本标书由 AI 生成，需要人工审核，请注意甄别。</p>
          </div>

          <div className="gen-page-right">
            <div className="gen-page-section-title">
              <div className="shuxian" />
              <span>生成内容预览</span>
              <Tag color="default">只读</Tag>
              {selected && (
                <Text type="secondary" className="gen-page-preview-subtitle">
                  {selected.title}
                </Text>
              )}
              {selected && (
                <Button
                  size="small"
                  type="link"
                  className="gen-page-preview-prompt"
                  onClick={() => setPromptOpen(true)}
                >
                  查看提示词
                </Button>
              )}
            </div>
            <div className="gen-page-preview">
              {!selected ? (
                <Text type="secondary">请从左侧目录选择章节</Text>
              ) : isSelectedGenerating ? (
                <div className="gen-page-preview-empty">
                  <Spin tip="正在生成…" />
                </div>
              ) : (
                <>
                  {(selected.review_status === 'yellow' || selected.review_status === 'red')
                    && selectedReviewErrors.length > 0 && (
                    <Alert
                      type={selected.review_status === 'red' ? 'error' : 'warning'}
                      showIcon
                      style={{ marginBottom: 12 }}
                      message={selected.review_status === 'red' ? '生成失败' : '待优化'}
                      description={
                        <ul style={{ margin: 0, paddingLeft: 18 }}>
                          {selectedReviewErrors.slice(0, 6).map((err, i) => (
                            <li key={`${i}-${err}`}>{err}</li>
                          ))}
                        </ul>
                      }
                    />
                  )}
                  {previewContent ? (
                    <div
                      className="md-preview"
                      dangerouslySetInnerHTML={renderMarkdownPreview(previewContent, chartPreviews)}
                    />
                  ) : (
                    <Text type="secondary">《{selected.title}》尚未生成</Text>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}
      </>
      )}

      <FormatConfirmModal
        open={formatModalOpen}
        nodes={nodes}
        catalogText={catalogText}
        onConfirm={handleFormatConfirm}
        onCancel={() => {
          setPendingSingleChapterId(null);
          setFormatModalOpen(false);
        }}
        onGoEdit={() => {
          setPendingSingleChapterId(null);
          setFormatModalOpen(false);
          onGoEditOutline?.();
        }}
      />

      <PromptInspectorDrawer
        open={promptOpen}
        onClose={() => setPromptOpen(false)}
        title={selected ? `《${selected.title}》生成提示词` : '章节生成提示词'}
        fetchPath={selected ? `/projects/${projectId}/chapters/${selected.id}/prompts` : null}
        hint="可查看写作规划、正文撰写、软质检各阶段提示词。"
      />
    </Card>
  );
}

export { GenerationPanel };
