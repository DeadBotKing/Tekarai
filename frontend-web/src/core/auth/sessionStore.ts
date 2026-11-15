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
  tenantId?: string;
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
    // Security: always wipe any persisted (localStorage) session — only the
    // current tab's sessionStorage is trusted. This guarantees the next
    // person to open the browser starts at the login screen.
    localStorage.removeItem(SESSION_KEY);
    const tabSession = parseSession(sessionStorage.getItem(SESSION_KEY));
    if (tabSession) return tabSession;
    return null;
  } catch {
    // Private mode, disabled storage, quota: run from memory only.
    return null;
  }
};

let memorySession: StoredSession | null = readStored();

export const sessionStore = {
  get: (): StoredSession | null => memorySession,
  /** @param _remember IGNORED — persistence is always disabled (shared-PC safety). */
  set: (session: StoredSession, _remember = false): void => {
    // Security policy: never persist across tabs/windows. Session dies with
    // the tab (shared-office-PC safety). Any existing persisted entry from
    // older versions is wiped out.
    const stamped: StoredSession = { ...session, remember: false };
    memorySession = stamped;
    try {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(stamped));
      localStorage.removeItem(SESSION_KEY);
    } catch {
      // Memory-only fallback keeps the UI usable when storage is unavailable.
    }
  },
  updateTokens: (tokens: TokenPair): void => {
    if (!memorySession) return;
    sessionStore.set({ ...memorySession, ...tokens }, false);
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
