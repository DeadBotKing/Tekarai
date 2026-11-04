import { useState } from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PermissionCatalogFa } from "../features/security/PermissionCatalogFa";
import { PERMISSION_LABELS_FA, permissionLabelFa, groupPermissionsFa } from "../features/security/permissionLabelsFa";
import codes from "./permissionCatalogCodes.json";

describe("Persian permission labels", () => {
  it("translates every action in the checked backend catalog", () => {
    expect(codes).toHaveLength(115);
    for (const code of codes) expect(PERMISSION_LABELS_FA[code], code).toBeTruthy();
  });
  it("keeps safety and assignment meanings explicit", () => {
    expect(permissionLabelFa("safety.permit.approve")).toContain("تعلیق");
    expect(permissionLabelFa("organization.assignment.manage")).toContain("انتساب");
    expect(permissionLabelFa("maintenance.workorder.logTime")).toContain("حذف زمان");
  });
  it("shows unknown codes without inventing their meaning", () => {
    expect(permissionLabelFa("custom.operation")).toContain("تعریف نشده");
    render(<PermissionCatalogFa actions={["custom.operation"]} />);
    expect(screen.getByText("custom.operation")).toBeInTheDocument();
  });
  it("searches Persian names, Arabic letter variants, categories and technical codes", () => {
    expect(groupPermissionsFa(["user.create","safety.permit.view"], "كاربر")[0].actions).toEqual(["user.create"]);
    expect(groupPermissionsFa(["user.create","safety.permit.view"], "safety.permit")[0].actions).toEqual(["safety.permit.view"]);
  });
  it("displays Persian text and passes the original code when toggled", () => {
    const toggle=vi.fn();
    render(<PermissionCatalogFa actions={["user.create"]} selected={[]} onToggle={toggle} />);
    fireEvent.click(screen.getByRole("checkbox"));
    expect(screen.getByText("ایجاد کاربران")).toBeInTheDocument();
    expect(toggle).toHaveBeenCalledWith("user.create",true);
  });
  it("does not remove hidden selections while searching", () => {
    function Demo(): JSX.Element {
      const [selected,setSelected]=useState(["user.create","safety.permit.view"]);
      return <><PermissionCatalogFa actions={["user.create","safety.permit.view"]} selected={selected} onToggle={(code,checked)=>setSelected(checked ? [...selected,code] : selected.filter(item=>item!==code))} /><output>{selected.join("|")}</output></>;
    }
    render(<Demo />);
    fireEvent.change(screen.getByLabelText("جستجوی مجوزها"),{target:{value:"user.create"}});
    expect(screen.getAllByRole("checkbox")).toHaveLength(1);
    fireEvent.click(screen.getByRole("checkbox"));
    expect(screen.getByText("safety.permit.view", { selector: "output" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("جستجوی مجوزها"),{target:{value:""}});
    expect(screen.getAllByRole("checkbox").filter(node=>(node as HTMLInputElement).checked)).toHaveLength(1);
  });
});
