import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AppProviders } from "../app/providers/AppProviders";
import { PermissionGuard } from "../shared/components/PermissionGuard";
import { sessionStore } from "../core/auth/sessionStore";

const authenticated = (): void => sessionStore.set({ accessToken: "test-access", refreshToken: "test-refresh", user: { id: "u1", displayName: "Test User", email: "test@example.test", role: "Member", permissions: ["project.view"] } });

describe("application contexts", () => {
  it("renders permitted actions and hides forbidden actions", () => {
    authenticated();
    render(<AppProviders><PermissionGuard permission="project.view"><span>visible action</span></PermissionGuard><PermissionGuard permission="admin.delete"><span>secret action</span></PermissionGuard></AppProviders>);
    expect(screen.getByText("visible action")).toBeInTheDocument();
    expect(screen.queryByText("secret action")).not.toBeInTheDocument();
  });

  it("applies RTL when the user selects Persian", () => {
    // Persian is the default locale, so the frame must come up mirrored:
    // the document carries both the language and the direction, which is
    // what every logical property in the stylesheet keys off.
    localStorage.setItem("tekarai.gui.locale.v4", "fa");
    render(<AppProviders><span>workspace</span></AppProviders>);
    expect(document.documentElement.dir).toBe("rtl");
    expect(document.documentElement.lang).toBe("fa");
  });

  it("hands the layout back to LTR for a left-to-right locale", async () => {
    // A site that can only be right-to-left is not localised, it is just
    // hardcoded the other way; switching must mirror everything back.
    localStorage.setItem("tekarai.gui.locale.v4", "en");
    vi.resetModules();
    const { AppProviders: Providers } = await import("../app/providers/AppProviders");
    render(<Providers><span>workspace</span></Providers>);
    expect(document.documentElement.dir).toBe("ltr");
    expect(document.documentElement.lang).toBe("en");
    localStorage.setItem("tekarai.gui.locale.v4", "fa");
  });
});
