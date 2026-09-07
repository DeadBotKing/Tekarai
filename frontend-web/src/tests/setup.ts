import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach } from "vitest";

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
  document.documentElement.dataset.theme = "light";
  document.documentElement.dir = "ltr";
  document.documentElement.lang = "en";
});

afterEach(() => cleanup());
