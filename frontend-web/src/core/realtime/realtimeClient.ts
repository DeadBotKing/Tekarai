export interface RealtimeEvent<T = unknown> {
  eventId: string;
  eventType: string;
  timestamp: string;
  payload: T;
}

export interface RealtimeOptions {
  url: string;
  accessToken?: string | null;
  tenantId?: string | null;
  onEvent: (event: RealtimeEvent) => void;
  onStatus?: (status: "connecting" | "connected" | "disconnected" | "error") => void;
}

/** Optional transport adapter. Business logic stays in feature/application code. */
export class RealtimeClient {
  private socket: WebSocket | null = null;
  private reconnectTimer: number | null = null;
  private closed = false;
  private attempts = 0;

  constructor(private readonly options: RealtimeOptions) {}

  connect(): void {
    this.closed = false;
    this.options.onStatus?.("connecting");
    try {
      const separator = this.options.url.includes("?") ? "&" : "?";
      const query = `${separator}tenantId=${encodeURIComponent(this.options.tenantId ?? "")}`;
      this.socket = new WebSocket(`${this.options.url}${query}`);
      this.socket.onopen = () => { this.attempts = 0; this.options.onStatus?.("connected"); };
      this.socket.onmessage = (message) => {
        try { this.options.onEvent(JSON.parse(message.data as string) as RealtimeEvent); } catch { this.options.onStatus?.("error"); }
      };
      this.socket.onerror = () => this.options.onStatus?.("error");
      this.socket.onclose = () => { this.options.onStatus?.("disconnected"); this.scheduleReconnect(); };
    } catch {
      this.options.onStatus?.("error");
      this.scheduleReconnect();
    }
  }

  disconnect(): void {
    this.closed = true;
    if (this.reconnectTimer !== null) window.clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
    this.socket?.close();
    this.socket = null;
  }

  private scheduleReconnect(): void {
    if (this.closed || this.reconnectTimer !== null) return;
    const wait = Math.min(30_000, 1_000 * 2 ** this.attempts++);
    this.reconnectTimer = window.setTimeout(() => { this.reconnectTimer = null; this.connect(); }, wait);
  }
}
