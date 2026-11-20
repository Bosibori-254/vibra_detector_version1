import { useEffect, useState } from 'react';
import type { AlertEvent } from './types';

export function useAlerts(): AlertEvent[] {
  const [events, setEvents] = useState<AlertEvent[]>([]);

  useEffect(() => {
    let socket: WebSocket | undefined;
    let closed = false;

    const connect = (): void => {
      const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
      socket = new WebSocket(`${protocol}://${window.location.host}/ws/alerts`);
      socket.onmessage = (message: MessageEvent<string>) => {
        try {
          const event = JSON.parse(message.data) as AlertEvent;
          setEvents((current) => [event, ...current].slice(0, 100));
        } catch {
          // Ignore malformed events.
        }
      };
      socket.onclose = () => {
        if (!closed) window.setTimeout(connect, 2000);
      };
    };

    connect();
    return () => {
      closed = true;
      socket?.close();
    };
  }, []);

  return events;
}
