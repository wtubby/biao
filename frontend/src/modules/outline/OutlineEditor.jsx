import {
  useState, useEffect, useCallback, useMemo, useRef,
  Card, Button, Input, Select,
  Tag, Space, message, Spin, Alert, Modal, Text,
} from '../../globals.js';

import { estimatePagesFromWords } from '../../lib/wordEstimate.js';
import {
  fetchOutline,
  fetchOutlineBundle,
  fetchOutlineCatalog,
  fetchOutlineTemplate,
  fetchOutlineTemplates,
  normalizeOutlineNodes,
  saveOutlineCatalog,
  setOutlineCatalogSource,
  changeGenerationMode,
  generateOutline,
  saveOutline,
  validateOutline,
  lockOutline,
  previewSplitLongLeaves,
  splitLongLeaves,
} from '../../api/outline.js';
import { fetchRequirements } from '../../api/requirements.js';
import { fetchKnowledgeFolders } from '../../api/knowledge.js';
import { PromptInspectorDrawer } from '../../components/PromptInspectorDrawer.jsx';
import { OutlineStepNav, DirectorySourceSwitch, DisplayModeSwitch } from './components.jsx';
import { OutlineTreeEditor } from './OutlineTreeEditor.jsx';
import { KnowledgeItemsDrawer } from '../knowledge/KnowledgeItemsDrawer.jsx';
import { useKnowledgeFolder } from '../knowledge/useKnowledgeFolder.js';
import { GlobalFactsPanel } from '../facts/GlobalFactsPanel.jsx';
import {
  getOrderedLeaves,
  getNodeDescendantIds, getNextSortOrder, recomputeOutlineStructure,
  createOutlineNode, serializeOutlineNodesForSave,
} from './helpers.jsx';

