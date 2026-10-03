/**
 * واژگان کدها — what a scanned string may mean, and what we print on labels.
 *
 * This mirrors `apps/maintenance/domain/services/scanCodeRules.py`. The server
 * is the authority (it alone can say whether `PUMP-204` exists), but the
 * client parses first so it can answer three questions without a round trip:
 * «آیا این اصلاً کد ماست؟», «به کجا باید برود؟», and «چه چیزی روی برچسب
 * چاپ شود؟» — the last one matters offline, where no server is reachable.
 *
 * Four input shapes are accepted, deliberately in this order:
 *
 * 1. an absolute or relative deep link into the app;
 * 2. a `tekarai://` custom-scheme link (printed on older asset labels);
 * 3. a bare UUID — kind unknown, the server probes every register;
 * 4. a human business code such as `PUMP-204` or `LINE1/PMP.204`.
 *
 * Anything else — free Persian text, a URL from another system, an empty
 * frame — yields an empty intent, and the UI says «کد ناشناس» rather than
 * guessing.
 */

export type ScanKind = "device" | "workOrder" | "sparePart" | "location";

export interface ScanIntent {
  /** Empty when the code carries no hint about which register to look in. */
  kind: ScanKind | "";
  /** A UUID when the code embedded one, otherwise "". */
  id: string;
  /** A business code (upper-cased) when that is what was scanned. */
  code: string;
  /** The raw scanned text, kept for diagnostics and the manual-entry box. */
  raw: string;
}

const EMPTY: ScanIntent = { kind: "", id: "", code: "", raw: "" };

const UUID_RE = /^[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}$/;
const DEEP_LINK_RE =
  /\/(?:app\/)?maintenance\/(devices|work-orders|spare-parts|locations)\/([0-9a-fA-F-]{8,})/;
const SCHEME_RE = /^tekarai:\/\/(device|work-order|part|location)\/([^/?#]+)/i;
const BUSINESS_CODE_RE = /^[A-Za-z0-9][A-Za-z0-9._\-/]{1,59}$/;
const MAX_SCAN_LENGTH = 512;

const SEGMENT_TO_KIND: Record<string, ScanKind> = {
  devices: "device",
  "work-orders": "workOrder",
  "spare-parts": "sparePart",
  locations: "location",
};

const SCHEME_TO_KIND: Record<string, ScanKind> = {
  device: "device",
  "work-order": "workOrder",
  part: "sparePart",
  location: "location",
};

const normaliseUuid = (value: string): string => {
  const bare = value.replace(/[{}]/g, "").trim().toLowerCase();
  if (!UUID_RE.test(bare)) return "";
  const hex = bare.replace(/-/g, "");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
};

/** متن اسکن‌شده → قصد. Never throws; unknown input yields an empty intent. */
export function parseScan(text: string): ScanIntent {
  const trimmed = (text ?? "").trim();
  if (!trimmed || trimmed.length > MAX_SCAN_LENGTH) return { ...EMPTY };

  const scheme = SCHEME_RE.exec(trimmed);
  if (scheme) {
    const kind = SCHEME_TO_KIND[scheme[1].toLowerCase()];
    const value = decodeURIComponent(scheme[2]).trim();
    const id = normaliseUuid(value);
    return { kind, id, code: id ? "" : value.toUpperCase(), raw: trimmed };
  }

  const link = DEEP_LINK_RE.exec(trimmed);
  if (link) {
    const kind = SEGMENT_TO_KIND[link[1]];
    const id = normaliseUuid(link[2]) || link[2].toLowerCase();
    return { kind, id, code: "", raw: trimmed };
  }

  const bare = normaliseUuid(trimmed);
  if (bare) return { kind: "", id: bare, code: "", raw: trimmed };

  // A URL we do not recognise is somebody else's code, not a business code.
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(trimmed)) return { ...EMPTY, raw: trimmed };
  if (BUSINESS_CODE_RE.test(trimmed)) {
    return { kind: "", id: "", code: trimmed.toUpperCase(), raw: trimmed };
  }
  return { ...EMPTY, raw: trimmed };
}

/** True when the scan is worth sending to the server. */
export const isResolvable = (intent: ScanIntent): boolean =>
  Boolean(intent.id || intent.code);

// ---------------------------------------------------------------------------
// Label generation
// ---------------------------------------------------------------------------

/**
 * The in-app route a resolved target opens.
 *
 * These must match `fieldOpsRepositoryImpl.py` exactly: the server returns the
 * route online, and this table is what an offline scan falls back to. A
 * mismatch means a printed label scans into a 404 only when there is no
 * signal — the worst possible place to find out.
 */
export function scanTargetPath(kind: ScanKind, id: string): string {
  switch (kind) {
    case "device":
      return `/app/maintenance/devices/${id}/profile`;
    case "workOrder":
      return `/app/maintenance/work-orders?focus=${id}`;
    case "sparePart":
      return `/app/maintenance/warehouse?focus=${id}`;
    default:
      return `/app/maintenance/locations?focus=${id}`;
  }
}

/**
 * The string encoded into a printed QR label.
 *
 * An absolute URL, so a phone's built-in camera app opens Tekarai directly;
 * falls back to the path when there is no `window` (tests, SSR).
 */
export function scanQrPayload(kind: ScanKind, id: string): string {
  const path = scanTargetPath(kind, id);
  if (typeof window !== "undefined" && window.location?.origin) {
    return `${window.location.origin}${path}`;
  }
  return path;
}
