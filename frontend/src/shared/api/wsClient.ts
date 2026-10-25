import { env } from "../../config/env";
import type { LotWsEvent, UserNotificationWsEvent } from "../types/domain";
import { extractAndSyncServerTime } from "./client";

export interface WsConnectionOptions<TEvent> {
  path: string;
  token?: string | null | undefined;
  sendFirstFrameAuth?: boolean | undefined;
  onEvent: (event: TEvent) => void;
  onOpen?: (() => void) | undefined;
  onClose?: (() => void) | undefined;
  onError?: ((error: Event) => void) | undefined;
}

export interface WsManagedSocket {
  close: () => void;
  sendJson: (payload: Record<string, unknown>) => void;
}

export function handleIncomingWsFrame<TEvent>(
  rawFrame: string | Record<string, unknown>,
  onEvent?: (event: TEvent) => void,
): TEvent {
  const parsed: unknown =
    typeof rawFrame === "string"
      ? (JSON.parse(rawFrame) as unknown)
      : rawFrame;

  extractAndSyncServerTime(parsed);
  const typedEvent = parsed as TEvent;
  onEvent?.(typedEvent);
  return typedEvent;
}

export function buildWsUrl(path: string, token?: string | null): string {
  const baseWs = env.VITE_WS_BASE_URL.replace(/\/+$/, "");
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const url = new URL(`${baseWs}${normalizedPath}`);
  if (token !== undefined && token !== null && token.length > 0) {
    url.searchParams.set("token", token);
  }
  return url.toString();
}

export function connectWebSocket<TEvent>(
  options: WsConnectionOptions<TEvent>,
): WsManagedSocket {
  const queryToken =
    options.sendFirstFrameAuth === true ? null : (options.token ?? null);
  const wsUrl = buildWsUrl(options.path, queryToken);
  const socket = new WebSocket(wsUrl);

  socket.onopen = () => {
    if (
      options.sendFirstFrameAuth === true &&
      options.token !== undefined &&
      options.token !== null &&
      options.token.length > 0
    ) {
      socket.send(
        JSON.stringify({
          type: "AUTH",
          token: options.token,
        }),
      );
    }
    options.onOpen?.();
  };

  socket.onmessage = (messageEvent: MessageEvent<unknown>) => {
    if (typeof messageEvent.data === "string") {
      handleIncomingWsFrame<TEvent>(messageEvent.data, options.onEvent);
    }
  };

  socket.onerror = (errorEvent: Event) => {
    options.onError?.(errorEvent);
  };

  socket.onclose = () => {
    options.onClose?.();
  };

  return {
    close: () => {
      socket.close();
    },
    sendJson: (payload: Record<string, unknown>) => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(payload));
      }
    },
  };
}

export function connectLotStream(
  lotId: string,
  onEvent: (event: LotWsEvent) => void,
): WsManagedSocket {
  return connectWebSocket<LotWsEvent>({
    path: `/lots/${lotId}`,
    onEvent,
  });
}

export function connectUserNotificationsStream(
  token: string,
  onEvent: (event: UserNotificationWsEvent) => void,
  sendFirstFrameAuth = false,
): WsManagedSocket {
  return connectWebSocket<UserNotificationWsEvent>({
    path: "/user/notifications",
    token,
    sendFirstFrameAuth,
    onEvent,
  });
}
