import { describe, expect, it } from "vitest";
import { validateForm } from "../shared/types/formSchema";

describe("schema-driven forms", () => {
  const schema = [{ name: "name", label: "Name", type: "text" as const, required: true }, { name: "email", label: "Email", type: "email" as const, required: true }];
  it("returns field-level validation errors", () => {
    expect(validateForm(schema, { name: "", email: "not-an-email" })).toEqual({ name: "This field is required.", email: "Enter a valid email address." });
  });
  it("accepts valid values", () => {
    expect(validateForm(schema, { name: "Nova", email: "owner@example.test" })).toEqual({});
  });
});
