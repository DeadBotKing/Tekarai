/**
 * Shared download helpers: save a Blob as a file, and build an Excel-friendly
 * CSV blob client-side (demo mode has no server to export from).

 * CSV follows the app's convention — UTF-8 with a BOM so Excel renders
 * Persian headers correctly.
 */

export const triggerDownload = (blob: Blob, filename: string): void => {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
};

const SEPARATOR = ",";

const escapeCsvCell = (value: unknown): string => {
  const text = String(value ?? "");
  if (/[",\n\r]/.test(text)) return `"${text.replace(/"/g, '""')}"`;
  return text;
};

export const rowsToCsvBlob = (rows: ReadonlyArray<ReadonlyArray<unknown>>): Blob => {
  const body = rows.map((row) => row.map(escapeCsvCell).join(SEPARATOR)).join("\r\n");
  return new Blob(["﻿" + body], { type: "text/csv;charset=utf-8" });
};
