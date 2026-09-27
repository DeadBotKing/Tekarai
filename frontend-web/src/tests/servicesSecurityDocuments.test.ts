import { describe, expect, it, vi } from "vitest";
import { ApiClient } from "../core/api/apiClient";
import type { TokenPair } from "../core/api/apiTypes";
import { createDocumentService } from "../features/documents/documentService";
import { createSecurityService } from "../features/security/securityService";

const responseOf = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const envelope = (data: unknown, meta: object = {}): object => ({ success: true, data, meta, errors: [] });

const deps = () => ({
  getAccessToken: () => "access-token",
  getRefreshToken: () => "refresh-token",
  setTokens: (_tokens: TokenPair) => undefined,
  clearTokens: vi.fn(),
  getTenantId: () => "tenant-a",
  onUnauthorized: vi.fn(),
});

const makeClient = (fetcher: typeof fetch): ApiClient =>
  new ApiClient({ baseUrl: "", apiVersion: "v1", defaultTimeoutMs: 1000, defaultRetries: 0, fetcher }, deps());

describe("securityService (users/roles/me/account)", () => {
  it("lists users through the identity endpoint with pagination", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(responseOf(envelope([{ id: "u1", tenantId: "t", username: "ali", email: "ali@x.test", displayName: "علی", status: "active", createdAt: "2026-01-01" }], { totalCount: 1 })));
    const service = createSecurityService(makeClient(fetcher));
    const users = await service.listUsers("ali");
    expect(users).toHaveLength(1);
    expect(users[0].username).toBe("ali");
    expect(fetcher).toHaveBeenCalledWith(expect.stringContaining("users?search=ali"), expect.anything());
  });

  it("invites a user with the backend contract (password >= 12, displayName optional)", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(responseOf(envelope({ id: "u2", tenantId: "t", username: "sara", email: "sara@x.test", displayName: "", status: "active", createdAt: "" }), 201));
    const service = createSecurityService(makeClient(fetcher));
    const invited = await service.inviteUser({ username: "sara", email: "sara@x.test", password: "S3cure!Passw0rd" });
    expect(invited.username).toBe("sara");
    const body = JSON.parse(String((fetcher.mock.calls[0][1] as RequestInit).body));
    expect(body).toEqual({ username: "sara", email: "sara@x.test", password: "S3cure!Passw0rd" });
  });

  it("lists roles, sessions, and starts MFA setup", async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(responseOf(envelope([{ id: "r1", code: "maintenanceManager", name: "مدیر نت", scopeType: "TENANT", actions: ["a.b"] }])))
      .mockResolvedValueOnce(responseOf(envelope([{ id: "s1", userId: "u", issuedAt: "", lastActivityAt: "", expiresAt: "", status: "active", ipAddress: "127.0.0.1", userAgent: "", device: "Chrome", current: true }])))
      .mockResolvedValueOnce(responseOf(envelope({ factorId: "f1", factorType: "totp", secret: "ABC123", otpauthUrl: "otpauth://totp/Tekarai" })));
    const service = createSecurityService(makeClient(fetcher));
    const roles = await service.listRoles();
    expect(roles[0].code).toBe("maintenanceManager");
    const sessions = await service.listSessions();
    expect(sessions[0].current).toBe(true);
    const setup = await service.setupMfa();
    expect(setup.otpauthUrl).toContain("otpauth://");
  });

  it("confirms MFA with factorId + code and receives recovery codes once", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(responseOf(envelope({ factorId: "f1", recoveryCodes: ["rc-1", "rc-2", "rc-3", "rc-4", "rc-5", "rc-6", "rc-7", "rc-8"] })));
    const service = createSecurityService(makeClient(fetcher));
    const result = await service.confirmMfa("f1", "123456");
    expect(result.recoveryCodes).toHaveLength(8);
    const body = JSON.parse(String((fetcher.mock.calls[0][1] as RequestInit).body));
    expect(body).toEqual({ factorId: "f1", code: "123456" });
  });
});

describe("documentService (real library)", () => {
  it("lists documents with search/category filters and pagination", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(responseOf(envelope([{ id: "d1", name: "dastor.pdf", contentType: "application/pdf", sizeBytes: 2048, category: "ایمنی", description: "", uploadedByIdentifier: "ali", uploadedAt: "2026-09-01T10:00:00" }], { totalCount: 1 })));
    const service = createDocumentService(makeClient(fetcher));
    const rows = await service.list({ search: "dastor", category: "ایمنی" });
    expect(rows).toHaveLength(1);
    const url = String(fetcher.mock.calls[0][0]);
    expect(url).toContain("documents?search=dastor");
    expect(url).toContain("limit=100");
  });

  it("downloads as a binary blob and deletes with the real endpoint", async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(new Uint8Array([1, 2, 3]), { status: 200, headers: { "content-type": "application/pdf" } }))
      .mockResolvedValueOnce(responseOf(envelope({ id: "d1", name: "x.pdf", contentType: "", sizeBytes: 0, category: "", description: "", uploadedByIdentifier: "", uploadedAt: "" })));
    const service = createDocumentService(makeClient(fetcher));
    const blob = await service.download("d1");
    expect(blob.size).toBe(3);
    await expect(service.remove("d1")).resolves.toMatchObject({ id: "d1" });
    expect(String((fetcher.mock.calls[1][1] as RequestInit).method)).toBe("DELETE");
  });
});
