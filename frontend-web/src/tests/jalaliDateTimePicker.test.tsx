import { useState } from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { JalaliDateTimePicker } from "../shared/components/JalaliDateTimePicker";

describe("Jalali permit date and local time", () => {
  it("shows a Persian calendar date while preserving the ISO date and time contract", () => {
    const change=vi.fn();
    render(<JalaliDateTimePicker label="شروع اعتبار" value="2026-10-07T08:30" onChange={change} />);
    expect(screen.getByRole("button",{name:"تاریخ شروع اعتبار"}).textContent).toContain("۱۴۰۵");
    fireEvent.change(screen.getByLabelText("ساعت شروع اعتبار"),{target:{value:"09:45"}});
    expect(change).toHaveBeenCalledWith("2026-10-07T09:45");
  });
  it("clears both date and time in the emitted value when a date is cleared", () => {
    const change=vi.fn();
    render(<JalaliDateTimePicker label="پایان اعتبار" value="2026-10-07T18:00" onChange={change} />);
    fireEvent.click(screen.getByRole("button",{name:"پاک کردن تاریخ"}));
    expect(change).toHaveBeenCalledWith("");
  });
  it("resets displayed time when the parent resets its form", () => {
    function Form(): JSX.Element {
      const [value,setValue]=useState("2026-10-07T14:30");
      return <><JalaliDateTimePicker label="شروع" value={value} onChange={setValue} /><button onClick={()=>setValue("")}>reset</button></>;
    }
    render(<Form />);
    fireEvent.click(screen.getByRole("button",{name:"reset"}));
    expect(screen.getByLabelText("ساعت شروع")).toHaveValue("00:00");
  });
});
