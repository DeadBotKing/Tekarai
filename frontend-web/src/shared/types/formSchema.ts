export type FormFieldType = "text" | "email" | "number" | "date" | "textarea" | "select" | "checkbox";

export interface FormOption { value: string; label: string; }

export interface FormFieldSchema {
  name: string;
  label: string;
  type: FormFieldType;
  required?: boolean;
  placeholder?: string;
  hint?: string;
  options?: FormOption[];
  min?: number;
  max?: number;
}

export type FormValues = Record<string, string | number | boolean>;
export type FormErrors = Record<string, string>;

export const validateForm = (schema: FormFieldSchema[], values: FormValues): FormErrors => {
  const errors: FormErrors = {};
  schema.forEach((field) => {
    const value = values[field.name];
    const empty = value === undefined || value === null || String(value).trim() === "" || value === false && field.type !== "checkbox";
    if (field.required && empty) { errors[field.name] = "This field is required."; return; }
    if (field.type === "email" && !empty && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(value))) errors[field.name] = "Enter a valid email address.";
    if (field.type === "number" && !empty && field.min !== undefined && Number(value) < field.min) errors[field.name] = `Value must be at least ${field.min}.`;
    if (field.type === "number" && !empty && field.max !== undefined && Number(value) > field.max) errors[field.name] = `Value must be at most ${field.max}.`;
  });
  return errors;
};
