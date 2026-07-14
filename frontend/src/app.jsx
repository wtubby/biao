import {
  useState, useEffect, useCallback, useRef,
  ConfigProvider, Menu, Spin, lazy, Suspense, message,
  APP_LOCALE, APP_THEME,
} from './globals.js';
import { hideBootLoading, showBootError } from './lib/boot.js';
import {
  parseHashRoute,
  pushHashRoute,
  replaceHashRoute,
  getCurrentHashRoute,
} from './lib/hashRoute.js';
import { apiFetch } from './api/client.js';
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
  const [routeStep, setRouteStep] = useState(null);
  const [bootstrapping, setBootstrapping] = useState(true);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const projectIdRef = useRef(null);

  useEffect(() => {
    projectIdRef.current = currentProject?.id || null;
  }, [currentProject?.id]);

  const openSettings = () => setSettingsOpen(true);

  const goToList = useCallback(({ replace = false } = {}) => {
    setCurrentProject(null);
    setRouteStep(null);
    setView('list');
    const route = { view: 'list' };
    if (replace) replaceHashRoute(route);
    else pushHashRoute(route);
  }, []);

  const enterProject = useCallback((p, { step = null, replace = false } = {}) => {
    setCurrentProject(p);
    setRouteStep(step);
    setView('project');
    const route = { view: 'project', projectId: p.id, step };
    if (replace) replaceHashRoute(route);
    else pushHashRoute(route);
  }, []);

  const handlePageChange = useCallback((step, { replace = false } = {}) => {
    setRouteStep(step);
    const projectId = projectIdRef.current;
    if (!projectId || !step) return;
    const route = { view: 'project', projectId, step };
    if (replace) replaceHashRoute(route);
    else pushHashRoute(route);
  }, []);

  const applyRoute = useCallback(async (route, { replaceInvalid = true } = {}) => {
    if (route.view === 'list') {
      setCurrentProject(null);
      setRouteStep(null);
      setView('list');
      return;
    }

    if (route.view !== 'project' || !route.projectId) {
      goToList({ replace: true });
      return;
    }

    if (projectIdRef.current === route.projectId) {
      setRouteStep(route.step);
      setView('project');
      return;
    }

    try {
      const p = await apiFetch(`/projects/${route.projectId}`);
      setCurrentProject(p);
      setRouteStep(route.step);
      setView('project');
    } catch (e) {
      message.error(e.message || '项目不存在或已删除');
      if (replaceInvalid) goToList({ replace: true });
    }
  }, [goToList]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const route = getCurrentHashRoute();
      if (route.view === 'project' && route.projectId) {
        try {
          const p = await apiFetch(`/projects/${route.projectId}`);
          if (cancelled) return;
          setCurrentProject(p);
          setRouteStep(route.step);
          setView('project');
        } catch (e) {
          if (!cancelled) {
            message.error(e.message || '项目不存在或已删除');
            replaceHashRoute({ view: 'list' });
            setView('list');
          }
        }
      } else {
        replaceHashRoute({ view: 'list' });
        if (!cancelled) setView('list');
      }
      if (!cancelled) setBootstrapping(false);
    })();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    const onHashChange = () => {
      applyRoute(parseHashRoute());
    };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, [applyRoute]);

  if (bootstrapping) {
    return (
      <ConfigProvider locale={APP_LOCALE} theme={APP_THEME}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}>
          <Spin size="large" tip="正在恢复页面…" />
        </div>
      </ConfigProvider>
    );
  }

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
              routePage={routeStep}
              onPageChange={handlePageChange}
              onBack={() => goToList()}
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
