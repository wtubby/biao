import {
  useState, useEffect, useCallback, useMemo, useRef,
  Card, message, Spin, Alert, Badge, Menu, Tooltip, Dragger,
} from '../../globals.js';

import { apiFetch, API, formatApiError } from '../../api/client.js';
import { fetchOutline } from '../../api/outline.js';
import {
  fetchRequirements,
  confirmAllRequirements,
  computeRequirementStats,
} from '../../api/requirements.js';
import { WORKFLOW_STEPS, STEP_ORDER, getNextAccessibleStep } from '../../constants/workflow.js';
import { PROJECT_STATUS_LABELS } from '../../constants/project.js';
import { Icon } from '../../components/icons.jsx';
import {
  StepFooter, getWorkflowProgressByStatus, WorkspaceBrand, WorkspaceProjectHeader, WorkspaceSidebarFooter,
} from '../../components/layout.jsx';
import { PageSuspense } from '../../components/PageSuspense.jsx';
import {
  TenderDetailPanel,
  CommercialPanel,
  GlobalFactsPanel,
  OutlineEditor,
  GenerationPanel,
  PreviewExport,
  SourcePreviewPane,
  ParseProgressPanel,
} from './lazyPanels.js';

function ProjectWorkspace({ project: initialProject, onBack, onOpenSettings }) {
  const [project, setProject] = useState(initialProject);
  const [currentPage, setCurrentPage] = useState('upload');
  const [uploading, setUploading] = useState(false);
  const [loadingProject, setLoadingProject] = useState(true);
  const [stats, setStats] = useState({ total: 0, confirmed: 0, risk: 0, riskConfirmed: 0 });
  const [confirming, setConfirming] = useState(false);
  const [parseTimedOut, setParseTimedOut] = useState(false);
  const [outlineLocked, setOutlineLocked] = useState(false);
  const [hasGeneratedChapter, setHasGeneratedChapter] = useState(false);
  const [sourceHighlight, setSourceHighlight] = useState(null);
  const parseTimedOutRef = useRef(false);

  useEffect(() => {
    if (currentPage !== 'confirm') {
      setSourceHighlight(null);
    }
  }, [currentPage]);

  const globalsFilled = useMemo(() => {
    const needsVoltage = !project.engineering_domain || project.engineering_domain === '电力工程';
    return !!(
      project.name
      && project.project_type
      && (!needsVoltage || project.voltage_level)
      && project.duration_days
      && project.location
    );
  }, [project]);

  const syncPageFromProject = useCallback(async (p) => {
    try {
      const reqs = await fetchRequirements(p.id);
      setStats(computeRequirementStats(reqs));
    } catch (_) { /* ignore */ }

    try {
      const outline = await fetchOutline(p.id);
      setOutlineLocked(outline.some((n) => n.is_locked === 1));
      // 有已生成正文即可进预览（含待优化黄章），不要求必须绿章
      setHasGeneratedChapter(outline.some(
        (n) => n.is_leaf === 1 && n.generated_content && n.review_status !== 'generating',
      ));
    } catch (_) { /* ignore */ }

    if (p.status === 'parsing') {
      setCurrentPage('upload');
    } else if (p.status === 'draft') {
      setCurrentPage('upload');
    } else if (p.status === 'confirming') {
      setCurrentPage('confirm');
    } else if (p.status === 'planning') {
      setCurrentPage('outline');
    } else if (p.status === 'outline_locked' || p.status === 'generating') {
      setCurrentPage('generate');
    } else if (p.status === 'done') {
      setCurrentPage('preview');
    }
    return p;
  }, []);

  const pollProject = useCallback(async () => {
    try {
      const p = await apiFetch(`/projects/${initialProject.id}`);
      setProject(p);
      await syncPageFromProject(p);
    } catch (_) { /* ignore poll errors */ }
  }, [initialProject.id, syncPageFromProject]);

  useEffect(() => {
    let cancelled = false;
    setLoadingProject(true);
    setUploading(false);
    setCurrentPage('upload');

    (async () => {
      try {
        const p = await apiFetch(`/projects/${initialProject.id}`);
        if (cancelled) return;
        setProject(p);
        await syncPageFromProject(p);
      } catch (_) {
        if (!cancelled) {
          setProject(initialProject);
          await syncPageFromProject(initialProject);
        }
      } finally {
        if (!cancelled) setLoadingProject(false);
      }
    })();

    return () => { cancelled = true; };
  }, [initialProject.id]);

  useEffect(() => {
    // 批量生成由 GenerationPanel SSE 驱动状态；此处仅轮询解析中
    if (project.status !== 'parsing') {
      parseTimedOutRef.current = false;
      setParseTimedOut(false);
      return undefined;
    }
    const timer = setInterval(() => {
      if (parseTimedOutRef.current) return;
      pollProject();
    }, 2000);
    parseTimedOutRef.current = false;
    setParseTimedOut(false);
    const timeout = setTimeout(() => {
      parseTimedOutRef.current = true;
      setParseTimedOut(true);
    }, 5 * 60 * 1000);
    return () => {
      clearInterval(timer);
      clearTimeout(timeout);
    };
  }, [project.status, pollProject]);

  const handleUpload = async (file) => {
    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await fetch(`${API}/projects/${project.id}/upload`, { method: 'POST', body: formData });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(formatApiError(err));
      }
      message.success('文件已上传，正在解析...');
      const suffix = (file.name || '').split('.').pop()?.toLowerCase();
      const sourceType = suffix === 'pdf' || suffix === 'docx' ? suffix : null;
      setProject((p) => ({
        ...p,
        status: 'parsing',
        has_source: true,
        source_type: sourceType || p.source_type,
        parse_error: null,
        parse_progress: {
          stage: 'reading',
          label: '阅读文档段落',
          message: '文件已上传，正在阅读文档…',
          percent: 15,
        },
      }));
      setParseTimedOut(false);
      parseTimedOutRef.current = false;
      setCurrentPage('upload');
    } catch (e) {
      message.error(e.message || '上传失败');
    } finally {
      setUploading(false);
    }
    return false;
  };

  const handleConfirmAll = async () => {
    setConfirming(true);
    try {
      const result = await confirmAllRequirements(project.id);
      message.success('全部确认完成，已进入大纲策划阶段');
      setProject((p) => ({ ...p, status: result.status }));
      setCurrentPage('outline');
    } catch (e) {
      message.error(e.message);
    } finally {
      setConfirming(false);
    }
  };

  const canConfirmAll = stats.risk === stats.riskConfirmed && globalsFilled;
  const pendingCount = stats.total - stats.confirmed;
  // 评分项可选：解析完成后即可进入确认页维护工程信息
  const canGoConfirm = project.status !== 'parsing' && project.status !== 'draft';
  const canGoFacts = canGoConfirm;
  // 须先 confirm-all 进入 planning（或更后状态），与后端 ALLOW_OUTLINE_* 对齐
  const outlineReady = ['planning', 'outline_locked', 'generating', 'done'].includes(project.status);
  const canGoOutline = canGoConfirm && stats.risk === stats.riskConfirmed && globalsFilled && outlineReady;
  // 以项目状态为准，避免「节点已锁但 status 仍为 planning」时误开生成入口
  const canGoGenerate = ['outline_locked', 'generating', 'done'].includes(project.status);
  // 大纲锁定后即可进预览：黄章可验章/改写；无正文时预览页会提示
  const canGoPreview = canGoGenerate || hasGeneratedChapter;
  const canGoCommercial = canGoConfirm && project.bid_scope === 'technical_commercial';
  const generatingCount = project.status === 'generating' ? 1 : 0;

  const stepAccess = {
    upload: true,
    confirm: canGoConfirm,
    commercial: canGoCommercial,
    facts: canGoFacts,
    outline: canGoOutline,
    generate: canGoGenerate,
    preview: canGoPreview,
  };

  const stepUnlockHint = {
    confirm: '请先上传并完成招标文件解析',
    commercial: '可选步骤：请先在确认页开启「技术标+商务标」',
    facts: '可选步骤：请先上传并完成招标文件解析；工程核心参数请在确认步骤维护',
    outline: '须在确认步骤保存完整工程信息，并点击「进入大纲策划」（评分项可选）',
    generate: '请先在大纲策划中点击「锁定并继续」，将项目状态推进到可生成（锁定后仍可返回调整）',
    preview: '请先在大纲策划中锁定结构，即可进入预览验章与导出',
  };

  const currentStepIndex = STEP_ORDER.indexOf(currentPage);
  const baseProgress = getWorkflowProgressByStatus(project.status);
  const workflowDone = Math.max(baseProgress.done, currentStepIndex);
  const workflowProgress = {
    ...baseProgress,
    done: workflowDone,
    percent: Math.round((workflowDone / baseProgress.total) * 100),
  };

  const goPrev = () => {
    if (currentStepIndex > 0) setCurrentPage(STEP_ORDER[currentStepIndex - 1]);
  };

  const nextStepKey = getNextAccessibleStep(currentPage, stepAccess);
  const nextStepAccessible = !!nextStepKey;

  const goNext = () => {
    if (currentPage === 'confirm') return;
    if (nextStepKey) {
      setCurrentPage(nextStepKey);
      return;
    }
    if (currentStepIndex < STEP_ORDER.length - 1) {
      message.info(stepUnlockHint[STEP_ORDER[currentStepIndex + 1]] || '请先完成当前步骤');
    }
  };

  return (
    <div className="workspace-layout workspace-layout--fullscreen">
      <div className="workspace-sidebar">
        <WorkspaceBrand />
        <Menu
          mode="inline"
          selectedKeys={[currentPage]}
          items={[
            {
              key: 'projects',
              label: (
                <span className="workspace-menu-label">
                  <Icon name="list" size={15} />
                  <span>项目列表</span>
                </span>
              ),
              onClick: () => onBack?.(),
            },
            { type: 'divider', className: 'workspace-menu-divider' },
            ...WORKFLOW_STEPS.map((step) => {
              const stepIndex = STEP_ORDER.indexOf(step.key);
              const disabled = !stepAccess[step.key];
              const isDone = stepIndex < currentStepIndex;
              const label = (
                <span className={`workspace-menu-label${isDone ? ' is-done' : ''}${step.optional ? ' is-optional' : ''}`}>
                  <Icon name={step.icon} size={15} />
                  <span>{step.label}</span>
                  {step.optional && (
                    <span className="workspace-menu-optional">可选</span>
                  )}
                  {isDone && !step.optional && (
                    <span className="workspace-menu-check">
                      <Icon name="success" size={14} />
                    </span>
                  )}
                  {step.key === 'confirm' && pendingCount > 0 && (
                    <Badge count={pendingCount} style={{ marginLeft: 4 }} />
                  )}
                  {step.key === 'generate' && generatingCount > 0 && (
                    <Badge status="processing" style={{ marginLeft: 4 }} />
                  )}
                </span>
              );
              return {
                key: step.key,
                label: disabled && stepUnlockHint[step.key]
                  ? <Tooltip title={stepUnlockHint[step.key]} placement="right">{label}</Tooltip>
                  : step.optional
                    ? <Tooltip title={step.description} placement="right">{label}</Tooltip>
                    : label,
                disabled,
                onClick: () => { if (!disabled) setCurrentPage(step.key); },
              };
            }),
          ]}
        />
        <WorkspaceSidebarFooter onOpenSettings={onOpenSettings} />
      </div>

      <div className="workspace-main">
        <WorkspaceProjectHeader
          projectName={project.name}
          statusText={PROJECT_STATUS_LABELS[project.status] || project.status}
          workflowProgress={workflowProgress}
        />
        <div className="workspace-main-scroll">
        <PageSuspense>
        <div className="workspace-main-content">
      {currentPage === 'upload' && (
        <div className="parse-dual-layout">
          <Card
            title="招标原文"
            className="section-card parse-dual-left"
            variant="borderless"
            style={{ marginTop: 0 }}
          >
            <div className="source-preview-card-body">
              <Spin spinning={loadingProject} tip="加载项目信息...">
                <SourcePreviewPane
                  projectId={project.id}
                  hasSource={!!project.has_source}
                  sourceType={project.source_type}
                />
              </Spin>
            </div>
          </Card>

          <Card
            title="上传与解析"
            className="section-card parse-dual-right"
            variant="borderless"
            style={{ marginTop: 0 }}
          >
            {project.parse_error && project.status !== 'parsing' && (
              <Alert
                type="error"
                showIcon
                message="上次解析失败，请重新上传文件"
                description={project.parse_error}
                style={{ marginBottom: 16 }}
              />
            )}
            <Spin spinning={uploading} tip="正在上传文件...">
              <div className="upload-dragger-wrap">
                <Dragger
                  accept=".pdf,.docx"
                  showUploadList={false}
                  beforeUpload={handleUpload}
                  disabled={loadingProject || uploading || project.status === 'parsing'}
                >
                  <div className="upload-icon-wrap">
                    <Icon name="upload" size={40} />
                  </div>
                  <p style={{ fontSize: 15, fontWeight: 500, margin: '0 0 6px' }}>
                    {project.status === 'parsing' ? '解析进行中，请稍候' : '点击或拖拽上传招标文件'}
                  </p>
                  <p style={{ color: '#6b7280', margin: 0, fontSize: 13 }}>
                    支持 PDF（带文字层）和 DOCX；解析完成后将自动进入确认步骤
                  </p>
                </Dragger>
              </div>
            </Spin>
            <Alert
              type="warning"
              showIcon
              style={{ marginTop: 12, marginBottom: 16 }}
              message="PDF 须为文字层版本（非扫描件）。扫描件请先 OCR 后再上传。"
            />
            <ParseProgressPanel
              status={project.status}
              parseProgress={project.parse_progress}
              parseError={project.parse_error}
              parseTimedOut={parseTimedOut}
              uploading={uploading}
            />
          </Card>
        </div>
      )}

      {currentPage === 'confirm' && project.status !== 'draft' && (
        <div className="parse-dual-layout confirm-dual-layout">
          <Card
            title="核对检查项"
            className="section-card parse-dual-right confirm-dual-form"
            variant="borderless"
            style={{ marginTop: 0 }}
          >
            {project.parse_error && (
              <Alert type="error" showIcon message="解析失败" description={project.parse_error} style={{ marginBottom: 16 }} />
            )}
            <TenderDetailPanel
              projectId={project.id}
              project={project}
              onProjectSaved={setProject}
              onStatsChange={setStats}
              onLocateSource={setSourceHighlight}
              activeLocateKey={sourceHighlight?.key}
            />
          </Card>
          <Card
            title="招标原文"
            className="section-card parse-dual-left confirm-dual-preview"
            variant="borderless"
            style={{ marginTop: 0 }}
          >
            <div className="source-preview-card-body">
              <SourcePreviewPane
                projectId={project.id}
                hasSource={!!project.has_source}
                sourceType={project.source_type}
                highlightTarget={sourceHighlight}
              />
            </div>
          </Card>
        </div>
      )}

      {currentPage === 'facts' && (
        <GlobalFactsPanel projectId={project.id} />
      )}

      {currentPage === 'commercial' && (
        <CommercialPanel
          projectId={project.id}
          onStatusChange={(data) => {
            if (data?.bid_scope) {
              setProject((p) => ({ ...p, bid_scope: data.bid_scope }));
            }
          }}
        />
      )}

      {currentPage === 'outline' && (
        <OutlineEditor
          projectId={project.id}
          projectStatus={project.status}
          targetPages={project.target_pages ?? 40}
          generationMode={project.generation_mode || 'full'}
          onGenerationModeChange={(mode) => setProject((p) => ({ ...p, generation_mode: mode }))}
          onLocked={(result) => {
            setProject((p) => ({ ...p, status: result?.status || 'outline_locked' }));
            setOutlineLocked(true);
          }}
        />
      )}

      {currentPage === 'generate' && (
        <GenerationPanel
          projectId={project.id}
          projectStatus={project.status}
          durationDays={project.duration_days}
          generationMode={project.generation_mode || 'full'}
          onGenerationModeChange={(mode) => setProject((p) => ({ ...p, generation_mode: mode }))}
          onGoEditOutline={() => setCurrentPage('outline')}
          onHasGeneratedChapter={() => setHasGeneratedChapter(true)}
          onStarted={() => setProject((p) => ({ ...p, status: 'generating' }))}
          onDone={({ greenCount = 0, yellowCount = 0 } = {}) => {
            setProject((p) => ({ ...p, status: 'done' }));
            // 绿章或待优化黄章均可进入预览做验章/改写
            if (greenCount + yellowCount > 0) {
              setHasGeneratedChapter(true);
              setCurrentPage('preview');
            }
          }}
          onPaused={() => setProject((p) => ({ ...p, status: 'outline_locked' }))}
        />
      )}

      {currentPage === 'preview' && (
        <PreviewExport
          projectId={project.id}
          durationDays={project.duration_days}
          bidScope={project.bid_scope || 'technical'}
        />
      )}
        </div>
        </PageSuspense>
        </div>

        <div className="workspace-main-footer">
        <StepFooter
          extra={currentPage === 'confirm'
            ? `已确认 ${stats.confirmed}/${stats.total}，刚性风险项 ${stats.riskConfirmed}/${stats.risk}`
            : currentPage === 'facts'
              ? '可选步骤，可随时跳过'
              : currentPage === 'outline' && canGoGenerate
                ? '结构已确认，可进入内容生成'
                : currentPage === 'outline'
                  ? '完成定目录 → 深化审核 → 锁定后，即可进入内容生成'
                  : `步骤 ${currentStepIndex + 1} / ${STEP_ORDER.length}`}
          onPrev={currentStepIndex > 0 ? goPrev : null}
          onNext={currentPage === 'preview'
            ? null
            : (currentPage === 'confirm' ? handleConfirmAll : goNext)}
          nextLabel={
            currentPage === 'confirm'
              ? '核对无误，进入大纲策划'
              : currentPage === 'facts'
                ? '跳过，进入大纲'
                : currentPage === 'outline' && canGoGenerate
                  ? '下一步：内容生成'
                  : currentPage === 'outline'
                    ? '请先锁定大纲'
                    : '下一步'
          }
          nextDisabled={currentPage === 'confirm'
            ? (!canConfirmAll || project.status === 'planning')
            : !nextStepAccessible}
          nextLoading={currentPage === 'confirm' ? confirming : false}
        />
        </div>
      </div>
    </div>
  );
}
export { ProjectWorkspace };
