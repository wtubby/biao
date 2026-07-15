import {
  useState, useEffect, useCallback, useRef, useMemo,
  Switch, Input, Select, Slider, Checkbox, message, Spin, Upload, Button, Space,
  Text,
} from '../../globals.js';

import {
  fetchGenerationConfig,
  updateGenerationConfig,
  uploadReferenceBid,
} from '../../api/generationConfig.js';
import { changeGenerationMode } from '../../api/outline.js';
import { DisplayModeSwitch } from '../outline/components.jsx';
import { TypesettingPanel } from './TypesettingPanel.jsx';
import { buildPagesEstimate } from '../../lib/wordEstimate.js';

const CHART_OPTIONS = [
  { value: 'none', label: '无' },
  { value: 'normal', label: '适中' },
  { value: 'abundant', label: '大量' },
];

const BID_CATEGORY_OPTIONS = [
  { value: 'service_plan', label: '服务方案' },
  { value: 'procurement_goods', label: '采购物资' },
  { value: 'engineering_tech', label: '工程技术标' },
  { value: 'construction_org', label: '施工组织设计' },
  { value: 'hazardous_work', label: '危大工程方案' },
];

const BODY_FORMAT_OPTIONS = [
  { value: 'general', label: '通用正文' },
  { value: 'heading_hierarchy', label: '标题层级正文' },
  { value: 'list_items', label: '列表项正文' },
];

const STANDARDS_OPTIONS = [
  { value: 'epc_guide', label: '电力 EPC 写作惯例（非标准条文）' },
  { value: 'none', label: '不附加' },
];

function ConfigRow({ label, children, className = '' }) {
  return (
    <div className={`generation-config-row${className ? ` ${className}` : ''}`}>
      <span className="generation-config-label">{label}</span>
      <div className="generation-config-control">{children}</div>
    </div>
  );
}

