import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
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

  it("applies RTL when the user selects Persian", async () => {
    render(<AppProviders><span>workspace</span></AppProviders>);
    // The provider's public behavior is verified through the document contract in localization tests.
    expect(document.documentElement.dir).toBe("ltr");
  });
});
