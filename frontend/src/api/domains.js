import { apiFetch } from './client.js';

export async function fetchDomains() {
  return apiFetch('/domains');
}
