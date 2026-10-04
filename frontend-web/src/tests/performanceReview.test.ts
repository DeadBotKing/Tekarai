import { describe, expect, it } from "vitest";

import {
  toRaterBreakdown,
  toRaterScore,
  toReviewCycle,
  toReviewResult,
} from "../features/maintenance/performanceReviewService";
import { createDemoPerformanceReviewService } from "../features/maintenance/performanceReviewDemoData";

describe("performance review mappers", () => {
  it("reads a cycle out of an API payload", () => {
    const cycle = toReviewCycle({
      id: "c-1",
      code: "REV-1",
      name: "دورهٔ اول",
      fromDate: "2026-03-21",
      toDate: "2026-09-22",
      status: "open",
      systemWeightPercent: 30,
      scoreCount: 4,
    });
    expect(cycle.code).toBe("REV-1");
    expect(cycle.systemWeightPercent).toBe(30);
    expect(cycle.scoreCount).toBe(4);
    expect(cycle.roleWeights).toEqual({});
  });

  it("defaults a missing status to draft rather than empty", () => {
    expect(toReviewCycle({ id: "c-2" }).status).toBe("draft");
  });

  it("keeps a null system score null instead of turning it into zero", () => {
    // This is the distinction the whole metric design rests on: "nothing to
    // measure" must never be rendered as "scored zero".
    const result = toReviewResult({
      id: "r-1",
      personnelId: "p-1",
      personnelName: "جواد امیرشاهی",
      finalScore: 70,
      humanScore: 70,
      systemScore: null,
    });
    expect(result.systemScore).toBeNull();
    expect(result.finalScore).toBe(70);
  });

  it("reads a real system score", () => {
    expect(toReviewResult({ systemScore: 88.5 }).systemScore).toBe(88.5);
  });

  it("maps the rater breakdown including the damping flag", () => {
    const rater = toRaterBreakdown({
      raterRole: "productionManager",
      rawScore: 95,
      baseWeight: 14,
      deviation: 5.88,
      damping: 0.15,
      reliability: 1,
      contribution: 4,
      damped: true,
      reason: "فاصلهٔ زیاد از اجماع",
    });
    expect(rater.damped).toBe(true);
    expect(rater.contribution).toBe(4);
    expect(rater.reason).toBe("فاصلهٔ زیاد از اجماع");
  });

  it("survives a result with no raters array", () => {
    expect(toReviewResult({ id: "r-2" }).raters).toEqual([]);
  });

  it("maps a submitted score", () => {
    const score = toRaterScore({
      id: "s-1",
      personnelName: "مینا رستمی",
      raterRole: "unitHead",
      score: "82",
    });
    expect(score.score).toBe(82);
    expect(score.personnelName).toBe("مینا رستمی");
  });
});

describe("performance review demo data", () => {
  const service = createDemoPerformanceReviewService();

  it("offers a cycle and the full rater roster", async () => {
    const payload = await service.listCycles();
    expect(payload.cycles).toHaveLength(1);
    expect(payload.raterRoles).toHaveLength(10);
    expect(payload.defaultRoleWeights.technicalManager).toBe(18);
  });

  it("ranks people by final score", async () => {
    const { results } = await service.getResults("cycle-demo-1");
    expect(results.map((row) => row.rank)).toEqual([1, 2, 3]);
    expect(results[0].finalScore).toBeGreaterThan(results[1].finalScore);
  });

  it("shows the biased raters damped in the worked example", async () => {
    const { results } = await service.getResults("cycle-demo-1");
    const javad = results.find((row) => row.personnelName === "جواد امیرشاهی");
    expect(javad).toBeDefined();
    expect(javad?.dampedCount).toBe(2);

    const damped = javad?.raters.filter((rater) => rater.damped).map((r) => r.raterRole);
    expect(damped).toEqual(["productionManager", "technicalManager"]);

    // The mark lands with the honest cluster near 71, not at the midpoint of
    // 95 and 40 — that is the entire point of the weighting.
    expect(javad?.humanScore).toBeGreaterThan(68);
    expect(javad?.humanScore).toBeLessThan(75);
  });

  it("never silences a dissenting rater completely", async () => {
    const { results } = await service.getResults("cycle-demo-1");
    const javad = results.find((row) => row.personnelName === "جواد امیرشاهی");
    javad?.raters.forEach((rater) => {
      expect(rater.contribution).toBeGreaterThan(0);
    });
  });

  it("every rater carries a stated reason", async () => {
    const { results } = await service.getResults("cycle-demo-1");
    results.forEach((row) =>
      row.raters.forEach((rater) => expect(rater.reason.length).toBeGreaterThan(0)),
    );
  });

  it("does not damp when there were too few raters to judge consensus", async () => {
    const { results } = await service.getResults("cycle-demo-1");
    const reza = results.find((row) => row.personnelName === "رضا کاظمی");
    expect(reza?.raterCount).toBe(2);
    expect(reza?.dampedCount).toBe(0);
    expect(reza?.notes.length).toBeGreaterThan(0);
  });

  it("keeps an unrated person out of the ranking entirely", async () => {
    // The defect this locks: a measured-only 100 outranking a reviewed 89.
    const { results, unrated, summary } = await service.getResults("cycle-demo-1");
    expect(results.every((row) => row.raterCount > 0)).toBe(true);
    expect(results.some((row) => row.personnelName === "سمیرا نوری")).toBe(false);
    expect(unrated).toHaveLength(1);
    expect(unrated[0].rank).toBe(0);
    expect(unrated[0].systemScore).toBe(100);
    expect(summary.unratedCount).toBe(1);
    // The top ranked person is the reviewed one, not the perfect-but-unrated one.
    expect(results[0].personnelName).toBe("مینا رستمی");
  });

  it("exposes a delete that the page can actually call", async () => {
    // The delete endpoint existed for a while with no UI calling it, which
    // is indistinguishable from not having the feature at all.
    await expect(service.deleteCycle("cycle-demo-1")).resolves.toBeUndefined();
  });

  it("hands back independent copies so the page cannot mutate the fixture", async () => {
    const first = await service.getResults("cycle-demo-1");
    first.results[0].finalScore = 1;
    const second = await service.getResults("cycle-demo-1");
    expect(second.results[0].finalScore).not.toBe(1);
  });
});
