import type { ApiClient } from "../../core/api/apiClient";
import { apiEndpoints } from "../../core/api/endpoints";

/**
 * Personnel performance review API (Phase 29).
 *
 * The scoring itself happens on the server; nothing here recomputes a mark.
 * That matters: a number shown next to someone's name has to be the same
 * number that was stored and audited, not one the browser derived.
 */

const text = (value: unknown, fallback = ""): string =>
  typeof value === "string" ? value : value == null ? fallback : String(value);

const count = (value: unknown): number => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
};

const optionalCount = (value: unknown): number | null => {
  if (value == null) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const flag = (value: unknown): boolean => value === true || value === "true";

export type CycleStatus = "draft" | "open" | "closed";

export interface ReviewCycle {
  id: string;
  code: string;
  name: string;
  fromDate: string;
  toDate: string;
  status: CycleStatus;
  systemWeightPercent: number;
  roleWeights: Record<string, number>;
  note: string;
  scoreCount: number;
}

export interface RaterScore {
  id: string;
  cycleId: string;
  personnelId: string;
  personnelName: string;
  raterRole: string;
  raterName: string;
  score: number;
  note: string;
}

export interface RaterBreakdown {
  raterRole: string;
  raterName: string;
  rawScore: number;
  baseWeight: number;
  deviation: number;
  damping: number;
  reliability: number;
  contribution: number;
  damped: boolean;
  reason: string;
}

export interface ReviewResult {
  id: string;
  personnelId: string;
  personnelName: string;
  finalScore: number;
  humanScore: number;
  systemScore: number | null;
  consensus: number;
  spread: number;
  raterCount: number;
  dampedCount: number;
  systemWeightPercent: number;
  rank: number;
  raters: RaterBreakdown[];
  systemMetrics: Record<string, number | null>;
  notes: string[];
}

export interface ReviewSummary {
  count: number;
  /** People with a measured score but no manager marks yet. */
  unratedCount: number;
  averageScore: number;
  highestScore: number;
  lowestScore: number;
  dampedTotal: number;
}

export interface PersonnelOption {
  id: string;
  personnelCode: string;
  fullName: string;
  specialty: string;
  unit: string;
}

export const toReviewCycle = (raw: Record<string, unknown>): ReviewCycle => ({
  id: text(raw.id),
  code: text(raw.code),
  name: text(raw.name),
  fromDate: text(raw.fromDate),
  toDate: text(raw.toDate),
  status: (text(raw.status, "draft") || "draft") as CycleStatus,
  systemWeightPercent: count(raw.systemWeightPercent),
  roleWeights: (raw.roleWeights as Record<string, number>) ?? {},
  note: text(raw.note),
  scoreCount: count(raw.scoreCount),
});

export const toRaterScore = (raw: Record<string, unknown>): RaterScore => ({
  id: text(raw.id),
  cycleId: text(raw.cycleId),
  personnelId: text(raw.personnelId),
  personnelName: text(raw.personnelName),
  raterRole: text(raw.raterRole),
  raterName: text(raw.raterName),
  score: count(raw.score),
  note: text(raw.note),
});

export const toRaterBreakdown = (raw: Record<string, unknown>): RaterBreakdown => ({
  raterRole: text(raw.raterRole),
  raterName: text(raw.raterName),
  rawScore: count(raw.rawScore),
  baseWeight: count(raw.baseWeight),
  deviation: count(raw.deviation),
  damping: count(raw.damping),
  reliability: count(raw.reliability),
  contribution: count(raw.contribution),
  damped: flag(raw.damped),
  reason: text(raw.reason),
});

export const toReviewResult = (raw: Record<string, unknown>): ReviewResult => ({
  id: text(raw.id),
  personnelId: text(raw.personnelId),
  personnelName: text(raw.personnelName),
  finalScore: count(raw.finalScore),
  humanScore: count(raw.humanScore),
  // Null is meaningful here and must survive the mapping: it says the work
  // record had nothing to measure, which is different from scoring zero.
  systemScore: optionalCount(raw.systemScore),
  consensus: count(raw.consensus),
  spread: count(raw.spread),
  raterCount: count(raw.raterCount),
  dampedCount: count(raw.dampedCount),
  systemWeightPercent: count(raw.systemWeightPercent),
  rank: count(raw.rank),
  raters: Array.isArray(raw.raters)
    ? (raw.raters as Record<string, unknown>[]).map(toRaterBreakdown)
    : [],
  systemMetrics: (raw.systemMetrics as Record<string, number | null>) ?? {},
  notes: Array.isArray(raw.notes) ? (raw.notes as unknown[]).map((note) => text(note)) : [],
});

export interface CycleListPayload {
  cycles: ReviewCycle[];
  raterRoles: string[];
  defaultRoleWeights: Record<string, number>;
}

export interface ScoreListPayload {
  cycle: ReviewCycle | null;
  scores: RaterScore[];
  personnel: PersonnelOption[];
  raterRoles: string[];
}

export interface ResultsPayload {
  cycle: ReviewCycle | null;
  results: ReviewResult[];
  /**
   * People nobody has scored yet. Kept apart from `results` on purpose: a
   * measured-only score is not comparable with one six managers argued over,
   * and ranking them together would reward never being reviewed.
   */
  unrated: ReviewResult[];
  summary: ReviewSummary;
}

export interface SaveCycleInput {
  id?: string;
  code: string;
  name: string;
  fromDate: string;
  toDate: string;
  status?: CycleStatus;
  systemWeightPercent?: number;
  note?: string;
}

export interface SaveScoreInput {
  cycleId: string;
  personnelId: string;
  raterRole: string;
  score: number;
  raterName?: string;
  note?: string;
}

const emptySummary: ReviewSummary = {
  count: 0,
  unratedCount: 0,
  averageScore: 0,
  highestScore: 0,
  lowestScore: 0,
  dampedTotal: 0,
};

export interface PerformanceReviewService {
  listCycles: (signal?: AbortSignal) => Promise<CycleListPayload>;
  saveCycle: (input: SaveCycleInput, signal?: AbortSignal) => Promise<ReviewCycle>;
  deleteCycle: (cycleId: string, signal?: AbortSignal) => Promise<void>;
  listScores: (cycleId: string, signal?: AbortSignal) => Promise<ScoreListPayload>;
  saveScore: (input: SaveScoreInput, signal?: AbortSignal) => Promise<RaterScore>;
  deleteScore: (scoreId: string, signal?: AbortSignal) => Promise<void>;
  compute: (cycleId: string, signal?: AbortSignal) => Promise<ResultsPayload>;
  getResults: (cycleId: string, signal?: AbortSignal) => Promise<ResultsPayload>;
}

const readResults = (raw: Record<string, unknown> | null): ResultsPayload => ({
  cycle: raw?.cycle ? toReviewCycle(raw.cycle as Record<string, unknown>) : null,
  results: Array.isArray(raw?.results)
    ? (raw?.results as Record<string, unknown>[]).map(toReviewResult)
    : [],
  unrated: Array.isArray(raw?.unrated)
    ? (raw?.unrated as Record<string, unknown>[]).map(toReviewResult)
    : [],
  summary: (raw?.summary as ReviewSummary) ?? emptySummary,
});

export const createPerformanceReviewService = (
  api: ApiClient,
): PerformanceReviewService => ({
  listCycles: async (signal) => {
    const raw = await api.get<Record<string, unknown>>(
      apiEndpoints.maintenance.reviewCycles,
      { signal },
    );
    return {
      cycles: ((raw?.cycles ?? []) as Record<string, unknown>[]).map(toReviewCycle),
      raterRoles: ((raw?.raterRoles ?? []) as unknown[]).map((role) => text(role)),
      defaultRoleWeights: (raw?.defaultRoleWeights as Record<string, number>) ?? {},
    };
  },
  saveCycle: async (input, signal) => {
    const raw = await api.post<Record<string, unknown>>(
      apiEndpoints.maintenance.reviewCycles,
      {
        id: input.id ?? "",
        code: input.code,
        name: input.name,
        fromDate: input.fromDate,
        toDate: input.toDate,
        status: input.status ?? "draft",
        systemWeightPercent: input.systemWeightPercent ?? 30,
        note: input.note ?? "",
      },
      // Never replay: a slow response must not open a second cycle.
      { signal, retry: 0 },
    );
    return toReviewCycle(raw ?? {});
  },
  deleteCycle: async (cycleId, signal) => {
    await api.delete(apiEndpoints.maintenance.reviewCycle(cycleId), { signal });
  },
  listScores: async (cycleId, signal) => {
    const raw = await api.get<Record<string, unknown>>(
      `${apiEndpoints.maintenance.reviewScores}?cycleId=${encodeURIComponent(cycleId)}`,
      { signal },
    );
    return {
      cycle: raw?.cycle ? toReviewCycle(raw.cycle as Record<string, unknown>) : null,
      scores: ((raw?.scores ?? []) as Record<string, unknown>[]).map(toRaterScore),
      personnel: ((raw?.personnel ?? []) as Record<string, unknown>[]).map((row) => ({
        id: text(row.id),
        personnelCode: text(row.personnelCode),
        fullName: text(row.fullName),
        specialty: text(row.specialty),
        unit: text(row.unit),
      })),
      raterRoles: ((raw?.raterRoles ?? []) as unknown[]).map((role) => text(role)),
    };
  },
  saveScore: async (input, signal) => {
    const raw = await api.post<Record<string, unknown>>(
      apiEndpoints.maintenance.reviewScores,
      {
        cycleId: input.cycleId,
        personnelId: input.personnelId,
        raterRole: input.raterRole,
        score: input.score,
        raterName: input.raterName ?? "",
        note: input.note ?? "",
      },
      { signal, retry: 0 },
    );
    return toRaterScore(raw ?? {});
  },
  deleteScore: async (scoreId, signal) => {
    await api.delete(apiEndpoints.maintenance.reviewScore(scoreId), { signal });
  },
  compute: async (cycleId, signal) => {
    const raw = await api.post<Record<string, unknown>>(
      apiEndpoints.maintenance.reviewCompute,
      { cycleId },
      { signal, retry: 0 },
    );
    return readResults(raw ?? null);
  },
  getResults: async (cycleId, signal) => {
    const raw = await api.get<Record<string, unknown>>(
      `${apiEndpoints.maintenance.reviewResults}?cycleId=${encodeURIComponent(cycleId)}`,
      { signal },
    );
    return readResults(raw ?? null);
  },
});
