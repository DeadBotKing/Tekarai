import type {
  ApiClientDependencies,
  ApiEnvelope,
  ApiRequestOptions,
  ApiErrorItem,
  HttpMethod,
  TokenPair,
} from "./apiTypes";

export class ApiClientError extends Error {
  readonly status: number;
  readonly code: string;
  readonly field?: string;
  readonly details?: Record<string, unknown>;
  readonly correlationId?: string;
  readonly isNetworkError: boolean;

  constructor(
    message: string,
    options: {
      status?: number;
      code?: string;
      field?: string;
      details?: Record<string, unknown>;
      correlationId?: string;
      isNetworkError?: boolean;
    } = {},
  ) {
    super(message);
    this.name = "ApiClientError";
    this.status = options.status ?? 0;
    this.code = options.code ?? "SYS_REQUEST_FAILED";
    this.field = options.field;
    this.details = options.details;
    this.correlationId = options.correlationId;
    this.isNetworkError = options.isNetworkError ?? false;
  }
}

export interface ApiClientConfig {
  baseUrl: string;
  apiVersion: string;
  defaultTimeoutMs: number;
  defaultRetries: number;
  fetcher?: typeof fetch;
}

const safeJson = async (response: Response): Promise<unknown> => {
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    return null;
  }
  try {
    return await response.json();
  } catch {
    return null;
  }
};

const isEnvelope = <T>(payload: unknown): payload is ApiEnvelope<T> => {
  if (!payload || typeof payload !== "object") return false;
  const candidate = payload as Record<string, unknown>;
  return typeof candidate.success === "boolean" && Array.isArray(candidate.errors);
};

const normalizeError = (
  status: number,
  payload: unknown,
  correlationId?: string,
): ApiClientError => {
  if (isEnvelope<unknown>(payload) && payload.errors.length > 0) {
    const first: ApiErrorItem = payload.errors[0];
    return new ApiClientError(first.message, {
      status,
      code: first.code,
      field: first.field,
      details: first.details,
      correlationId: payload.meta.correlationId ?? correlationId,
    });
  }
  return new ApiClientError(status >= 500 ? "The server could not complete the request." : "The request was rejected.", {
    status,
    code: status === 404 ? "SYS_RECORD_NOT_FOUND" : "SYS_REQUEST_FAILED",
    correlationId,
  });
};

const canRetry = (error: unknown): boolean => {
  if (error instanceof DOMException && error.name === "AbortError") return false;
  if (error instanceof ApiClientError) {
    return error.isNetworkError || error.status >= 500 || error.status === 408 || error.status === 429;
  }
  return error instanceof TypeError;
};

const delay = (milliseconds: number): Promise<void> =>
  new Promise((resolve) => window.setTimeout(resolve, milliseconds));

const withQuery = (path: string, query?: ApiRequestOptions["query"]): string => {
  if (!query) return path;
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  });
  const queryString = params.toString();
  return queryString ? `${path}${path.includes("?") ? "&" : "?"}${queryString}` : path;
};

