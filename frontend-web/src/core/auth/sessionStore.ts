import type { TokenPair } from "../api/apiTypes";

const SESSION_KEY = "tekarai.gui.session.v1";

export interface StoredSession extends TokenPair {
  user: UserSession;
}

export interface UserSession {
  id: string;
  displayName: string;
  email: string;
  role: string;
  permissions: string[];
}

const readStored = (): StoredSession | null => {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    const session = parsed as Partial<StoredSession>;
    if (!session.accessToken || !session.refreshToken || !session.user) return null;
    return session as StoredSession;
  } catch {
    return null;
  }
};

let memorySession: StoredSession | null = readStored();

export const sessionStore = {
  get: (): StoredSession | null => memorySession,
  set: (session: StoredSession): void => {
    memorySession = session;
    try {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
    } catch {
      // Memory-only fallback keeps the UI usable when storage is unavailable.
    }
  },
  updateTokens: (tokens: TokenPair): void => {
    if (!memorySession) return;
    sessionStore.set({ ...memorySession, ...tokens });
  },
  clear: (): void => {
    memorySession = null;
    try {
      sessionStorage.removeItem(SESSION_KEY);
    } catch {
      // Nothing else to do: the in-memory session is already cleared.
    }
  },
};
