import { useEffect, useRef, useState } from 'react';
import { getToken } from '../api';

/** Живой WS-поток портала: replica:new / scene:new / scene:day / stage:event */
export function useLive(onEvent: (ev: any) => void) {
  const cb = useRef(onEvent); cb.current = onEvent;
  const [connected, setConnected] = useState(false);
  useEffect(() => {
    let ws: WebSocket | null = null; let alive = true; let retry: any;
    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      const tok = getToken();
      ws = new WebSocket(`${proto}://${location.host}/ws${tok ? `?token=${tok}` : ''}`);
      ws.onopen = () => alive && setConnected(true);
      ws.onmessage = (e) => { try { const m = JSON.parse(e.data); if (m.event !== 'pong') cb.current(m); } catch {} };
      ws.onclose = () => { alive && setConnected(false); retry = setTimeout(connect, 2500); };
      ws.onerror = () => ws?.close();
    };
    connect();
    const ping = setInterval(() => { if (ws?.readyState === 1) ws.send(JSON.stringify({ type: 'ping' })); }, 20000);
    return () => { alive = false; clearInterval(ping); clearTimeout(retry); ws?.close(); };
  }, []);
  return connected;
}
