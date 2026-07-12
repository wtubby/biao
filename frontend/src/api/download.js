import { API, formatApiError } from './client.js';

export function parseDownloadFilename(res, fallback) {
  const disposition = res.headers.get('Content-Disposition') || '';
  const utfMatch = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utfMatch?.[1]) {
    try {
      return decodeURIComponent(utfMatch[1]);
    } catch {
      /* ignore */
    }
  }
  const plainMatch = disposition.match(/filename="?([^";]+)"?/i);
  if (plainMatch?.[1]) return plainMatch[1];
  return fallback;
}

export async function downloadBlobResponse(res, fallbackName) {
  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = parseDownloadFilename(res, fallbackName);
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

/** 发起导出类请求并触发浏览器下载；失败时抛出 Error */
export async function downloadFromApi(path, fallbackName) {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(formatApiError(err));
  }
  await downloadBlobResponse(res, fallbackName);
  return res;
}
