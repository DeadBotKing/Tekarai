import { describe, expect, it, beforeEach, vi } from "vitest";

const KEY = "tekarai.gui.session.v1";
const session = {
  accessToken: "a",
  refreshToken: "r",
  user: { id: "u1", displayName: "x", email: "x@y.z", role: "technician", permissions: [] },
};

/**
 * The module reads storage once, at import time — the same thing a page load
 * does. So each case needs a fresh module registry.
 */
describe("sessionStore — بازیابی هنگام باز شدن صفحه", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    vi.resetModules();
  });

  it("does NOT restore an unmarked localStorage session (the upgrade case)", async () => {
    localStorage.setItem(KEY, JSON.stringify(session));
    const { sessionStore } = await import("../core/auth/sessionStore");
    expect(sessionStore.get()).toBeNull();
    expect(localStorage.getItem(KEY)).toBeNull();
  });

  it("restores one the user asked to keep", async () => {
    localStorage.setItem(KEY, JSON.stringify({ ...session, remember: true }));
    const { sessionStore } = await import("../core/auth/sessionStore");
    expect(sessionStore.get()?.accessToken).toBe("a");
  });

  it("restores a tab session without any marker", async () => {
    sessionStorage.setItem(KEY, JSON.stringify(session));
    const { sessionStore } = await import("../core/auth/sessionStore");
    expect(sessionStore.get()?.accessToken).toBe("a");
  });
});
