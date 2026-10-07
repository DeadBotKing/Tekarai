/**
 * The permission matrix, checked in the UI rather than asserted in a doc.
 *
 * The backend refuses actions the caller may not perform — that is where
 * security lives and it has its own tests. This is about the other half: a
 * technician who can see an "approve purchase order" button is being invited
 * to fail, and a manager whose approve button is missing will phone support
 * instead. Neither is a security hole; both are the product being wrong.
 *
 * Every case drives the real `PermissionProvider` with a real permission
 * list, so a rename in `PERMISSIONS` breaks this file instead of quietly
 * hiding a control from everybody.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";

import {
  PERMISSIONS,
  usePermissions,
} from "../core/permissions/permissionContext";
import { PermissionGuard } from "../shared/components/PermissionGuard";
import { AppProviders } from "../app/providers/AppProviders";
import { sessionStore } from "../core/auth/sessionStore";

/**
 * `PermissionProvider` reads the live session rather than taking a prop, so
 * a test that wants a given permission set has to log a user in with it.
 * Driving it through the real session is the point: a change to how
 * permissions reach the provider should break these tests.
 */
const withPermissions = (permissions: string[], children: ReactNode) => {
  sessionStore.set({
    accessToken: "test-access",
    refreshToken: "test-refresh",
    user: {
      id: "u-matrix",
      displayName: "کاربر آزمایشی",
      email: "matrix@example.test",
      role: "Technician",
      permissions,
    },
  });
  return render(
    <MemoryRouter>
      <AppProviders>{children}</AppProviders>
    </MemoryRouter>,
  );
};

/** The roles this product actually ships, and what each may do. */
const ROLE_MATRIX: Record<string, string[]> = {
  technician: [
    PERMISSIONS.maintenanceDeviceList,
    PERMISSIONS.maintenanceWorkOrderList,
    PERMISSIONS.maintenanceWorkOrderUpdate,
  ],
  maintenanceManager: [
    PERMISSIONS.maintenanceDeviceList,
    PERMISSIONS.maintenanceDeviceManage,
    PERMISSIONS.maintenanceWorkOrderList,
    PERMISSIONS.maintenanceWorkOrderUpdate,
    PERMISSIONS.procurementRequisitionCreate,
  ],
  procurementOfficer: [
    PERMISSIONS.procurementRequisitionCreate,
    PERMISSIONS.procurementRequisitionApprove,
    PERMISSIONS.procurementPurchaseOrderCreate,
  ],
  readOnly: [PERMISSIONS.maintenanceDeviceList],
  platformAdmin: ["*"],
};

