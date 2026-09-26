import { useCallback, useEffect, useRef, useState } from "react";
import { runtimeConfig } from "../../app/configuration/runtimeConfig";
import { sessionStore } from "../../core/auth/sessionStore";

/**
 * Thin client for the Phase 8 gateway at `ws/communication/`.
 *
 * The socket authenticates with `?token=<access token>` (the server also accepts
 * an `Authorization: Bearer` header, which browsers cannot set on WebSockets)
 * and rejects unauthenticated upgrades with close code 4401. When realtime is
 * disabled — the default, and always in demo mode — nothing connects and the
 * page simply polls/optimistically updates instead.
 */

export type ChatSocketStatus = "disabled" | "connecting" | "online" | "offline";

export interface ChatRealtimeEvent {
  type: string;
  conversationId?: string;
  payload?: Record<string, unknown>;
}

interface Options {
  enabled: boolean;
  conversationId: string;
  onEvent: (event: ChatRealtimeEvent) => void;
}

const socketUrl = (token: string): string => {
  const base = runtimeConfig.apiBaseUrl || window.location.origin;
  const url = new URL(base, window.location.origin);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = "/ws/communication/";
  url.search = token ? `?token=${encodeURIComponent(token)}` : "";
  return url.toString();
};

export interface ChatRealtime {
  status: ChatSocketStatus;
  /** User ids currently typing in the subscribed conversation. */
  typingUserIds: string[];
  sendTyping: (isTyping: boolean) => void;
}

export function useChatRealtime({ enabled, conversationId, onEvent }: Options): ChatRealtime {
  const active = enabled && runtimeConfig.realtimeEnabled && !runtimeConfig.demoMode;
  const [status, setStatus] = useState<ChatSocketStatus>(active ? "connecting" : "disabled");
  const [typingUserIds, setTypingUserIds] = useState<string[]>([]);
  const socketRef = useRef<WebSocket | null>(null);
  const handlerRef = useRef(onEvent);
  handlerRef.current = onEvent;

  useEffect(() => {
    if (!active || typeof WebSocket === "undefined") {
      setStatus("disabled");
      return undefined;
    }
    const token = sessionStore.get()?.accessToken ?? "";
    let socket: WebSocket;
    try {
      socket = new WebSocket(socketUrl(token));
    } catch {
      setStatus("offline");
      return undefined;
    }
    socketRef.current = socket;
    setStatus("connecting");

    socket.onopen = () => {
      setStatus("online");
      if (conversationId) {
        socket.send(JSON.stringify({ type: "subscribe", conversationId }));
      }
    };
    socket.onclose = () => {
      setStatus("offline");
      socketRef.current = null;
    };
    socket.onerror = () => setStatus("offline");
    socket.onmessage = (event: MessageEvent<string>) => {
      let parsed: Record<string, unknown>;
      try {
        parsed = JSON.parse(event.data) as Record<string, unknown>;
      } catch {
        return;
      }
      const type = String(parsed.type ?? "");
      if (type === "typing") {
        const userId = String(parsed.userId ?? "");
        const isTyping = Boolean(parsed.isTyping);
        setTypingUserIds((current) =>
          isTyping
            ? Array.from(new Set([...current, userId])).filter(Boolean)
            : current.filter((item) => item !== userId),
        );
        return;
      }
      handlerRef.current({
        type,
        conversationId: parsed.conversationId ? String(parsed.conversationId) : undefined,
        payload: (parsed.payload ?? parsed) as Record<string, unknown>,
      });
    };

    return () => {
      if (socket.readyState === WebSocket.OPEN && conversationId) {
        socket.send(JSON.stringify({ type: "unsubscribe", conversationId }));
      }
      socket.close();
      socketRef.current = null;
    };
  }, [active, conversationId]);

  useEffect(() => {
    setTypingUserIds([]);
  }, [conversationId]);

  const sendTyping = useCallback(
    (isTyping: boolean) => {
      const socket = socketRef.current;
      if (!socket || socket.readyState !== WebSocket.OPEN || !conversationId) return;
      socket.send(JSON.stringify({ type: "typing", conversationId, isTyping }));
    },
    [conversationId],
  );

  return { status, typingUserIds, sendTyping };
}
