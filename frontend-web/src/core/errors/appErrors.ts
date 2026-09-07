import { ApiClientError } from "../api/apiClient";

export type ErrorCategory = "validation" | "authentication" | "authorization" | "notFound" | "conflict" | "server" | "network" | "timeout" | "unknown";

export interface UserFacingError {
  category: ErrorCategory;
  title: string;
  message: string;
  code: string;
  retryable: boolean;
}

export const classifyError = (error: unknown): UserFacingError => {
  if (error instanceof ApiClientError) {
    if (error.code === "SYS_NETWORK_ERROR") return { category: "network", title: "Connection problem", message: error.message, code: error.code, retryable: true };
    if (error.code === "SYS_REQUEST_TIMEOUT") return { category: "timeout", title: "Request timed out", message: error.message, code: error.code, retryable: true };
    if (error.status === 401) return { category: "authentication", title: "Access required", message: error.message, code: error.code, retryable: false };
    if (error.status === 403) return { category: "authorization", title: "Permission denied", message: error.message, code: error.code, retryable: false };
    if (error.status === 404) return { category: "notFound", title: "Not found", message: error.message, code: error.code, retryable: false };
    if (error.status === 409) return { category: "conflict", title: "Conflict", message: error.message, code: error.code, retryable: false };
    if (error.status >= 500) return { category: "server", title: "Server error", message: error.message, code: error.code, retryable: true };
    if (error.status === 400) return { category: "validation", title: "Validation error", message: error.message, code: error.code, retryable: false };
  }
  return { category: "unknown", title: "Something went wrong", message: "The operation could not be completed.", code: "SYS_UNKNOWN_ERROR", retryable: true };
};
