import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

/**
 * No unit test may touch the network.
 *
 * jsdom's fetch used to reach out for real, and the api client turned the
 * refusal into a generic SYS_NETWORK_ERROR — so a spec that accidentally
 * escaped its mock failed with an error that named neither the URL nor the
 * cause. This guard fails such a spec immediately and says what it asked
 * for. Tests that exercise the HTTP layer override fetch themselves (and
 * `restoreMocks` puts this guard back afterwards).
 */
beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      return Promise.reject(
        new Error(
          `Unmocked network request to ${url}. Unit tests must not hit the network: ` +
            `use demo mode or stub fetch in the spec.`,
        ),
      );
    }),
  );
});

afterEach(() => vi.unstubAllGlobals());

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
  document.documentElement.dataset.theme = "light";
  document.documentElement.dir = "ltr";
  document.documentElement.lang = "en";
});

afterEach(() => cleanup());
