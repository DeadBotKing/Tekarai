import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppProviders } from "../app/providers/AppProviders";
import { sessionStore } from "../core/auth/sessionStore";
import { CreatableSelect } from "../shared/components/CreatableSelect";
import {
  MAX_OPTION_LENGTH,
  mergeOptions,
  normalizeOption,
  readCustomOptions,
  rememberOption,
  validateOption,
} from "../features/maintenance/optionCatalog";
import { MaintenanceLocationsPage } from "../pages/MaintenanceLocationsPage";
import { LOCATION_KINDS } from "../shared/types/domain";
import { taxonomyLabel } from "../core/localization/taxonomyLabel";
import { translate } from "../core/localization/i18n";

const identity = (value: string): string => value;

describe("option catalog", () => {
  beforeEach(() => localStorage.clear());

  it("normalises a typed value the same way the API does", () => {
    expect(normalizeOption("  سوله   ۳ ")).toBe("سوله ۳");
    expect(validateOption("   ")).toEqual({ ok: false, reason: "empty" });
    expect(validateOption("x".repeat(MAX_OPTION_LENGTH + 1))).toEqual({
      ok: false,
      reason: "tooLong",
    });
    expect(validateOption("سوله", ["Site", "سوله"])).toEqual({ ok: false, reason: "duplicate" });
    expect(validateOption(" جوشکاری ")).toEqual({ ok: true, value: "جوشکاری" });
  });

  it("remembers new options per catalogue without touching the canonical list", () => {
    rememberOption("location.kind", "سوله");
    rememberOption("location.kind", "سوله");
    rememberOption("pm.discipline", "جوشکاری");
    expect(readCustomOptions("location.kind")).toEqual(["سوله"]);
    expect(readCustomOptions("pm.discipline")).toEqual(["جوشکاری"]);
  });

  it("merges canonical codes, saved data and local additions without duplicates", () => {
    rememberOption("location.kind", "سوله");
    const options = mergeOptions({
      canonical: ["site", "building"],
      translate: identity,
      fromData: ["site", "خط تولید", "خط تولید"],
      catalogKey: "location.kind",
      current: "اتاق برق",
    });
    expect(options.map((option) => option.value)).toEqual([
      "site",
      "building",
      "سوله",
      "خط تولید",
      "اتاق برق",
    ]);
  });

  it("labels canonical codes from the dictionary and custom ones verbatim", () => {
    const t = (key: Parameters<typeof translate>[1]): string => translate("fa", key);
    expect(taxonomyLabel(t, "cmms.department.", "mechanical")).toBe("مکانیک");
    expect(taxonomyLabel(t, "cmms.department.", "جوشکاری")).toBe("جوشکاری");
  });
});

describe("CreatableSelect", () => {
  beforeEach(() => localStorage.clear());

  const Harness = ({ onPick }: { onPick: (value: string) => void }): JSX.Element => (
    <AppProviders>
      <CreatableSelect
        label="نوع مکان"
        value="site"
        canonical={["site", "building"]}
        catalogKey="location.kind"
        options={[
          { value: "site", label: "سایت" },
          { value: "building", label: "ساختمان" },
        ]}
        onChange={onPick}
      />
    </AppProviders>
  );

  it("adds a value that was never in the list and reports it upward", async () => {
    const onPick = vi.fn();
    render(<Harness onPick={onPick} />);

    fireEvent.change(screen.getByLabelText(/نوع مکان/), { target: { value: "__addOption__" } });
    const editor = await screen.findByLabelText("مقدار جدید");
    fireEvent.change(editor, { target: { value: " سوله " } });
    fireEvent.click(screen.getByRole("button", { name: "ثبت مورد جدید" }));

    expect(onPick).toHaveBeenCalledWith("سوله");
    expect(readCustomOptions("location.kind")).toEqual(["سوله"]);
  });

  it("refuses an empty value and keeps the editor open", async () => {
    const onPick = vi.fn();
    render(<Harness onPick={onPick} />);

    fireEvent.change(screen.getByLabelText(/نوع مکان/), { target: { value: "__addOption__" } });
    const editor = await screen.findByLabelText("مقدار جدید");
    fireEvent.change(editor, { target: { value: "   " } });
    fireEvent.click(screen.getByRole("button", { name: "ثبت مورد جدید" }));

    expect(onPick).not.toHaveBeenCalled();
    expect(screen.getByText("یک مقدار وارد کنید.")).toBeInTheDocument();
    expect(screen.getByLabelText("مقدار جدید")).toBeInTheDocument();
  });

  it("cancels back to the dropdown without changing the value", async () => {
    const onPick = vi.fn();
    render(<Harness onPick={onPick} />);

    fireEvent.change(screen.getByLabelText(/نوع مکان/), { target: { value: "__addOption__" } });
    fireEvent.click(await screen.findByRole("button", { name: "انصراف" }));

    expect(onPick).not.toHaveBeenCalled();
    expect(screen.getByLabelText(/نوع مکان/)).toBeInTheDocument();
  });
});

describe("locations page dropdown", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStore.set({
      accessToken: "test-access",
      refreshToken: "test-refresh",
      user: {
        id: "u1",
        displayName: "Test User",
        email: "test@example.test",
        role: "Maintenance",
        permissions: ["maintenance.device.list", "maintenance.device.manage"],
      },
    });
  });

  it("offers the seven built-in kinds plus an add entry", async () => {
    render(
      <AppProviders>
        <MemoryRouter initialEntries={["/app/maintenance/locations"]}>
          <Routes>
            <Route path="/app/maintenance/locations" element={<MaintenanceLocationsPage />} />
          </Routes>
        </MemoryRouter>
      </AppProviders>,
    );

    await waitFor(() => expect(screen.getByText("سایت اصفهان")).toBeInTheDocument());
    fireEvent.click(screen.getAllByRole("button", { name: /افزودن مکان/ })[0]);

    const kindSelect = await screen.findByLabelText(/نوع مکان/);
    const values = within(kindSelect as HTMLSelectElement)
      .getAllByRole("option")
      .map((option) => (option as HTMLOptionElement).value);

    LOCATION_KINDS.forEach((kind) => expect(values).toContain(kind));
    expect(values).toContain("__addOption__");
  });
});
