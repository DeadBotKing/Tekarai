import { Fragment, useCallback, useEffect, useMemo, useState } from "react";

import { useApiClient } from "../core/api/apiContext";
import { useLocalization } from "../core/localization/localizationContext";
import { PERMISSIONS } from "../core/permissions/permissionContext";
import { runtimeConfig } from "../app/configuration/runtimeConfig";
import { createPerformanceReviewService } from "../features/maintenance/performanceReviewService";
import type {
  PersonnelOption,
  RaterScore,
  ReviewCycle,
  ReviewResult,
  ReviewSummary,
} from "../features/maintenance/performanceReviewService";
import { createDemoPerformanceReviewService } from "../features/maintenance/performanceReviewDemoData";
import { Modal, Toast } from "../shared/components/overlays";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  MetricCard,
  PermissionGuard,
  SectionHeader,
  SelectInput,
  TextInput,
} from "../shared/components/primitives";
import { BarChart } from "../shared/components/charts";
import { Icon } from "../shared/components/Icon";
import { formatJalali, toPersianDigits, todayIso } from "../core/localization/jalali";
import { JalaliDatePicker } from "../shared/components/JalaliDatePicker";


/**
 * Role label lookup.
 *
 * `t` takes a union of known keys, so a template literal cannot be passed to
 * it. Listing the roles explicitly keeps the compiler checking that every one
 * of them actually has a translation, which a cast would have thrown away.
 */
const ROLE_LABEL_KEYS = {
  technicalManager: "review.role.technicalManager",
  productionManager: "review.role.productionManager",
  hrManager: "review.role.hrManager",
  qaManager: "review.role.qaManager",
  hseUnit: "review.role.hseUnit",
  labManager: "review.role.labManager",
  planningManager: "review.role.planningManager",
  warehouseManager: "review.role.warehouseManager",
  unitHead: "review.role.unitHead",
  unitSupervisor: "review.role.unitSupervisor",
} as const;

const TAB_LABEL_KEYS = {
  comparison: "review.tab.comparison",
  scores: "review.tab.scores",
  cycles: "review.tab.cycles",
} as const;

const REASON_LABEL_KEYS = {
  fullWeight: "review.reason.fullWeight",
  dampedAbove: "review.reason.dampedAbove",
  dampedBelow: "review.reason.dampedBelow",
  unreliable: "review.reason.unreliable",
} as const;

type KnownRole = keyof typeof ROLE_LABEL_KEYS;
type KnownReason = keyof typeof REASON_LABEL_KEYS;

const isKnownReason = (code: string): code is KnownReason => code in REASON_LABEL_KEYS;

const isKnownRole = (role: string): role is KnownRole => role in ROLE_LABEL_KEYS;

const emptySummary: ReviewSummary = {
  count: 0,
  unratedCount: 0,
  averageScore: 0,
  highestScore: 0,
  lowestScore: 0,
  dampedTotal: 0,
};

/** Green for a strong mark, amber for middling, red for weak. */
const scoreColour = (score: number): string =>
  score >= 80 ? "#2faa6e" : score >= 60 ? "#e0a32e" : "#d4524a";

const scoreTone = (score: number): "success" | "warning" | "danger" =>
  score >= 80 ? "success" : score >= 60 ? "warning" : "danger";

type TabId = "comparison" | "scores" | "cycles";


