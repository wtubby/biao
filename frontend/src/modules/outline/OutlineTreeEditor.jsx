import {
  useMemo,
  Button, Tag, Text, Spin, Popconfirm, Alert, Tree, Tooltip, Space, Dropdown, Modal,
} from '../../globals.js';

import {
  buildOutlineTreeData, computeOutlineNumberLabels,
} from './helpers.jsx';
import { OutlineLeafDetail } from './OutlineLeafDetail.jsx';

function OutlineTreeEditor({
  nodes,
  generating,
  saving,
  regeneratingLeaf = null,
  selectedNodeId,
  checkedKeys,
  requirements,
  selectedNode,
  selectedLeaf,
  locked = false,
  onSelect,
  onCheck,
  onUpdateNode,
  onAddRoot,
  onAddChild,
  onDeleteNode,
  onBatchDelete,
  onOpenBatchEdit,
  onSave,
  onRegenerateGuidance,
  onUndoGuidance,
  canUndoGuidance = false,
}) {
  const numberLabels = useMemo(() => computeOutlineNumberLabels(nodes), [nodes]);

  const renderNumber = (nodeId) => {
    const label = numberLabels.get(nodeId);
    if (!label) return null;
    return (
      <Text type="secondary" style={{ fontFamily: 'Consolas, monospace', fontSize: 12 }}>
        {label}
      </Text>
    );
  };

  const treeData = buildOutlineTreeData(nodes, (n) => (
    <Space size={4} className="outline-tree-node-title">
      {renderNumber(n.id)}
      <Text strong={n.is_leaf === 1}>{n.title}</Text>
      {n.expand_degraded && (
        <Tooltip title={n.expand_warning || '展开失败，已降级'}>
          <Tag color="warning" style={{ margin: 0, fontSize: 11, lineHeight: '18px' }}>降级</Tag>
        </Tooltip>
      )}
    </Space>
  ));

  if (nodes.length === 0) {
    return (
      <Alert message="请先生成编写思路" type="info" showIcon style={{ marginBottom: 8 }} />
    );
  }

  const batchMenu = {
    items: [
      { key: 'edit', label: '批量改标题', disabled: !checkedKeys.length },
      { key: 'delete', label: '批量删除', danger: true, disabled: !checkedKeys.length },
    ],
    onClick: ({ key }) => {
      if (key === 'edit') onOpenBatchEdit();
      if (key === 'delete') {
        Modal.confirm({
          title: `删除已勾选的 ${checkedKeys.length} 个节点及其子节？`,
          okText: '删除',
          okType: 'danger',
          onOk: () => onBatchDelete(),
        });
      }
    },
  };

  return (
    <Spin spinning={generating} className="outline-tree-editor">
      <div className="outline-tree-editor-layout">
        <div className="outline-tree-editor-left">
          <div className="outline-tree-toolbar">
            <Space size={6} wrap>
              <Button size="small" onClick={onAddRoot}>加一级</Button>
              <Button size="small" onClick={onAddChild} disabled={!selectedNodeId}>加子节</Button>
              <Popconfirm title="删除该章节及子节？" onConfirm={onDeleteNode} disabled={!selectedNodeId}>
                <Button size="small" danger disabled={!selectedNodeId}>删除</Button>
              </Popconfirm>
              <Dropdown menu={batchMenu} trigger={['click']}>
                <Button size="small">
                  批量{checkedKeys.length > 0 ? ` (${checkedKeys.length})` : ''}
                </Button>
              </Dropdown>
            </Space>
          </div>
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
        </div>
        <div className="outline-tree-editor-right">
          <OutlineLeafDetail
            selectedNode={selectedNode}
            selectedLeaf={selectedLeaf}
            renderNumber={renderNumber}
            requirements={requirements}
            regeneratingLeaf={regeneratingLeaf}
            locked={locked}
            saving={saving}
            canUndoGuidance={canUndoGuidance}
            onUpdateNode={onUpdateNode}
            onRegenerateGuidance={onRegenerateGuidance}
            onUndoGuidance={onUndoGuidance}
            onSave={onSave}
          />
        </div>
      </div>
    </Spin>
  );
}

export { OutlineTreeEditor };
