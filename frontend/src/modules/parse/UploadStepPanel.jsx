import {
  Alert, Spin, Dragger,
} from '../../globals.js';
import { ParseProgressPanel } from './ParseProgressPanel.jsx';

function UploadStepPanel({
  project,
  loadingProject,
  uploading,
  parseTimedOut,
  onUpload,
}) {
  const isParsing = project.status === 'parsing';
  const hasSource = !!project.has_source;
  const disabled = loadingProject || uploading || isParsing;

  return (
    <div className="upload-step-panel">
      <div className="upload-step-hero">
        <div className="upload-step-hero-title">需求文件</div>
        <div className="upload-step-hero-desc">
          系统会自动解析并提取关键项目信息，解析完成后进入核对配置
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

      <Spin spinning={uploading} tip="正在上传文件...">
        <div className="upload-product-card-wrap">
          <Dragger
            accept=".pdf,.docx"
            showUploadList={false}
            beforeUpload={onUpload}
            disabled={disabled}
            className="upload-product-dragger"
          >
            <div className="upload-product-card">
              <div className="upload-product-icons" aria-hidden="true">
                <span className="upload-product-icon upload-product-icon--pdf">PDF</span>
                <span className="upload-product-icon upload-product-icon--doc">DOCX</span>
              </div>
              <div className="upload-product-title">
                {isParsing
                  ? '解析进行中，请稍候'
                  : hasSource
                    ? '重新上传招标文件'
                    : '上传文件，快速识别项目核心要点'}
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
