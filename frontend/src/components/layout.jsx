import {
  useState, useCallback, useEffect,
  Button, Tag, Space, Alert, Title, Text,
} from '../globals.js';

import { Icon } from './icons.jsx';
import { STEP_ORDER } from '../constants/workflow.js';
import { PROJECT_STATUS_LABELS } from '../constants/project.js';
import { apiFetch } from '../api/client.js';
function PageHeader({ title, description, extra, tags }) {
  return (
    <div className="page-header">
      <div>
        <Title level={3}>{title}</Title>
        {description && <div className="page-header-desc">{description}</div>}
        {tags && <Space style={{ marginTop: 8 }}>{tags}</Space>}
      </div>
      {extra && <div className="page-header-extra">{extra}</div>}
    </div>
  );
}

function StepFooter({ extra, onPrev, onNext, prevLabel, nextLabel, prevDisabled, nextDisabled, nextLoading }) {
  return (
    <div className="step-footer">
      <div className="step-footer-extra">{extra}</div>
      <Space>
        {onPrev && (
          <Button onClick={onPrev} disabled={prevDisabled}>
            {prevLabel || '上一步'}
          </Button>
        )}
        {onNext && (
          <Button
            type="primary"
            onClick={onNext}
            disabled={nextDisabled}
            loading={nextLoading}
          >
            {nextLabel || '下一步'}
          </Button>
        )}
      </Space>
    </div>
  );
}

function getWorkflowProgressByStatus(status) {
  // STEP_ORDER: upload, confirm, commercial, facts, outline, generate, preview
  const doneMap = {
    draft: 0,
    parsing: 1,
    confirming: 2,
    planning: 4,
    outline_locked: 5,
    generating: 5,
    done: STEP_ORDER.length,
  };
  const done = doneMap[status] ?? 0;
  return {
    done,
    total: STEP_ORDER.length,
    percent: Math.round((done / STEP_ORDER.length) * 100),
    label: PROJECT_STATUS_LABELS[status] || status,
  };
}

function WorkflowProgressRing({ done, total }) {
  const radius = 18;
  const circumference = 2 * Math.PI * radius;
  const percent = total ? done / total : 0;
  const offset = circumference * (1 - percent);
  return (
    <div className="workspace-progress-ring" aria-hidden="true">
      <svg width="44" height="44" viewBox="0 0 44 44">
        <circle className="workspace-progress-ring-bg" cx="22" cy="22" r={radius} />
        <circle
          className="workspace-progress-ring-fg"
          cx="22"
          cy="22"
          r={radius}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
        />
      </svg>
    </div>
  );
}

function EnvStatusBanner() {
  const [status, setStatus] = useState(null);
  const [dismissed, setDismissed] = useState(false);
  const [rechecking, setRechecking] = useState(false);

  const load = useCallback(async (recheck = false) => {
    try {
      const data = await apiFetch(`/env-status${recheck ? '?recheck=true' : ''}`);
      setStatus(data);
    } catch {
      // 检测接口本身失败不影响主流程，静默忽略
    }
  }, []);

  useEffect(() => { load(false); }, [load]);

  if (!status || status.graphviz || dismissed) return null;

  const handleRecheck = async () => {
    setRechecking(true);
    await load(true);
    setRechecking(false);
  };

  return (
    <Alert
      type="warning"
      showIcon
      closable
      onClose={() => setDismissed(true)}
      style={{ borderRadius: 0 }}
      message="缺少 Graphviz，流程图/组织架构图将无法正常生成"
      description={
        <Space direction="vertical" size={4}>
          <Text>{status.graphviz_hint}</Text>
          <Button size="small" loading={rechecking} onClick={handleRecheck}>
            已安装，重新检测
          </Button>
        </Space>
      }
    />
  );
}

function WorkspaceBrand() {
  return (
    <div className="workspace-sidebar-brand">
      <div className="workspace-sidebar-brand-logo" aria-hidden="true">
        <Icon name="bolt" size={18} />
      </div>
      <div>
        <div className="workspace-sidebar-brand-title">Tech-Bid-Engine</div>
        <div className="workspace-sidebar-brand-sub">电力 EPC 技术方案引擎</div>
      </div>
    </div>
  );
}

function WorkspaceProjectHeader({ projectName, statusText, workflowProgress }) {
  return (
    <div className="workspace-main-header">
      <div className="workspace-main-header-info">
        <div className="workspace-main-header-name">{projectName || '未命名项目'}</div>
        <Tag color="blue">{statusText}</Tag>
      </div>
      <div className="workspace-progress workspace-progress--light">
        <WorkflowProgressRing done={workflowProgress.done} total={workflowProgress.total} />
        <div className="workspace-progress-text">
          <strong>{workflowProgress.done}/{workflowProgress.total}</strong>
          <div>步骤已完成</div>
        </div>
      </div>
    </div>
  );
}

function WorkspaceSidebarFooter({ onBack, onOpenSettings }) {
  return (
    <div className="workspace-sidebar-footer">
      {onBack && (
        <Button type="text" className="workspace-sidebar-footer-btn" onClick={onBack}>
          ← 返回项目列表
        </Button>
      )}
      <Button type="text" className="workspace-sidebar-footer-btn" onClick={onOpenSettings}>
        <span className="workspace-menu-label">
          <Icon name="settings" size={14} />
          <span>API 设置</span>
        </span>
      </Button>
    </div>
  );
}
export {
  PageHeader,
  StepFooter,
  getWorkflowProgressByStatus,
  WorkflowProgressRing,
  EnvStatusBanner,
  WorkspaceBrand,
  WorkspaceProjectHeader,
  WorkspaceSidebarFooter,
};
