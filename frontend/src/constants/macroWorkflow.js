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
    internalSteps: ['confirm', 'facts'],
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

/** @param {string} currentPage @param {Record<string, boolean>} stepAccess */
export function getMacroWorkflowState(currentPage, stepAccess) {
  const currentMacroKey = getMacroStepKey(currentPage);
  const currentMacroIndex = getMacroStepIndex(currentMacroKey);

  return MACRO_WORKFLOW_STEPS.map((step, index) => {
    const accessible = step.internalSteps.some((key) => stepAccess[key]);
    const isCurrent = step.key === currentMacroKey;
    const isDone = index < currentMacroIndex;
    return {
      ...step,
      index,
      isCurrent,
      isDone,
      accessible,
    };
  });
}
