import {
  useState, useEffect, useCallback,
  Button, Tag, Space, message, Spin, Alert, Drawer,
} from '../../globals.js';

import { apiFetch } from '../../api/client.js';
function colorizeComplianceHtml(html) {
  if (!html) return '';
  return html
    .replace(/✗/g, '<span class="compliance-mark compliance-mark--fail">✗</span>')
    .replace(/⚠/g, '<span class="compliance-mark compliance-mark--warn">⚠</span>')
    .replace(/△/g, '<span class="compliance-mark compliance-mark--warn">△</span>')
    .replace(/✓/g, '<span class="compliance-mark compliance-mark--pass">✓</span>');
}

function ComplianceReportDrawer({ open, onClose, projectId }) {
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState(null);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const data = await apiFetch(`/projects/${projectId}/compliance/report`);
      setReport(data.exists ? data : null);
    } catch (e) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => { if (open) load(); }, [open, load]);

  const handleRecheck = async () => {
    setLoading(true);
    try {
      const data = await apiFetch(`/projects/${projectId}/compliance/check`, { method: 'POST' });
      setReport({ exists: true, stale: false, ...data });
      message.success('合规检查完成');
    } catch (e) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  const html = report?.markdown && window.marked
    ? { __html: colorizeComplianceHtml(window.marked.parse(report.markdown)) }
    : { __html: '<p style="color:#999">暂无合规报告，点击"重新检查"生成</p>' };

  return (
    <Drawer title="合规终审报告" open={open} onClose={onClose} width={720} destroyOnClose
      extra={<Button size="small" type="primary" loading={loading} onClick={handleRecheck}>重新检查</Button>}
    >
      <Spin spinning={loading}>
        {report?.exists && (
          <Space style={{ marginBottom: 12 }} wrap>
            <Tag color={report.passed ? 'success' : 'error'}>
              {report.passed ? '通过' : '未通过'}
            </Tag>
            <Tag color="error">失败项 {report.failure_count}</Tag>
            <Tag color="warning">警告项 {report.warning_count}</Tag>
          </Space>
        )}
        {report?.stale && (
          <Alert
            type="warning"
            showIcon
            message="有章节在本次检查后被重新生成，报告可能已过期，建议重新检查"
            style={{ marginBottom: 12 }}
          />
        )}
        <div className="markdown-preview md-preview compliance-report" dangerouslySetInnerHTML={html} />
      </Spin>
    </Drawer>
  );
}
export { colorizeComplianceHtml, ComplianceReportDrawer };
