import { Tag } from '../../globals.js';

const STATUS_META = {
  draft: { label: '草稿', color: 'default' },
  active: { label: '现行', color: 'success' },
  superseded: { label: '被替代', color: 'orange' },
  withdrawn: { label: '废止', color: 'error' },
};

export function StandardStatusBadge({ status }) {
  const meta = STATUS_META[status] || { label: status || '未知', color: 'default' };
  return <Tag color={meta.color}>{meta.label}</Tag>;
}
