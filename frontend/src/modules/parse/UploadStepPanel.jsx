import {
  useRef,
  Alert, Spin, Dragger, Button, Modal, Text,
} from '../../globals.js';
import { ParseProgressPanel } from './ParseProgressPanel.jsx';

const ALLOW_REUPLOAD_STATUSES = new Set(['draft', 'confirming', 'planning']);
const LATE_LOCKED_STATUSES = new Set(['outline_locked', 'generating', 'done']);

function UploadStepPanel({
  project,
  loadingProject,
  uploading,
  parseTimedOut,
  onUpload,
}) {
  const fileInputRef = useRef(null);
  const status = project.status;
  const isParsing = status === 'parsing';
  const hasSource = !!project.has_source;
  const canReupload = ALLOW_REUPLOAD_STATUSES.has(status);
  const isLateLocked = LATE_LOCKED_STATUSES.has(status);
  const busy = loadingProject || uploading || isParsing;
  // 首次上传：尚无文件且仍允许上传
  const showFirstUpload = !hasSource && canReupload && !isParsing;
  // 已有文件或已进入后期：展示只读卡片，避免误拖拽覆盖
  const showReadonlySource = hasSource || isLateLocked;

  const sourceLabel = project.source_type
    ? String(project.source_type).toUpperCase()
    : '已上传文件';
  const sourceIconClass = project.source_type === 'docx'
    ? 'upload-product-icon--doc'
    : 'upload-product-icon--pdf';

  const openReuploadPicker = () => {
    Modal.confirm({
      title: '确认重新上传招标文件？',
      content: '重新上传将清空已确认的评分项、大纲与已生成正文，且不可恢复。确定继续？',
      okText: '确认重新上传',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: () => {
        fileInputRef.current?.click();
      },
    });
  };

  const onFilePicked = (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (file) onUpload(file);
  };

  return (
    <div className="upload-step-panel">
      <div className="upload-step-hero">
        <div className="upload-step-hero-title">需求文件</div>
        <div className="upload-step-hero-desc">
          {showReadonlySource
            ? '下方展示当前已上传的招标文件。更换文件需明确确认，避免误覆盖后续成果。'
            : '系统会自动解析并提取关键项目信息，解析完成后进入核对配置'}
        </div>
      </div>

      {project.parse_error && project.status !== 'parsing' && (
        <Alert
          type="error"
          showIcon
          message="上次解析失败，请重新上传文件"
          description={project.parse_error}
          style={{ marginBottom: 16 }}
        />
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.docx"
        style={{ display: 'none' }}
        onChange={onFilePicked}
      />

      <Spin spinning={uploading} tip="正在上传文件...">
        <div className="upload-product-card-wrap">
          {showFirstUpload ? (
            <Dragger
              accept=".pdf,.docx"
              showUploadList={false}
              beforeUpload={onUpload}
              disabled={busy}
              className="upload-product-dragger"
            >
              <div className="upload-product-card">
                <div className="upload-product-icons" aria-hidden="true">
                  <span className="upload-product-icon upload-product-icon--pdf">PDF</span>
                  <span className="upload-product-icon upload-product-icon--doc">DOCX</span>
                </div>
                <div className="upload-product-title">
                  上传文件，快速识别项目核心要点
                </div>
                <div className="upload-product-desc">
                  点击或拖拽文件到此处，支持 PDF（文字层）与 DOCX
                </div>
                <div className="upload-product-formats">
                  <span>文件格式</span>
                  <em>pdf、docx</em>
                  <span className="upload-product-formats-tip">（不支持扫描版 PDF）</span>
                </div>
              </div>
            </Dragger>
          ) : (
            <div className="upload-product-card upload-product-card--readonly">
              <div className="upload-product-icons" aria-hidden="true">
                <span className={`upload-product-icon ${sourceIconClass}`}>
                  {sourceLabel}
                </span>
              </div>
              <div className="upload-product-title">
                {isParsing ? '解析进行中，请稍候' : '当前已上传招标文件'}
              </div>
              <div className="upload-product-desc">
                {isParsing
                  ? '解析期间不可更换文件'
                  : isLateLocked
                    ? '大纲已锁定或正文已生成，不可在此更换招标文件'
                    : '此区域为只读展示；如需换标书请使用下方「重新上传」'}
              </div>
              {canReupload && !isParsing && (
                <Button
                  danger
                  disabled={busy}
                  onClick={openReuploadPicker}
                  className="upload-reupload-btn"
                >
                  重新上传标书
                </Button>
              )}
              {isLateLocked && (
                <Text type="secondary" className="upload-reupload-hint">
                  若必须换标书，请新建项目后重新走完整流程
                </Text>
              )}
            </div>
          )}
        </div>
      </Spin>

      <Alert
        type="warning"
        showIcon
        className="upload-step-scan-tip"
        message="PDF 须为文字层版本（非扫描件）。扫描件请先 OCR 后再上传。"
      />

      <div className="upload-step-progress">
        <ParseProgressPanel
          status={project.status}
          parseProgress={project.parse_progress}
          parseError={project.parse_error}
          parseTimedOut={parseTimedOut}
          uploading={uploading}
        />
      </div>
    </div>
  );
}

export { UploadStepPanel };
