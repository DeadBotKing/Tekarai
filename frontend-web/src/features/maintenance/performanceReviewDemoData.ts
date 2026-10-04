import type {
  CycleListPayload,
  PerformanceReviewService,
  RaterScore,
  ResultsPayload,
  ReviewCycle,
  ReviewResult,
  SaveCycleInput,
  SaveScoreInput,
  ScoreListPayload,
} from "./performanceReviewService";

/**
 * Offline sample data for the performance review page (Phase 29).
 *
 * The worked example is deliberately the awkward one: a technician two
 * managers disagree about violently, so the demo shows the weighting doing
 * its job rather than a tidy case where every rater already agrees.
 *
 * The arithmetic below is a *reproduction* of the server's result for this
 * fixed scenario, not a second implementation of the engine — demo mode never
 * scores anything the server has not already scored. Nothing here is reachable
 * when `demoMode` is false.
 */

const RATER_ROLES = [
  "technicalManager",
  "productionManager",
  "hrManager",
  "qaManager",
  "hseUnit",
  "labManager",
  "planningManager",
  "warehouseManager",
  "unitHead",
  "unitSupervisor",
];

const DEFAULT_ROLE_WEIGHTS: Record<string, number> = {
  technicalManager: 18,
  unitHead: 16,
  productionManager: 14,
  unitSupervisor: 14,
  qaManager: 9,
  hseUnit: 9,
  hrManager: 8,
  labManager: 5,
  planningManager: 5,
  warehouseManager: 4,
};

const demoCycle: ReviewCycle = {
  id: "cycle-demo-1",
  code: "REV-1405-S1",
  name: "ارزیابی نیمهٔ اول ۱۴۰۵",
  fromDate: "2026-03-21",
  toDate: "2026-09-22",
  status: "open",
  systemWeightPercent: 30,
  roleWeights: {},
  note: "",
  scoreCount: 11,
};

const demoPersonnel = [
  { id: "p-1", personnelCode: "P-001", fullName: "جواد امیرشاهی", specialty: "مکانیک", unit: "نگهداری" },
  { id: "p-2", personnelCode: "P-002", fullName: "مینا رستمی", specialty: "برق", unit: "نگهداری" },
  { id: "p-3", personnelCode: "P-003", fullName: "رضا کاظمی", specialty: "ابزار دقیق", unit: "نگهداری" },
];

const demoScores: RaterScore[] = [
  { id: "s-1", cycleId: demoCycle.id, personnelId: "p-1", personnelName: "جواد امیرشاهی", raterRole: "productionManager", raterName: "مدیر تولید", score: 95, note: "" },
  { id: "s-2", cycleId: demoCycle.id, personnelId: "p-1", personnelName: "جواد امیرشاهی", raterRole: "technicalManager", raterName: "مدیر فنی", score: 40, note: "" },
  { id: "s-3", cycleId: demoCycle.id, personnelId: "p-1", personnelName: "جواد امیرشاهی", raterRole: "unitHead", raterName: "رئیس واحد", score: 72, note: "" },
  { id: "s-4", cycleId: demoCycle.id, personnelId: "p-1", personnelName: "جواد امیرشاهی", raterRole: "unitSupervisor", raterName: "سرپرست واحد", score: 70, note: "" },
  { id: "s-5", cycleId: demoCycle.id, personnelId: "p-1", personnelName: "جواد امیرشاهی", raterRole: "qaManager", raterName: "مدیر کیفیت", score: 74, note: "" },
  { id: "s-6", cycleId: demoCycle.id, personnelId: "p-1", personnelName: "جواد امیرشاهی", raterRole: "hseUnit", raterName: "ایمنی و بهداشت", score: 71, note: "" },
  { id: "s-7", cycleId: demoCycle.id, personnelId: "p-2", personnelName: "مینا رستمی", raterRole: "technicalManager", raterName: "مدیر فنی", score: 88, note: "" },
  { id: "s-8", cycleId: demoCycle.id, personnelId: "p-2", personnelName: "مینا رستمی", raterRole: "unitHead", raterName: "رئیس واحد", score: 90, note: "" },
  { id: "s-9", cycleId: demoCycle.id, personnelId: "p-2", personnelName: "مینا رستمی", raterRole: "qaManager", raterName: "مدیر کیفیت", score: 86, note: "" },
  { id: "s-10", cycleId: demoCycle.id, personnelId: "p-3", personnelName: "رضا کاظمی", raterRole: "technicalManager", raterName: "مدیر فنی", score: 64, note: "" },
  { id: "s-11", cycleId: demoCycle.id, personnelId: "p-3", personnelName: "رضا کاظمی", raterRole: "unitHead", raterName: "رئیس واحد", score: 61, note: "" },
];