describe("PermissionGuard hides what the caller may not do", () => {
  it("renders the control when the permission is held", () => {
    withPermissions(
      [PERMISSIONS.procurementRequisitionApprove],
      <PermissionGuard permission={PERMISSIONS.procurementRequisitionApprove}>
        <button type="button">تأیید درخواست</button>
      </PermissionGuard>,
    );
    expect(screen.getByRole("button", { name: "تأیید درخواست" })).toBeTruthy();
  });

  it("renders nothing at all when it is not", () => {
    withPermissions(
      [PERMISSIONS.maintenanceDeviceList],
      <PermissionGuard permission={PERMISSIONS.procurementRequisitionApprove}>
        <button type="button">تأیید درخواست</button>
      </PermissionGuard>,
    );
    expect(screen.queryByRole("button", { name: "تأیید درخواست" })).toBeNull();
  });

  it("can explain the refusal instead of hiding, when asked to", () => {
    // A control that vanishes is confusing for an action the user expects to
    // have. `fallback="denied"` is for those.
    withPermissions(
      [],
      <PermissionGuard
        permission={PERMISSIONS.procurementRequisitionApprove}
        fallback="denied"
        label="برای تأیید، دسترسی لازم را ندارید"
      >
        <button type="button">تأیید درخواست</button>
      </PermissionGuard>,
    );
    expect(screen.getByRole("status")).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("requires every permission when given a list", () => {
    // `has([a, b])` is an AND. Treating it as an OR would expose a control
    // to someone holding only half of what it needs.
    withPermissions(
      [PERMISSIONS.procurementRequisitionCreate],
      <PermissionGuard
        permission={[
          PERMISSIONS.procurementRequisitionCreate,
          PERMISSIONS.procurementRequisitionApprove,
        ]}
      >
        <button type="button">ایجاد و تأیید</button>
      </PermissionGuard>,
    );
    expect(screen.queryByRole("button")).toBeNull();
  });
});

describe("the wildcard", () => {
  it("opens every control for a platform administrator", () => {
    withPermissions(
      ["*"],
      <PermissionGuard permission={PERMISSIONS.procurementPurchaseOrderApprove}>
        <button type="button">تأیید سفارش خرید</button>
      </PermissionGuard>,
    );
    expect(screen.getByRole("button")).toBeTruthy();
  });

  it("is not matched by a lookalike string", () => {
    // "*" must be exact. A prefix wildcard like "procurement.*" is not
    // implemented, and a test that passes it would document a feature that
    // does not exist.
    withPermissions(
      ["procurement.*"],
      <PermissionGuard permission={PERMISSIONS.procurementPurchaseOrderApprove}>
        <button type="button">تأیید سفارش خرید</button>
      </PermissionGuard>,
    );
    expect(screen.queryByRole("button")).toBeNull();
  });
});

describe("the shipped role matrix", () => {
  const Probe = ({ permission }: { permission: string }): JSX.Element => {
    const { has } = usePermissions();
    return <span data-testid="result">{has(permission) ? "allow" : "deny"}</span>;
  };

  const check = (role: string, permission: string): string => {
    const view = withPermissions(ROLE_MATRIX[role], <Probe permission={permission} />);
    const result = view.getByTestId("result").textContent ?? "";
    view.unmount();
    return result;
  };

  it("lets a technician work orders but not approve purchases", () => {
    expect(check("technician", PERMISSIONS.maintenanceWorkOrderUpdate)).toBe("allow");
    expect(check("technician", PERMISSIONS.procurementRequisitionApprove)).toBe("deny");
    expect(check("technician", PERMISSIONS.maintenanceDeviceManage)).toBe("deny");
  });

  it("lets a maintenance manager raise a requisition but not approve it", () => {
    // Raising and approving the same requisition is the separation-of-duties
    // rule this product sells. If this ever flips to allow, that is a
    // deliberate decision and it should break a test on the way through.
    expect(check("maintenanceManager", PERMISSIONS.procurementRequisitionCreate)).toBe(
      "allow",
    );
    expect(check("maintenanceManager", PERMISSIONS.procurementRequisitionApprove)).toBe(
      "deny",
    );
  });

  it("lets a procurement officer approve but not manage devices", () => {
    expect(check("procurementOfficer", PERMISSIONS.procurementRequisitionApprove)).toBe(
      "allow",
    );
    expect(check("procurementOfficer", PERMISSIONS.maintenanceDeviceManage)).toBe("deny");
  });

  it("gives a read-only user nothing that writes", () => {
    expect(check("readOnly", PERMISSIONS.maintenanceDeviceList)).toBe("allow");
    for (const permission of [
      PERMISSIONS.maintenanceDeviceManage,
      PERMISSIONS.maintenanceWorkOrderUpdate,
      PERMISSIONS.procurementRequisitionCreate,
    ]) {
      expect(check("readOnly", permission)).toBe("deny");
    }
  });

  it("gives a platform administrator everything", () => {
    for (const permission of Object.values(PERMISSIONS)) {
      expect(check("platformAdmin", permission)).toBe("allow");
    }
  });

  it("denies every permission to a user with none", () => {
    const view = withPermissions(
      [],
      <Probe permission={PERMISSIONS.maintenanceDeviceList} />,
    );
    expect(view.getByTestId("result").textContent).toBe("deny");
  });
});
