import { env } from "../../config/env";
import { useAuthStore } from "../store/authStore";
import { syncWithServerTime } from "../store/clockStore";
import type { AccessTokenResponse, ApiErrorPayload } from "../types/domain";

export class ApiClientError extends Error {
  public readonly status: number;
  public readonly errorCode: string;
  public readonly details: Record<string, unknown>;
  public readonly serverTime: string | null;

  public constructor(
    status: number,
    errorCode: string,
    message: string,
    details: Record<string, unknown> = {},
    serverTime: string | null = null,
  ) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.errorCode = errorCode;
    this.details = details;
    this.serverTime = serverTime;
  }
}

export interface ApiRequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE" | undefined;
  body?: unknown;
  headers?: Record<string, string> | undefined;
  params?:
    | Record<string, string | number | boolean | undefined | null>
    | undefined;
  skipAuthRefresh?: boolean | undefined;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function extractAndSyncServerTime(payload: unknown): void {
  if (!isRecord(payload)) {
    return;
  }
  const serverTime = payload["server_time"];
  if (typeof serverTime === "string" && serverTime.length > 0) {
    syncWithServerTime(serverTime);
  }
}

function buildUrl(
  path: string,
  params?: Record<string, string | number | boolean | undefined | null>,
): string {
  const baseUrl = env.VITE_API_BASE_URL.replace(/\/+$/, "");
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const fullUrl = new URL(`${baseUrl}${normalizedPath}`);

  if (params !== undefined) {
    for (const [key, val] of Object.entries(params)) {
      if (val !== undefined && val !== null && String(val).length > 0) {
        fullUrl.searchParams.set(key, String(val));
      }
    }
  }
  return fullUrl.toString();
}

async function tryRefreshAccessToken(): Promise<string | null> {
  const refreshUrl = buildUrl("/auth/refresh");
  const response = await fetch(refreshUrl, {
    method: "POST",
    credentials: "include",
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    useAuthStore.getState().clearSession();
    return null;
  }

  const data: unknown = await response.json();
  extractAndSyncServerTime(data);

  if (isRecord(data) && typeof data["access_token"] === "string") {
    const tokenResponse = data as unknown as AccessTokenResponse;
    useAuthStore.getState().setSession(
      tokenResponse.access_token,
      tokenResponse.user,
    );
    return tokenResponse.access_token;
  }

  return null;
}

export async function apiRequest<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  const method = options.method ?? "GET";
  const url = buildUrl(path, options.params);
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...(options.headers ?? {}),
  };

  const currentToken = useAuthStore.getState().accessToken;
  if (currentToken !== null && headers["Authorization"] === undefined) {
    headers["Authorization"] = `Bearer ${currentToken}`;
  }

  let serializedBody: BodyInit | null = null;
  if (options.body instanceof FormData) {
    serializedBody = options.body;
  } else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    serializedBody = JSON.stringify(options.body);
  }

  const fetchInit: RequestInit = {
    method,
    headers,
    credentials: "include",
  };
  if (serializedBody !== null) {
    fetchInit.body = serializedBody;
  }

  let response = await fetch(url, fetchInit);

  const isAuthEndpoint =
    path.includes("/auth/login") ||
    path.includes("/auth/register") ||
    path.includes("/auth/refresh");

  if (
    response.status === 401 &&
    options.skipAuthRefresh !== true &&
    !isAuthEndpoint
  ) {
    const refreshedToken = await tryRefreshAccessToken();
    if (refreshedToken !== null) {
      headers["Authorization"] = `Bearer ${refreshedToken}`;
      const retryInit: RequestInit = {
        method,
        headers,
        credentials: "include",
      };
      if (serializedBody !== null) {
        retryInit.body = serializedBody;
      }
      response = await fetch(url, retryInit);
    }
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const textBody = await response.text();
  const parsedBody: unknown =
    textBody.length > 0 ? (JSON.parse(textBody) as unknown) : null;

  extractAndSyncServerTime(parsedBody);

  if (!response.ok) {
    if (
      isRecord(parsedBody) &&
      typeof parsedBody["error_code"] === "string" &&
      typeof parsedBody["message"] === "string"
    ) {
      const errorPayload = parsedBody as unknown as ApiErrorPayload;
      throw new ApiClientError(
        response.status,
        errorPayload.error_code,
        errorPayload.message,
        isRecord(errorPayload.details) ? errorPayload.details : {},
        typeof errorPayload.server_time === "string"
          ? errorPayload.server_time
          : null,
      );
    }
    throw new ApiClientError(
      response.status,
      "HTTP_ERROR",
      `Request failed with status ${String(response.status)}`,
    );
  }

  return parsedBody as T;
}

export const apiClient = {
  request: apiRequest,
  get: <T>(
    path: string,
    params?: Record<string, string | number | boolean | undefined | null>,
    headers?: Record<string, string>,
  ): Promise<T> => {
    const opts: ApiRequestOptions = { method: "GET" };
    if (params !== undefined) {
      opts.params = params;
    }
    if (headers !== undefined) {
      opts.headers = headers;
    }
    return apiRequest<T>(path, opts);
  },
  post: <T>(
    path: string,
    body?: unknown,
    headers?: Record<string, string>,
  ): Promise<T> => {
    const opts: ApiRequestOptions = { method: "POST" };
    if (body !== undefined) {
      opts.body = body;
    }
    if (headers !== undefined) {
      opts.headers = headers;
    }
    return apiRequest<T>(path, opts);
  },
  put: <T>(
    path: string,
    body?: unknown,
    headers?: Record<string, string>,
  ): Promise<T> => {
    const opts: ApiRequestOptions = { method: "PUT" };
    if (body !== undefined) {
      opts.body = body;
    }
    if (headers !== undefined) {
      opts.headers = headers;
    }
    return apiRequest<T>(path, opts);
  },
  delete: <T>(
    path: string,
    headers?: Record<string, string>,
  ): Promise<T> => {
    const opts: ApiRequestOptions = { method: "DELETE" };
    if (headers !== undefined) {
      opts.headers = headers;
    }
    return apiRequest<T>(path, opts);
  },
};
