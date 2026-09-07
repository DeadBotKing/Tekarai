export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export interface ApiErrorItem {
  code: string;
  message: string;
  field?: string;
  details?: Record<string, unknown>;
}

export interface PaginationMeta {
  page?: number;
  pageSize?: number;
  total?: number;
  next?: string | null;
  previous?: string | null;
  nextCursor?: string | null;
  hasNext?: boolean;
}

export interface ApiMeta {
  correlationId?: string;
  pagination?: PaginationMeta;
  [key: string]: unknown;
}

export interface ApiEnvelope<T> {
  success: boolean;
  data: T | null;
  meta: ApiMeta;
  errors: ApiErrorItem[];
}

export interface ApiRequestOptions extends Omit<RequestInit, "body" | "method"> {
  method?: HttpMethod;
  body?: unknown;
  query?: Record<string, string | number | boolean | null | undefined>;
  retry?: number;
  timeoutMs?: number;
  skipAuthRefresh?: boolean;
}

export interface TokenPair {
  accessToken: string;
  refreshToken: string;
  tokenType?: string;
  expiresIn?: number;
}

export interface ApiClientDependencies {
  getAccessToken: () => string | null;
  getRefreshToken: () => string | null;
  setTokens: (tokens: TokenPair) => void;
  clearTokens: () => void;
  getTenantId: () => string | null;
  onUnauthorized?: () => void;
}
