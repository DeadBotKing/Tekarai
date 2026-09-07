export type TelemetryEvent =
  | "navigation"
  | "api_failure"
  | "ui_error"
  | "critical_action"
  | "performance";

interface TelemetryPayload {
  event: TelemetryEvent;
  route?: string;
  status?: number;
  durationMs?: number;
  metadata?: Record<string, string | number | boolean>;
}

const SENSITIVE_KEYS = /token|password|secret|authorization|cookie|email/i;

const redact = (value: Record<string, unknown> = {}): Record<string, unknown> =>
  Object.fromEntries(Object.entries(value).map(([key, item]) => [
    key,
    SENSITIVE_KEYS.test(key) ? "[REDACTED]" : item,
  ]));

export const telemetry = {
  record: (payload: TelemetryPayload): void => {
    if (import.meta.env.DEV) {
      // Development-only diagnostics; sensitive keys are redacted before output.
      console.info("[Tekarai telemetry]", redact(payload as unknown as Record<string, unknown>));
    }
    window.dispatchEvent(new CustomEvent("tekarai:telemetry", { detail: redact(payload as unknown as Record<string, unknown>) }));
  },
};
