/**
 * 一次性工具：从 frontend/app.jsx 按标记拆分为 frontend/src 模块。
 * 正常运行 compile_frontend.mjs 即可，无需重复执行本脚本。
 */
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const srcDir = join(root, "frontend", "src");
const legacy = readFileSync(join(root, "frontend", "app.jsx"), "utf8");
const lines = legacy.split(/\r?\n/);

function slice(start, end) {
  return lines.slice(start - 1, end).join("\n");
}

function write(rel, body) {
  const path = join(srcDir, rel);
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, `${body.trim()}\n`, "utf8");
  console.log("wrote", rel);
}

const globalsImport = `import {
  useState, useEffect, useCallback, useMemo, useRef,
  Card, Button, Table, Form, Input, InputNumber, Select,
  Upload, Tag, Space, message, Spin, Popconfirm, Alert, Typography, Row, Col,
  Modal, Divider, ConfigProvider, Tree, Progress, List, Badge, Popover,
  Menu, Radio, Drawer, Tooltip, Tabs,
  Dragger, Option, Title, Text, Password,
  APP_LOCALE, APP_THEME,
} from '../globals.js';
`;

const globalsImportModule = globalsImport.replace("'../globals.js'", "'../../globals.js'");

mkdirSync(srcDir, { recursive: true });

write("globals.js", `
const { useState, useEffect, useCallback, useMemo, useRef } = React;
const {
  Card, Button, Table, Form, Input, InputNumber, Select,
  Upload, Tag, Space, message, Spin, Popconfirm, Alert, Typography, Row, Col,
  Modal, Divider, ConfigProvider, Tree, Progress, List, Badge, Popover,
  Menu, Radio, Drawer, Tooltip, Tabs,
} = antd;
const { Dragger } = Upload;
const { Option } = Select;
const { Title, Text } = Typography;
const { Password } = Input;
const APP_LOCALE = (antd.locales && antd.locales.zh_CN) || undefined;
const APP_THEME = {
  token: {
    colorPrimary: '#2563eb',
    colorPrimaryHover: '#1d4ed8',
    borderRadius: 6,
    borderRadiusLG: 12,
    fontFamily: "'Inter', 'Noto Sans SC', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  },
};
export {
  useState, useEffect, useCallback, useMemo, useRef,
  Card, Button, Table, Form, Input, InputNumber, Select,
  Upload, Tag, Space, message, Spin, Popconfirm, Alert, Typography, Row, Col,
  Modal, Divider, ConfigProvider, Tree, Progress, List, Badge, Popover,
  Menu, Radio, Drawer, Tooltip, Tabs,
  Dragger, Option, Title, Text, Password,
  APP_LOCALE, APP_THEME,
};
`);

write("api/client.js", `
export const API = \`\${window.location.origin}/api\`;

export function formatApiError(err) {
  if (Array.isArray(err.detail)) {
    return err.detail.map((d) => d.msg || JSON.stringify(d)).join('; ');
  }
  if (err.detail && typeof err.detail === 'object' && err.detail.message) {
    return err.detail.message;
  }
  return err.detail || '请求失败';
}

export async function apiFetch(path, options = {}) {
  const res = await fetch(\`\${API}\${path}\`, options);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(formatApiError(err));
  }
  return res.json();
}
`);

write("lib/boot.js", `
export function hideBootLoading() {
  const el = document.getElementById('boot-loading');
  if (el) el.style.display = 'none';
}

export function showBootError(msg) {
  hideBootLoading();
  const el = document.getElementById('boot-error');
  if (el) {
    el.style.display = 'block';
    el.textContent = msg;
  }
}
`);

write("constants/workflow.js", `
export const WORKFLOW_STEPS = [
  { key: 'upload', label: '上传标书', icon: 'upload', description: '上传 PDF/DOCX 招标文件，自动解析评分项' },
  { key: 'confirm', label: '确认评分项', icon: 'check', description: '核对评分项与工程全局参数，确认刚性风险项' },
  { key: 'facts', label: '全局事实变量', icon: 'facts', description: '维护技术方案引用的全局事实与变量分组' },
  { key: 'outline', label: '大纲编辑', icon: 'outline', description: 'AI 深化大纲，可手动增删改章节与写作指导' },
  { key: 'generate', label: '内容生成', icon: 'generate', description: '按章节批量或单章生成技术方案正文' },
  { key: 'preview', label: '预览与导出', icon: 'preview', description: '审阅、修改章节内容并导出 Word 文档' },
];

export const STEP_ORDER = WORKFLOW_STEPS.map((s) => s.key);
`);

write("constants/project.js", `
export const PROJECT_TYPES = [
  '线路工程',
  '变电站新建',
  '变电站改造',
  '电缆工程',
  '设备安装',
  '检修调试',
  '其他',
];

export const ENGINEERING_DOMAINS = ['电力工程', '市政工程', '建筑工程', '水利工程', '其他'];

export const CONTRACT_MODES = ['EPC', 'PC', '施工总承包', '设计施工一体化', '其他'];
`);

