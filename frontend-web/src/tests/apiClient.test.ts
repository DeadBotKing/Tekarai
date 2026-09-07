import { describe, expect, it, vi } from "vitest";
import { ApiClient, ApiClientError } from "../core/api/apiClient";
import type { TokenPair } from "../core/api/apiTypes";

const responseOf = (body: unknown, status = 200, headers: Record<string, string> = { "content-type": "application/json" }): Response => new Response(JSON.stringify(body), { status, headers });

const deps = (overrides: Partial<{ access: string | null; refresh: string | null; tenant: string | null }> = {}) => {
  let access = overrides.access ?? "access-old";
  let refresh = overrides.refresh ?? "refresh-old";
  return { getAccessToken: () => access, getRefreshToken: () => refresh, setTokens: (tokens: TokenPair) => { access = tokens.accessToken; refresh = tokens.refreshToken; }, clearTokens: vi.fn(), getTenantId: () => overrides.tenant ?? "tenant-a", onUnauthorized: vi.fn() };
};

describe("ApiClient", () => {
  it("sends the standard envelope, tenant context and query parameters", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(responseOf({ success: true, data: { ok: true }, meta: { correlationId: "corr-1" }, errors: [] }));
    const client = new ApiClient({ baseUrl: "", apiVersion: "v1", defaultTimeoutMs: 1000, defaultRetries: 0, fetcher }, deps());
    await expect(client.get<{ ok: boolean }>("projects", { query: { page: 2, empty: "" } })).resolves.toEqual({ ok: true });
    expect(fetcher).toHaveBeenCalledTimes(1);
    const [url, init] = fetcher.mock.calls[0];
    expect(url).toBe("/api/v1/projects?page=2");
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer access-old");
    expect(new Headers(init?.headers).get("X-Tenant-ID")).toBe("tenant-a");
  });

  it("maps backend errors to stable client errors", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(responseOf({ success: false, data: null, meta: {}, errors: [{ code: "PERM_PERMISSION_DENIED", message: "No access." }] }, 403));
    const client = new ApiClient({ baseUrl: "", apiVersion: "v1", defaultTimeoutMs: 1000, defaultRetries: 0, fetcher }, deps());
    const result = client.get("restricted");
    await expect(result).rejects.toBeInstanceOf(ApiClientError);
    await expect(result).rejects.toMatchObject({ status: 403, code: "PERM_PERMISSION_DENIED", message: "No access." });
  });

  it("refreshes once after a 401 and replays the original request", async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(responseOf({ success: false, data: null, meta: {}, errors: [{ code: "AUTH_TOKEN_EXPIRED", message: "Expired." }] }, 401))
      .mockResolvedValueOnce(responseOf({ success: true, data: { accessToken: "access-new", refreshToken: "refresh-new" }, meta: {}, errors: [] }))
      .mockResolvedValueOnce(responseOf({ success: true, data: { id: "p1" }, meta: {}, errors: [] }));
    const client = new ApiClient({ baseUrl: "", apiVersion: "v1", defaultTimeoutMs: 1000, defaultRetries: 0, fetcher }, deps());
    await expect(client.get<{ id: string }>("projects/p1")).resolves.toEqual({ id: "p1" });
    expect(fetcher).toHaveBeenCalledTimes(3);
    expect(new Headers(fetcher.mock.calls[2][1]?.headers).get("Authorization")).toBe("Bearer access-new");
  });
});
