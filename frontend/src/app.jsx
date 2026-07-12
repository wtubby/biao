import {
  useState, ConfigProvider, Menu, Button, Spin, lazy, Suspense,
  APP_LOCALE, APP_THEME,
} from './globals.js';
import { hideBootLoading, showBootError } from './lib/boot.js';
import { Icon } from './components/icons.jsx';
import { EnvStatusBanner, WorkspaceBrand, WorkspaceSidebarFooter } from './components/layout.jsx';
import { SettingsModal } from './components/SettingsModal.jsx';
import { ProjectList } from './modules/project/ProjectList.jsx';

const ProjectWorkspace = lazy(() =>
  import('./modules/project/ProjectWorkspace.jsx').then((m) => ({ default: m.ProjectWorkspace })),
);

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
          <Suspense fallback={(
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}>
              <Spin size="large" tip="正在加载工作台…" />
            </div>
          )}
          >
            <ProjectWorkspace
              key={currentProject.id}
              project={currentProject}
              onBack={goToList}
              onOpenSettings={openSettings}
            />
          </Suspense>
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
