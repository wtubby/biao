export const WORKFLOW_STEPS = [
  { key: 'upload', label: '上传标书', icon: 'upload', description: '上传 PDF/DOCX 招标文件，自动解析评分项' },
  { key: 'confirm', label: '确认评分项', icon: 'check', description: '分步核对工程信息、资格审查、评分项与要求文本，确认后进入大纲' },
  { key: 'outline', label: '大纲编辑', icon: 'outline', description: '设置全局写作约束，AI 深化大纲并审核章节结构' },
  { key: 'generate', label: '内容生成', icon: 'generate', description: '按章节批量或单章生成技术方案正文' },
  { key: 'preview', label: '预览与导出', icon: 'preview', description: '审阅、修改章节内容并导出 Word 文档' },
];

export const STEP_ORDER = WORKFLOW_STEPS.map((s) => s.key);

/** 主流程顺序（跳过可选步骤），用于底部「下一步」 */
export const PRIMARY_STEP_ORDER = STEP_ORDER.filter(
  (key) => !WORKFLOW_STEPS.find((s) => s.key === key)?.optional,
);

const COMPLETED_PRIMARY_STEPS_BY_STATUS = {
  draft: [],
  parsing: [],
  confirming: ['upload'],
  planning: ['upload', 'confirm'],
  outline_locked: ['upload', 'confirm', 'outline'],
  generating: ['upload', 'confirm', 'outline'],
  done: PRIMARY_STEP_ORDER,
};

const PAGE_BY_STATUS = {
  draft: 'upload',
  parsing: 'upload',
  confirming: 'confirm',
  planning: 'outline',
  outline_locked: 'generate',
  generating: 'generate',
  done: 'preview',
};

/** 返回项目状态对应的主流程完成步骤；可选步骤不计入完成率 */
export function getCompletedPrimarySteps(status) {
  return COMPLETED_PRIMARY_STEPS_BY_STATUS[status] || [];
}

export function isWorkflowStepDone(status, stepKey) {
  return getCompletedPrimarySteps(status).includes(stepKey);
}

export function getPageByProjectStatus(status) {
  return PAGE_BY_STATUS[status] || 'upload';
}

/** 返回下一个可进入的步骤 key；无可进入时返回 null */
export function getNextAccessibleStep(currentPage, stepAccess) {
  if (currentPage === 'preview') return null;
  const primaryIdx = PRIMARY_STEP_ORDER.indexOf(currentPage);
  if (primaryIdx >= 0) {
    for (let i = primaryIdx + 1; i < PRIMARY_STEP_ORDER.length; i += 1) {
      const key = PRIMARY_STEP_ORDER[i];
      if (stepAccess[key]) return key;
    }
  }
  const currentStepIndex = STEP_ORDER.indexOf(currentPage);
  for (let i = currentStepIndex + 1; i < STEP_ORDER.length; i += 1) {
    if (stepAccess[STEP_ORDER[i]]) return STEP_ORDER[i];
  }
  return null;
}