const joinUrl = (baseUrl: string, path: string): string => {
  const cleanBase = baseUrl.replace(/\/$/, "");
  const cleanPath = path.replace(/^\//, "");
  return cleanBase ? `${cleanBase}/${cleanPath}` : `/${cleanPath}`;
};

export class ApiClient {
  private readonly config: ApiClientConfig;
  private readonly dependencies: ApiClientDependencies;
  private readonly inFlight = new Map<string, Promise<unknown>>();
  private isRefreshing = false;
  private refreshPromise: Promise<boolean> | null = null;

  constructor(config: ApiClientConfig, dependencies: ApiClientDependencies) {
    this.config = config;
    this.dependencies = dependencies;
  }

  get<T>(path: string, options: Omit<ApiRequestOptions, "method" | "body"> = {}): Promise<T> {
    return this.request<T>(path, { ...options, method: "GET" });
  }

  post<T>(path: string, body?: unknown, options: Omit<ApiRequestOptions, "method" | "body"> = {}): Promise<T> {
    return this.request<T>(path, { ...options, method: "POST", body });
  }

  patch<T>(path: string, body?: unknown, options: Omit<ApiRequestOptions, "method" | "body"> = {}): Promise<T> {
    return this.request<T>(path, { ...options, method: "PATCH", body });
  }

  delete<T>(path: string, options: Omit<ApiRequestOptions, "method" | "body"> = {}): Promise<T> {
    return this.request<T>(path, { ...options, method: "DELETE" });
  }

  upload<T>(path: string, file: File, options: { fieldName?: string; signal?: AbortSignal; onProgress?: (progress: number) => void } = {}): Promise<T> {
    const controller = new AbortController();
    const request = new XMLHttpRequest();
    const url = joinUrl(this.config.baseUrl, `api/${this.config.apiVersion}/${path}`);
    const accessToken = this.dependencies.getAccessToken();
    const tenantId = this.dependencies.getTenantId();
    return new Promise<T>((resolve, reject) => {
      request.open("POST", url);
      request.timeout = this.config.defaultTimeoutMs;
      request.setRequestHeader("Accept", "application/json");
      request.setRequestHeader("X-Client-Version", "tekarai-gui-0.18.0");
      if (accessToken) request.setRequestHeader("Authorization", `Bearer ${accessToken}`);
      if (tenantId) request.setRequestHeader("X-Tenant-ID", tenantId);
      request.upload.onprogress = (event) => { if (event.lengthComputable) options.onProgress?.(Math.round((event.loaded / event.total) * 100)); };
      request.onload = () => {
        const correlationId = request.getResponseHeader("X-Correlation-ID") ?? undefined;
        let payload: unknown = null;
        try { payload = request.responseText ? JSON.parse(request.responseText) : null; } catch { payload = null; }
        if (request.status < 200 || request.status >= 300) { reject(normalizeError(request.status, payload, correlationId)); return; }
        if (isEnvelope<T>(payload)) { if (!payload.success) reject(normalizeError(request.status, payload, correlationId)); else resolve(payload.data as T); return; }
        resolve(payload as T);
      };
      request.onerror = () => reject(new ApiClientError("The network is unavailable. Please retry.", { code: "SYS_NETWORK_ERROR", isNetworkError: true }));
      request.ontimeout = () => reject(new ApiClientError("The upload timed out or was cancelled.", { code: "SYS_REQUEST_TIMEOUT", status: 408, isNetworkError: true }));
      request.onabort = () => reject(new ApiClientError("The upload was cancelled.", { code: "SYS_REQUEST_CANCELLED", status: 499 }));
      const abort = (): void => { controller.abort(); request.abort(); };
      options.signal?.addEventListener("abort", abort, { once: true });
      request.onloadend = () => options.signal?.removeEventListener("abort", abort);
      const form = new FormData(); form.append(options.fieldName ?? "file", file); request.send(form);
    });
  }

  async request<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
    const method: HttpMethod = options.method ?? "GET";
    const requestPath = withQuery(path, options.query);
    const dedupeKey = method === "GET" ? `${method}:${requestPath}` : "";
    if (dedupeKey) {
      const existing = this.inFlight.get(dedupeKey);
      if (existing) return (await existing) as T;
    }

    const promise = this.execute<T>(requestPath, options);
    if (dedupeKey) {
      this.inFlight.set(dedupeKey, promise);
      promise.finally(() => this.inFlight.delete(dedupeKey)).catch(() => undefined);
    }
    return promise;
  }

  private async execute<T>(path: string, options: ApiRequestOptions): Promise<T> {
    const method = options.method ?? "GET";
    const retries = options.retry ?? (method === "GET" ? this.config.defaultRetries : 0);
    try {
      return await this.executeWithRetry<T>(path, options, retries);
    } catch (error) {
      if (error instanceof ApiClientError && error.status === 401 && !options.skipAuthRefresh) {
        const refreshed = await this.refreshAccessToken();
        if (refreshed) {
          return this.executeWithRetry<T>(path, { ...options, skipAuthRefresh: true }, 0);
        }
        this.dependencies.clearTokens();
        this.dependencies.onUnauthorized?.();
      }
      throw error;
    }
  }

  private async executeWithRetry<T>(path: string, options: ApiRequestOptions, retriesLeft: number): Promise<T> {
    try {
      return await this.executeOnce<T>(path, options);
    } catch (error) {
      if (retriesLeft <= 0 || !canRetry(error)) throw error;
      await delay(200 * 2 ** (this.config.defaultRetries - retriesLeft));
      return this.executeWithRetry<T>(path, options, retriesLeft - 1);
    }
  }

  private async executeOnce<T>(path: string, options: ApiRequestOptions): Promise<T> {
    const controller = new AbortController();
    const timeout = window.setTimeout(
      () => controller.abort(),
      options.timeoutMs ?? this.config.defaultTimeoutMs,
    );
    const signal = options.signal;
    const abortFromCaller = (): void => controller.abort();
    signal?.addEventListener("abort", abortFromCaller, { once: true });
    const accessToken = this.dependencies.getAccessToken();
    const tenantId = this.dependencies.getTenantId();
    const headers = new Headers(options.headers);
    headers.set("Accept", "application/json");
    headers.set("X-Client-Version", "tekarai-gui-0.18.0");
    if (options.body !== undefined) headers.set("Content-Type", "application/json");
    if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
    if (tenantId) headers.set("X-Tenant-ID", tenantId);

    try {
      const fetcher = this.config.fetcher ?? fetch;
      const response = await fetcher(joinUrl(this.config.baseUrl, `api/${this.config.apiVersion}/${path}`), {
        ...options,
        method: options.method ?? "GET",
        headers,
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        signal: controller.signal,
      });
      const correlationId = response.headers.get("X-Correlation-ID") ?? undefined;
      const payload = await safeJson(response);
      if (!response.ok) throw normalizeError(response.status, payload, correlationId);
      if (isEnvelope<T>(payload)) {
        if (!payload.success) throw normalizeError(response.status, payload, correlationId);
        return payload.data as T;
      }
      return payload as T;
    } catch (error) {
      if (error instanceof ApiClientError) throw error;
      if (error instanceof DOMException && error.name === "AbortError") {
        throw new ApiClientError("The request timed out or was cancelled.", {
          code: "SYS_REQUEST_TIMEOUT",
          status: 408,
          isNetworkError: true,
        });
      }
      throw new ApiClientError("The network is unavailable. Please retry.", {
        code: "SYS_NETWORK_ERROR",
        isNetworkError: true,
      });
    } finally {
      window.clearTimeout(timeout);
      signal?.removeEventListener("abort", abortFromCaller);
    }
  }

  private async refreshAccessToken(): Promise<boolean> {
    if (this.isRefreshing && this.refreshPromise) return this.refreshPromise;
    const refreshToken = this.dependencies.getRefreshToken();
    if (!refreshToken) return false;
    this.isRefreshing = true;
    this.refreshPromise = this.post<TokenPair>("auth/refresh", { refreshToken }, {
      skipAuthRefresh: true,
      retry: 0,
    })
      .then((tokens) => {
        this.dependencies.setTokens(tokens);
        return true;
      })
      .catch(() => false)
      .finally(() => {
        this.isRefreshing = false;
        this.refreshPromise = null;
      });
    return this.refreshPromise;
  }
}

export const createApiClient = (
  config: ApiClientConfig,
  dependencies: ApiClientDependencies,
): ApiClient => new ApiClient(config, dependencies);
