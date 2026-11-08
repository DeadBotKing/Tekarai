import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { runtimeConfig } from "../../app/configuration/runtimeConfig";
import type { TokenPair } from "../api/apiTypes";
import { sessionStore, type StoredSession, type UserSession } from "./sessionStore";
import { demoLogin, demoLogout } from "../../features/demo/demoData";
import { useApiClient } from "../api/apiContext";
import { clearCachedApiResponses } from "../offline/registerServiceWorker";

export class FirstPasswordRequiredError extends Error {
  challenge: string;
  constructor(challenge: string) { super('تغییر رمز اولیه لازم است.'); this.challenge = challenge; }
}

export class MfaRequiredError extends Error {
  challenge: string;
  constructor(challenge: string) { super('تأیید دومرحله‌ای لازم است.'); this.challenge = challenge; }
}

interface LoginCredentials {
  tenantCode: string;
  identifier: string;
  password: string;
  /** "Keep me signed in on this device" — off means the tab owns the session. */
  remember?: boolean;
}

interface AuthContextValue {
  session: StoredSession | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  offlinePreview: boolean;
  login: (credentials: LoginCredentials) => Promise<void>;
  logout: () => Promise<void>;
  completeMfa: (challenge: string, code: string, remember: boolean) => Promise<void>;
  updateSessionTokens: (tokens: TokenPair) => void;
  adoptAdministrativeSession: (response: TokenPair & { user: UserSession; permissions?: string[] }) => void;
}

const offlinePreview = runtimeConfig.demoMode;

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }): JSX.Element {
  const api = useApiClient();
  const [session, setSession] = useState<StoredSession | null>(() => sessionStore.get());
  const [isLoading, setIsLoading] = useState(false);

  const updateSessionTokens = useCallback((tokens: TokenPair): void => {
    sessionStore.updateTokens(tokens);
    setSession(sessionStore.get());
  }, []);

  const login = useCallback(async (credentials: LoginCredentials): Promise<void> => {
    setIsLoading(true);
    try {
      let tokens: TokenPair;
      let user: UserSession;
      if (offlinePreview) {
        ({ tokens, user } = await demoLogin(credentials));
      } else {
        const { remember: _remember, ...payload } = credentials;
        const response = await api.post<TokenPair & { user?: UserSession; permissions?: string[]; passwordChangeRequired?: boolean; passwordChangeChallenge?: string; mfaRequired?: boolean; mfaChallenge?: string }>("auth/login", payload);
        if (response.passwordChangeRequired && response.passwordChangeChallenge) {
          throw new FirstPasswordRequiredError(response.passwordChangeChallenge);
        }
        if (response.mfaRequired && response.mfaChallenge) throw new MfaRequiredError(response.mfaChallenge);
        if (!response.accessToken || !response.refreshToken) throw new Error('تأیید ورود تکمیل نشده است.');
        tokens = response;
        const fallback: UserSession = {
          id: "unknown",
          displayName: credentials.identifier,
          email: credentials.identifier,
          role: "Member",
          permissions: [],
        };
        user = { ...fallback, ...(response.user ?? {}), permissions: response.permissions ?? response.user?.permissions ?? [] };
      }
      const nextSession: StoredSession = { ...tokens, user };
      sessionStore.set(nextSession, credentials.remember === true);
      setSession(nextSession);
    } finally {
      setIsLoading(false);
    }
  }, [api]);

  const completeMfa = useCallback(async (challenge: string, code: string, remember: boolean): Promise<void> => {
    setIsLoading(true);
    try {
      const response = await api.post<TokenPair & { user: UserSession; permissions?: string[] }>('auth/mfa/challenge', { challengeToken: challenge, code }, { retry: 0 });
      if (!response.accessToken || !response.refreshToken) throw new Error('تأیید ورود تکمیل نشده است.');
      const next: StoredSession = { ...response, user: { ...response.user, permissions: response.permissions || response.user?.permissions || [] } };
      sessionStore.set(next, remember); setSession(next);
    } finally { setIsLoading(false); }
  }, [api]);

  const adoptAdministrativeSession = useCallback((response: TokenPair & { user: UserSession; permissions?: string[] }): void => {
    if (!response.accessToken || !response.refreshToken || !response.user?.id) throw new Error('ورود مدیریت تکمیل نشده است.');
    // Never spread the response: enrollment secrets/recovery codes are transient.
    const next: StoredSession = {
      accessToken: response.accessToken, refreshToken: response.refreshToken,
      expiresIn: response.expiresIn, tokenType: response.tokenType,
      user: { ...response.user, role: 'Superadmin', permissions: response.permissions ?? [] },
    };
    clearCachedApiResponses();
    sessionStore.set(next, false); setSession(next);
  }, []);

  const logout = useCallback(async (): Promise<void> => {
    setIsLoading(true);
    try {
      const refreshToken = sessionStore.get()?.refreshToken;
      if (offlinePreview) {
        await demoLogout();
      } else if (refreshToken) {
        await api.post("auth/logout", { refreshToken }, { retry: 0 });
      }
    } catch {
      // A local logout must complete even when the server is unavailable.
    } finally {
      sessionStore.clear();
      setSession(null);
      setIsLoading(false);
      // Offline reads are cached by the service worker; a shared phone must
      // not show the next technician the previous one's work orders.
      clearCachedApiResponses();
    }
  }, [api]);

  const value = useMemo<AuthContextValue>(() => ({
    session,
    isAuthenticated: Boolean(session),
    offlinePreview,
    isLoading,
    login,
    logout,
    updateSessionTokens,
    completeMfa,
    adoptAdministrativeSession,
  }), [isLoading, login, logout, session, updateSessionTokens, completeMfa, adoptAdministrativeSession]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = (): AuthContextValue => {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
};
