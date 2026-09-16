import { ApiClient } from "../../core/api/apiClient";
import { apiEndpoints } from "../../core/api/endpoints";

export interface ApiKeyRecord {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  createdAt: string;
  expiresAt: string;
  revokedAt: string;
  lastUsedAt: string;
}

export interface CreatedApiKey {
  apiKey: ApiKeyRecord;
  rawKey: string;
}

export interface SessionRecord {
  id: string;
  issuedAt: string;
  lastActivityAt: string;
  expiresAt: string;
  status: string;
  device: string;
  current: boolean;
}

export interface MfaSetup {
  factorId: string;
  factorType: string;
  secret: string;
  otpauthUrl: string;
}

export interface MfaConfirmation {
  factorId: string;
  recoveryCodes: string[];
}

export const createSecurityService = (api: ApiClient) => ({
  listApiKeys: (tenantId: string, ownerId: string) => api.get<ApiKeyRecord[]>(apiEndpoints.identity.apiKeys, { query: { tenantId, ownerId } }),
  createApiKey: (tenantId: string, name: string, ownerId: string) => api.post<CreatedApiKey>(apiEndpoints.identity.apiKeys, { tenantId, name, ownerType: "user", ownerId, scopes: [] }),
  revokeApiKey: (id: string) => api.delete<{ revoked: boolean }>(apiEndpoints.identity.apiKey(id), { retry: 0 }),
  listSessions: () => api.get<SessionRecord[]>(apiEndpoints.identity.sessions),
  revokeAllSessions: (userId: string) => api.post<{ revoked: boolean }>(apiEndpoints.identity.revokeAllSessions, { userId }, { retry: 0 }),
  setupMfa: () => api.post<MfaSetup>(apiEndpoints.identity.mfaSetup, { factorType: "totp" }),
  confirmMfa: (factorId: string, code: string) => api.post<MfaConfirmation>(apiEndpoints.identity.mfaConfirm, { factorId, code }),
  disableMfa: (password: string) => api.post<{ disabled: boolean }>(apiEndpoints.identity.mfaDisable, { password }, { retry: 0 }),
});
