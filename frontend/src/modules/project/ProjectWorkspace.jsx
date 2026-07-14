import {
  useState, useEffect, useCallback, useMemo, useRef,
  Card, message, Spin, Alert, Badge, Menu, Tooltip,
} from '../../globals.js';

import { apiFetch, API, formatApiError } from '../../api/client.js';
import { fetchOutline } from '../../api/outline.js';
import {
  fetchRequirements,
  confirmAllRequirements,
  computeRequirementStats,
} from '../../api/requirements.js';
import {
  WORKFLOW_STEPS,
  STEP_ORDER,
  getNextAccessibleStep,
  getPageByProjectStatus,
  isWorkflowStepDone,
} from '../../constants/workflow.js';
import { isWorkflowStepKey } from '../../lib/hashRoute.js';
import { MacroWorkflowBar } from '../../components/MacroWorkflowBar.jsx';
import { getMacroWorkflowState } from '../../constants/macroWorkflow.js';
import { PROJECT_STATUS_LABELS } from '../../constants/project.js';
import { Icon } from '../../components/icons.jsx';
import {
  StepFooter, getWorkflowProgressByStatus, WorkspaceBrand, WorkspaceProjectHeader, WorkspaceSidebarFooter,
} from '../../components/layout.jsx';
import { PageSuspense } from '../../components/PageSuspense.jsx';
import {
  TenderDetailPanel,
  OutlineEditor,
  GenerationPanel,
  PreviewExport,
  SourcePreviewPane,
} from './lazyPanels.js';
import { UploadConfigPanel } from '../parse/UploadConfigPanel.jsx';
import { UploadStepPanel } from '../parse/UploadStepPanel.jsx';