function ChartDensityPills({ value, disabled, onChange }) {
  return (
    <div className="generation-config-pills" role="radiogroup" aria-label="图表程度">
      {CHART_OPTIONS.map((opt) => {
        const selected = (value || 'normal') === opt.value;
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={selected}
            className={`generation-config-pill${selected ? ' is-active' : ''}`}
            disabled={disabled}
            onClick={() => onChange(opt.value)}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

function GenerationConfigPanel({
  projectId,
  disabled = false,
  showWordSlider = true,
  showModeSwitch = true,
  generationMode = 'full',
  onGenerationModeChange,
  onConfigUpdated,
}) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [pagesSaving, setPagesSaving] = useState(false);
  const [config, setConfig] = useState(null);
  const savedReferenceTextRef = useRef('');
  const draftReferenceTextRef = useRef('');
  const pagesPatchSeqRef = useRef(0);

  const applyConfigResult = (data) => {
    const { success: _success, ...rest } = data || {};
    setConfig(rest);
    const refText = rest.reference_bid_text || '';
    savedReferenceTextRef.current = refText;
    draftReferenceTextRef.current = refText;
    return rest;
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchGenerationConfig(projectId);
      applyConfigResult(data);
    } catch (e) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => { load(); }, [load]);

  const patchConfig = async (patch, options = {}) => {
    if (disabled) return;
    const quiet = !!options.quiet;
    if (!quiet) setSaving(true);
    try {
      const result = await updateGenerationConfig(projectId, patch);
      const cleaned = applyConfigResult(result);
      onConfigUpdated?.(cleaned, {
        outlineChanged: Object.prototype.hasOwnProperty.call(patch, 'target_pages')
          || Object.prototype.hasOwnProperty.call(patch, 'custom_word_count')
          || Object.prototype.hasOwnProperty.call(patch, 'custom_total_words'),
        quiet,
      });
    } catch (e) {
      message.error(e.message);
    } finally {
      if (!quiet) setSaving(false);
    }
  };

  const handlePagesChange = (v) => {
    const wpp = config?.estimate?.words_per_page ?? 780;
    setConfig((c) => ({
      ...c,
      target_pages: v,
      custom_word_count: false,
      estimate: {
        ...(c.estimate || {}),
        ...buildPagesEstimate(v, wpp),
      },
    }));
  };

  const handlePagesCommit = async (v) => {
    if (disabled) return;
    const seq = ++pagesPatchSeqRef.current;
    setPagesSaving(true);
    handlePagesChange(v);
    try {
      const result = await updateGenerationConfig(projectId, {
        target_pages: v,
        custom_word_count: false,
      });
      if (seq !== pagesPatchSeqRef.current) return;
      const cleaned = applyConfigResult(result);
      onConfigUpdated?.(cleaned, { outlineChanged: true, quiet: true });
    } catch (e) {
      if (seq === pagesPatchSeqRef.current) message.error(e.message);
    } finally {
      if (seq === pagesPatchSeqRef.current) setPagesSaving(false);
    }
  };

  const handleModeChange = async (mode) => {
    if (disabled || mode === generationMode) return;
    setSaving(true);
    try {
      const result = await changeGenerationMode({
        projectId,
        mode,
        currentMode: generationMode,
        locked: disabled,
      });
      if (!result) return;
      onGenerationModeChange?.(result.mode || mode, result);
      await load();
      if (result.outline_updated) {
        message.success(result.message);
      } else {
        message.info(result.message);
      }
    } catch (e) {
      message.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  const advancedSummary = useMemo(() => {
    if (!config) return '';
    const category = (
      config.bid_category_options?.find((o) => o.value === config.bid_category)
      || BID_CATEGORY_OPTIONS.find((o) => o.value === (config.bid_category || 'engineering_tech'))
    )?.label || '工程技术标';
    const flags = [];
    if (config.use_knowledge_library !== false) flags.push('自有库');
    if (config.reference_bid_enabled) flags.push('以标写标');
    if (config.deep_humanize) flags.push('去痕');
    return [category, ...flags].join(' · ');
  }, [config]);

  if (loading || !config) {
    return (
      <div className="generation-config-panel generation-config-panel--loading">
        <Spin size="small" tip="加载配置…" />
      </div>
    );
  }

  const estimate = config.estimate || {};
  const targetPages = config.target_pages ?? 40;
  const pageMin = config.target_pages_range?.min ?? 10;
  const pageMax = config.target_pages_range?.max ?? 1200;
  const wordsPerPage = config.estimate?.words_per_page ?? 780;
  const bidCategoryOptions = (config.bid_category_options?.length
    ? config.bid_category_options
    : BID_CATEGORY_OPTIONS
  ).map((opt) => ({ value: opt.value, label: opt.label }));
  const busy = disabled || saving;

  return (
    <div className={`generation-config-panel${pagesSaving ? ' is-pages-saving' : ''}`}>
      <div className="generation-config-primary">
        <div className="generation-config-inline-pair">
          {showModeSwitch && (
            <ConfigRow label="生成档位">
              <DisplayModeSwitch
                value={generationMode}
                disabled={busy}
                loading={saving}
                onChange={handleModeChange}
              />
            </ConfigRow>
          )}
          <ConfigRow label="图表程度">
            <ChartDensityPills
              value={config.chart_density || 'normal'}
              disabled={busy}
              onChange={(v) => patchConfig({ chart_density: v })}
            />
          </ConfigRow>
        </div>

        {showWordSlider && (
          <div className="generation-config-pages">
            <div className="generation-config-pages-header">
              <span className="generation-config-label">标书篇幅</span>
              <Text type="secondary" className="generation-config-meta">
                {config.custom_word_count
                  ? `自定义 ${estimate.display_words || '—'}`
                  : `约 ${estimate.display_words || buildPagesEstimate(targetPages, wordsPerPage).display_words} · ${estimate.estimated_pages || targetPages} 页`}
              </Text>
            </div>
            <Slider
              className="generation-config-slider"
              min={pageMin}
              max={pageMax}
              step={5}
              disabled={disabled || config.custom_word_count}
              value={Math.min(pageMax, Math.max(pageMin, targetPages))}
              onChange={handlePagesChange}
              onAfterChange={handlePagesCommit}
            />
          </div>
        )}
      </div>

      <details className="generation-config-advanced">
        <summary>
          <span>高级设置</span>
          <Text type="secondary" className="generation-config-advanced-summary">
            {advancedSummary}
          </Text>
        </summary>
        <div className="generation-config-advanced-body">
          <ConfigRow label="方案类型">
            <Select
              size="small"
              className="generation-config-select generation-config-select--wide"
              disabled={busy}
              value={config.bid_category || 'engineering_tech'}
              options={bidCategoryOptions}
              onChange={(v) => patchConfig({ bid_category: v })}
            />
          </ConfigRow>

          <ConfigRow label="正文格式">
            <Select
              size="small"
              className="generation-config-select"
              disabled={busy}
              value={config.body_format || 'general'}
              options={BODY_FORMAT_OPTIONS}
              onChange={(v) => patchConfig({ body_format: v })}
            />
          </ConfigRow>

          <ConfigRow label="写作惯例">
            <Select
              size="small"
              className="generation-config-select generation-config-select--wide"
              disabled={busy}
              value={config.standards_pack || 'epc_guide'}
              options={STANDARDS_OPTIONS}
              onChange={(v) => patchConfig({ standards_pack: v })}
            />
          </ConfigRow>

          {showWordSlider && (
            <div className="generation-config-pages-custom">
              <Checkbox
                checked={!!config.custom_word_count}
                disabled={busy || pagesSaving}
                onChange={(e) => {
                  if (!e.target.checked) {
                    patchConfig({ custom_word_count: false });
                  } else {
                    setConfig((c) => ({ ...c, custom_word_count: true }));
                  }
                }}
              >
                自定义字数
              </Checkbox>
              {config.custom_word_count && (
                <div className="generation-config-pages-input">
                  <Input
                    type="number"
                    size="small"
                    min={3000}
                    max={500000}
                    disabled={busy}
                    value={config.custom_total_words || estimate.total_words || ''}
                    onChange={(e) => setConfig((c) => ({
                      ...c,
                      custom_total_words: e.target.value ? Number(e.target.value) : null,
                    }))}
                    placeholder="总字数"
                  />
                  <button
                    type="button"
                    className="generation-config-inline-btn"
                    disabled={busy}
                    onClick={() => patchConfig({
                      custom_word_count: true,
                      custom_total_words: config.custom_total_words || estimate.total_words,
                    })}
                  >
                    应用
                  </button>
                </div>
              )}
            </div>
          )}

          <div className="generation-config-switches">
            <label className="generation-config-switch-item">
              <span className="generation-config-label">自有库</span>
              <Switch
                size="small"
                checked={config.use_knowledge_library !== false}
                disabled={busy}
                onChange={(v) => patchConfig({ use_knowledge_library: v })}
              />
            </label>
            <label className="generation-config-switch-item">
              <span className="generation-config-label">以标写标</span>
              <Switch
                size="small"
                checked={!!config.reference_bid_enabled}
                disabled={busy}
                onChange={(v) => patchConfig({ reference_bid_enabled: v })}
              />
            </label>
            <label className="generation-config-switch-item">
              <span className="generation-config-label">刚性绑定</span>
              <Switch
                size="small"
                checked={config.require_risk_binding !== false}
                disabled={busy}
                onChange={(v) => patchConfig({ require_risk_binding: v })}
              />
            </label>
            <label className="generation-config-switch-item">
              <span className="generation-config-label">深度去痕</span>
              <Switch
                size="small"
                checked={!!config.deep_humanize}
                disabled={busy}
                onChange={(v) => patchConfig({ deep_humanize: v })}
              />
            </label>
            <label className="generation-config-switch-item">
              <span className="generation-config-label">SmartArt</span>
              <Switch
                size="small"
                checked={!!config.smartart_enabled}
                disabled={busy}
                onChange={(v) => patchConfig({ smartart_enabled: v })}
              />
            </label>
          </div>

          {config.reference_bid_enabled && (
            <div className="generation-config-ref">
              <div className="generation-config-ref-header">
                <span className="generation-config-label">参考标书</span>
                <Space wrap size="small">
                  <Upload
                    accept=".pdf,.docx,.txt,.md"
                    showUploadList={false}
                    disabled={busy}
                    beforeUpload={async (file) => {
                      setSaving(true);
                      try {
                        const result = await uploadReferenceBid(projectId, file);
                        applyConfigResult(result);
                        onConfigUpdated?.(result);
                        message.success(result.message || '参考标书已导入');
                      } catch (e) {
                        message.error(e.message);
                      } finally {
                        setSaving(false);
                      }
                      return false;
                    }}
                  >
                    <Button size="small" disabled={busy}>上传</Button>
                  </Upload>
                  {config.reference_bid_filename && (
                    <Text type="secondary" className="generation-config-meta" ellipsis>
                      {config.reference_bid_filename}
                    </Text>
                  )}
                </Space>
              </div>
              <Input.TextArea
                rows={2}
                disabled={busy}
                placeholder="也可粘贴历史中标技术标片段"
                value={config.reference_bid_text || ''}
                onChange={(e) => {
                  const next = e.target.value;
                  draftReferenceTextRef.current = next;
                  setConfig((c) => ({ ...c, reference_bid_text: next }));
                }}
                onBlur={() => {
                  const next = draftReferenceTextRef.current || '';
                  if (next === savedReferenceTextRef.current) return;
                  patchConfig({ reference_bid_text: next });
                }}
              />
              <button
                type="button"
                className="generation-config-inline-btn"
                disabled={busy}
                onClick={() => patchConfig({ reference_bid_text: draftReferenceTextRef.current || '' })}
              >
                保存文本
              </button>
            </div>
          )}

          <TypesettingPanel
            typesetting={config.typesetting}
            options={config.typesetting_options}
            disabled={disabled}
            saving={saving}
            onChange={(next) => patchConfig({ typesetting: next })}
            onReset={() => patchConfig({
              typesetting: config.typesetting_options?.defaults || config.typesetting,
            })}
          />
        </div>
      </details>
    </div>
  );
}

export { GenerationConfigPanel };
