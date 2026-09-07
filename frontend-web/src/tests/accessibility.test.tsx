import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AppProviders } from "../app/providers/AppProviders";
import { LoginPage } from "../pages/LoginPage";


describe("accessibility smoke contract", () => {
  it("keeps the sign-in form labelled and keyboard-addressable", () => {
    render(<MemoryRouter><AppProviders><LoginPage /></AppProviders></MemoryRouter>);
    expect(screen.getByRole("heading", { name: /welcome back/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/tenant code/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/email or username/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign in/i })).toHaveAttribute("type", "submit");
  });
});
