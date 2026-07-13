import {
  useState, useEffect, useCallback,
  Alert, Spin, Text, message,
} from '../../globals.js';

import { setGenerationMode, setOutlineCatalogSource, fetchOutlineCatalog } from '../../api/outline.js';
import { fetchParseSummary } from '../../api/parse.js';
import { fetchTenderDetail, updateTenderDetail } from '../../api/tenderDetail.js';
import { Icon } from '../../components/icons.jsx';
import { DirectorySourceSwitch, DisplayModeSwitch } from '../outline/components.jsx';

function ConfigRow({ label, hint, children }) {
  return (
    <div className="upload-config-row">
      <div className="upload-config-row-head">
        <div className="upload-config-row-label">{label}</div>
        {hint && <div className="upload-config-row-hint">{hint}</div>}
      </div>
      <div className="upload-config-row-body">{children}</div>
    </div>
  );
}

function BlindBidPills({ value, disabled, loading, onChange }) {
  const options = [
    { key: false, label: '关闭' },
    { key: true, label: '开启' },
  ];
  return (
    <div className="upload-config-pills" role="radiogroup" aria-label="暗标要求">
      {options.map((opt) => {
        const selected = value === opt.key;
        return (
          <button
            key={String(opt.key)}
            type="button"
            role="radio"
            aria-checked={selected}
            className={`upload-config-pill${selected ? ' is-active' : ''}`}
            disabled={disabled || loading}
            onClick={() => onChange(opt.key)}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

function UploadConfigPanel({
  projectId,
  project,
  onProjectChange,
  parseReady = false,
}) {
  const [loading, setLoading] = useState(true);
  const [savingKey, setSavingKey] = useState('');
  const [blindBid, setBlindBid] = useState(false);
  const [blindBidAutoDetected, setBlindBidAutoDetected] = useState(false);
  const [catalogSource, setCatalogSource] = useState('score_points');
  const [catalogPreviews, setCatalogPreviews] = useState(null);

  const generationMode = project?.generation_mode || 'full';

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [detail, summary, catalog] = await Promise.all([
        fetchTenderDetail(projectId).catch(() => null),
        fetchParseSummary(projectId).catch(() => null),
        parseReady ? fetchOutlineCatalog(projectId).catch(() => null) : Promise.resolve(null),
      ]);
      if (detail?.notice?.blind_bid === true) setBlindBid(true);
      else if (detail?.notice?.blind_bid === false) setBlindBid(false);
      setBlindBidAutoDetected(!!summary?.blind_bid_auto_detected);
      if (catalog?.source) setCatalogSource(catalog.source);
      if (catalog?.previews) setCatalogPreviews(catalog.previews);
    } finally {
      setLoading(false);
    }
  }, [projectId, parseReady]);

  useEffect(() => { load(); }, [load]);

  // 解析过程中轮询同步暗标预检结果（关键词命中会写入 notice.blind_bid）
  useEffect(() => {
    if (project?.status !== 'parsing') return undefined;
    let cancelled = false;
    const syncParseHints = async () => {
      try {
        const [detail, summary] = await Promise.all([
          fetchTenderDetail(projectId).catch(() => null),
          fetchParseSummary(projectId).catch(() => null),
        ]);
        if (cancelled) return;
        if (detail?.notice?.blind_bid === true) setBlindBid(true);
        else if (detail?.notice?.blind_bid === false) setBlindBid(false);
        setBlindBidAutoDetected(!!summary?.blind_bid_auto_detected);
      } catch {
        /* 轮询失败忽略 */
      }
    };
    syncParseHints();
    const timer = setInterval(syncParseHints, 2500);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [projectId, project?.status]);

  const withSave = async (key, fn) => {
    setSavingKey(key);
    try {
      await fn();
    } catch (e) {
      message.error(e.message || '保存失败');
    } finally {
      setSavingKey('');
    }
  };

  const handleBlindBid = (enabled) => {
    if (enabled === blindBid) return;
    withSave('blind', async () => {
      await updateTenderDetail(projectId, { notice: { blind_bid: enabled } });
      setBlindBid(enabled);
    });
  };

  const handleGenerationMode = (mode) => {
    if (mode === generationMode) return;
    withSave('mode', async () => {
      const result = await setGenerationMode(projectId, mode);
      onProjectChange?.({ generation_mode: result.mode });
    });
  };

  const handleCatalogSource = (source) => {
    if (source === catalogSource) return;
    withSave('catalog', async () => {
      const result = await setOutlineCatalogSource(projectId, source);
      setCatalogSource(source);
      if (result.previews) setCatalogPreviews(result.previews);
    });
  };

  return (
    <div className="upload-config-panel">
      <Text type="secondary" className="upload-config-panel-sub">
        可先预选，后续步骤可继续细调
      </Text>

      {loading ? (
        <div className="upload-config-loading">
          <Spin size="small" />
        </div>
      ) : (
        <div className="upload-config-body">
          <ConfigRow
            label="暗标要求"
            hint={blindBidAutoDetected ? '已根据招标文件关键词预检，请核对' : '影响正文匿名约束与导出页眉'}
          >
            <BlindBidPills
              value={blindBid}
              loading={savingKey === 'blind'}
              onChange={handleBlindBid}
            />
          </ConfigRow>

          <ConfigRow label="生成档位" hint="精简版页数更少，满血版内容更完整">
            <DisplayModeSwitch
              value={generationMode}
              loading={savingKey === 'mode'}
              onChange={handleGenerationMode}
            />
          </ConfigRow>

          <ConfigRow
            label="目录依据"
            hint={parseReady ? '大纲阶段将按此来源初始化目录' : '解析完成后可切换'}
          >
            <DirectorySourceSwitch
              value={catalogSource}
              previews={catalogPreviews}
              loading={savingKey === 'catalog'}
              disabled={!parseReady}
              onChange={handleCatalogSource}
            />
          </ConfigRow>

          {!parseReady && (
            <Alert
              type="info"
              showIcon
              className="upload-config-tip"
              message="上传并完成解析后，可切换目录依据"
            />
          )}
        </div>
      )}

      <div className="upload-config-foot">
        <Icon name="facts" size={14} />
        <span>工程参数、评分项等将在「核对配置」步骤完善</span>
      </div>
    </div>
  );
}

export { UploadConfigPanel };
