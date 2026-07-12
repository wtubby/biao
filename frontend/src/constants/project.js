export const PROJECT_TYPES = [
  '线路工程',
  '变电站新建',
  '变电站改造',
  '电缆工程',
  '设备安装',
  '检修调试',
  '其他',
];

export const ENGINEERING_DOMAINS = ['电力工程', '市政工程', '建筑工程', '水利工程', '其他'];

export const CONTRACT_MODES = ['EPC', 'PC', '施工总承包', '设计施工一体化', '其他'];

/** 项目状态展示文案（侧栏/列表/进度环共用） */
export const PROJECT_STATUS_LABELS = {
  draft: '待上传',
  parsing: '解析中',
  confirming: '待确认',
  planning: '大纲策划',
  outline_locked: '待生成',
  generating: '生成中',
  done: '已完成',
};

export const PROJECT_STATUS_BADGES = {
  draft: 'default',
  parsing: 'processing',
  confirming: 'warning',
  planning: 'planning',
  outline_locked: 'ready',
  generating: 'processing',
  done: 'success',
};
