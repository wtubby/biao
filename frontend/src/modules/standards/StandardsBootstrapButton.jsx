import { useState } from '../../globals.js';
import { Button, Select, Space, message } from '../../globals.js';
import { bootstrapStandards, fetchBootstrapStatus } from '../../api/standards.js';

const POLL_MS = 2000;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitUntilBootstrapSettled(domain) {
  for (;;) {
    const data = await fetchBootstrapStatus(domain);
    const status = data.status || 'idle';
    if (status === 'done' || status === 'failed') {
      return data;
    }
    await sleep(POLL_MS);
  }
}

export function StandardsBootstrapButton({ domainOptions = [], onBootstrapped }) {
  const [domain, setDomain] = useState(undefined);
  const [loading, setLoading] = useState(false);

  const handleClick = async () => {
    setLoading(true);
    try {
      const selected = domain || undefined;
      const started = await bootstrapStandards(selected);
      if (started.status === 'already_running') {
        message.info('导入任务已在进行中，请稍候…');
      } else {
        message.success('已启动从知识库导入草稿');
      }
      const data = await waitUntilBootstrapSettled(selected);
      if (data.status === 'failed') {
        message.error(data.error || '导入失败');
        return;
      }
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
