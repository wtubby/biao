/** 与后端 PARSE_STAGE_* 对齐的解析阶段定义（用于分步进度 UI） */
export const PARSE_STAGES = [
  { key: 'reading', label: '阅读文档段落' },
  { key: 'extracting', label: '提取关键信息' },
  { key: 'saving', label: '写入解析结果' },
  { key: 'done', label: '解析完成' },
];

const STAGE_ORDER = ['reading', 'extracting', 'saving', 'done'];

export function getParseStageIndex(stage) {
  if (!stage || stage === 'error') return -1;
  const idx = STAGE_ORDER.indexOf(stage);
  return idx >= 0 ? idx : -1;
}

export function isParseStageDone(currentStage, stageKey) {
  if (currentStage === 'done') return true;
  if (currentStage === 'error') return false;
  const current = getParseStageIndex(currentStage);
  const target = getParseStageIndex(stageKey);
  if (current < 0 || target < 0) return false;
  return target < current;
}

export function isParseStageActive(currentStage, stageKey) {
  if (!currentStage || currentStage === 'error' || currentStage === 'done') {
    return currentStage === stageKey;
  }
  return currentStage === stageKey;
}
