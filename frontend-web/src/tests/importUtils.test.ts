import { describe, expect, it, vi } from "vitest";
import { canonicalKey, parseCsvRows, parseImportFile, toNumber } from "../core/files/importUtils";

describe("importUtils — CSV parsing", () => {
  it("parses CSV with English headers and trims values", () => {
    const rows = parseCsvRows("code,name,unit,quantityOnHand,minimumStock,unitCost\r\nSAL-1, برینگ ,عدد,12,4,185000\nBLT-2,تسمه,عدد,3,2,90000");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toEqual({ code: "SAL-1", name: "برینگ", unit: "عدد", quantityonhand: "12", minimumstock: "4", unitcost: "185000" });
  });

  it("accepts Persian headers and autodetects semicolons", () => {
    const rows = parseCsvRows("کد;نام;واحد;موجودی\r\nSAL-1;برینگ;عدد;12");
    expect(rows[0].code).toBe("SAL-1");
    expect(rows[0].quantityonhand).toBe("12");
  });

  it("skips blank lines and malformed files", () => {
    expect(parseCsvRows("only-header")).toHaveLength(0);
    expect(parseCsvRows("code,name\n\nS-1,ن\n")).toHaveLength(1);
  });

  it("rejects unsupported files and parses .csv by extension", async () => {
    const { File: NodeFile } = await import("node:buffer");
    const toFile = (body: string, name: string): File => new NodeFile([body], name) as unknown as File;
    await expect(parseImportFile(toFile("code,name\nS1,ن", "parts.csv"))).resolves.toHaveLength(1);
    await expect(parseImportFile(toFile("x", "parts.json"))).rejects.toThrow("Unsupported");
  });
});

describe("importUtils — header aliases & numbers", () => {
  it.each([
    ["Code", "code"],
    ["کد قطعه", "code"],
    ["Minimum Stock", "minimumstock"],
    ["حداقل موجودی", "minimumstock"],
    ["قیمت واحد", "unitcost"],
    ["Quantity On Hand", "quantityonhand"],
  ])("maps %s to %s", (header, expected) => {
    expect(canonicalKey(header)).toBe(expected);
  });

  it("parses eastern-arabic digits and noisy values", () => {
    expect(toNumber("۱۲")).toBe(12);
    expect(toNumber("1,250")).toBe(1250);
    expect(toNumber("")).toBe(0);
  });
});

describe("importUtils — XLSX", () => {
  it("reads the first worksheet of an .xlsx file", async () => {
    const xlsx = await import("xlsx");
    const sheet = xlsx.utils.json_to_sheet([{ code: "S-9", name: "پمپ", unit: "عدد", quantityOnHand: 7 }]);
    const workbook = xlsx.utils.book_new();
    xlsx.utils.book_append_sheet(workbook, sheet, "Sheet1");
    const binary = xlsx.write(workbook, { type: "array", bookType: "xlsx" }) as ArrayBuffer;
    // jsdom's File lacks arrayBuffer(); the node:buffer File matches browser behaviour.
    const { File: NodeFile } = await import("node:buffer");
    const file = new NodeFile([new Uint8Array(binary)], "book.xlsx") as unknown as File;
    const rows = await parseImportFile(file);
    expect(rows).toHaveLength(1);
    expect(rows[0].code).toBe("S-9");
    expect(rows[0].quantityonhand).toBe("7");
    vi.restoreAllMocks();
  });
});