// --- components ---
write("components/icons.jsx", `${globalsImport}
${slice(36, 87)}
export { Icon, ChapterStatusIcon, ICON_PATHS };
`);

write("components/layout.jsx", `${globalsImport}
import { Icon } from './icons.jsx';
import { STEP_ORDER } from '../constants/workflow.js';
import { apiFetch } from '../api/client.js';
${slice(89, 269)}
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
`);

write("components/MetricCard.jsx", `${globalsImport}
${slice(1262, 1270)}
export { MetricCard };
`);

write("components/PromptInspectorDrawer.jsx", `${globalsImport}
import { apiFetch } from '../api/client.js';
${slice(304, 420)}
export { PromptInspectorDrawer };
`);

// outline helpers
write("modules/outline/helpers.jsx", `
import { Badge } from '../../globals.js';
${slice(495, 637)}
export {
  reviewStatusToBadgeStatus,
  OutlineReviewBadge,
  buildOutlineTreeData,
  getOrderedLeaves,
  newOutlineId,
  getNodeDescendantIds,
  getNextSortOrder,
  recomputeOutlineStructure,
  createOutlineNode,
  serializeOutlineNodesForSave,
};
`);

write("modules/outline/components.jsx", `${globalsImportModule}
import { Icon } from '../../components/icons.jsx';
import { apiFetch } from '../../api/client.js';
${slice(1590, 1638)}
export { OutlineStepNum, OutlineStepRow, KnowledgeStatusBadge };
`);

write("modules/compliance/ComplianceReportDrawer.jsx", `${globalsImportModule}
import { apiFetch } from '../../api/client.js';
${slice(422, 493)}
export { colorizeComplianceHtml, ComplianceReportDrawer };
`);

write("modules/chart/preview.js", `${globalsImportModule}
import { apiFetch } from '../../api/client.js';
${slice(2663, 2862)}
export {
  CHART_CAPTIONS,
  CHART_LABELS,
  useChartPreviews,
  renderMarkdownPreview,
};
`);

// Large modules - wrap exports
const largeModules = [
  ["components/SettingsModal.jsx", 639, 762, "SettingsModal", `${globalsImport}\nimport { apiFetch } from '../api/client.js';\nimport { Icon } from './icons.jsx';\n`],
  ["modules/project/ProjectList.jsx", 764, 906, "ProjectList", `${globalsImportModule}\nimport { apiFetch } from '../../api/client.js';\nimport { PageHeader } from '../../components/layout.jsx';\nimport { Icon } from '../../components/icons.jsx';\n`],
  ["modules/confirm/ContradictionsAlert.jsx", 908, 952, "ContradictionsAlert", `${globalsImportModule}\nimport { apiFetch } from '../../api/client.js';\n`],
  ["modules/confirm/ResponseMatrixDrawer.jsx", 954, 1084, "ResponseMatrixDrawer", `${globalsImportModule}\nimport { apiFetch } from '../../api/client.js';\nimport { MetricCard } from '../../components/MetricCard.jsx';\n`],
  ["modules/confirm/GlobalParamsForm.jsx", 1086, 1260, "GlobalParamsForm", `${globalsImportModule}\nimport { apiFetch } from '../../api/client.js';\nimport { PROJECT_TYPES, ENGINEERING_DOMAINS, CONTRACT_MODES } from '../../constants/project.js';\n`],
  ["modules/confirm/RequirementsTable.jsx", 1272, 1588, "RequirementsTable", `${globalsImportModule}\nimport { apiFetch } from '../../api/client.js';\nimport { MetricCard } from '../../components/MetricCard.jsx';\n`],
  ["modules/outline/OutlineEditor.jsx", 1640, 2279, "OutlineEditor", `${globalsImportModule}
import { apiFetch, API } from '../../api/client.js';
import { Icon } from '../../components/icons.jsx';
import { PromptInspectorDrawer } from '../../components/PromptInspectorDrawer.jsx';
import { OutlineStepNum, OutlineStepRow, KnowledgeStatusBadge } from './components.jsx';
import {
  OutlineReviewBadge, buildOutlineTreeData, getOrderedLeaves,
  getNodeDescendantIds, getNextSortOrder, recomputeOutlineStructure,
  createOutlineNode, serializeOutlineNodesForSave,
} from './helpers.jsx';
`],
  ["modules/generation/GenerationPanel.jsx", 2281, 2661, "GenerationPanel", `${globalsImportModule}
import { apiFetch, API } from '../../api/client.js';
import { ChapterStatusIcon, Icon } from '../../components/icons.jsx';
import { PromptInspectorDrawer } from '../../components/PromptInspectorDrawer.jsx';
import { buildOutlineTreeData } from '../outline/helpers.jsx';
import { useChartPreviews, renderMarkdownPreview } from '../chart/preview.js';
`],
  ["modules/export/PreviewExport.jsx", 2864, 3274, "PreviewExport", `${globalsImportModule}
import { apiFetch, API } from '../../api/client.js';
import { ChapterStatusIcon, Icon } from '../../components/icons.jsx';
import { PromptInspectorDrawer } from '../../components/PromptInspectorDrawer.jsx';
import { ComplianceReportDrawer } from '../compliance/ComplianceReportDrawer.jsx';
import { OutlineReviewBadge, buildOutlineTreeData } from '../outline/helpers.jsx';
import { useChartPreviews, renderMarkdownPreview } from '../chart/preview.js';
`],
  ["modules/facts/GlobalFactsPanel.jsx", 3276, 3435, "GlobalFactsPanel", `${globalsImportModule}\nimport { apiFetch } from '../../api/client.js';\n`],
  ["modules/project/ProjectWorkspace.jsx", 3437, 3837, "ProjectWorkspace", `${globalsImportModule}
import { apiFetch, API } from '../../api/client.js';
import { WORKFLOW_STEPS, STEP_ORDER } from '../../constants/workflow.js';
import { Icon } from '../../components/icons.jsx';
import {
  StepFooter, getWorkflowProgressByStatus, WorkspaceBrand, WorkspaceProjectHeader, WorkspaceSidebarFooter,
} from '../../components/layout.jsx';
import { SettingsModal } from '../../components/SettingsModal.jsx';
import { ProjectList } from './ProjectList.jsx';
import { ContradictionsAlert } from '../confirm/ContradictionsAlert.jsx';
import { ResponseMatrixDrawer } from '../confirm/ResponseMatrixDrawer.jsx';
import { GlobalParamsForm, projectToFormValues } from '../confirm/GlobalParamsForm.jsx';
import { RequirementsTable } from '../confirm/RequirementsTable.jsx';
import { GlobalFactsPanel } from '../facts/GlobalFactsPanel.jsx';
import { OutlineEditor } from '../outline/OutlineEditor.jsx';
import { GenerationPanel } from '../generation/GenerationPanel.jsx';
import { PreviewExport } from '../export/PreviewExport.jsx';
`],
];

