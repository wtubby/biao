import {
  Alert, Progress, Spin, Tag, Text,
} from '../../globals.js';
import {
  PARSE_STAGES,
  isParseStageActive,
  isParseStageDone,
} from '../../constants/parseStages.js';
import { Icon } from '../../components/icons.jsx';

function stageStatus(progress, stageKey) {
  const stage = progress?.stage;
  if (stage === 'error') {
    // 失败时：已走过的阶段标完成，当前停在 extracting/saving 前的最后一步用 error
    if (stageKey === 'reading') return 'finish';
    if (stageKey === 'extracting') return 'error';
    return 'wait';
  }
  if (isParseStageDone(stage, stageKey)) return 'finish';
  if (isParseStageActive(stage, stageKey)) return 'process';
  return 'wait';
}

function StageIcon({ status }) {
  if (status === 'finish') return <Icon name="success" size={16} />;
  if (status === 'process') return <Spin size="small" />;
  if (status === 'error') return <Icon name="error" size={16} />;
  return <span className="parse-stage-dot" />;
}

/**
 * 右侧：AI 解析分阶段进度（阅读段落 → 提取关键信息 → 写入结果）
 */
function ParseProgressPanel({
  status,
  parseProgress,
  parseError,
  parseTimedOut,
  uploading,
}) {
  const isParsing = status === 'parsing';
  const progress = parseProgress || (isParsing
    ? { stage: 'reading', label: '阅读文档段落', message: '正在解析中…', percent: 10 }
    : null);
  const percent = typeof progress?.percent === 'number' ? progress.percent : (isParsing ? 10 : 0);
  const showStages = isParsing || progress?.stage === 'done' || progress?.stage === 'error' || !!parseError;

  return (
    <div className="parse-progress-panel">
      <div className="parse-progress-header">
        <Text strong>AI 解析进度</Text>
        {isParsing && <Tag color="processing">解析中</Tag>}
        {progress?.stage === 'done' && !parseError && <Tag color="success">已完成</Tag>}
        {(progress?.stage === 'error' || parseError) && status !== 'parsing' && (
          <Tag color="error">需核对</Tag>
        )}
      </div>

      {parseTimedOut && isParsing && (
        <Alert
          type="warning"
          showIcon
          message="解析超时，请重新上传"
          description="解析已超过 5 分钟仍未完成，可能是网络问题或 API 限流。"
          style={{ marginBottom: 12 }}
        />
      )}

      {parseError && !isParsing && (
        <Alert
          type="error"
          showIcon
          message="解析异常"
          description={parseError}
          style={{ marginBottom: 12 }}
        />
      )}

      {uploading && (
        <Alert type="info" showIcon message="正在上传文件…" style={{ marginBottom: 12 }} />
      )}

      {!showStages && !uploading && (
        <div className="parse-progress-idle">
          <p>上传招标文件后，将在此展示分阶段解析进度：</p>
          <ul>
            <li>阅读文档段落与表格</li>
            <li>提取工程信息与评分项</li>
            <li>写入解析结果供确认</li>
          </ul>
        </div>
      )}

      {showStages && (
        <>
          <Progress
            percent={percent}
            status={progress?.stage === 'error' || parseError ? 'exception' : (progress?.stage === 'done' ? 'success' : 'active')}
            strokeColor={progress?.stage === 'done' ? undefined : { from: '#60a5fa', to: '#2563eb' }}
            style={{ marginBottom: 16 }}
          />
          <p className="parse-progress-message">
            {progress?.message || progress?.label || (isParsing ? '正在解析…' : '')}
          </p>
          <ol className="parse-stage-list">
            {PARSE_STAGES.filter((s) => s.key !== 'done' || progress?.stage === 'done').map((s) => {
              const st = stageStatus(progress, s.key);
              return (
                <li key={s.key} className={`parse-stage-item is-${st}`}>
                  <span className="parse-stage-icon"><StageIcon status={st} /></span>
                  <span className="parse-stage-label">{s.label}</span>
                  {st === 'process' && progress?.chunk_total > 1 && (
                    <span className="parse-stage-meta">
                      {progress.chunk_index}/{progress.chunk_total}
                    </span>
                  )}
                </li>
              );
            })}
          </ol>
        </>
      )}
    </div>
  );
}

export { ParseProgressPanel };