function OutlineEditor({
  projectId,
  projectStatus = 'planning',
  targetPages = 40,
  generationMode = 'full',
  onLocked,
  onGenerationModeChange,
}) {
  const [nodes, setNodes] = useState([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [locking, setLocking] = useState(false);
  const [validating, setValidating] = useState(false);
  const [validation, setValidation] = useState(null);
  const [locked, setLocked] = useState(false);
  const [folders, setFolders] = useState([]);
  const [requirements, setRequirements] = useState([]);
  const [catalogText, setCatalogText] = useState('');
  const [catalogCount, setCatalogCount] = useState(0);
  const [catalogSource, setCatalogSource] = useState('score_points');
  const [catalogPreviews, setCatalogPreviews] = useState(null);
  const [switchingSource, setSwitchingSource] = useState(false);
  const [switchingMode, setSwitchingMode] = useState(false);
  const [templates, setTemplates] = useState([]);
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [promptOpen, setPromptOpen] = useState(false);
  const [outlineWarnings, setOutlineWarnings] = useState([]);
  const [checkedKeys, setCheckedKeys] = useState([]);
  const [batchEditOpen, setBatchEditOpen] = useState(false);
  const [batchPrefix, setBatchPrefix] = useState('');
  const [batchSuffix, setBatchSuffix] = useState('');
  const [batchFind, setBatchFind] = useState('');
  const [batchReplace, setBatchReplace] = useState('');
  const [wizardStep, setWizardStep] = useState(1);
  const [splittingLong, setSplittingLong] = useState(false);
  const [splitPreviewCount, setSplitPreviewCount] = useState(0);
  const LONG_LEAF_SPLIT_THRESHOLD = 1500;
  const knowledge = useKnowledgeFolder(projectId);
  const autoFilledScoreRef = useRef(false);
  const statusSyncAttemptedRef = useRef(false);
  const outlineNodes = useMemo(() => normalizeOutlineNodes(nodes), [nodes]);

  const applyCatalogSource = useCallback(async (source, { silent = false } = {}) => {
    if (locked) return null;
    setSwitchingSource(true);
    try {
      const result = await setOutlineCatalogSource(projectId, source);
      setCatalogSource(result.source || source);
      setCatalogText(result.text || '');
      setCatalogCount(result.count || 0);
      if (result.previews) setCatalogPreviews(result.previews);
      if (!silent) {
        if (result.applied) {
          message.success(result.message || '目录已更新');
        } else if (result.message) {
          message.info(result.message);
        }
      }
      return result;
    } catch (e) {
      if (!silent) message.error(e.message);
      throw e;
    } finally {
      setSwitchingSource(false);
    }
  }, [projectId, locked]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [outlineBundle, reqs, flds, catalog] = await Promise.all([
        fetchOutlineBundle(projectId),
        fetchRequirements(projectId),
        fetchKnowledgeFolders(projectId),
        fetchOutlineCatalog(projectId),
      ]);
      const outline = normalizeOutlineNodes(outlineBundle);
      setNodes(outline);
      setRequirements(reqs.filter((r) => r.status === 'confirmed'));
      setFolders(flds);
      const isLocked = outline.some((n) => n.is_locked === 1);
      setLocked(isLocked);
      let nextText = catalog.text || '';
      let nextCount = (catalog.catalog || []).length;
      let nextSource = catalog.source || 'score_points';
      let nextPreviews = catalog.previews || null;

      // 有已确认评分项且目录为空：自动按评分点填入一级目录
      const scorePreview = nextPreviews?.score_points;
      if (
        !isLocked
        && !autoFilledScoreRef.current
        && nextSource === 'score_points'
        && !nextText.trim()
        && scorePreview?.available
      ) {
        autoFilledScoreRef.current = true;
        try {
          const result = await setOutlineCatalogSource(projectId, 'score_points');
          nextSource = result.source || 'score_points';
          nextText = result.text || '';
          nextCount = result.count || 0;
          if (result.previews) nextPreviews = result.previews;
          if (result.applied) {
            message.success(result.message || '已按评分点自动生成目录');
          }
        } catch (e) {
          message.warning(e.message || '按评分点自动生成失败，请手动填写');
        }
      }

      setCatalogText(nextText);
      setCatalogCount(nextCount);
      setCatalogSource(nextSource);
      setCatalogPreviews(nextPreviews);
      const degradedWarnings = [
        ...new Set(
          outline
            .filter((n) => n.expand_degraded && n.expand_warning)
            .map((n) => n.expand_warning),
        ),
      ];
      const persisted = Array.isArray(outlineBundle.warnings) ? outlineBundle.warnings : [];
      setOutlineWarnings([...new Set([...persisted, ...degradedWarnings])]);
    } catch (e) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    autoFilledScoreRef.current = false;
    load();
  }, [load]);

  useEffect(() => {
    fetchOutlineTemplates()
      .then((data) => setTemplates(data.templates || []))
      .catch(() => {});
  }, []);

  const handleApplyTemplate = async (templateId) => {
    if (!templateId) return;
    try {
      const tpl = await fetchOutlineTemplate(templateId);
      setCatalogText(tpl.text || '');
      message.success(`已导入模板「${tpl.name}」`);
    } catch (e) {
      message.error(e.message);
    }
  };

  const handleGenerationModeChange = async (mode) => {
    if (mode === generationMode || locked) return;
    setSwitchingMode(true);
    try {
      const result = await changeGenerationMode({
        projectId,
        mode,
        currentMode: generationMode,
        locked,
        reload: load,
      });
      if (!result) return;
      onGenerationModeChange?.(result.mode || mode, result);
      if (result.outline_updated) {
        message.success(result.message);
      } else {
        message.info(result.message);
      }
    } catch (e) {
      message.error(e.message);
    } finally {
      setSwitchingMode(false);
    }
  };

  const goWizardStep = (num) => {
    setWizardStep(num);
  };

  const handleSaveCatalog = async () => {
    if (!catalogText.trim()) { message.warning('请先填写目录大纲'); return; }
    setLoading(true);
    try {
      const result = await saveOutlineCatalog(projectId, catalogText);
      setCatalogCount(result.count || 0);
      message.success(`目录已保存，识别 ${result.count} 个章节`);
      goWizardStep(2);
    } catch (e) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCatalogSourceChange = async (source) => {
    if (source === catalogSource || locked) return;
    await applyCatalogSource(source);
  };

  const handleGenerateFromScorePoints = () => applyCatalogSource('score_points');

  const handleApplyReferenceFormat = () => applyCatalogSource('reference_format');

  const handleValidate = async ({ silent = false } = {}) => {
    setValidating(true);
    try {
      const result = await validateOutline(projectId);
      setValidation(result);
      if (!silent) {
        if (!result.passed) {
          message.warning(result.message || '请先绑定刚性风险评分项，或在内容生成页关闭「刚性绑定」后再锁定');
        } else if (result.has_advisory_gaps) {
          message.success('刚性项已覆盖；仍有建议性未绑定项');
        } else {
          message.success('大纲结构完整，可以锁定');
        }
      }
      return result;
    } catch (e) {
      if (!silent) message.error(e.message);
      return null;
    } finally {
      setValidating(false);
    }
  };

  const refreshSplitPreview = useCallback(async () => {
    if (locked || outlineNodes.length === 0) {
      setSplitPreviewCount(0);
      return;
    }
    try {
      const preview = await previewSplitLongLeaves(projectId);
      setSplitPreviewCount(preview.count || 0);
    } catch {
      setSplitPreviewCount(0);
    }
  }, [projectId, locked, outlineNodes.length]);

  const applySplitResult = async (result) => {
    const bundle = await fetchOutlineBundle(projectId);
    const outline = normalizeOutlineNodes(bundle);
    setNodes(outline);
    const persisted = Array.isArray(bundle?.warnings) ? bundle.warnings : [];
    const warnings = [...new Set([...(result.warnings || []), ...(persisted || [])])];
    setOutlineWarnings(warnings);
    if (result.message) message.success(result.message);
    if (result.warnings?.length) {
      message.warning(`拆分有 ${result.warnings.length} 条提示，请查看下方说明`);
    }
    await handleValidate({ silent: true });
    await refreshSplitPreview();
  };

  const handleSplitLongLeaves = async (leafId) => {
    if (locked) {
      message.warning('大纲已锁定，无法拆分');
      return;
    }
    setSplittingLong(true);
    try {
      const result = await splitLongLeaves(projectId, leafId ? { leafId } : {});
      await applySplitResult(result);
    } catch (e) {
      message.error(e.message);
    } finally {
      setSplittingLong(false);
    }
  };

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const result = await generateOutline(projectId);
      const bundle = await fetchOutlineBundle(projectId);
      const outline = normalizeOutlineNodes(bundle);
      const persisted = Array.isArray(bundle?.warnings) ? bundle.warnings : [];
      setNodes(outline);
      const warnings = [...new Set([...(result.warnings || []), ...(persisted || [])])];
      setOutlineWarnings(warnings);
      const leaves = outline.filter((n) => n.is_leaf === 1);
      const guided = leaves.filter((n) => n.guidance_brief || n.content_boundary).length;
      const bound = leaves.filter((n) => (n.requirement_ids || []).length > 0).length;
      message.success(
        result.message
          ? `${result.message}：${outline.length} 个节点，${leaves.length} 个叶子，${guided} 个已生成写作指导，${bound} 个已绑定评分项`
          : `大纲已深化：${outline.length} 个节点，${leaves.length} 个叶子，${guided} 个已生成写作指导，${bound} 个已绑定评分项`,
      );
      if (warnings.length > 0) {
        message.warning(`有 ${warnings.length} 条大纲质量提示，请查看下方说明并人工检查`);
      }
      await handleValidate({ silent: true });
      goWizardStep(2);
    } catch (e) {
      message.error(e.message);
    } finally {
      setGenerating(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = serializeOutlineNodesForSave(outlineNodes);
      await saveOutline(projectId, payload);
      const outline = normalizeOutlineNodes(await fetchOutline(projectId));
      setNodes(outline);
      message.success('大纲已保存');
      setValidation(null);
    } catch (e) {
      message.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleLock = async () => {
    if (!outlineNodes.length) { message.warning('请先生成大纲后再锁定'); return; }
    setLocking(true);
    try {
      const result = await lockOutline(projectId);
      message.success('大纲已锁定，正在进入内容生成');
      setLocked(true);
      setWizardStep(3);
      onLocked?.(result);
    } catch (e) {
      message.error(e.message);
      // 锁定失败时（如刚性绑定未过）拉一次校验并回到深化审核
      const result = await handleValidate({ silent: true });
      if (result && !result.passed) {
        goWizardStep(2);
      }
    } finally {
      setLocking(false);
    }
  };

  const updateNode = (id, fields) => {
    setNodes((prev) => normalizeOutlineNodes(prev).map((n) => (n.id === id ? { ...n, ...fields } : n)));
  };

  const addOutlineNode = ({ parentId, title }) => {
    const sortOrder = getNextSortOrder(outlineNodes, parentId);
    const newNode = createOutlineNode({ parentId, title });
    newNode.sort_order = sortOrder;
    setNodes(recomputeOutlineStructure([...outlineNodes, newNode]));
    setSelectedNodeId(newNode.id);
  };

  const handleAddRoot = () => addOutlineNode({ parentId: null, title: '新章节' });

  const handleAddChild = () => {
    if (!selectedNodeId) return;
    addOutlineNode({ parentId: selectedNodeId, title: '新子节' });
  };

  const handleAddSibling = () => {
    if (!selectedNodeId) return;
    const current = outlineNodes.find((n) => n.id === selectedNodeId);
    if (!current) return;
    addOutlineNode({ parentId: current.parent_id || null, title: '新同级节' });
  };

  const handleDeleteNode = () => {
    if (!selectedNodeId) return;
    const removeIds = getNodeDescendantIds(outlineNodes, selectedNodeId);
    const next = outlineNodes.filter((n) => !removeIds.has(n.id));
    setNodes(recomputeOutlineStructure(next));
    setSelectedNodeId(null);
  };

  const handleBatchDelete = () => {
    if (!checkedKeys.length) {
      message.warning('请先勾选要删除的章节');
      return;
    }
    const removeIds = new Set();
    checkedKeys.forEach((id) => {
      getNodeDescendantIds(outlineNodes, id).forEach((rid) => removeIds.add(rid));
    });
    const next = outlineNodes.filter((n) => !removeIds.has(n.id));
    setNodes(recomputeOutlineStructure(next));
    setCheckedKeys([]);
    setSelectedNodeId(null);
    message.success(`已删除 ${removeIds.size} 个节点`);
  };

  const handleBatchEditApply = () => {
    if (!checkedKeys.length) {
      message.warning('请先勾选要编辑的章节');
      return;
    }
    const next = outlineNodes.map((n) => {
      if (!checkedKeys.includes(n.id)) return n;
      let title = n.title || '';
      if (batchFind) title = title.split(batchFind).join(batchReplace || '');
      if (batchPrefix) title = `${batchPrefix}${title}`;
      if (batchSuffix) title = `${title}${batchSuffix}`;
      return { ...n, title };
    });
    setNodes(recomputeOutlineStructure(next));
    setBatchEditOpen(false);
    setBatchPrefix('');
    setBatchSuffix('');
    setBatchFind('');
    setBatchReplace('');
    message.success(`已批量更新 ${checkedKeys.length} 个章节标题`);
  };

  const closeBatchEdit = () => {
    setBatchEditOpen(false);
    setBatchPrefix('');
    setBatchSuffix('');
    setBatchFind('');
    setBatchReplace('');
  };

  const leafCount = outlineNodes.filter((n) => n.is_leaf === 1).length;
  const guidanceCount = outlineNodes.filter((n) => n.is_leaf === 1 && (n.guidance_brief || n.content_boundary)).length;
  // 节点已锁但项目仍为 planning：状态不同步，需重新锁定以推进 status
  const statusReady = ['outline_locked', 'generating', 'done'].includes(projectStatus);
  const needsStatusSync = locked && !statusReady;

  useEffect(() => {
    if (!needsStatusSync || loading || statusSyncAttemptedRef.current) return;
    statusSyncAttemptedRef.current = true;
    setLocking(true);
    lockOutline(projectId)
      .then((result) => {
        message.success('已自动同步大纲锁定状态，正在进入内容生成');
        onLocked?.(result);
      })
      .catch(() => {
        // 保留手动同步入口，避免历史数据校验失败时阻塞页面。
        statusSyncAttemptedRef.current = false;
      })
      .finally(() => setLocking(false));
  }, [needsStatusSync, loading, projectId, onLocked]);

  const orderedLeaves = useMemo(() => getOrderedLeaves(outlineNodes), [outlineNodes]);
  const wordEstimate = useMemo(() => {
    const leaves = orderedLeaves;
    const items = leaves.map((leaf) => ({
      id: leaf.id,
      title: leaf.title,
      words: leaf.target_words || 0,
      expandDegraded: !!leaf.expand_degraded,
    }));
    const totalWords = items.reduce((sum, item) => sum + item.words, 0);
    const estimatedPages = estimatePagesFromWords(totalWords);
    return {
      items,
      totalWords,
      estimatedPages,
      targetPages: targetPages || 40,
      unboundLeaves: items.filter((item) => item.words === 0).length,
    };
  }, [orderedLeaves, targetPages]);

  useEffect(() => {
    if (!outlineNodes.length) {
      setSelectedNodeId(null);
      return;
    }
    if (!selectedNodeId || !outlineNodes.some((n) => n.id === selectedNodeId)) {
      const firstLeaf = orderedLeaves[0];
      setSelectedNodeId(firstLeaf?.id || outlineNodes[0].id);
    }
  }, [outlineNodes, orderedLeaves, selectedNodeId]);

  const handleNodeSelect = (keys) => {
    const id = keys[0];
    if (!id) return;
    setSelectedNodeId(id);
  };

  const selectedNode = useMemo(
    () => outlineNodes.find((n) => n.id === selectedNodeId) || null,
    [outlineNodes, selectedNodeId],
  );
  const selectedLeaf = selectedNode?.is_leaf === 1 ? selectedNode : null;

  const step1Done = catalogCount > 0;
  useEffect(() => {
    refreshSplitPreview();
  }, [refreshSplitPreview]);

  const step2Done = outlineNodes.length > 0;
  const step3Done = locked && statusReady;
  const wizardInitializedRef = useRef(false);

  useEffect(() => {
    if (locked && statusReady) {
      setWizardStep(3);
      wizardInitializedRef.current = true;
      return;
    }
    if (needsStatusSync) {
      setWizardStep(3);
      wizardInitializedRef.current = true;
      return;
    }
    if (wizardInitializedRef.current) return;
    if (loading) return;
    if (!step1Done) setWizardStep(1);
    else if (!step2Done) setWizardStep(2);
    else setWizardStep(2);
    wizardInitializedRef.current = true;
  }, [locked, statusReady, needsStatusSync, loading, step1Done, step2Done]);

  const wizardNavSteps = [
    { num: 1, shortTitle: '定目录', title: '定目录', done: step1Done },
    { num: 2, shortTitle: '深化审核', title: '深化并审核', done: step2Done },
    { num: 3, shortTitle: '锁定', title: '确认锁定', done: step3Done },
  ];

  return (
    <Card
      title={(
        <Space>
          大纲策划
          {locked && <Tag color="green">已锁定</Tag>}
        </Space>
      )}
      className="section-card outline-workspace-card"
      variant="borderless"
      style={{ marginTop: 0 }}
    >
      {loading && outlineNodes.length === 0 && !generating ? (
        <div className="outline-page-state">
          <Spin tip="加载大纲…" />
        </div>
      ) : (
        <div className="outline-workspace">
          {needsStatusSync && (
            <Alert
              type="warning"
              showIcon
              message="大纲节点已锁，但项目状态仍为「planning」，无法生成正文"
              description={locking ? '正在自动同步项目状态…' : '自动同步未成功，请在「确认锁定」中重新锁定。'}
              style={{ marginBottom: 12 }}
            />
          )}

          <OutlineStepNav
            steps={wizardNavSteps}
            current={wizardStep}
            onSelect={goWizardStep}
          />

          <div className="outline-workspace-body">
            {wizardStep === 1 && (
              <div className="outline-stage outline-catalog-stage">
                <div className="outline-catalog-side">
                  <div className="outline-stage-title">目录依据</div>
                  <p className="outline-stage-desc">
                    {catalogSource === 'score_points'
                      ? '有已确认评分项时自动填入一级目录；也可重新填入或手写。无评分项请切换「按参考格式生成」。'
                      : '使用本标书核对页中的「投标文件参考格式」生成目录；无提取结果时可手动粘贴。'}
                  </p>
                  <DirectorySourceSwitch
                    value={catalogSource}
                    disabled={locked || switchingSource}
                    loading={switchingSource}
                    previews={catalogPreviews}
                    onChange={handleCatalogSourceChange}
                  />
                  {catalogPreviews?.[catalogSource]?.hint && (
                    <Alert
                      type={catalogPreviews[catalogSource].available ? 'info' : 'warning'}
                      showIcon
                      style={{ marginTop: 12 }}
                      message={catalogPreviews[catalogSource].hint}
                    />
                  )}
                  {catalogSource === 'reference_format'
                    && templates.length > 0
                    && catalogPreviews?.reference_format?.available === false && (
                    <div className="outline-catalog-template">
                      <Text type="secondary" style={{ fontSize: 12 }}>无本标书参考格式时，可选用预设模板</Text>
                      <Select
                        allowClear
                        placeholder="选择预设模板（兜底）"
                        style={{ width: '100%', marginTop: 8 }}
                        disabled={locked}
                        options={templates.map((tpl) => ({
                          value: tpl.id,
                          label: tpl.description ? `${tpl.name}（${tpl.description}）` : tpl.name,
                        }))}
                        onChange={handleApplyTemplate}
                      />
                    </div>
                  )}
                </div>

                <div className="outline-catalog-editor">
                  <div className="outline-stage-title">目录文本</div>
                  <Input.TextArea
                    className="outline-catalog-textarea"
                    value={catalogText}
                    disabled={locked}
                    placeholder={
                      catalogSource === 'score_points'
                        ? '有已确认评分项时将自动填入；也可点下方次要按钮生成，或直接手写目录。'
                        : '将填入本标书「投标文件参考格式」。示例：\n（一）工程概况\n（二）施工组织设计\n（三）施工方案及技术措施\n  1. 基础施工\n  2. 杆塔组立\n  3. 架线施工'
                    }
                    onChange={(e) => setCatalogText(e.target.value)}
                  />
                  <div className="outline-stage-actions">
                    <Button
                      type="primary"
                      loading={loading && !generating && !switchingSource}
                      disabled={locked}
                      onClick={handleSaveCatalog}
                    >
                      保存目录并继续
                    </Button>
                    {catalogSource === 'score_points' && (
                      <Button
                        loading={switchingSource}
                        disabled={locked || catalogPreviews?.score_points?.available === false}
                        title={
                          catalogPreviews?.score_points?.available === false
                            ? (catalogPreviews?.score_points?.hint || '请先确认评分项')
                            : undefined
                        }
                        onClick={handleGenerateFromScorePoints}
                      >
                        按评分点重新填入
                      </Button>
                    )}
                    {catalogSource === 'reference_format' && (
                      <Button
                        loading={switchingSource}
                        disabled={locked || catalogPreviews?.reference_format?.available === false}
                        title={
                          catalogPreviews?.reference_format?.available === false
                            ? (catalogPreviews?.reference_format?.hint || '本标书暂无参考格式，请回核对页补充或手动粘贴')
                            : undefined
                        }
                        onClick={handleApplyReferenceFormat}
                      >
                        应用本标书参考格式
                      </Button>
                    )}
                    {step1Done && (
                      <Text type="success" style={{ fontSize: 12 }}>已识别 {catalogCount} 个章节</Text>
                    )}
                  </div>
                </div>
              </div>
            )}

            {wizardStep === 2 && (
              <div className="outline-stage outline-review-stage">
                <div className="outline-review-toolbar">
                  <div className="outline-review-toolbar-main">
                    <Text type="secondary" style={{ fontSize: 12 }}>生成档位</Text>
                    <DisplayModeSwitch
                      value={generationMode}
                      disabled={locked}
                      loading={switchingMode}
                      onChange={handleGenerationModeChange}
                    />
                    <Button
                      type="primary"
                      loading={generating}
                      disabled={!step1Done || locked}
                      onClick={handleGenerate}
                    >
                      {step2Done ? '重新 AI 深化' : 'AI 深化大纲'}
                    </Button>
                    {step2Done && (
                      <Button
                        size="small"
                        loading={validating}
                        disabled={outlineNodes.length === 0}
                        onClick={() => handleValidate()}
                      >
                        检查绑定
                      </Button>
                    )}
                    <Button
                      size="small"
                      loading={splittingLong}
                      disabled={!step2Done || locked || splitPreviewCount === 0}
                      onClick={() => handleSplitLongLeaves()}
                    >
                      拆分长章节{splitPreviewCount > 0 ? ` (${splitPreviewCount})` : ''}
                    </Button>
                    <Button size="small" disabled={!step1Done} onClick={() => setPromptOpen(true)}>
                      查看提示词
                    </Button>
                  </div>
                  <div className="outline-review-toolbar-meta">
                    {step2Done ? (
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {outlineNodes.length} 节点 · {leafCount} 叶子 · {guidanceCount} 含写作指导
                      </Text>
                    ) : (
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {!step1Done ? '请先完成定目录' : '深化后将在此审阅章节树并调整绑定'}
                      </Text>
                    )}
                    {step2Done && !generating && (
                      <Button type="default" onClick={() => goWizardStep(3)}>
                        下一步：确认锁定
                      </Button>
                    )}
                  </div>
                </div>

                <details className="outline-facts-details">
                  <summary>
                    <span>全局写作约束（可选）</span>
                    <Text type="secondary">统一全文中的人名、品牌、数字和术语</Text>
                  </summary>
                  <div className="outline-facts-details-body">
                    <GlobalFactsPanel projectId={projectId} title="约束分组" />
                  </div>
                </details>

                {generating && (
                  <Alert
                    type="info"
                    showIcon
                    message="正在调用 AI 深化大纲…"
                    description="系统正在生成骨架并逐支展开章节，通常需要 1～3 分钟，请勿关闭页面。"
                  />
                )}
                {outlineWarnings.length > 0 && (
                  <Alert
                    type="warning"
                    showIcon
                    message={`${outlineWarnings.length} 条大纲质量提示`}
                    description={(
                      <div>
                        {outlineWarnings.map((w, i) => (
                          <div key={i}>• {w}</div>
                        ))}
                      </div>
                    )}
                  />
                )}
                {validation && !validation.passed && (
                  <Alert
                    type="warning"
                    showIcon
                    message={validation.message || '刚性风险评分项未完全绑定'}
                    description={(
                      <div>
                        {(validation.uncovered_risk_items || []).slice(0, 8).map((item) => (
                          <div key={item.id}>· {item.title}</div>
                        ))}
                      </div>
                    )}
                  />
                )}
                {validation && validation.passed && (
                  <Alert
                    type="success"
                    showIcon
                    message="绑定检查通过，可以锁定"
                    description={
                      validation.has_advisory_gaps
                        ? '刚性项已覆盖；仍有建议性未绑定项，可在生成后通过「响应矩阵」查看。'
                        : '评分项覆盖良好。'
                    }
                  />
                )}

                <div className="outline-review-main">
                  {step2Done ? (
                    <OutlineTreeEditor
                      projectId={projectId}
                      nodes={outlineNodes}
                      generating={generating}
                      saving={saving}
                      splittingLong={splittingLong}
                      longLeafThreshold={LONG_LEAF_SPLIT_THRESHOLD}
                      selectedNodeId={selectedNodeId}
                      checkedKeys={checkedKeys}
                      requirements={requirements}
                      folders={folders}
                      orderedLeaves={orderedLeaves}
                      selectedNode={selectedNode}
                      selectedLeaf={selectedLeaf}
                      knowledge={knowledge}
                      onSelect={handleNodeSelect}
                      onCheck={setCheckedKeys}
                      onUpdateNode={updateNode}
                      onAddRoot={handleAddRoot}
                      onAddChild={handleAddChild}
                      onAddSibling={handleAddSibling}
                      onDeleteNode={handleDeleteNode}
                      onBatchDelete={handleBatchDelete}
                      onOpenBatchEdit={() => setBatchEditOpen(true)}
                      onSave={handleSave}
                      onSplitLeaf={(leafId) => handleSplitLongLeaves(leafId)}
                    />
                  ) : (
                    <div className="outline-review-empty">
                      <Text type="secondary">
                        点击上方「AI 深化大纲」后，将在此左右分栏审阅章节树并编辑写作要点。
                      </Text>
                    </div>
                  )}
                </div>
              </div>
            )}

            {wizardStep === 3 && (
              <div className="outline-stage outline-lock-stage">
                <div className="outline-lock-card">
                  <div className="outline-stage-title">
                    {step3Done ? '大纲已锁定' : needsStatusSync ? '重新锁定以同步状态' : '确认锁定'}
                  </div>
                  <p className="outline-stage-desc">
                    {needsStatusSync
                      ? '章节虽已标记锁定，但项目仍为 planning。再次锁定后即可进入内容生成。'
                      : step3Done
                        ? '结构已确认，内容生成已解锁。仍可返回前两步微调后保存。'
                        : '锁定表示章节结构已确认，并进入内容生成。锁定后仍可回本页调整，修改后请保存。'}
                  </p>

                  {step2Done && wordEstimate.totalWords > 0 && (
                    <div className="outline-lock-estimate">
                      <Text strong>
                        预计全文约 {wordEstimate.totalWords.toLocaleString()} 字
                        （约 {wordEstimate.estimatedPages} 页，目标 {wordEstimate.targetPages} 页）
                      </Text>
                      <div className="outline-lock-estimate-list">
                        {wordEstimate.items.slice(0, 8).map((item) => (
                          <div key={item.id}>
                            {item.expandDegraded ? '⚠ ' : ''}
                            {item.title}：{item.words > 0 ? `${item.words.toLocaleString()} 字` : '未绑定评分项'}
                          </div>
                        ))}
                        {wordEstimate.items.length > 8 && (
                          <div>… 另有 {wordEstimate.items.length - 8} 个叶子章节</div>
                        )}
                        {wordEstimate.unboundLeaves > 0 && (
                          <div className="outline-lock-estimate-warn">
                            {wordEstimate.unboundLeaves} 个章节尚未绑定评分项，暂无字数预估
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {validation && !validation.passed && !step3Done && (
                    <Alert
                      type="warning"
                      showIcon
                      style={{ marginBottom: 16 }}
                      message="尚有未绑定刚性项，锁定可能失败"
                      description={(
                        <Button type="link" size="small" style={{ padding: 0 }} onClick={() => goWizardStep(2)}>
                          返回深化审核，检查绑定
                        </Button>
                      )}
                    />
                  )}

                  <div className="outline-stage-actions">
                    {!step2Done && (
                      <Button onClick={() => goWizardStep(2)}>返回深化审核</Button>
                    )}
                    <Button
                      type="primary"
                      danger={!step3Done}
                      disabled={step3Done || outlineNodes.length === 0}
                      loading={locking}
                      onClick={handleLock}
                    >
                      {step3Done ? '已锁定' : needsStatusSync ? '重新锁定以同步状态' : '锁定并进入内容生成'}
                    </Button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      <KnowledgeItemsDrawer
        open={knowledge.drawerOpen}
        folder={knowledge.folder}
        items={knowledge.items}
        status={knowledge.status}
        error={knowledge.error}
        loading={knowledge.loading}
        onClose={knowledge.closeDrawer}
        onDeleteItem={knowledge.deleteItem}
        onRetry={knowledge.processFolder}
      />

      <PromptInspectorDrawer
        open={promptOpen}
        onClose={() => setPromptOpen(false)}
        title="大纲深化提示词"
        fetchPath={step1Done ? `/projects/${projectId}/prompts/outline` : null}
        hint="展示 AI 深化大纲时发送的 System / User 提示词。修改目录、评分项或全局参数后请重新打开预览。"
      />

      <Modal
        title={`批量编辑目录（已选 ${checkedKeys.length} 项）`}
        open={batchEditOpen}
        onOk={handleBatchEditApply}
        onCancel={closeBatchEdit}
        okText="应用"
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Input addonBefore="前缀" value={batchPrefix} onChange={(e) => setBatchPrefix(e.target.value)} placeholder="可选" />
          <Input addonBefore="后缀" value={batchSuffix} onChange={(e) => setBatchSuffix(e.target.value)} placeholder="可选" />
          <Input addonBefore="查找" value={batchFind} onChange={(e) => setBatchFind(e.target.value)} placeholder="可选" />
          <Input addonBefore="替换" value={batchReplace} onChange={(e) => setBatchReplace(e.target.value)} placeholder="可选" />
        </Space>
      </Modal>
    </Card>
  );
}
export { OutlineEditor };