for (const [rel, start, end, exportName, header] of largeModules) {
  let body = slice(start, end);
  if (exportName === "GlobalParamsForm") {
    body = body.replace(/^const PROJECT_TYPES[\s\S]*?^function projectToFormValues/m, "function projectToFormValues");
  }
  write(rel, `${header}\n${body}\nexport { ${exportName}${exportName === "GlobalParamsForm" ? ", projectToFormValues" : ""} };`);
}

write("app.jsx", `
import {
  useState, ConfigProvider, Menu, Button,
  APP_LOCALE, APP_THEME,
} from './globals.js';
import { hideBootLoading, showBootError } from './lib/boot.js';
import { Icon } from './components/icons.jsx';
import { EnvStatusBanner, WorkspaceBrand, WorkspaceSidebarFooter } from './components/layout.jsx';
import { SettingsModal } from './components/SettingsModal.jsx';
import { ProjectList } from './modules/project/ProjectList.jsx';
import { ProjectWorkspace } from './modules/project/ProjectWorkspace.jsx';

function App() {
  const [view, setView] = useState('list');
  const [currentProject, setCurrentProject] = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const openSettings = () => setSettingsOpen(true);
  const goToList = () => { setCurrentProject(null); setView('list'); };
  const enterProject = (p) => { setCurrentProject(p); setView('project'); };

  return (
    <ConfigProvider locale={APP_LOCALE} theme={APP_THEME}>
      <EnvStatusBanner />
      {view === 'list' ? (
        <div className="workspace-layout workspace-layout--fullscreen">
          <div className="workspace-sidebar">
            <WorkspaceBrand />
            <Menu
              theme="dark"
              mode="inline"
              selectedKeys={['projects']}
              items={[{
                key: 'projects',
                label: (
                  <span className="workspace-menu-label">
                    <Icon name="list" size={15} />
                    <span>项目列表</span>
                  </span>
                ),
              }]}
            />
            <WorkspaceSidebarFooter onOpenSettings={openSettings} />
          </div>
          <div className="workspace-main">
            <div className="workspace-main-scroll">
              <ProjectList onSelect={enterProject} onCreate={enterProject} />
            </div>
          </div>
        </div>
      ) : (
        currentProject && (
          <ProjectWorkspace
            key={currentProject.id}
            project={currentProject}
            onBack={goToList}
            onOpenSettings={openSettings}
          />
        )
      )}
      <SettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </ConfigProvider>
  );
}

try {
  if (!window.React || !window.ReactDOM || !window.antd) {
    throw new Error('前端依赖库未加载，请检查网络或重新运行 start.bat');
  }
  ReactDOM.createRoot(document.getElementById('root')).render(<App />);
  hideBootLoading();
} catch (e) {
  showBootError(e.message || String(e));
}
`);

console.log('split complete');
