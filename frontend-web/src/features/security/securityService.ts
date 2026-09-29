import { ApiClient } from "../../core/api/apiClient";
import { apiEndpoints } from "../../core/api/endpoints";

/** Real identity endpoints (Phase 31): users, roles, account & MFA. */

export interface UserAccount {
  id: string;
  tenantId: string;
  username: string;
  email: string;
  displayName: string;
  status: string;
  createdAt: string;
}

export interface RoleRecord {
  id: string;
  code: string;
  name: string;
  scopeType: string;
  actions: string[];
}

export interface SessionRecord {
  id: string;
  userId: string;
  issuedAt: string;
  lastActivityAt: string;
  expiresAt: string;
  status: string;
  ipAddress: string;
  userAgent: string;
  device: string;
  current: boolean;
}

export interface MfaSetupResult {
  factorId: string;
  factorType: string;
  secret: string;
  otpauthUrl: string;
}

export interface MfaConfirmedResult {
  factorId: string;
  recoveryCodes: string[];
}

export interface InviteUserInput {
  username: string;
  email: string;
  password: string;
  displayName?: string;
}

export interface SecurityService {
  listUsers: (search?: string, signal?: AbortSignal) => Promise<UserAccount[]>;
  inviteUser: (input: InviteUserInput, signal?: AbortSignal) => Promise<UserAccount>;
  listRoles: (signal?: AbortSignal) => Promise<RoleRecord[]>;
  createRole: (input: { code: string; name: string; scopeType: string; actions: string[] }, signal?: AbortSignal) => Promise<RoleRecord>;
  updateRole: (roleId: string, input: { name: string; actions: string[] }, signal?: AbortSignal) => Promise<RoleRecord>;
  assignRole: (userId: string, roleId: string, tenantId?: string, signal?: AbortSignal) => Promise<unknown>;
  me: (signal?: AbortSignal) => Promise<{ user: UserAccount; permissions: string[] }>;
  changePassword: (currentPassword: string, newPassword: string, signal?: AbortSignal) => Promise<unknown>;
  listSessions: (signal?: AbortSignal) => Promise<SessionRecord[]>;
  revokeSession: (sessionId: string, signal?: AbortSignal) => Promise<unknown>;
  revokeAllSessions: (signal?: AbortSignal) => Promise<unknown>;
  setupMfa: (signal?: AbortSignal) => Promise<MfaSetupResult>;
  confirmMfa: (factorId: string, code: string, signal?: AbortSignal) => Promise<MfaConfirmedResult>;
  disableMfa: (factorId?: string, signal?: AbortSignal) => Promise<unknown>;
}

const authOptions = { retry: 0 as const };

export const createSecurityService = (api: ApiClient): SecurityService => ({
  listUsers: async (search = "", signal) => {
    const all: UserAccount[] = [];
    for (let page = 1; page <= 200; page += 1) {
      const batch = await api.get<UserAccount[]>(apiEndpoints.users, {
        signal,
        query: { search, page, pageSize: 100 },
      });
      all.push(...batch);
      if (batch.length < 100) break;
    }
    return all;
  },
  inviteUser: (input, signal) =>
    api.post<UserAccount>(apiEndpoints.users, input, { signal, ...authOptions }),
  listRoles: (signal) => api.get<RoleRecord[]>(apiEndpoints.roles, { signal }),
  createRole: (input, signal) => api.post<RoleRecord>(apiEndpoints.roles, input, { signal, ...authOptions }),
  updateRole: (roleId, input, signal) => api.patch<RoleRecord>(`${apiEndpoints.roles}/${roleId}`, input, { signal, ...authOptions }),
  assignRole: (userId, roleId, tenantId, signal) => api.post(`users/${userId}/roles`, { roleId, ...(tenantId ? { tenantId } : {}) }, { signal, ...authOptions }),
  me: (signal) => api.get<{ user: UserAccount; permissions: string[] }>(apiEndpoints.auth.me, { signal }),
  changePassword: (currentPassword, newPassword, signal) =>
    api.post(apiEndpoints.auth.passwordChange, { currentPassword, newPassword }, { signal, ...authOptions }),
  listSessions: (signal) => api.get<SessionRecord[]>(apiEndpoints.identity.sessions, { signal }),
  revokeSession: (sessionId, signal) =>
    api.delete(`${apiEndpoints.identity.sessions}/${sessionId}`, { signal, ...authOptions }),
  revokeAllSessions: (signal) =>
    api.post(apiEndpoints.identity.revokeAllSessions, {}, { signal, ...authOptions }),
  setupMfa: (signal) =>
    api.post<MfaSetupResult>(apiEndpoints.identity.mfaSetup, { factorType: "totp" }, { signal, ...authOptions }),
  confirmMfa: (factorId, code, signal) =>
    api.post<MfaConfirmedResult>(apiEndpoints.identity.mfaConfirm, { factorId, code }, { signal, ...authOptions }),
  disableMfa: (factorId, signal) =>
    api.post(apiEndpoints.identity.mfaDisable, factorId ? { factorId } : {}, { signal, ...authOptions }),
});
