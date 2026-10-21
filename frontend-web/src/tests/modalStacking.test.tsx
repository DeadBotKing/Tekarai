import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { LocalizationProvider } from "../core/localization/localizationContext";
import { Modal } from "../shared/components/overlays";

function NestedModalHarness(): JSX.Element {
  const [orderOpen, setOrderOpen] = useState(false);
  const [supplierOpen, setSupplierOpen] = useState(false);
  const [renderCount, setRenderCount] = useState(0);

  return (
    <LocalizationProvider>
      <button type="button" onClick={() => setOrderOpen(true)}>Open purchase order</button>
      {/* This dialog intentionally precedes its parent in the DOM, as on ProcurementPage. */}
      <Modal open={supplierOpen} title="Add supplier" onClose={() => setSupplierOpen(false)}>
        <p>Supplier form</p>
      </Modal>
      <Modal open={orderOpen} title="Create purchase order" onClose={() => setOrderOpen(false)}>
        <button
          type="button"
          onClick={() => {
            setSupplierOpen(true);
            setRenderCount((current) => current + 1);
          }}
        >
          Add supplier
        </button>
        <span>{renderCount}</span>
      </Modal>
    </LocalizationProvider>
  );
}

const layerOf = (dialog: HTMLElement): number => {
  const overlay = dialog.closest<HTMLElement>(".overlay");
  expect(overlay).not.toBeNull();
  const match = overlay?.style.zIndex.match(/\+\s*(\d+)\s*\)/);
  return match ? Number(match[1]) : 0;
};

describe("global modal stacking", () => {
  it("keeps the newly opened supplier dialog above its re-rendered purchase-order parent", async () => {
    const user = userEvent.setup();
    render(<NestedModalHarness />);

    await user.click(screen.getByRole("button", { name: "Open purchase order" }));
    const orderDialog = await screen.findByRole("dialog", { name: "Create purchase order" });
    await user.click(within(orderDialog).getByRole("button", { name: "Add supplier" }));
    const supplierDialog = await screen.findByRole("dialog", { name: "Add supplier" });

    expect(layerOf(supplierDialog)).toBeGreaterThan(layerOf(orderDialog));

    // Escape dismisses the topmost dialog only; the parent remains available.
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Add supplier" })).not.toBeInTheDocument());
    expect(screen.getByRole("dialog", { name: "Create purchase order" })).toBeInTheDocument();
  });
});