function ProjectWorkspace({
  project: initialProject,
  routePage = null,
  onPageChange,
  onBack,
  onOpenSettings,
}) {
  const [project, setProject] = useState(initialProject);
  const [currentPage, setCurrentPage] = useState(() => (
    isWorkflowStepKey(routePage) ? routePage : getPageByProjectStatus(initialProject.status)
  ));
  const [uploading, setUploading] = useState(false);
  const [loadingProject, setLoadingProject] = useState(true);
  const [stats, setStats] = useState({ total: 0, confirmed: 0, risk: 0, riskConfirmed: 0 });
  const [confirming, setConfirming] = useState(false);
  const [parseTimedOut, setParseTimedOut] = useState(false);
  const [outlineLocked, setOutlineLocked] = useState(false);
  const [hasGeneratedChapter, setHasGeneratedChapter] = useState(false);
  const [sourceHighlight, setSourceHighlight] = useState(null);
  const [confirmWizardStep, setConfirmWizardStep] = useState(1);
  const parseTimedOutRef = useRef(false);
  const confirmWizardInitRef = useRef(false);
  const onPageChangeRef = useRef(onPageChange);
  const routeValidatedRef = useRef(false);

  useEffect(() => {
    onPageChangeRef.current = onPageChange;
  }, [onPageChange]);

  const goPage = useCallback((page, { replace = false } = {}) => {
    if (!isWorkflowStepKey(page)) return;
    setCurrentPage(page);
    onPageChangeRef.current?.(page, { replace });
  }, []);

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

  useEffect(() => {
    if (currentPage !== 'confirm') {
      setSourceHighlight(null);
      confirmWizardInitRef.current = false;
      return;
    }
    if (confirmWizardInitRef.current || loadingProject) return;
    confirmWizardInitRef.current = true;
    if (!globalsFilled) {
      setConfirmWizardStep(1);
    } else if (stats.risk > 0 && stats.risk !== stats.riskConfirmed) {
      setConfirmWizardStep(3);
    } else {
      setConfirmWizardStep(2);
    }
  }, [currentPage, loadingProject, globalsFilled, stats.risk, stats.riskConfirmed]);

  const loadWorkspaceMeta = useCallback(async (p) => {
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
  }, []);

  const pollProject = useCallback(async () => {
    try {
      const p = await apiFetch(`/projects/${initialProject.id}`);
      setProject(p);
      await loadWorkspaceMeta(p);
      if (p.status !== 'parsing') {
        goPage(getPageByProjectStatus(p.status), { replace: true });
      }
    } catch (_) { /* ignore poll errors */ }
  }, [initialProject.id, loadWorkspaceMeta, goPage]);

  useEffect(() => {
    let cancelled = false;
    setLoadingProject(true);
    setUploading(false);
    routeValidatedRef.current = false;
    const initialPage = isWorkflowStepKey(routePage)
      ? routePage
      : getPageByProjectStatus(initialProject.status);
    setCurrentPage(initialPage);
    onPageChangeRef.current?.(initialPage, { replace: true });

    (async () => {
      try {
        const p = await apiFetch(`/projects/${initialProject.id}`);
        if (cancelled) return;
        setProject(p);
        await loadWorkspaceMeta(p);
      } catch (_) {
        if (!cancelled) {
          setProject(initialProject);
          await loadWorkspaceMeta(initialProject);
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
      goPage('upload', { replace: true });
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
      goPage('outline');
    } catch (e) {
      message.error(e.message);
    } finally {
      setConfirming(false);
    }
  };

  const canConfirmAll = stats.risk === stats.riskConfirmed && globalsFilled;

  const confirmBlockReason = useMemo(() => {
    if (currentPage !== 'confirm') return null;
    if (project.status === 'planning') {
      return '项目已进入大纲策划阶段，请直接前往「大纲」页面';
    }
    const missingGlobals = [];
    const needsVoltage = !project.engineering_domain || project.engineering_domain === '电力工程';
    if (!project.name) missingGlobals.push('项目名称');
    if (!project.project_type) missingGlobals.push('项目类型');
    if (needsVoltage && !project.voltage_level) missingGlobals.push('电压等级');
    if (!project.duration_days) missingGlobals.push('工期');
    if (!project.location) missingGlobals.push('地点');
    if (missingGlobals.length > 0) {
      return `请先在「工程信息」表单中补全并保存：${missingGlobals.join('、')}`;
    }
    if (stats.risk !== stats.riskConfirmed) {
      return `还有 ${stats.risk - stats.riskConfirmed} 个刚性风险项未确认，请在评分项表格中逐一点击「确认」`;
    }
    return null;
  }, [currentPage, project, stats]);

  const pendingCount = stats.total - stats.confirmed;
  // 评分项可选：解析完成后即可进入确认页维护工程信息
  const canGoConfirm = project.status !== 'parsing' && project.status !== 'draft';
  // 须先 confirm-all 进入 planning（或更后状态），与后端 ALLOW_OUTLINE_* 对齐
  const outlineReady = ['planning', 'outline_locked', 'generating', 'done'].includes(project.status);
  const canGoOutline = canGoConfirm && stats.risk === stats.riskConfirmed && globalsFilled && outlineReady;
  // 以项目状态为准，避免「节点已锁但 status 仍为 planning」时误开生成入口
  const canGoGenerate = ['outline_locked', 'generating', 'done'].includes(project.status);
  // 大纲锁定后即可进预览：黄章可验章/改写；无正文时预览页会提示
  const canGoPreview = canGoGenerate || hasGeneratedChapter;
  const generatingCount = project.status === 'generating' ? 1 : 0;

  const stepUnlockHint = {
    confirm: '请先上传并完成招标文件解析',
    outline: '须在确认步骤保存完整工程信息，并点击「进入大纲策划」（评分项可选）',
    generate: '请先在大纲策划中点击「锁定并继续」，将项目状态推进到可生成（锁定后仍可返回调整）',
    preview: '请先在大纲策划中锁定结构，即可进入预览验章与导出',
  };

  const stepAccess = {
    upload: true,
    confirm: canGoConfirm,
    outline: canGoOutline,
    generate: canGoGenerate,
    preview: canGoPreview,
  };

  // URL 指定了尚未解锁的步骤时，回落到当前状态对应页
  useEffect(() => {
    if (loadingProject || routeValidatedRef.current) return;
    routeValidatedRef.current = true;
    if (isWorkflowStepKey(currentPage) && stepAccess[currentPage]) {
      onPageChangeRef.current?.(currentPage, { replace: true });
      return;
    }
    const fallback = getPageByProjectStatus(project.status);
    goPage(fallback, { replace: true });
  }, [loadingProject, currentPage, project.status, canGoConfirm, canGoOutline, canGoGenerate, canGoPreview, goPage]);

  // 浏览器前进/后退：同步路由步
  useEffect(() => {
    if (loadingProject || !isWorkflowStepKey(routePage) || routePage === currentPage) return;
    if (stepAccess[routePage]) {
      setCurrentPage(routePage);
      return;
    }
    message.info(stepUnlockHint[routePage] || '该步骤尚未解锁');
    goPage(currentPage, { replace: true });
  }, [routePage, loadingProject, canGoConfirm, canGoOutline, canGoGenerate, canGoPreview, currentPage, goPage]);

  const currentStepIndex = STEP_ORDER.indexOf(currentPage);
  const workflowProgress = getWorkflowProgressByStatus(project.status);
  const macroWorkflowSteps = getMacroWorkflowState(currentPage, stepAccess, project.status);

  const goPrev = () => {
    if (currentPage === 'confirm' && confirmWizardStep > 1) {
      setConfirmWizardStep((s) => s - 1);
      return;
    }
    if (currentStepIndex > 0) goPage(STEP_ORDER[currentStepIndex - 1]);
  };

  const confirmWizardNextLabels = {
    1: '下一步：资格审查',
    2: '下一步：评分要求',
    3: '下一步：商务与技术要求',
    4: '核对无误，进入大纲策划',
  };

  const confirmWizardExtras = {
    1: globalsFilled ? '工程信息已完整，可进入资格审查' : '请填写并保存工程信息与投标人须知',
    2: '请在右侧招标原文中逐条核对资格性与废标条款',
    3: `已确认 ${stats.confirmed}/${stats.total}，刚性风险项 ${stats.riskConfirmed}/${stats.risk}`,
    4: '补充商务/技术要求文本后，可进入大纲策划',
  };

  const confirmNextDisabled = useMemo(() => {
    if (currentPage !== 'confirm') return false;
    if (project.status === 'planning') return true;
    if (confirmWizardStep === 1) return !globalsFilled;
    if (confirmWizardStep === 3) return stats.risk > 0 && stats.risk !== stats.riskConfirmed;
    if (confirmWizardStep === 4) return !canConfirmAll;
    return false;
  }, [currentPage, confirmWizardStep, globalsFilled, stats, canConfirmAll, project.status]);

  const confirmNextDisabledReason = useMemo(() => {
    if (currentPage !== 'confirm' || !confirmNextDisabled) return null;
    if (confirmWizardStep === 1) return confirmBlockReason;
    if (confirmWizardStep === 3 && stats.risk > 0 && stats.risk !== stats.riskConfirmed) {
      return `还有 ${stats.risk - stats.riskConfirmed} 个刚性风险项未确认，请在技术评分表格中逐一点击「确认」`;
    }
    if (confirmWizardStep === 4) return confirmBlockReason;
    return null;
  }, [currentPage, confirmNextDisabled, confirmWizardStep, confirmBlockReason, stats]);

  const goConfirmWizardNext = () => {
    if (confirmWizardStep < 4) {
      setConfirmWizardStep((s) => s + 1);
      return;
    }
    handleConfirmAll();
  };

  const nextStepKey = getNextAccessibleStep(currentPage, stepAccess);
  const nextStepAccessible = !!nextStepKey;

  const goNext = () => {
    if (currentPage === 'confirm') return;
    if (nextStepKey) {
      goPage(nextStepKey);
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
              const disabled = !stepAccess[step.key];
              const isDone = !step.optional && isWorkflowStepDone(project.status, step.key);
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
                onClick: () => { if (!disabled) goPage(step.key); },
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
        <MacroWorkflowBar steps={macroWorkflowSteps} />
        <div className="workspace-main-scroll">
        <PageSuspense>
        <div className="workspace-main-content">
      {currentPage === 'upload' && (
        <div className="upload-dual-layout">
          <Card
            title="招标原文"
            className="section-card upload-dual-preview"
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

          <div className="upload-dual-actions">
            <Card
              title="上传与解析"
              className="section-card upload-dual-action-card"
              variant="borderless"
              style={{ marginTop: 0 }}
            >
              <UploadStepPanel
                project={project}
                loadingProject={loadingProject}
                uploading={uploading}
                parseTimedOut={parseTimedOut}
                onUpload={handleUpload}
              />
            </Card>

            <Card
              title="生成配置"
              className="section-card upload-dual-action-card"
              variant="borderless"
              style={{ marginTop: 0 }}
            >
              <UploadConfigPanel
                projectId={project.id}
                project={project}
                onProjectChange={(patch) => setProject((p) => ({ ...p, ...patch }))}
              />
            </Card>
          </div>
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
              wizardStep={confirmWizardStep}
              onWizardStepChange={setConfirmWizardStep}
              globalsFilled={globalsFilled}
              stats={stats}
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
            goPage('generate');
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
          onGoEditOutline={() => goPage('outline')}
          onHasGeneratedChapter={() => setHasGeneratedChapter(true)}
          onStarted={() => setProject((p) => ({ ...p, status: 'generating' }))}
          onDone={({ greenCount = 0, yellowCount = 0 } = {}) => {
            setProject((p) => ({ ...p, status: 'done' }));
            if (greenCount + yellowCount > 0) {
              setHasGeneratedChapter(true);
            }
          }}
          onPaused={() => setProject((p) => ({ ...p, status: 'outline_locked' }))}
          onGoPreview={() => goPage('preview')}
        />
      )}

      {currentPage === 'preview' && (
        <PreviewExport
          projectId={project.id}
          durationDays={project.duration_days}
          onGoGenerate={() => goPage('generate')}
        />
      )}
        </div>
        </PageSuspense>
        </div>

        <div className="workspace-main-footer">
        <StepFooter
          extra={currentPage === 'confirm'
            ? confirmWizardExtras[confirmWizardStep] || confirmBlockReason
            : currentPage === 'outline' && canGoGenerate
                ? '大纲已锁定，可进入内容生成'
                : currentPage === 'outline'
                  ? '在本页完成定目录 → 深化审核 → 锁定'
                  : `步骤 ${currentStepIndex + 1} / ${STEP_ORDER.length}`}
          onPrev={currentPage === 'confirm'
            ? (confirmWizardStep > 1 || currentStepIndex > 0 ? goPrev : null)
            : (currentStepIndex > 0 ? goPrev : null)}
          onNext={currentPage === 'preview'
            ? null
            : (currentPage === 'confirm' ? goConfirmWizardNext : goNext)}
          nextLabel={
            currentPage === 'confirm'
              ? confirmWizardNextLabels[confirmWizardStep] || '下一步'
              : currentPage === 'outline' && canGoGenerate
                  ? '下一步：内容生成'
                  : currentPage === 'outline'
                    ? '请在上方完成锁定'
                    : '下一步'
          }
          nextDisabled={currentPage === 'confirm'
            ? confirmNextDisabled
            : currentPage === 'outline'
              ? !canGoGenerate
              : !nextStepAccessible}
          nextDisabledReason={currentPage === 'confirm'
            ? confirmNextDisabledReason
            : currentPage === 'outline' && !canGoGenerate
              ? '请先在大纲第 3 步点击「锁定并进入内容生成」'
              : null}
          nextLoading={currentPage === 'confirm' && confirmWizardStep === 4 ? confirming : false}
        />
        </div>
      </div>
    </div>
  );
}
export { ProjectWorkspace };
