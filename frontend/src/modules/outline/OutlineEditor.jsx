import {
  useState, useEffect, useCallback, useMemo, useRef, forwardRef, useImperativeHandle,
  Card, Button, Input, Select, Dropdown,
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
  generateOutline,
  regenerateLeafGuidance,
  saveOutline,
  validateOutline,
  lockOutline,
  previewSplitLongLeaves,
  splitLongLeaves,
} from '../../api/outline.js';
import { fetchRequirements } from '../../api/requirements.js';
import { PromptInspectorDrawer } from '../../components/PromptInspectorDrawer.jsx';
import { DirectorySourceSwitch } from './components.jsx';
import { OutlineTreeEditor } from './OutlineTreeEditor.jsx';
import {
  getOrderedLeaves,
  getNodeDescendantIds, getNextSortOrder, recomputeOutlineStructure,
  createOutlineNode, serializeOutlineNodesForSave,
} from './helpers.jsx';

const OutlineEditor = forwardRef(function OutlineEditor({
  projectId,
  projectStatus = 'planning',
  targetPages = 40,
  onLocked,
  onFooterStateChange,
}, ref) {
  const [nodes, setNodes] = useState([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [locking, setLocking] = useState(false);
  const [validating, setValidating] = useState(false);
  const [validation, setValidation] = useState(null);
  const [locked, setLocked] = useState(false);
  const [requirements, setRequirements] = useState([]);
  const [catalogText, setCatalogText] = useState('');
  const [catalogCount, setCatalogCount] = useState(0);
  const [catalogSource, setCatalogSource] = useState('score_points');
  const [catalogPreviews, setCatalogPreviews] = useState(null);
  const [switchingSource, setSwitchingSource] = useState(false);
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
  const [regeneratingLeaf, setRegeneratingLeaf] = useState(null);
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
      const [outlineBundle, reqs, catalog] = await Promise.all([
        fetchOutlineBundle(projectId),
        fetchRequirements(projectId),
        fetchOutlineCatalog(projectId),
      ]);
      const outline = normalizeOutlineNodes(outlineBundle);
      setNodes(outline);
      setRequirements(reqs.filter((r) => r.status === 'confirmed'));
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

  const goWizardStep = (num) => {
    setWizardStep(num === 1 ? 1 : 2);
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

  const handleRegenerateLeafGuidance = async (leafId) => {
    if (!leafId || locked) return;
    setRegeneratingLeaf(leafId);
    try {
      const leaf = outlineNodes.find((n) => n.id === leafId);
      const result = await regenerateLeafGuidance(projectId, leafId, {
        styleTier: leaf?.style_tier || 'balanced',
      });
      const node = result?.node;
      if (node) {
        setNodes((prev) => normalizeOutlineNodes(prev).map((n) => (
          n.id === node.id
            ? {
              ...n,
              ...node,
              guidance_brief: node.guidance_brief ?? n.guidance_brief,
              content_boundary: node.content_boundary ?? n.content_boundary,
              style_tier: node.style_tier || n.style_tier || 'balanced',
              target_words: node.target_words ?? n.target_words,
            }
            : n
        )));
        message.success('已重新生成编写思路');
      }
    } catch (e) {
      message.error(e.message);
    } finally {
      setRegeneratingLeaf(null);
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

  useImperativeHandle(ref, () => ({
    regenerateIdeas: async () => {
      if (locked) {
        message.warning('大纲已锁定，无法重新生成思路');
        return;
      }
      if (!catalogCount) {
        message.warning('请先完成定目录');
        return;
      }
      await handleGenerate();
    },
    writeBody: async () => {
      await handleLock();
    },
  }), [locked, catalogCount, handleGenerate, handleLock]);

  // 向工作区页脚同步大纲操作态
  useEffect(() => {
    onFooterStateChange?.({
      canRegenerate: !locked && catalogCount > 0,
      canWrite: outlineNodes.length > 0,
      regenerating: generating,
      locking,
      locked,
      statusReady: ['outline_locked', 'generating', 'done'].includes(projectStatus),
    });
  }, [
    locked, catalogCount, outlineNodes.length, generating, locking, projectStatus, onFooterStateChange,
  ]);

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
  const wizardInitializedRef = useRef(false);

  useEffect(() => {
    if (wizardInitializedRef.current) return;
    if (loading) return;
    // 已有目录或大纲时直接进入审阅；锁定态也留在审阅页，由底栏「编写正文」推进
    if (!step1Done) setWizardStep(1);
    else setWizardStep(2);
    wizardInitializedRef.current = true;
  }, [loading, step1Done]);

  const moreMenuItems = [
    {
      key: 'regenerate',
      label: step2Done ? '重新生成思路' : '生成编写思路',
      disabled: !step1Done || locked || generating,
    },
    {
      key: 'catalog',
      label: '改目录文本',
    },
    {
      key: 'validate',
      label: '检查绑定',
      disabled: outlineNodes.length === 0 || validating,
    },
    {
      key: 'split',
      label: splitPreviewCount > 0 ? `拆分长章节 (${splitPreviewCount})` : '拆分长章节',
      disabled: !step2Done || locked || splitPreviewCount === 0 || splittingLong,
    },
    {
      key: 'prompt',
      label: '查看提示词',
      disabled: !step1Done,
    },
  ];

  const handleMoreMenuClick = ({ key }) => {
    if (key === 'regenerate') handleGenerate();
    else if (key === 'catalog') goWizardStep(1);
    else if (key === 'validate') handleValidate();
    else if (key === 'split') handleSplitLongLeaves();
    else if (key === 'prompt') setPromptOpen(true);
  };

  const showCatalog = wizardStep === 1;

  return (
    <Card
      title={(
        <Space>
          {showCatalog ? '定目录' : '目录与编写思路'}
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
          <div className="outline-workspace-body">
            {showCatalog ? (
              <div className="outline-stage outline-catalog-stage">
                <DirectorySourceSwitch
                  value={catalogSource}
                  disabled={locked || switchingSource}
                  loading={switchingSource}
                  previews={catalogPreviews}
                  onChange={handleCatalogSourceChange}
                />
                {catalogPreviews?.[catalogSource]?.hint && (
                  <Text type="secondary" className="outline-catalog-hint">
                    {catalogPreviews[catalogSource].hint}
                  </Text>
                )}
                {catalogSource === 'reference_format'
                  && templates.length > 0
                  && catalogPreviews?.reference_format?.available === false && (
                  <Select
                    allowClear
                    placeholder="选用预设模板"
                    style={{ width: '100%', maxWidth: 360 }}
                    disabled={locked}
                    options={templates.map((tpl) => ({
                      value: tpl.id,
                      label: tpl.description ? `${tpl.name}（${tpl.description}）` : tpl.name,
                    }))}
                    onChange={handleApplyTemplate}
                  />
                )}
                <Input.TextArea
                  className="outline-catalog-textarea"
                  value={catalogText}
                  disabled={locked}
                  placeholder={'每行一个章节，例如：\n（一）工程概况\n（二）施工组织设计\n  1. 基础施工\n  2. 杆塔组立'}
                  onChange={(e) => setCatalogText(e.target.value)}
                />
                <div className="outline-stage-actions">
                  <Button
                    type="primary"
                    loading={loading && !generating && !switchingSource}
                    disabled={locked}
                    onClick={handleSaveCatalog}
                  >
                    {step2Done ? '保存目录' : '保存并继续'}
                  </Button>
                  {catalogSource === 'score_points' && (
                    <Button
                      loading={switchingSource}
                      disabled={locked || catalogPreviews?.score_points?.available === false}
                      onClick={handleGenerateFromScorePoints}
                    >
                      按评分点填入
                    </Button>
                  )}
                  {catalogSource === 'reference_format' && (
                    <Button
                      loading={switchingSource}
                      disabled={locked || catalogPreviews?.reference_format?.available === false}
                      onClick={handleApplyReferenceFormat}
                    >
                      填入参考格式
                    </Button>
                  )}
                  {step1Done && step2Done && (
                    <Button type="link" onClick={() => goWizardStep(2)}>返回编辑</Button>
                  )}
                  {step1Done && (
                    <Text type="secondary" style={{ fontSize: 12 }}>已识别 {catalogCount} 章</Text>
                  )}
                </div>
              </div>
            ) : (
              <div className="outline-stage outline-review-stage">
                <div className="outline-review-toolbar">
                  <div className="outline-review-toolbar-main">
                    {!step2Done && (
                      <Button
                        type="primary"
                        loading={generating}
                        disabled={!step1Done || locked}
                        onClick={handleGenerate}
                      >
                        生成编写思路
                      </Button>
                    )}
                    <Dropdown
                      menu={{ items: moreMenuItems, onClick: handleMoreMenuClick }}
                      trigger={['click']}
                    >
                      <Button size="small">更多</Button>
                    </Dropdown>
                  </div>
                  {step2Done && (
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {leafCount} 章
                      {wordEstimate.totalWords > 0 ? ` · 约 ${wordEstimate.estimatedPages} 页` : ''}
                    </Text>
                  )}
                </div>

                {needsStatusSync && (
                  <Alert
                    type="warning"
                    showIcon
                    message="状态未同步，无法生成正文"
                    action={(
                      <Button size="small" type="link" loading={locking} onClick={handleLock}>
                        同步
                      </Button>
                    )}
                  />
                )}

                {generating && (
                  <Alert type="info" showIcon message="正在生成编写思路与目录，约 1～3 分钟…" />
                )}
                {outlineWarnings.length > 0 && (
                  <Alert
                    type="warning"
                    showIcon
                    message={`${outlineWarnings.length} 条提示`}
                    description={(
                      <div>
                        {outlineWarnings.slice(0, 5).map((w, i) => (
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
                    message={validation.message || '尚有刚性评分项未绑定'}
                    description={(
                      <div>
                        {(validation.uncovered_risk_items || []).slice(0, 5).map((item) => (
                          <div key={item.id}>· {item.title}</div>
                        ))}
                      </div>
                    )}
                  />
                )}

                <div className="outline-review-main">
                  {step2Done ? (
                    <OutlineTreeEditor
                      nodes={outlineNodes}
                      generating={generating}
                      saving={saving}
                      regeneratingLeaf={regeneratingLeaf}
                      selectedNodeId={selectedNodeId}
                      checkedKeys={checkedKeys}
                      requirements={requirements}
                      selectedNode={selectedNode}
                      selectedLeaf={selectedLeaf}
                      locked={locked}
                      onSelect={handleNodeSelect}
                      onCheck={setCheckedKeys}
                      onUpdateNode={updateNode}
                      onAddRoot={handleAddRoot}
                      onAddChild={handleAddChild}
                      onDeleteNode={handleDeleteNode}
                      onBatchDelete={handleBatchDelete}
                      onOpenBatchEdit={() => setBatchEditOpen(true)}
                      onSave={handleSave}
                      onRegenerateGuidance={handleRegenerateLeafGuidance}
                    />
                  ) : (
                    <div className="outline-review-empty">
                      <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
                        目录已就绪。生成后：左侧调结构，右侧改思路。
                      </Text>
                      <Button
                        type="primary"
                        loading={generating}
                        disabled={!step1Done || locked}
                        onClick={handleGenerate}
                      >
                        生成编写思路
                      </Button>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

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
});

export { OutlineEditor };