const demoResults: ReviewResult[] = [
  {
    id: "r-2",
    personnelId: "p-2",
    personnelName: "مینا رستمی",
    finalScore: 89.2,
    humanScore: 88.3,
    systemScore: 91.4,
    consensus: 88,
    spread: 4,
    raterCount: 3,
    dampedCount: 0,
    systemWeightPercent: 30,
    rank: 1,
    raters: [
      { raterRole: "technicalManager", raterName: "مدیر فنی", rawScore: 88, baseWeight: 18, deviation: 0, damping: 1, reliability: 1, contribution: 41.9, damped: false, reason: "fullWeight" },
      { raterRole: "unitHead", raterName: "رئیس واحد", rawScore: 90, baseWeight: 16, deviation: 0.5, damping: 1, reliability: 1, contribution: 37.2, damped: false, reason: "fullWeight" },
      { raterRole: "qaManager", raterName: "مدیر کیفیت", rawScore: 86, baseWeight: 9, deviation: -0.5, damping: 1, reliability: 1, contribution: 20.9, damped: false, reason: "fullWeight" },
    ],
    systemMetrics: { pmCompliance: 94, completionRate: 92, reworkPenalty: 88, onTimeCompletion: null },
    notes: [],
  },
  {
    id: "r-1",
    personnelId: "p-1",
    personnelName: "جواد امیرشاهی",
    finalScore: 76.5,
    humanScore: 70.9,
    systemScore: 89.6,
    consensus: 71.5,
    spread: 4,
    raterCount: 6,
    dampedCount: 2,
    systemWeightPercent: 30,
    rank: 2,
    raters: [
      { raterRole: "productionManager", raterName: "مدیر تولید", rawScore: 95, baseWeight: 14, deviation: 5.88, damping: 0.15, reliability: 1, contribution: 4.0, damped: true, reason: "dampedAbove:85" },
      { raterRole: "technicalManager", raterName: "مدیر فنی", rawScore: 40, baseWeight: 18, deviation: -7.88, damping: 0.15, reliability: 1, contribution: 5.1, damped: true, reason: "dampedBelow:85" },
      { raterRole: "unitHead", raterName: "رئیس واحد", rawScore: 72, baseWeight: 16, deviation: 0.13, damping: 1, reliability: 1, contribution: 30.3, damped: false, reason: "fullWeight" },
      { raterRole: "unitSupervisor", raterName: "سرپرست واحد", rawScore: 70, baseWeight: 14, deviation: -0.38, damping: 1, reliability: 1, contribution: 26.5, damped: false, reason: "fullWeight" },
      { raterRole: "qaManager", raterName: "مدیر کیفیت", rawScore: 74, baseWeight: 9, deviation: 0.63, damping: 1, reliability: 1, contribution: 17.1, damped: false, reason: "fullWeight" },
      { raterRole: "hseUnit", raterName: "ایمنی و بهداشت", rawScore: 71, baseWeight: 9, deviation: -0.13, damping: 1, reliability: 1, contribution: 17.1, damped: false, reason: "fullWeight" },
    ],
    systemMetrics: { pmCompliance: 92, completionRate: 95, reworkPenalty: 80, onTimeCompletion: null },
    notes: [],
  },
  {
    id: "r-3",
    personnelId: "p-3",
    personnelName: "رضا کاظمی",
    finalScore: 65.1,
    humanScore: 62.4,
    systemScore: 71.4,
    consensus: 62.5,
    spread: 4,
    raterCount: 2,
    dampedCount: 0,
    systemWeightPercent: 30,
    rank: 3,
    raters: [
      { raterRole: "technicalManager", raterName: "مدیر فنی", rawScore: 64, baseWeight: 18, deviation: 0.25, damping: 1, reliability: 1, contribution: 52.9, damped: false, reason: "fullWeight" },
      { raterRole: "unitHead", raterName: "رئیس واحد", rawScore: 61, baseWeight: 16, deviation: -0.25, damping: 1, reliability: 1, contribution: 47.1, damped: false, reason: "fullWeight" },
    ],
    systemMetrics: { pmCompliance: 70, completionRate: 75, reworkPenalty: 68, onTimeCompletion: null },
    notes: ["کمتر از ۴ ارزیاب — تعدیل سوگیری اعمال نشد"],
  },
];

