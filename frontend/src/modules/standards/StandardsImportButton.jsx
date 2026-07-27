import { useState } from '../../globals.js';
import { Button, Upload, message, Modal } from '../../globals.js';
import { importStandardsFile } from '../../api/standards.js';

export function StandardsImportButton({ onImported }) {
  const [loading, setLoading] = useState(false);

  const beforeUpload = async (file) => {
    setLoading(true);
    try {
      const result = await importStandardsFile(file);
      const errCount = (result.errors || []).length;
      Modal.info({
        title: '导入完成',
        content: (
          <div>
            <p>新建 {result.created || 0} 条，更新 {result.updated || 0} 条。</p>
            {errCount > 0 && (
              <div>
                <p>跳过/失败 {errCount} 行：</p>
                <ul style={{ paddingLeft: 18, margin: 0 }}>
                  {(result.errors || []).slice(0, 8).map((e) => (
                    <li key={e}>{e}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ),
      });
      onImported?.(result);
    } catch (e) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
    return false;
  };

  return (
    <Upload
      accept=".csv,.tsv,.xlsx,.xlsm"
      showUploadList={false}
      beforeUpload={beforeUpload}
    >
      <Button loading={loading}>批量导入</Button>
    </Upload>
  );
}
