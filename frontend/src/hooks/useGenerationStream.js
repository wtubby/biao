import { useRef, useCallback, useEffect } from '../globals.js';
import { getGenerationStreamUrl } from '../api/generation.js';

/**
 * 订阅项目批量生成 SSE 流。active 为 true 时断线会自动重连。
 */
export function useGenerationStream({ projectId, active, onEvent }) {
  const esRef = useRef(null);
  const closedRef = useRef(false);
  const reconnectTimerRef = useRef(null);
  const onEventRef = useRef(onEvent);
  const activeRef = useRef(active);

  useEffect(() => { onEventRef.current = onEvent; }, [onEvent]);
  useEffect(() => { activeRef.current = active; }, [active]);

  const disconnect = useCallback(() => {
    closedRef.current = true;
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    esRef.current?.close();
    esRef.current = null;
  }, []);

  const connect = useCallback(() => {
    closedRef.current = false;
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }

    const openConnection = () => {
      if (closedRef.current) return;
      const es = new EventSource(getGenerationStreamUrl(projectId));
      esRef.current = es;
      es.onmessage = (ev) => {
        try {
          onEventRef.current(JSON.parse(ev.data));
        } catch {
          // ignore malformed events
        }
      };
      es.onerror = () => {
        es.close();
        esRef.current = null;
        if (closedRef.current) return;
        if (!activeRef.current) return;
        if (reconnectTimerRef.current) return;
        reconnectTimerRef.current = setTimeout(() => {
          reconnectTimerRef.current = null;
          openConnection();
        }, 3000);
      };
    };

    openConnection();
  }, [projectId]);

  useEffect(() => () => disconnect(), [disconnect]);

  return { connect, disconnect };
}
