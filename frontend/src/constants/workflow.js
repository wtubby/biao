export const WORKFLOW_STEPS = [
  { key: 'upload', label: '上传标书', icon: 'upload', description: '上传 PDF/DOCX 招标文件，自动解析评分项' },
  { key: 'confirm', label: '确认评分项', icon: 'check', description: '核对评分项与工程全局参数，确认刚性风险项' },
  {
    key: 'commercial',
    label: '商务标',
    icon: 'list',
    description: '可选：编辑并确认商务/资格响应草稿，导出独立分册',
    optional: true,
  },
  {
    key: 'facts',
    label: '全局事实变量',
    icon: 'facts',
    description: '可选：维护技术方案引用的全局事实与变量分组，保证全书数字、人名、品牌一致',
    optional: true,
  },
  { key: 'outline', label: '大纲编辑', icon: 'outline', description: 'AI 深化大纲，可手动增删改章节与写作指导' },
  { key: 'generate', label: '内容生成', icon: 'generate', description: '按章节批量或单章生成技术方案正文' },
  { key: 'preview', label: '预览与导出', icon: 'preview', description: '审阅、修改章节内容并导出 Word 文档' },
];

export const STEP_ORDER = WORKFLOW_STEPS.map((s) => s.key);

/** 主流程顺序（跳过可选步骤），用于底部「下一步」 */
export const PRIMARY_STEP_ORDER = STEP_ORDER.filter(
  (key) => !WORKFLOW_STEPS.find((s) => s.key === key)?.optional,
);

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
