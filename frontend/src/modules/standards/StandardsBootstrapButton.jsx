import { useState } from '../../globals.js';
import { Button, Select, Space, message } from '../../globals.js';
import { bootstrapStandards } from '../../api/standards.js';

export function StandardsBootstrapButton({ domainOptions = [], onBootstrapped }) {
  const [domain, setDomain] = useState(undefined);
  const [loading, setLoading] = useState(false);

  const handleClick = async () => {
    setLoading(true);
    try {
      const data = await bootstrapStandards(domain || undefined);
      const n = data.created || 0;
      message.success(n > 0 ? `新建 ${n} 条草稿` : '未发现可新建条目（可能均已存在）');
      onBootstrapped?.(data);
    } catch (e) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Space>
      <Select
        allowClear
        placeholder="全部领域"
        style={{ width: 160 }}
        value={domain}
        onChange={setDomain}
        options={domainOptions.map((d) => ({ value: d.key, label: d.label || d.key }))}
      />
      <Button type="primary" loading={loading} onClick={handleClick}>
        从知识库导入草稿
      </Button>
    </Space>
  );
}
