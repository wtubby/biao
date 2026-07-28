import { useState, useCallback, useEffect, useRef } from '../../globals.js';
import { message } from '../../globals.js';
import { fetchStandards } from '../../api/standards.js';
import { fetchDomains } from '../../api/domains.js';

export function useStandardsList() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [domain, setDomain] = useState(undefined);
  const [status, setStatus] = useState(undefined);
  const [q, setQ] = useState('');
  const [debouncedQ, setDebouncedQ] = useState('');
  const [domainOptions, setDomainOptions] = useState([]);
  const requestSeq = useRef(0);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQ(q), 300);
    return () => clearTimeout(timer);
  }, [q]);

  const load = useCallback(async () => {
    const seq = ++requestSeq.current;
    setLoading(true);
    try {
      const data = await fetchStandards({
        domain: domain || undefined,
        status: status || undefined,
        q: debouncedQ.trim() || undefined,
      });
      if (seq !== requestSeq.current) return;
      setItems(data.items || []);
    } catch (e) {
      if (seq === requestSeq.current) message.error(e.message);
    } finally {
      if (seq === requestSeq.current) setLoading(false);
    }
  }, [domain, status, debouncedQ]);

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
