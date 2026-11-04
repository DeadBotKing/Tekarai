import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { UserPicker } from "../shared/components/UserPicker";

describe("UserPicker browsing", () => {
  it("loads the list without typing and selects a user", async () => {
    const user = { id: "u1", displayName: "رضا احمدی", username: "reza" };
    const search = vi.fn().mockResolvedValue([user]);
    const onSelect = vi.fn();
    render(<UserPicker browse value={null} onSelect={onSelect} search={search} />);
    fireEvent.focus(screen.getByRole("combobox"));
    const option = await screen.findByRole("option");
    expect(search).toHaveBeenCalledWith("");
    fireEvent.click(option);
    expect(onSelect).toHaveBeenCalledWith(user);
  });
});
