import { apiFetch } from './client.js';

export function fetchStandards({ domain, status, q } = {}) {
  const params = new URLSearchParams();
  if (domain) params.set('domain', domain);
  if (status) params.set('status', status);
  if (q) params.set('q', q);
  const qs = params.toString();
  return apiFetch(`/standards${qs ? `?${qs}` : ''}`);
}

export function fetchStandard(code) {
  return apiFetch(`/standards/${encodeURIComponent(code)}`);
}

export function upsertStandard(code, body) {
  return apiFetch(`/standards/${encodeURIComponent(code)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export function markSuperseded(code, byCode) {
  return apiFetch(`/standards/${encodeURIComponent(code)}/mark-superseded`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ by_code: byCode }),
  });
}

export function markWithdrawn(code) {
  return apiFetch(`/standards/${encodeURIComponent(code)}/mark-withdrawn`, { method: 'POST' });
}

export function bootstrapStandards(domain) {
  const params = domain ? `?domain=${encodeURIComponent(domain)}` : '';
  return apiFetch(`/standards/bootstrap${params}`, { method: 'POST' });
}

export function fetchBootstrapStatus(domain) {
  const params = domain ? `?domain=${encodeURIComponent(domain)}` : '';
  return apiFetch(`/standards/bootstrap/status${params}`);
}

export function fetchStandardCoverage() {
  return apiFetch('/standards/coverage');
}

export function importStandardsFile(file) {
  const form = new FormData();
  form.append('file', file);
  return apiFetch('/standards/import', { method: 'POST', body: form });
}
