import { useState } from '../../globals.js';
import {
  Input, Select, Space, Tabs,
} from '../../globals.js';
import { PageHeader } from '../../components/layout.jsx';
import { useStandardsList } from './useStandardsList.js';
import { StandardsTable } from './StandardsTable.jsx';
import { StandardDetailDrawer } from './StandardDetailDrawer.jsx';
import { StandardsCoveragePanel } from './StandardsCoveragePanel.jsx';
import { StandardsImportButton } from './StandardsImportButton.jsx';
import { StandardsBootstrapButton } from './StandardsBootstrapButton.jsx';

const STATUS_FILTER = [
  { value: 'draft', label: '草稿' },
  { value: 'active', label: '现行' },
  { value: 'superseded', label: '被替代' },
  { value: 'withdrawn', label: '废止' },
];

export function StandardsPage() {
  const {
    items,
    loading,
    domain,
    setDomain,
    status,
    setStatus,
    q,
    setQ,
    domainOptions,
    reload,
  } = useStandardsList();

  const [editCode, setEditCode] = useState(null);
  const [coverageKey, setCoverageKey] = useState(0);

  const refreshAll = () => {
    reload();
    setCoverageKey((k) => k + 1);
  };

  return (
    <div className="project-list-page">
      <PageHeader
        title="标准库管理"
        description="维护现行/废止规范标准号，供生成推荐与 QA 拦截复用"
      />

      <div className="project-panel">
        <Tabs
          items={[
            {
              key: 'list',
              label: '标准列表',
              children: (
                <>
                  <div className="project-list-toolbar" style={{ marginBottom: 12 }}>
                    <Space wrap>
                      <StandardsBootstrapButton
                        domainOptions={domainOptions}
                        onBootstrapped={refreshAll}
                      />
                      <StandardsImportButton onImported={refreshAll} />
                    </Space>
                    <Space wrap>
                      <Select
                        allowClear
                        placeholder="全部领域"
                        style={{ width: 150 }}
                        value={domain}
                        onChange={setDomain}
                        options={domainOptions.map((d) => ({
                          value: d.key,
                          label: d.label || d.key,
                        }))}
                      />
                      <Select
                        allowClear
                        placeholder="全部状态"
                        style={{ width: 130 }}
                        value={status}
                        onChange={setStatus}
                        options={STATUS_FILTER}
                      />
                      <Input
                        allowClear
                        placeholder="搜索编号/标题…"
                        style={{ width: 220 }}
                        value={q}
                        onChange={(e) => setQ(e.target.value)}
                        onPressEnter={reload}
                      />
                    </Space>
                  </div>
                  <StandardsTable
                    items={items}
                    loading={loading}
                    onEdit={(row) => setEditCode(row.code)}
                    onChanged={refreshAll}
                  />
                </>
              ),
            },
            {
              key: 'coverage',
              label: '覆盖度看板',
              children: <StandardsCoveragePanel refreshKey={coverageKey} />,
            },
          ]}
        />
      </div>

      <StandardDetailDrawer
        open={!!editCode}
        code={editCode}
        domainOptions={domainOptions}
        onClose={() => setEditCode(null)}
        onSaved={refreshAll}
      />
    </div>
  );
}
