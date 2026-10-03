import type { TokenPair } from "../api/apiTypes";

/**
 * Where the signed-in session lives between page loads.
 *
 * `localStorage`, not `sessionStorage`, and that is a deliberate trade.
 * A technician installs this as an app, walks into a plant with no signal and
 * closes it between jobs. With `sessionStorage` the session dies with the tab
 * and they are asked to log in — which, with no network, is impossible. Work
 * already captured would sit in the queue unreachable. Surviving a restart is
 * the whole point of an offline app, so the tokens have to outlive the tab.
 *
 * The cost is that an XSS bug could read the tokens. That is mitigated where
 * it should be: short-lived access tokens with refresh rotation server-side,
 * no `dangerouslySetInnerHTML` in this codebase, and `logout()` wiping both
 * the tokens and the cached API responses.
 */
const SESSION_KEY = "tekarai.gui.session.v1";

/** Pre-PWA storage; read once so an open tab is not logged out on upgrade. */
const LEGACY_KEY = "tekarai.gui.session.v1";

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

const parseSession = (raw: string | null): StoredSession | null => {
  try {
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

const readStored = (): StoredSession | null => {
  try {
    const current = parseSession(localStorage.getItem(SESSION_KEY));
    if (current) return current;
    const legacy = parseSession(sessionStorage.getItem(LEGACY_KEY));
    if (legacy) {
      // Migrate in place: the next reload finds it in localStorage.
      localStorage.setItem(SESSION_KEY, JSON.stringify(legacy));
      sessionStorage.removeItem(LEGACY_KEY);
    }
    return legacy;
  } catch {
    // Private mode, disabled storage, quota: run from memory only.
    return null;
  }
};

let memorySession: StoredSession | null = readStored();

export const sessionStore = {
  get: (): StoredSession | null => memorySession,
  set: (session: StoredSession): void => {
    memorySession = session;
    try {
      localStorage.setItem(SESSION_KEY, JSON.stringify(session));
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
      localStorage.removeItem(SESSION_KEY);
      sessionStorage.removeItem(LEGACY_KEY);
    } catch {
      // Nothing else to do: the in-memory session is already cleared.
    }
  },
};
