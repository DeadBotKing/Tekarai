import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { runtimeConfig } from "../../app/configuration/runtimeConfig";
import type { TokenPair } from "../api/apiTypes";
import { sessionStore, type StoredSession, type UserSession } from "./sessionStore";
import { demoLogin, demoLogout } from "../../features/demo/demoData";
import { useApiClient } from "../api/apiContext";

interface LoginCredentials {
  tenantCode: string;
  identifier: string;
  password: string;
}

interface AuthContextValue {
  session: StoredSession | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (credentials: LoginCredentials) => Promise<void>;
  logout: () => Promise<void>;
  updateSessionTokens: (tokens: TokenPair) => void;
}

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
      if (runtimeConfig.demoMode) {
        ({ tokens, user } = await demoLogin(credentials));
      } else {
        const response = await api.post<TokenPair & { user?: UserSession }>("auth/login", credentials);
        tokens = response;
        user = response.user ?? {
          id: "unknown",
          displayName: credentials.identifier,
          email: credentials.identifier,
          role: "Member",
          permissions: [],
        };
      }
      const nextSession: StoredSession = { ...tokens, user };
      sessionStore.set(nextSession);
      setSession(nextSession);
    } finally {
      setIsLoading(false);
    }
  }, [api]);

  const logout = useCallback(async (): Promise<void> => {
    setIsLoading(true);
    try {
      const refreshToken = sessionStore.get()?.refreshToken;
      if (runtimeConfig.demoMode) {
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
    }
  }, [api]);

  const value = useMemo<AuthContextValue>(() => ({
    session,
    isAuthenticated: Boolean(session),
    isLoading,
    login,
    logout,
    updateSessionTokens,
  }), [isLoading, login, logout, session, updateSessionTokens]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = (): AuthContextValue => {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
};
