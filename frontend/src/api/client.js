export const API = `${window.location.origin}/api`;

export function formatApiError(err) {
  if (Array.isArray(err.detail)) {
    return err.detail.map((d) => d.msg || JSON.stringify(d)).join('; ');
  }
  if (err.detail && typeof err.detail === 'object' && err.detail.message) {
    return err.detail.message;
  }
  return err.detail || '请求失败';
}

export async function apiFetch(path, options = {}) {
  const res = await fetch(`${API}${path}`, options);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(formatApiError(err));
  }
  return res.json();
}