export function PerformanceReviewPage(): JSX.Element {
  const api = useApiClient();
  const { t, locale } = useLocalization();
  const service = useMemo(
    () =>
      runtimeConfig.demoMode
        ? createDemoPerformanceReviewService()
        : createPerformanceReviewService(api),
    [api],
  );

  const [tab, setTab] = useState<TabId>("comparison");
  const [cycles, setCycles] = useState<ReviewCycle[]>([]);
  const [raterRoles, setRaterRoles] = useState<string[]>([]);
  const [selectedCycleId, setSelectedCycleId] = useState<string>("");
  const [results, setResults] = useState<ReviewResult[]>([]);
  const [unrated, setUnrated] = useState<ReviewResult[]>([]);
  const [summary, setSummary] = useState<ReviewSummary>(emptySummary);
  const [scores, setScores] = useState<RaterScore[]>([]);
  const [personnel, setPersonnel] = useState<PersonnelOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>("");
  const [toast, setToast] = useState<string>("");
  const [expanded, setExpanded] = useState<string>("");
  const [cycleDialog, setCycleDialog] = useState(false);
  const [scoreDialog, setScoreDialog] = useState(false);
  const [cycleToDelete, setCycleToDelete] = useState<ReviewCycle | null>(null);

  const [cycleForm, setCycleForm] = useState({
    code: "",
    name: "",
    fromDate: todayIso(),
    toDate: todayIso(),
    systemWeightPercent: "30",
  });
  const [scoreForm, setScoreForm] = useState({
    personnelId: "",
    raterRole: "",
    score: "75",
    raterName: "",
    note: "",
  });

  const selectedCycle = useMemo(
    () => cycles.find((cycle) => cycle.id === selectedCycleId) ?? null,
    [cycles, selectedCycleId],
  );

  const loadCycles = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const payload = await service.listCycles();
      setCycles(payload.cycles);
      setRaterRoles(payload.raterRoles);
      setSelectedCycleId((current) =>
        current && payload.cycles.some((cycle) => cycle.id === current)
          ? current
          : (payload.cycles[0]?.id ?? ""),
      );
    } catch {
      setError(t("review.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [service, t]);

  const loadCycleDetail = useCallback(
    async (cycleId: string) => {
      if (!cycleId) {
        setResults([]);
        setUnrated([]);
        setScores([]);
        setSummary(emptySummary);
        return;
      }
      try {
        const [resultsPayload, scoresPayload] = await Promise.all([
          service.getResults(cycleId),
          service.listScores(cycleId),
        ]);
        setResults(resultsPayload.results);
        setUnrated(resultsPayload.unrated);
        setSummary(resultsPayload.summary);
        setScores(scoresPayload.scores);
        setPersonnel(scoresPayload.personnel);
      } catch {
        setError(t("review.loadFailed"));
      }
    },
    [service, t],
  );

  useEffect(() => {
    void loadCycles();
  }, [loadCycles]);

  useEffect(() => {
    void loadCycleDetail(selectedCycleId);
  }, [loadCycleDetail, selectedCycleId]);

  const handleCompute = async (): Promise<void> => {
    if (!selectedCycleId) return;
    setBusy(true);
    try {
      const payload = await service.compute(selectedCycleId);
      setResults(payload.results);
      setUnrated(payload.unrated);
      setSummary(payload.summary);
      setToast(t("review.computed"));
      setTab("comparison");
    } catch {
      setError(t("review.computeFailed"));
    } finally {
      setBusy(false);
    }
  };

  const handleSaveCycle = async (): Promise<void> => {
    setBusy(true);
    try {
      const saved = await service.saveCycle({
        code: cycleForm.code,
        name: cycleForm.name,
        fromDate: cycleForm.fromDate,
        toDate: cycleForm.toDate,
        status: "open",
        systemWeightPercent: Number(cycleForm.systemWeightPercent) || 0,
      });
      setCycleDialog(false);
      setCycleForm({
        code: "",
        name: "",
        fromDate: todayIso(),
        toDate: todayIso(),
        systemWeightPercent: "30",
      });
      await loadCycles();
      setSelectedCycleId(saved.id);
      setToast(t("review.cycleSaved"));
    } catch {
      setError(t("review.saveFailed"));
    } finally {
      setBusy(false);
    }
  };

  const handleSaveScore = async (): Promise<void> => {
    if (!selectedCycleId) return;
    setBusy(true);
    try {
      await service.saveScore({
        cycleId: selectedCycleId,
        personnelId: scoreForm.personnelId,
        raterRole: scoreForm.raterRole,
        score: Number(scoreForm.score) || 0,
        raterName: scoreForm.raterName,
        note: scoreForm.note,
      });
      setScoreDialog(false);
      setScoreForm({ personnelId: "", raterRole: "", score: "75", raterName: "", note: "" });
      await loadCycleDetail(selectedCycleId);
      setToast(t("review.scoreSaved"));
    } catch {
      setError(t("review.saveFailed"));
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteCycle = async (): Promise<void> => {
    if (!cycleToDelete) return;
    setBusy(true);
    try {
      await service.deleteCycle(cycleToDelete.id);
      const removedId = cycleToDelete.id;
      setCycleToDelete(null);
      // Drop the selection first: leaving it pointing at a deleted cycle
      // would make the next detail fetch 404 behind the user's back.
      setSelectedCycleId((current) => (current === removedId ? "" : current));
      await loadCycles();
      setToast(t("review.cycleDeleted"));
    } catch {
      setError(t("review.deleteFailed"));
      setCycleToDelete(null);
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteScore = async (scoreId: string): Promise<void> => {
    setBusy(true);
    try {
      await service.deleteScore(scoreId);
      await loadCycleDetail(selectedCycleId);
      setToast(t("review.scoreRemoved"));
    } catch {
      setError(t("review.saveFailed"));
    } finally {
      setBusy(false);
    }
  };

  const number = (value: number): string =>
    locale === "fa" ? toPersianDigits(value.toFixed(1)) : value.toFixed(1);

  // An unknown role still has to render something rather than crash — it can
  // only arrive from data written before a role was retired.
  const roleLabel = (role: string): string =>
    isKnownRole(role) ? t(ROLE_LABEL_KEYS[role]) : role;

  /**
   * Turn the engine's reason codes into sentences in the reader's language.
   * The backend sends e.g. `dampedBelow:85`; the percentage is interpolated
   * rather than recomputed so the words can never disagree with the maths.
   */
  const reasonText = (reason: string): string =>
    reason
      .split(";")
      .map((part) => {
        const [code, value] = part.split(":");
        if (!isKnownReason(code)) return part;
        const percent = value
          ? locale === "fa"
            ? toPersianDigits(value)
            : value
          : "";
        return t(REASON_LABEL_KEYS[code], { percent });
      })
      .join(" · ");

  const chartData = results.map((row) => Math.round(row.finalScore * 10) / 10);
  const chartLabels = results.map((row) => row.personnelName || "—");
  const chartColours = results.map((row) => scoreColour(row.finalScore));

  if (loading) return <LoadingState label={t("review.loading")} />;

  return (
    <PermissionGuard permission={PERMISSIONS.maintenanceDeviceList}>
      <div className="page">
        <SectionHeader
          title={t("review.title")}
          subtitle={t("review.subtitle")}
          actions={
            <>
              <Button variant="secondary" onClick={() => setCycleDialog(true)}>
                <Icon name="plus" /> {t("review.newCycle")}
              </Button>
              <Button
                variant="primary"
                onClick={() => void handleCompute()}
                disabled={busy || !selectedCycleId}
              >
                <Icon name="refresh" /> {t("review.compute")}
              </Button>
            </>
          }
        />

        {error ? (
          <ErrorState
            title={t("review.errorTitle")}
            description={error}
            retry={() => void loadCycles()}
          />
        ) : null}

        <Card>
          <div className="toolbar">
            <SelectInput
              label={t("review.cycle")}
              value={selectedCycleId}
              onChange={(event) => setSelectedCycleId(event.target.value)}
              options={
                cycles.length === 0
                  ? [{ value: "", label: t("review.noCycles") }]
                  : cycles.map((cycle) => ({
                      value: cycle.id,
                      label: `${cycle.name} (${cycle.code})`,
                    }))
              }
            />
            {selectedCycle ? (
              <span className="muted-cell">
                {formatJalali(selectedCycle.fromDate)} — {formatJalali(selectedCycle.toDate)}
                {" · "}
                {t("review.systemShare")}:{" "}
                {locale === "fa"
                  ? toPersianDigits(String(selectedCycle.systemWeightPercent))
                  : selectedCycle.systemWeightPercent}
                %
              </span>
            ) : null}
          </div>
        </Card>

        <div className="registry-tabs" role="tablist">
          {(["comparison", "scores", "cycles"] as TabId[]).map((id) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={tab === id}
              className={`registry-tab ${tab === id ? "registry-tab--active" : ""}`}
              onClick={() => setTab(id)}
            >
              {t(TAB_LABEL_KEYS[id])}
            </button>
          ))}
        </div>

        {tab === "comparison" ? (
          <>
            <div className="metric-grid">
              <MetricCard
                icon="users"
                tone="blue"
                label={t("review.peopleScored")}
                value={locale === "fa" ? toPersianDigits(String(summary.count)) : String(summary.count)}
              />
              <MetricCard
                icon="target"
                tone="green"
                label={t("review.highest")}
                value={number(summary.highestScore)}
              />
              <MetricCard
                icon="chart"
                tone="purple"
                label={t("review.average")}
                value={number(summary.averageScore)}
              />
              <MetricCard
                icon="warning"
                tone="amber"
                label={t("review.damped")}
                value={
                  locale === "fa"
                    ? toPersianDigits(String(summary.dampedTotal))
                    : String(summary.dampedTotal)
                }
              />
            </div>

            <Card>
              <SectionHeader
                title={t("review.chartTitle")}
                subtitle={t("review.chartHint")}
              />
              {results.length === 0 ? (
                <EmptyState
                  title={t("review.noResults")}
                  description={t("review.noResultsHint")}
                />
              ) : (
                <BarChart
                  data={chartData}
                  labels={chartLabels}
                  barColors={chartColours}
                  ariaLabel={t("review.chartTitle")}
                />
              )}
            </Card>

            {results.length > 0 ? (
              <Card>
                <div className="table-scroll">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>{t("review.rank")}</th>
                        <th>{t("review.person")}</th>
                        <th>{t("review.finalScore")}</th>
                        <th>{t("review.humanScore")}</th>
                        <th>{t("review.systemScore")}</th>
                        <th>{t("review.raters")}</th>
                        <th>{t("review.damped")}</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {results.map((row) => (
                        // The fragment is the list child, so the key belongs
                        // here; React cannot see one on the inner rows.
                        <Fragment key={row.id}>
                          <tr>
                            <td>
                              {locale === "fa"
                                ? toPersianDigits(String(row.rank))
                                : row.rank}
                            </td>
                            <td className="plaintext">{row.personnelName || "—"}</td>
                            <td>
                              <Badge tone={scoreTone(row.finalScore)}>
                                {number(row.finalScore)}
                              </Badge>
                            </td>
                            <td>{number(row.humanScore)}</td>
                            <td>
                              {row.systemScore == null ? (
                                <span className="muted-cell">{t("review.noMeasurement")}</span>
                              ) : (
                                number(row.systemScore)
                              )}
                            </td>
                            <td>
                              {locale === "fa"
                                ? toPersianDigits(String(row.raterCount))
                                : row.raterCount}
                            </td>
                            <td>
                              {row.dampedCount > 0 ? (
                                <Badge tone="warning">
                                  {locale === "fa"
                                    ? toPersianDigits(String(row.dampedCount))
                                    : row.dampedCount}
                                </Badge>
                              ) : (
                                <span className="muted-cell">—</span>
                              )}
                            </td>
                            <td>
                              <Button
                                variant="subtle"
                                onClick={() =>
                                  setExpanded(expanded === row.id ? "" : row.id)
                                }
                              >
                                {expanded === row.id
                                  ? t("review.hideWhy")
                                  : t("review.why")}
                              </Button>
                            </td>
                          </tr>
                          {expanded === row.id ? (
                            <tr>
                              <td colSpan={8}>
                                <div className="content-card">
                                  <p className="muted-cell">{t("review.whyHint")}</p>
                                  <div className="table-scroll">
                                    <table className="data-table">
                                      <thead>
                                        <tr>
                                          <th>{t("review.rater")}</th>
                                          <th>{t("review.rawScore")}</th>
                                          <th>{t("review.baseWeight")}</th>
                                          <th>{t("review.contribution")}</th>
                                          <th>{t("review.reason")}</th>
                                        </tr>
                                      </thead>
                                      <tbody>
                                        {row.raters.map((rater) => (
                                          <tr key={`${row.id}-${rater.raterRole}`}>
                                            <td className="plaintext">
                                              {roleLabel(rater.raterRole)}
                                            </td>
                                            <td>{number(rater.rawScore)}</td>
                                            <td>{number(rater.baseWeight)}</td>
                                            <td>
                                              {rater.damped ? (
                                                <Badge tone="warning">
                                                  {number(rater.contribution)}%
                                                </Badge>
                                              ) : (
                                                `${number(rater.contribution)}%`
                                              )}
                                            </td>
                                            <td className="plaintext">{reasonText(rater.reason)}</td>
                                          </tr>
                                        ))}
                                      </tbody>
                                    </table>
                                  </div>
                                  {row.notes.length > 0 ? (
                                    <ul>
                                      {row.notes.map((note) => (
                                        <li className="muted-cell" key={note}>
                                          {note}
                                        </li>
                                      ))}
                                    </ul>
                                  ) : null}
                                </div>
                              </td>
                            </tr>
                          ) : null}
                        </Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            ) : null}

            {unrated.length > 0 ? (
              <Card>
                <SectionHeader
                  title={t("review.unratedTitle")}
                  subtitle={t("review.unratedHint")}
                />
                <div className="table-scroll">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>{t("review.person")}</th>
                        <th>{t("review.systemScore")}</th>
                        <th>{t("review.raters")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {unrated.map((row) => (
                        <tr key={row.id}>
                          <td className="plaintext">{row.personnelName || "—"}</td>
                          <td>
                            {row.systemScore == null
                              ? t("review.noMeasurement")
                              : number(row.systemScore)}
                          </td>
                          <td>
                            <Badge tone="neutral">{t("review.notRated")}</Badge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            ) : null}
          </>
        ) : null}

        {tab === "scores" ? (
          <Card>
            <SectionHeader
              title={t("review.scoresTitle")}
              subtitle={t("review.scoresHint")}
              actions={
                <Button
                  variant="primary"
                  onClick={() => setScoreDialog(true)}
                  disabled={!selectedCycleId}
                >
                  <Icon name="plus" /> {t("review.addScore")}
                </Button>
              }
            />
            {scores.length === 0 ? (
              <EmptyState
                title={t("review.noScores")}
                description={t("review.noScoresHint")}
              />
            ) : (
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>{t("review.person")}</th>
                      <th>{t("review.rater")}</th>
                      <th>{t("review.rawScore")}</th>
                      <th>{t("review.note")}</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {scores.map((row) => (
                      <tr key={row.id}>
                        <td className="plaintext">{row.personnelName || "—"}</td>
                        <td className="plaintext">{roleLabel(row.raterRole)}</td>
                        <td>{number(row.score)}</td>
                        <td className="plaintext">{row.note || "—"}</td>
                        <td>
                          <Button
                            variant="danger"
                            onClick={() => void handleDeleteScore(row.id)}
                            disabled={busy}
                          >
                            <Icon name="close" />
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        ) : null}

        {tab === "cycles" ? (
          <Card>
            <SectionHeader
              title={t("review.cyclesTitle")}
              subtitle={t("review.cyclesHint")}
            />
            {cycles.length === 0 ? (
              <EmptyState
                title={t("review.noCycles")}
                description={t("review.noCyclesHint")}
              />
            ) : (
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>{t("review.code")}</th>
                      <th>{t("review.name")}</th>
                      <th>{t("review.period")}</th>
                      <th>{t("review.systemShare")}</th>
                      <th>{t("review.scoreCount")}</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {cycles.map((cycle) => (
                      <tr key={cycle.id}>
                        <td className="plaintext">{cycle.code}</td>
                        <td className="plaintext">{cycle.name}</td>
                        <td>
                          {formatJalali(cycle.fromDate)} — {formatJalali(cycle.toDate)}
                        </td>
                        <td>
                          {locale === "fa"
                            ? toPersianDigits(String(cycle.systemWeightPercent))
                            : cycle.systemWeightPercent}
                          %
                        </td>
                        <td>
                          {locale === "fa"
                            ? toPersianDigits(String(cycle.scoreCount))
                            : cycle.scoreCount}
                        </td>
                        <td>
                          {cycle.status === "closed" ? (
                            // Deleting a published round would erase the
                            // marks it was justified by.
                            <span className="muted-cell">
                              {t("review.closedNoDelete")}
                            </span>
                          ) : (
                            <Button
                              variant="danger"
                              onClick={() => setCycleToDelete(cycle)}
                              disabled={busy}
                            >
                              <Icon name="close" /> {t("common.delete")}
                            </Button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        ) : null}

        <Modal
          open={cycleDialog}
          title={t("review.newCycle")}
          onClose={() => setCycleDialog(false)}
          footer={
            <>
              <Button variant="ghost" onClick={() => setCycleDialog(false)}>
                {t("common.cancel")}
              </Button>
              <Button
                variant="primary"
                onClick={() => void handleSaveCycle()}
                disabled={busy || !cycleForm.code || !cycleForm.name}
              >
                {t("common.save")}
              </Button>
            </>
          }
        >
          <TextInput
            label={t("review.code")}
            value={cycleForm.code}
            onChange={(event) =>
              setCycleForm({ ...cycleForm, code: event.target.value })
            }
          />
          <TextInput
            label={t("review.name")}
            value={cycleForm.name}
            onChange={(event) =>
              setCycleForm({ ...cycleForm, name: event.target.value })
            }
          />
          <JalaliDatePicker
            label={t("review.fromDate")}
            value={cycleForm.fromDate}
            onChange={(iso) => setCycleForm({ ...cycleForm, fromDate: iso })}
          />
          <JalaliDatePicker
            label={t("review.toDate")}
            value={cycleForm.toDate}
            onChange={(iso) => setCycleForm({ ...cycleForm, toDate: iso })}
          />
          <TextInput
            label={t("review.systemSharePercent")}
            value={cycleForm.systemWeightPercent}
            onChange={(event) =>
              setCycleForm({ ...cycleForm, systemWeightPercent: event.target.value })
            }
          />
          <p className="muted-cell">{t("review.systemShareHint")}</p>
        </Modal>

        <Modal
          open={scoreDialog}
          title={t("review.addScore")}
          onClose={() => setScoreDialog(false)}
          footer={
            <>
              <Button variant="ghost" onClick={() => setScoreDialog(false)}>
                {t("common.cancel")}
              </Button>
              <Button
                variant="primary"
                onClick={() => void handleSaveScore()}
                disabled={busy || !scoreForm.personnelId || !scoreForm.raterRole}
              >
                {t("common.save")}
              </Button>
            </>
          }
        >
          <SelectInput
            label={t("review.person")}
            value={scoreForm.personnelId}
            onChange={(event) =>
              setScoreForm({ ...scoreForm, personnelId: event.target.value })
            }
            options={[
              { value: "", label: "—" },
              ...personnel.map((person) => ({
                value: person.id,
                label: person.fullName,
              })),
            ]}
          />
          <SelectInput
            label={t("review.rater")}
            value={scoreForm.raterRole}
            onChange={(event) =>
              setScoreForm({ ...scoreForm, raterRole: event.target.value })
            }
            options={[
              { value: "", label: "—" },
              ...raterRoles.map((role) => ({ value: role, label: roleLabel(role) })),
            ]}
          />
          <TextInput
            label={t("review.rawScore")}
            value={scoreForm.score}
            onChange={(event) =>
              setScoreForm({ ...scoreForm, score: event.target.value })
            }
          />
          <TextInput
            label={t("review.note")}
            value={scoreForm.note}
            onChange={(event) =>
              setScoreForm({ ...scoreForm, note: event.target.value })
            }
          />
        </Modal>

        <Modal
          open={cycleToDelete !== null}
          title={t("review.deleteCycleTitle")}
          onClose={() => setCycleToDelete(null)}
          footer={
            <>
              <Button variant="ghost" onClick={() => setCycleToDelete(null)}>
                {t("common.cancel")}
              </Button>
              <Button
                variant="danger"
                onClick={() => void handleDeleteCycle()}
                disabled={busy}
              >
                {t("common.delete")}
              </Button>
            </>
          }
        >
          <p>
            {t("review.deleteCycleConfirm", {
              name: cycleToDelete?.name ?? "",
            })}
          </p>
          {/* Spell out the cascade: the count is the part people miss. */}
          <p className="muted-cell">
            {t("review.deleteCycleCascade", {
              count:
                locale === "fa"
                  ? toPersianDigits(String(cycleToDelete?.scoreCount ?? 0))
                  : String(cycleToDelete?.scoreCount ?? 0),
            })}
          </p>
        </Modal>

        {toast ? <Toast message={toast} onClose={() => setToast("")} /> : null}
      </div>
    </PermissionGuard>
  );
}
