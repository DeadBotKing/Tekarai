/**
 * Open dropdown vocabularies (Phase 26.1).
 *
 * Every registry dropdown ships with a canonical catalogue, but a plant always
 * has a word of its own — a hall the operators call «سوله», a discipline named
 * «جوشکاری». An option a user adds at run time has to survive three places:
 *
 * 1. the record being saved (handled by the API — the value is stored verbatim);
 * 2. every other user's dropdown (handled by {@link mergeOptions}, which folds
 *    the values already present in the loaded rows back into the list);
 * 3. this browser, before anything has been saved with it (handled by the
 *    localStorage catalogue below).
 */

/** Longest label the API and the database columns accept. */
export const MAX_OPTION_LENGTH = 24;

const STORAGE_PREFIX = "tekarai.optionCatalog.";

/** Catalogue identifiers, so a typo cannot silently create a second catalogue. */
export type OptionCatalogKey =
  | "location.kind"
  | "personnel.specialty"
  | "personnel.shift"
  | "pm.discipline"
  | "device.department"
  | "device.equipmentType"
  | "device.criticality"
  | "assignment.role";

export interface SelectOption {
  value: string;
  label: string;
}

const readStorage = (key: OptionCatalogKey): string[] => {
  try {
    const raw = window.localStorage.getItem(`${STORAGE_PREFIX}${key}`);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string") : [];
  } catch {
    return [];
  }
};

const writeStorage = (key: OptionCatalogKey, values: string[]): void => {
  try {
    window.localStorage.setItem(`${STORAGE_PREFIX}${key}`, JSON.stringify(values));
  } catch {
    /* private mode or a full quota — the value still reaches the server. */
  }
};

/** Collapse inner whitespace exactly like the API does, so no duplicates appear. */
export const normalizeOption = (value: string): string => value.trim().split(/\s+/).join(" ");

export type OptionRejection = "empty" | "tooLong" | "duplicate";

/** Validate a user-typed option against the same rules the API enforces. */
export function validateOption(
  value: string,
  existing: readonly string[] = [],
): { ok: true; value: string } | { ok: false; reason: OptionRejection } {
  const normalized = normalizeOption(value);
  if (!normalized) return { ok: false, reason: "empty" };
  if (normalized.length > MAX_OPTION_LENGTH) return { ok: false, reason: "tooLong" };
  const lowered = normalized.toLocaleLowerCase();
  if (existing.some((item) => item.toLocaleLowerCase() === lowered)) {
    return { ok: false, reason: "duplicate" };
  }
  return { ok: true, value: normalized };
}

/** Options this browser added that are not part of the canonical catalogue. */
export const readCustomOptions = (key: OptionCatalogKey): string[] => readStorage(key);

/** Remember a new option for this browser. Returns the stored list. */
export function rememberOption(key: OptionCatalogKey, value: string): string[] {
  const normalized = normalizeOption(value);
  if (!normalized) return readStorage(key);
  const current = readStorage(key);
  const lowered = normalized.toLocaleLowerCase();
  if (current.some((item) => item.toLocaleLowerCase() === lowered)) return current;
  const next = [...current, normalized];
  writeStorage(key, next);
  return next;
}

/** Forget a locally added option (it stays on any record already saved with it). */
export function forgetOption(key: OptionCatalogKey, value: string): string[] {
  const lowered = normalizeOption(value).toLocaleLowerCase();
  const next = readStorage(key).filter((item) => item.toLocaleLowerCase() !== lowered);
  writeStorage(key, next);
  return next;
}

export interface MergeOptionsInput {
  /** Built-in codes, in display order. */
  canonical: readonly string[];
  /** Translate a canonical code (unknown values are shown verbatim). */
  translate: (value: string) => string;
  /** Values already used by the loaded rows — how other users' additions arrive. */
  fromData?: readonly string[];
  /** Catalogue key, to fold in options added in this browser. */
  catalogKey?: OptionCatalogKey;
  /** The current value, so a record never loses its own option. */
  current?: string;
}

/**
 * Build the dropdown list: canonical codes first, then everything the plant
 * added — whether that came from saved rows, this browser, or the current value.
 */
export function mergeOptions({
  canonical,
  translate,
  fromData = [],
  catalogKey,
  current = "",
}: MergeOptionsInput): SelectOption[] {
  const seen = new Set<string>();
  const options: SelectOption[] = [];

  const push = (value: string, label: string): void => {
    const normalized = normalizeOption(value);
    if (!normalized) return;
    const lowered = normalized.toLocaleLowerCase();
    if (seen.has(lowered)) return;
    seen.add(lowered);
    options.push({ value: normalized, label });
  };

  canonical.forEach((code) => push(code, translate(code)));
  const extras = [...(catalogKey ? readCustomOptions(catalogKey) : []), ...fromData, current];
  extras.forEach((value) => push(value, translate(value)));
  return options;
}
