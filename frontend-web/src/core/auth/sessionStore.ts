import type { TokenPair } from "../api/apiTypes";

/**
 * Where the signed-in session lives between page loads — and that is the
 * user's decision, not ours.
 *
 * - **"Keep me signed in" off (default):** `sessionStorage`. The session dies
 *   with the tab, so a shared office PC never lets the next person in.
 * - **On:** `localStorage`. A technician installs this as an app, walks into
 *   a plant with no signal and closes it between jobs; without persistence
 *   they would be asked to log in with no network to do it, and the work
 *   already in the offline queue would be stranded.
 *
 * Persisting costs something — an XSS bug could read the tokens — so it is
 * opt-in, mitigated by short-lived access tokens with server-side refresh
 * rotation and a `logout()` that wipes the tokens and the cached API
 * responses together.
 *
 * A persisted session must carry `remember: true`. One build shipped without
 * the checkbox and wrote every session to `localStorage`; those entries were
 * never consciously chosen, so they are discarded on sight and the person is
 * asked for their password once. Trusting an unmarked entry would mean the
 * upgrade silently keeps logging them in — which is the bug this flag exists
 * to end.
 */
const SESSION_KEY = "tekarai.gui.session.v1";

export interface StoredSession extends TokenPair {
  user: UserSession;
  /** Written only for a session the user asked to keep. */
  remember?: boolean;
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
    // This tab first: a session kept only for the tab must win over a
    // remembered one, otherwise signing in as someone else here would
    // silently revert on the next reload.
    const tabSession = parseSession(sessionStorage.getItem(SESSION_KEY));
    if (tabSession) return tabSession;

    const persisted = parseSession(localStorage.getItem(SESSION_KEY));
    if (persisted?.remember === true) return persisted;
    // Unmarked ⇒ written before the checkbox existed. Drop it.
    if (persisted) localStorage.removeItem(SESSION_KEY);
    return null;
  } catch {
    // Private mode, disabled storage, quota: run from memory only.
    return null;
  }
};

let memorySession: StoredSession | null = readStored();

/** True while the active session was stored with "keep me signed in". */
const isRemembered = (): boolean => memorySession?.remember === true;

export const sessionStore = {
  get: (): StoredSession | null => memorySession,
  /** @param remember persist beyond this tab (the login checkbox). */
  set: (session: StoredSession, remember = isRemembered()): void => {
    const stamped: StoredSession = { ...session, remember };
    memorySession = stamped;
    try {
      const target = remember ? localStorage : sessionStorage;
      const other = remember ? sessionStorage : localStorage;
      target.setItem(SESSION_KEY, JSON.stringify(stamped));
      other.removeItem(SESSION_KEY);
    } catch {
      // Memory-only fallback keeps the UI usable when storage is unavailable.
    }
  },
  updateTokens: (tokens: TokenPair): void => {
    if (!memorySession) return;
    // A token refresh must not quietly promote a tab-only session to a
    // remembered one, so the current choice is preserved.
    sessionStore.set({ ...memorySession, ...tokens }, isRemembered());
  },
  clear: (): void => {
    memorySession = null;
    try {
      localStorage.removeItem(SESSION_KEY);
      sessionStorage.removeItem(SESSION_KEY);
    } catch {
      // Nothing else to do: the in-memory session is already cleared.
    }
  },
};