/**
 * Someone with a clean but thin work record and no manager marks. Included
 * so the page always demonstrates that an unrated person is reported apart
 * from the ranking rather than topping it on measured score alone.
 */
const demoUnrated: ReviewResult[] = [
  {
    id: "r-4",
    personnelId: "p-4",
    personnelName: "سمیرا نوری",
    finalScore: 100,
    humanScore: 0,
    systemScore: 100,
    consensus: 0,
    spread: 0,
    raterCount: 0,
    dampedCount: 0,
    systemWeightPercent: 30,
    rank: 0,
    raters: [],
    systemMetrics: { pmCompliance: 100, completionRate: 100, reworkPenalty: 100, onTimeCompletion: null },
    notes: ["noRaters"],
  },
];

const demoSummary = {
  count: 3,
  unratedCount: 1,
  averageScore: 76.93,
  highestScore: 89.2,
  lowestScore: 65.1,
  dampedTotal: 2,
};

const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T;

export const createDemoPerformanceReviewService = (): PerformanceReviewService => ({
  listCycles: async (): Promise<CycleListPayload> => ({
    cycles: [clone(demoCycle)],
    raterRoles: [...RATER_ROLES],
    defaultRoleWeights: { ...DEFAULT_ROLE_WEIGHTS },
  }),
  saveCycle: async (input: SaveCycleInput) => ({
    ...clone(demoCycle),
    id: input.id || demoCycle.id,
    code: input.code,
    name: input.name,
    fromDate: input.fromDate,
    toDate: input.toDate,
    status: input.status ?? "draft",
    systemWeightPercent: input.systemWeightPercent ?? 30,
  }),
  deleteCycle: async () => undefined,
  listScores: async (): Promise<ScoreListPayload> => ({
    cycle: clone(demoCycle),
    scores: clone(demoScores),
    personnel: clone(demoPersonnel),
    raterRoles: [...RATER_ROLES],
  }),
  saveScore: async (input: SaveScoreInput): Promise<RaterScore> => ({
    id: `s-demo-${input.personnelId}-${input.raterRole}`,
    cycleId: input.cycleId,
    personnelId: input.personnelId,
    personnelName:
      demoPersonnel.find((person) => person.id === input.personnelId)?.fullName ?? "",
    raterRole: input.raterRole,
    raterName: input.raterName ?? "",
    score: input.score,
    note: input.note ?? "",
  }),
  deleteScore: async () => undefined,
  compute: async (): Promise<ResultsPayload> => ({
    cycle: clone(demoCycle),
    results: clone(demoResults),
    unrated: clone(demoUnrated),
    summary: { ...demoSummary },
  }),
  getResults: async (): Promise<ResultsPayload> => ({
    cycle: clone(demoCycle),
    results: clone(demoResults),
    unrated: clone(demoUnrated),
    summary: { ...demoSummary },
  }),
});
