import {
  Input, Select, Button, Text, Alert, Option, Popconfirm,
} from '../../globals.js';

import { ChapterStyleSwitch } from './components.jsx';

/** 选中章节：标题 / 风格 / 编写思路 / 评分绑定 */
function OutlineLeafDetail({
  selectedNode,
  selectedLeaf,
  renderNumber,
  requirements,
  regeneratingLeaf = null,
  locked = false,
  saving = false,
  canUndoGuidance = false,
  onUpdateNode,
  onRegenerateGuidance,
  onUndoGuidance,
  onSave,
}) {
  if (!selectedNode) {
    return (
      <div className="outline-leaf-detail">
        <div className="outline-leaf-detail-empty">
          <Text type="secondary">在左侧选择章节，编辑编写思路</Text>
        </div>
      </div>
    );
  }

  if (!selectedLeaf) {
    return (
      <div className="outline-leaf-detail">
        <div className="outline-leaf-detail-body">
          <Text type="secondary" style={{ fontSize: 12 }}>父级章节 · 仅改标题</Text>
          <Input
            value={selectedNode.title}
            onChange={(e) => onUpdateNode(selectedNode.id, { title: e.target.value })}
            placeholder="章节标题"
            addonBefore={renderNumber(selectedNode.id)}
          />
          <Button onClick={onSave} loading={saving} className="outline-tree-editor-save">
            保存
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="outline-leaf-detail">
      <div className="outline-leaf-detail-body">
        <div className="outline-leaf-detail-title">
          <Input
            value={selectedLeaf.title}
            onChange={(e) => onUpdateNode(selectedLeaf.id, { title: e.target.value })}
            placeholder="章节标题"
            addonBefore={renderNumber(selectedLeaf.id)}
          />
          {selectedLeaf.target_words > 0 && (
            <Text type="secondary" style={{ fontSize: 12, flexShrink: 0 }}>
              约 {selectedLeaf.target_words} 字
            </Text>
          )}
        </div>

        <div className="outline-leaf-detail-field">
          <ChapterStyleSwitch
            value={selectedLeaf.style_tier || 'balanced'}
            onChange={(tier) => onUpdateNode(selectedLeaf.id, { style_tier: tier })}
          />
        </div>

        <div className="outline-leaf-detail-field outline-leaf-detail-field--grow">
          <div className="outline-leaf-detail-label-row">
            <Text type="secondary" className="outline-leaf-detail-label">编写思路</Text>
            <div className="outline-leaf-detail-actions">
              {canUndoGuidance && (
                <Button
                  type="link"
                  size="small"
                  disabled={locked || regeneratingLeaf === selectedLeaf.id}
                  onClick={() => onUndoGuidance?.(selectedLeaf.id)}
                >
                  撤销
                </Button>
              )}
              <Popconfirm
                title="重新生成将覆盖当前编写思路"
                description="已手工修改的内容会丢失，确定继续？"
                okText="重新生成"
                cancelText="取消"
                disabled={locked || regeneratingLeaf === selectedLeaf.id}
                onConfirm={() => onRegenerateGuidance?.(selectedLeaf.id)}
              >
                <Button
                  type="link"
                  size="small"
                  loading={regeneratingLeaf === selectedLeaf.id}
                  disabled={locked}
                >
                  重新生成
                </Button>
              </Popconfirm>
            </div>
          </div>
          <Input.TextArea
            className="outline-guidance-textarea"
            rows={8}
            value={selectedLeaf.guidance_brief || ''}
            placeholder="本节写什么、重点回应哪些评分点"
            onChange={(e) => onUpdateNode(selectedLeaf.id, { guidance_brief: e.target.value })}
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

        {selectedLeaf.expand_degraded && (
          <Alert
            type="warning"
            showIcon
            message="本节为降级结果，请检查思路与绑定"
            description={selectedLeaf.expand_warning || undefined}
          />
        )}

        <Button type="primary" onClick={onSave} loading={saving} className="outline-tree-editor-save">
          保存
        </Button>
      </div>
    </div>
  );
}

export { OutlineLeafDetail };
