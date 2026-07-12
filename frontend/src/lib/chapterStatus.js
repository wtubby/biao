/** 解析章节 review_errors（可能是 JSON 字符串或数组） */
export function parseReviewErrors(raw) {
  if (!raw) return [];
  if (Array.isArray(raw)) return raw.map(String);
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.map(String) : [String(parsed)];
  } catch {
    return [String(raw)];
  }
}

export function formatChapterDuration(seconds) {
  if (seconds == null || Number.isNaN(seconds)) return '';
  const value = Number(seconds);
  if (value < 60) return `${value.toFixed(1)}s`;
  const minutes = Math.floor(value / 60);
  const remain = Math.round(value % 60);
  return remain > 0 ? `${minutes}m ${remain}s` : `${minutes}m`;
}

export function getReviewStatusTagColor(status) {
  if (status === 'green') return 'success';
  if (status === 'yellow') return 'warning';
  if (status === 'red') return 'error';
  return 'default';
}

export function formatReviewErrorsText(raw, fallback = '请根据提示修改后重试') {
  const errs = parseReviewErrors(raw);
  return errs.length ? errs.join('；') : fallback;
}
