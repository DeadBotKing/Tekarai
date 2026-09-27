import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AppProviders } from "../app/providers/AppProviders";
import { LoginPage } from "../pages/LoginPage";


describe("accessibility smoke contract", () => {
  it("keeps the sign-in form labelled and keyboard-addressable", () => {
    render(<MemoryRouter><AppProviders><LoginPage /></AppProviders></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "خوش آمدید" })).toBeInTheDocument();
    expect(screen.getByLabelText(/کد Tenant/)).toBeInTheDocument();
    expect(screen.getByLabelText(/ایمیل یا نام کاربری/)).toBeInTheDocument();
    expect(screen.getByLabelText(/گذرواژه/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "ورود" })).toHaveAttribute("type", "submit");
  });
});
