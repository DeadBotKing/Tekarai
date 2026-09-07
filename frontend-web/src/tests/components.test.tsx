import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Button, ProgressBar, TextInput } from "../shared/components/primitives";
import { DataTable } from "../shared/components/DataTable";
import { AppProviders } from "../app/providers/AppProviders";

const rows = [{ id: "1", name: "Alpha", status: "active" }, { id: "2", name: "Beta", status: "pending" }];

describe("design system", () => {
  it("supports accessible button and input contracts", () => {
    const handler = vi.fn();
    render(<><Button onClick={handler}>Save</Button><TextInput label="Project name" required /></>);
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(handler).toHaveBeenCalledOnce();
    expect(screen.getByLabelText(/Project name/)).toHaveAttribute("aria-invalid", "false");
  });

  it("exposes a bounded progress value", () => {
    render(<ProgressBar value={140} label="Coverage" />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "100");
  });
});

describe("DataTable", () => {
  it("sorts, selects and paginates generic rows", () => {
    render(<AppProviders><DataTable columns={[{ key: "name", label: "Name", accessor: (row) => row.name, sortable: true }, { key: "status", label: "Status", accessor: (row) => row.status }]} data={rows} rowKey={(row) => row.id} pageSize={1} /></AppProviders>);
    expect(screen.getByText("Alpha")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    expect(screen.getByText("Beta")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: /select row 2/i }));
    expect(screen.getByText(/1 selected/i)).toBeInTheDocument();
  });
});
