/**
 * Bulk import helpers (Phase 31): parse .xlsx/.xls (SheetJS) and .csv
 * (UTF-8, semicolon/comma autodetect) into row objects keyed by header.
 * Column matching is case-insensitive and accepts Persian AND English headers
 * so maintenance teams can import the workbook they already keep.
 */

export type ImportRow = Record<string, string>;

const HEADER_ALIASES: Record<string, string[]> = {
  code: ["code", "کد", "کد قطعه", "کد دستگاه"],
  name: ["name", "نام", "نام قطعه", "نام دستگاه", "عنوان"],
  unit: ["unit", "واحد"],
  quantityonhand: ["quantityonhand", "quantity", "qty", "موجودی", "موجودی فعلی"],
  minimumstock: ["minimumstock", "minimum", "حداقل موجودی", "حداقل"],
  unitcost: ["unitcost", "cost", "price", "قیمت", "قیمت واحد"],
  location: ["location", "محل", "مکان"],
  department: ["department", "واحد", "دپارتمان"],
  pmintervaldays: ["pmintervaldays", "بازه", "بازه PM", "pm"],
};

export const canonicalKey = (header: string): string => {
  const normalized = header.trim().toLowerCase().replace(/[\s_]+/g, "");
  for (const [key, aliases] of Object.entries(HEADER_ALIASES)) {
    if (key === normalized || aliases.some((alias) => alias.toLowerCase().replace(/[\s_]+/g, "") === normalized)) {
      return key;
    }
  }
  return normalized;
};

export const parseCsvRows = (text: string): ImportRow[] => {
  const lines = text.replace(/^﻿/, "").split(/\r?\n/).filter((line) => line.trim().length > 0);
  if (lines.length < 2) return [];
  const delimiter = lines[0].includes(";") && lines[0].split(";").length > lines[0].split(",").length ? ";" : ",";
  const splitLine = (line: string): string[] => {
    const cells: string[] = [];
    let current = "";
    let quoted = false;
    for (const char of line) {
      if (char === '"') { quoted = !quoted; continue; }
      if (char === delimiter && !quoted) { cells.push(current.trim()); current = ""; continue; }
      current += char;
    }
    cells.push(current.trim());
    return cells;
  };
  const headers = splitLine(lines[0]).map(canonicalKey);
  return lines.slice(1).map((line) => {
    const cells = splitLine(line);
    const row: ImportRow = {};
    headers.forEach((header, index) => { row[header] = cells[index] ?? ""; });
    return row;
  });
};

export const parseImportFile = async (file: File): Promise<ImportRow[]> => {
  if (/\.csv$/i.test(file.name)) {
    return parseCsvRows(await file.text());
  }
  if (/\.(xlsx|xls)$/i.test(file.name)) {
    // A *static* specifier, so Vite emits xlsx as its own lazy chunk instead
    // of leaving a bare `import("xlsx")` in the output. The previous
    // `/* @vite-ignore */` + indirect-specifier form was never resolvable by
    // a browser, which meant Excel import failed in every production build
    // and reported it as "run npm install" — advice the user cannot act on.
    //
    // The chunk is still only fetched when someone actually picks a
    // spreadsheet; the CSV path above never touches it.
    let xlsx: typeof import("xlsx");
    try {
      xlsx = await import("xlsx");
    } catch {
      throw new Error(
        "بارگذاری پردازشگر فایل اکسل ناموفق بود. اتصال شبکه را بررسی کنید یا همان داده را با فرمت CSV وارد کنید.",
      );
    }
    const workbook = xlsx.read(new Uint8Array(await file.arrayBuffer()), { type: "array" });
    const sheet = workbook.Sheets[workbook.SheetNames[0]];
    const rows = xlsx.utils.sheet_to_json(sheet, { defval: "" }) as Record<string, unknown>[];
    return rows.map((row: Record<string, unknown>) => {
      const mapped: ImportRow = {};
      for (const [header, value] of Object.entries(row)) {
        mapped[canonicalKey(header)] = String(value ?? "").trim();
      }
      return mapped;
    });
  }
  throw new Error("Unsupported file type. Please choose an .xlsx or .csv file.");
};

/** Arabic-Indic digit tolerant number parse for import sheets. */
export const toNumber = (raw: string, fallback = 0): number => {
  const eastern = raw.replace(/[۰-۹]/g, (d) => String("۰۱۲۳۴۵۶۷۸۹".indexOf(d)));
  const value = Number(eastern.replace(/[^\d.-]/g, ""));
  return Number.isFinite(value) ? value : fallback;
};
