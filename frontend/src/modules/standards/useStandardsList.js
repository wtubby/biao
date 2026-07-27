import { useState, useCallback, useEffect } from '../../globals.js';
import { message } from '../../globals.js';
import { fetchStandards } from '../../api/standards.js';
import { fetchDomains } from '../../api/domains.js';

export function useStandardsList() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [domain, setDomain] = useState(undefined);
  const [status, setStatus] = useState(undefined);
  const [q, setQ] = useState('');
  const [domainOptions, setDomainOptions] = useState([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchStandards({
        domain: domain || undefined,
        status: status || undefined,
        q: q.trim() || undefined,
      });
      setItems(data.items || []);
    } catch (e) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  }, [domain, status, q]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    fetchDomains()
      .then((data) => setDomainOptions(data.domains || []))
      .catch(() => {});
  }, []);

  return {
    items,
    loading,
    domain,
    setDomain,
    status,
    setStatus,
    q,
    setQ,
    domainOptions,
    reload: load,
  };
}
