import { Modal, Typography, Tree, Text } from '../../globals.js';
import { buildOutlineTreeData } from '../outline/helpers.jsx';

function FormatConfirmModal({
  open,
  nodes,
  catalogText,
  onConfirm,
  onCancel,
  onGoEdit,
}) {
  const treeData = buildOutlineTreeData(nodes || [], (n) => (
    <Text>{n.title}</Text>
  ));

  return (
    <Modal
      open={open}
      title="确认投标文件格式"
      okText="确认并开始生成"
      cancelText="取消"
      onOk={onConfirm}
      onCancel={onCancel}
      width={560}
      footer={(_, { OkBtn, CancelBtn }) => (
        <div className="format-confirm-footer">
          <CancelBtn />
          <button type="button" className="ant-btn" onClick={onGoEdit}>去修改大纲</button>
          <OkBtn />
        </div>
      )}
    >
      <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
        请确认以下目录结构符合招标文件「投标文件格式 / 技术部分」要求，确认后将开始生成正文。
      </Typography.Paragraph>
      {catalogText && (
        <pre className="format-confirm-catalog">{catalogText.slice(0, 1200)}{catalogText.length > 1200 ? '\n…' : ''}</pre>
      )}
      <div className="format-confirm-tree">
        <Tree treeData={treeData} defaultExpandAll selectable={false} />
      </div>
    </Modal>
  );
}

export { FormatConfirmModal };
