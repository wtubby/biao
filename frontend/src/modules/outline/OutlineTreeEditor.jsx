import {
  Button, Input, Select, Tag, Space, Spin, Popconfirm, Alert, Row, Col, Tree, Tooltip, Option, Text,
} from '../../globals.js';

import { KnowledgeFolderActions } from '../knowledge/KnowledgeFolderActions.jsx';
import {
  OutlineReviewBadge, buildOutlineTreeData,
} from './helpers.jsx';

function OutlineTreeEditor({
  projectId,
  nodes,
  generating,
  saving,
  splittingLong = false,
  longLeafThreshold = 1500,
  selectedNodeId,
  checkedKeys,
  requirements,
  folders,
  orderedLeaves,
  selectedNode,
  selectedLeaf,
  knowledge,
  onSelect,
  onCheck,
  onUpdateNode,
  onAddRoot,
  onAddChild,
  onAddSibling,
  onDeleteNode,
  onBatchDelete,
  onOpenBatchEdit,
  onSave,
  onSplitLeaf,
}) {
  const treeData = buildOutlineTreeData(nodes, (n) => (
    <Space size="small">
      <Text strong={n.is_leaf === 1}>{n.title}</Text>
      {n.expand_degraded && (
        <Tooltip title={n.expand_warning || '该分支 AI 展开失败，已降级为单叶子节点'}>
          <Tag color="warning" style={{ margin: 0, fontSize: 11, lineHeight: '18px' }}>
            ⚠ 展开降级
          </Tag>
        </Tooltip>
      )}
      <OutlineReviewBadge status={n.review_status} />
      {n.is_leaf === 1 && (n.guidance_brief || n.content_boundary) && (
        <Tag color="blue" style={{ margin: 0, fontSize: 11, lineHeight: '18px' }}>已深化</Tag>
      )}
      {n.is_leaf === 1 && (n.requirement_ids || []).length > 0 && (
        <Tag color="green" style={{ margin: 0, fontSize: 11, lineHeight: '18px' }}>已绑定</Tag>
      )}
    </Space>
  ));

  if (nodes.length === 0) {
    return <Alert message="请先 AI 深化大纲后再审阅章节" type="info" showIcon style={{ marginBottom: 8 }} />;
  }

  return (
    <Spin spinning={generating}>
      <Row gutter={16}>
        <Col xs={24} md={9}>
          <Space wrap style={{ marginBottom: 8 }}>
            <Button size="small" onClick={onAddRoot}>添加一级章节</Button>
            <Button size="small" onClick={onAddChild} disabled={!selectedNodeId}>添加子节</Button>
            <Button size="small" onClick={onAddSibling} disabled={!selectedNodeId}>添加同级</Button>
            <Popconfirm
              title="删除该章节及其所有子节？"
              onConfirm={onDeleteNode}
              disabled={!selectedNodeId}
            >
              <Button size="small" danger disabled={!selectedNodeId}>删除</Button>
            </Popconfirm>
            <Button size="small" disabled={!checkedKeys.length} onClick={onOpenBatchEdit}>
              批量编辑
            </Button>
            <Popconfirm
              title={`删除已勾选的 ${checkedKeys.length} 个节点及其子节？`}
              onConfirm={onBatchDelete}
              disabled={!checkedKeys.length}
            >
              <Button size="small" danger disabled={!checkedKeys.length}>批量删除</Button>
            </Popconfirm>
          </Space>
          <div className="outline-tree-panel">
            <Tree
              checkable
              checkedKeys={checkedKeys}
              onCheck={(keys) => onCheck(Array.isArray(keys) ? keys : keys.checked)}
              treeData={treeData}
              defaultExpandAll
              selectedKeys={selectedNodeId ? [selectedNodeId] : []}
              onSelect={onSelect}
            />
          </div>
        </Col>
        <Col xs={24} md={15}>
          <div className="outline-leaf-detail">
            {!selectedNode ? (
              <div className="outline-leaf-detail-empty">
                <Text type="secondary">
                  {orderedLeaves.length === 0
                    ? '暂无叶子章节'
                    : '请在左侧选择章节进行编辑'}
                </Text>
              </div>
            ) : !selectedLeaf ? (
              <div className="outline-leaf-detail-body">
                <div className="outline-leaf-detail-title">
                  <Text strong>父级章节</Text>
                  <Text type="secondary" style={{ fontSize: 12 }}>仅可编辑标题；写作指导请选择叶子章节</Text>
                </div>
                <div className="outline-leaf-detail-field">
                  <Text type="secondary" className="outline-leaf-detail-label">章节标题</Text>
                  <Input
                    size="small"
                    value={selectedNode.title}
                    onChange={(e) => onUpdateNode(selectedNode.id, { title: e.target.value })}
                    placeholder="章节标题"
                  />
                </div>
              </div>
            ) : (
              <div className="outline-leaf-detail-body">
                <div className="outline-leaf-detail-title">
                  <Text strong>{selectedLeaf.title || '未命名章节'}</Text>
                  {selectedLeaf.target_words > 0 && (
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      目标约 {selectedLeaf.target_words} 字
                    </Text>
                  )}
                  {onSplitLeaf && selectedLeaf.target_words >= longLeafThreshold && (
                    <Button
                      size="small"
                      loading={splittingLong}
                      onClick={() => onSplitLeaf(selectedLeaf.id)}
                    >
                      结构拆分本节
                    </Button>
                  )}
                </div>
                <div className="outline-leaf-detail-field">
                  <Text type="secondary" className="outline-leaf-detail-label">章节标题</Text>
                  <Input
                    size="small"
                    value={selectedLeaf.title}
                    onChange={(e) => onUpdateNode(selectedLeaf.id, { title: e.target.value })}
                    placeholder="章节标题"
                  />
                </div>
                <div className="outline-leaf-detail-field">
                  <Text type="secondary" className="outline-leaf-detail-label">评分项</Text>
                  <Select
                    mode="multiple"
                    size="small"
                    allowClear
                    style={{ width: '100%' }}
                    value={selectedLeaf.requirement_ids || []}
                    placeholder="可不选"
                    onChange={(v) => onUpdateNode(selectedLeaf.id, { requirement_ids: v || [] })}
                  >
                    {requirements.map((r) => (
                      <Option key={r.id} value={r.id}>{r.requirement_title}</Option>
                    ))}
                  </Select>
                </div>
                <div className="outline-leaf-detail-field">
                  <Text type="secondary" className="outline-leaf-detail-label">知识库</Text>
                  <Select
                    size="small"
                    allowClear
                    style={{ width: '100%' }}
                    value={selectedLeaf.bound_folder || undefined}
                    placeholder={folders.length > 0 ? '可不选' : '暂无文件夹'}
                    disabled={folders.length === 0}
                    onChange={(v) => onUpdateNode(selectedLeaf.id, { bound_folder: v || null })}
                  >
                    {folders.map((f) => <Option key={f} value={f}>{f}</Option>)}
                  </Select>
                </div>
                <div className="outline-leaf-detail-field">
                  <Text type="secondary" className="outline-leaf-detail-label">写作要点</Text>
                  <Input.TextArea
                    rows={3}
                    value={selectedLeaf.guidance_brief || ''}
                    placeholder="本节应写什么、重点回应哪些评分关注点"
                    onChange={(e) => onUpdateNode(selectedLeaf.id, { guidance_brief: e.target.value })}
                  />
                </div>
                <div className="outline-leaf-detail-field">
                  <Text type="secondary" className="outline-leaf-detail-label">内容边界</Text>
                  <Input.TextArea
                    rows={4}
                    value={selectedLeaf.content_boundary || ''}
                    placeholder="写什么、不写什么"
                    onChange={(e) => onUpdateNode(selectedLeaf.id, { content_boundary: e.target.value })}
                  />
                </div>
                {selectedLeaf.expand_degraded && (
                  <Alert
                    type="warning"
                    showIcon
                    style={{ marginTop: 8 }}
                    message="该章节为 AI 展开降级结果"
                    description={selectedLeaf.expand_warning || '请人工检查写作指导与评分项绑定是否完整。'}
                  />
                )}
                <KnowledgeFolderActions
                  folder={selectedLeaf.bound_folder}
                  projectId={projectId}
                  onProcess={knowledge.processFolder}
                  onView={knowledge.openDrawer}
                />
              </div>
            )}
          </div>
        </Col>
      </Row>
      <Button onClick={onSave} loading={saving} style={{ marginTop: 12 }}>
        保存大纲
      </Button>
    </Spin>
  );
}

export { OutlineTreeEditor };
