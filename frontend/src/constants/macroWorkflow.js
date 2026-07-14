/** 顶部简化 4 步进度（映射侧栏完整流程） */
export const MACRO_WORKFLOW_STEPS = [
  {
    key: 'parse',
    label: '文件解析',
    shortLabel: '解析',
    internalSteps: ['upload'],
  },
  {
    key: 'confirm',
    label: '核对配置',
    shortLabel: '核对',
    internalSteps: ['confirm'],
  },
  {
    key: 'outline',
    label: '目录生成',
    shortLabel: '目录',
    internalSteps: ['outline'],
  },
  {
    key: 'write',
    label: '正文编写',
    shortLabel: '编写',
    internalSteps: ['generate', 'preview'],
  },
];

export function getMacroStepKey(currentPage) {
  const found = MACRO_WORKFLOW_STEPS.find((step) => step.internalSteps.includes(currentPage));
  return found?.key || 'parse';
}

export function getMacroStepIndex(macroKey) {
  return MACRO_WORKFLOW_STEPS.findIndex((step) => step.key === macroKey);
}

const COMPLETED_MACRO_STEPS_BY_STATUS = {
  draft: [],
  parsing: [],
  confirming: ['parse'],
  planning: ['parse', 'confirm'],
  outline_locked: ['parse', 'confirm', 'outline'],
  generating: ['parse', 'confirm', 'outline'],
  done: MACRO_WORKFLOW_STEPS.map((step) => step.key),
};

/**
 * 当前页面只决定高亮位置；完成状态始终来自项目状态，
 * 避免查看历史页面时进度倒退或跳到未来页面时虚增。
 */
export function getMacroWorkflowState(currentPage, stepAccess, projectStatus) {
  const currentMacroKey = getMacroStepKey(currentPage);
  const completedKeys = COMPLETED_MACRO_STEPS_BY_STATUS[projectStatus] || [];

  return MACRO_WORKFLOW_STEPS.map((step, index) => {
    const accessible = step.internalSteps.some((key) => stepAccess[key]);
    const isCurrent = step.key === currentMacroKey;
    const isDone = completedKeys.includes(step.key);
    return {
      ...step,
      index,
      isCurrent,
      isDone,
      accessible,
    };
  });
}
