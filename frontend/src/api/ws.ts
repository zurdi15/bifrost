import type { WsEvent } from './types';

export interface UiSocketHandlers {
  onEvent: (event: WsEvent) => void;
  onOpen: () => void;
  onDown: (retryInMs: number) => void;
}

const BACKOFF_BASE_MS = 1000;
const BACKOFF_CAP_MS = 30_000;

/** UI WebSocket with jittered exponential reconnection. The stores own state;
 * this class only moves frames. */
export class UiSocket {
  private ws: WebSocket | null = null;
  private attempts = 0;
  private closed = false;
  private timer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private readonly handlers: UiSocketHandlers,
    private readonly url: string = defaultUrl(),
  ) {}

  connect(): void {
    this.closed = false;
    this.open();
  }

  close(): void {
    this.closed = true;
    if (this.timer) clearTimeout(this.timer);
    this.ws?.close();
    this.ws = null;
  }

  private open(): void {
    const ws = new WebSocket(this.url);
    this.ws = ws;

    ws.onopen = () => {
      this.attempts = 0;
      ws.send(JSON.stringify({ sub: ['metrics', 'nodes', 'containers', 'k8s', 'events'] }));
      this.handlers.onOpen();
    };
    ws.onmessage = (raw: MessageEvent<string>) => {
      try {
        const parsed = JSON.parse(raw.data);
        if (typeof parsed.topic === 'string') this.handlers.onEvent(parsed as WsEvent);
      } catch {
        /* tolerate junk frames */
      }
    };
    ws.onclose = () => this.scheduleReconnect();
    ws.onerror = () => ws.close();
  }

  private scheduleReconnect(): void {
    if (this.closed) return;
    const backoff = Math.min(BACKOFF_BASE_MS * 2 ** this.attempts, BACKOFF_CAP_MS);
    const delay = backoff / 2 + Math.random() * (backoff / 2);
    this.attempts += 1;
    this.handlers.onDown(delay);
    this.timer = setTimeout(() => this.open(), delay);
  }
}

function defaultUrl(): string {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${location.host}/api/ws/ui`;
}
