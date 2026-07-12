import {
  Spin, Alert, List, Popconfirm, Button, Drawer,
} from '../../globals.js';

export function KnowledgeItemsDrawer({
  open,
  folder,
  items,
  status,
  error,
  loading,
  onClose,
  onDeleteItem,
  onRetry,
}) {
  return (
    <Drawer
      title={`知识条目：${folder}`}
      open={open}
      onClose={onClose}
      width={480}
    >
      <Spin spinning={loading}>
        {status === 'processing' && (
          <Alert type="info" showIcon message="正在提取知识条目..." style={{ marginBottom: 12 }} />
        )}
        {status === 'failed' && (
          <Alert
            type="error"
            showIcon
            message="知识条目提取失败"
            description={error || '未知错误'}
            action={onRetry ? (
              <Button size="small" danger onClick={() => onRetry(folder)}>
                重试
              </Button>
            ) : null}
            style={{ marginBottom: 12 }}
          />
        )}
        <List
          dataSource={items}
          locale={{ emptyText: '暂无条目，请点击「提取条目」' }}
          renderItem={(item) => (
            <List.Item
              actions={[
                <Popconfirm key="del" title="删除此条目？" onConfirm={() => onDeleteItem(item.id)}>
                  <Button type="link" size="small" danger>删除</Button>
                </Popconfirm>,
              ]}
            >
              <List.Item.Meta title={item.title} description={item.resume} />
            </List.Item>
          )}
        />
      </Spin>
    </Drawer>
  );
}
