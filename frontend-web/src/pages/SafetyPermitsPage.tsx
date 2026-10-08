import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiClientError } from "../core/api/apiClient";
import { useApiClient } from "../core/api/apiContext";
import { PERMISSIONS } from "../core/permissions/permissionContext";
import { DataTable, type DataTableColumn } from "../shared/components/DataTable";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  PermissionGuard,
} from "../shared/components/primitives";

/**
 * مجوز کار — permit to work.
 *
 * This screen is a control, not a form. The design follows from that:
 *
 * * **The blockers are shown, always.** When a permit cannot be issued the
 *   page lists every outstanding item at once rather than refusing one at
 *   a time. A supervisor who has to click approve four times to discover
 *   four problems will stop using the system.
 * * **The approve button is disabled when the permit is not ready**, but
 *   the server still refuses independently. The disabled state is a
 *   courtesy; the guard is in the domain. A UI check alone would be
 *   bypassed by the first person who learns the URL.
 * * **Time remaining is displayed on every live permit**, because the
 *   single most common failure of a paper permit system is work running
 *   past the window nobody was watching.
 * * **The isolation register is the centre of an isolation-class permit**,
 *   not a sub-tab. Applied and verified are separate columns with separate
 *   names, because they are separate acts by separate people.
 *
 * Deliberately fixture-free: one code path, the API. Under demo fixtures
 * it shows its error state rather than inventing permits — a fabricated
 * permit is a dangerous thing to put on a screen.
 */

interface Validity {
  hasStarted: boolean;
  isExpired: boolean;
  isWithinWindow: boolean;
  minutesUntilStart: number;
  minutesRemaining: number;
  isExpiringSoon: boolean;
  isOverdueWithWorkInProgress: boolean;
}

interface Precaution {
  id: string;
  code: string;
  text: string;
  isMandatory: boolean;
  confirmed: boolean;
  confirmedByName: string;
  confirmedAt: string | null;
}

interface IsolationPoint {
  id: string;
  pointCode: string;
  description: string;
  energyType: string;
  energyLabel: string;
  isolationMethod: string;
  lockTag: string;
  appliedByName: string;
  verifiedByName: string;
  removedByName: string;
  isApplied: boolean;
  isVerified: boolean;
  isRemoved: boolean;
}

interface PermitEvent {
  id: string;
  action: string;
  toStatus: string;
  toStatusLabel: string;
  actorName: string;
  note: string;
  occurredAt: string | null;
}

export interface PermitSummary {
  id: string;
  number: string;
  permitType: string;
  permitTypeLabel: string;
  status: string;
  statusLabel: string;
  title: string;
  riskLevel: string;
  riskLabel: string;
  locationName: string;
  requesterName: string;
  performerName: string;
  approverName: string;
  validFrom: string | null;
  validTo: string | null;
  requiresIsolation: boolean;
  validity: Validity;
}

interface PermitDetail extends PermitSummary {
  description: string;
  maxValidityHours: number;
  rejectionReason: string;
  suspensionReason: string;
  closureNote: string;
  readiness: { isReadyToIssue: boolean; blockers: string[] };
  precautions: Precaution[];
  isolations: IsolationPoint[];
  events: PermitEvent[];
}

interface TypeOption {
  value: string;
  label: string;
  requiresIsolation: boolean;
  maxValidityHours: number;
}

interface ListPayload {
  items: PermitSummary[];
  options: {
    statuses: { value: string; label: string }[];
    types: TypeOption[];
    riskLevels: { value: string; label: string }[];
    energyTypes: { value: string; label: string }[];
  };
}

const statusTones: Record<string, "neutral" | "success" | "warning" | "danger" | "info" | "purple"> =
  {
    draft: "neutral",
    submitted: "info",
    approved: "purple",
    active: "success",
    suspended: "warning",
    completed: "info",
    closed: "neutral",
    rejected: "danger",
    cancelled: "neutral",
    expired: "danger",
  };

const riskTones: Record<string, "neutral" | "success" | "warning" | "danger"> = {
  low: "success",
  medium: "neutral",
  high: "warning",
  critical: "danger",
};

const faNumber = (value: number): string => value.toLocaleString("fa-IR");

/** Minutes as something a person reads at a glance: «۳ ساعت و ۱۵ دقیقه». */
export const formatDuration = (minutes: number): string => {
  if (minutes <= 0) return "۰ دقیقه";
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) return `${faNumber(rest)} دقیقه`;
  if (rest === 0) return `${faNumber(hours)} ساعت`;
  return `${faNumber(hours)} ساعت و ${faNumber(rest)} دقیقه`;
};

const formatDateTime = (raw: string | null): string => {
  if (!raw) return "—";
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("fa-IR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
};

/**
 * The one line that matters on a live permit.
 *
 * Overdue-with-work-in-progress is called out separately and loudly: it
 * means people may still be on the job under an authorisation that has
 * run out, and it is the only state here that needs somebody to walk to
 * the job face.
 */
export const validitySummary = (validity: Validity): { text: string; tone: "neutral" | "success" | "warning" | "danger" } => {
  if (validity.isOverdueWithWorkInProgress) {
    return { text: "کار در جریان با مجوز منقضی‌شده — نیاز به بررسی فوری", tone: "danger" };
  }
  if (validity.isExpired) return { text: "اعتبار به پایان رسیده", tone: "danger" };
  if (!validity.hasStarted) {
    return { text: `${formatDuration(validity.minutesUntilStart)} تا شروع اعتبار`, tone: "neutral" };
  }
  if (validity.isExpiringSoon) {
    return { text: `${formatDuration(validity.minutesRemaining)} تا پایان اعتبار`, tone: "warning" };
  }
  return { text: `${formatDuration(validity.minutesRemaining)} باقی‌مانده`, tone: "success" };
};

const emptyForm = {
  permitType: "general",
  title: "",
  description: "",
  riskLevel: "medium",
  locationName: "",
  performerName: "",
  contractorName: "",
  personnelCount: "1",
  validFrom: "",
  validTo: "",
};

const emptyIsolation = {
  pointCode: "",
  description: "",
  energyType: "electrical",
  isolationMethod: "",
  lockTag: "",
};

export function SafetyPermitsPage(): JSX.Element {
  const api = useApiClient();
  const [payload, setPayload] = useState<ListPayload | null>(null);
  const [selected, setSelected] = useState<PermitDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [statusFilter, setStatusFilter] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [isolationForm, setIsolationForm] = useState(emptyIsolation);

  const load = useCallback(() => {
    setLoading(true);
    const query = statusFilter ? `?status=${encodeURIComponent(statusFilter)}` : "";
    void api
      .get<ListPayload>(`safety/permits${query}`)
      .then((data) => {
        setPayload(data);
        setError(null);
      })
      .catch((cause: unknown) =>
        setError(
          cause instanceof ApiClientError && cause.message
            ? cause.message
            : "دریافت فهرست مجوزهای کار ناموفق بود.",
        ),
      )
      .finally(() => setLoading(false));
  }, [api, statusFilter]);

  useEffect(load, [load]);

  const failureMessage = (cause: unknown, fallback: string): string =>
    cause instanceof ApiClientError && cause.message ? cause.message : fallback;

  const openPermit = (permitId: string): void => {
    void api
      .get<PermitDetail>(`safety/permits/${permitId}`)
      .then(setSelected)
      .catch((cause: unknown) => setNotice(failureMessage(cause, "دریافت جزئیات مجوز ناموفق بود.")));
  };

  /** Every action funnels through here so refusals are surfaced uniformly. */
  const runAction = (permitId: string, action: string, body: Record<string, unknown> = {}): void => {
    setBusy(true);
    setNotice("");
    void api
      .post<PermitDetail>(`safety/permits/${permitId}/${action}`, body)
      .then((detail) => {
        setSelected(detail);
        load();
      })
      .catch((cause: unknown) => setNotice(failureMessage(cause, "انجام این عملیات ممکن نشد.")))
      .finally(() => setBusy(false));
  };

  const askReasonThenRun = (permitId: string, action: string, prompt: string): void => {
    const reason = window.prompt(prompt) ?? "";
    if (!reason.trim()) return;
    runAction(permitId, action, { reason });
  };

  const createPermit = (): void => {
    setBusy(true);
    setNotice("");
    void api
      .post<PermitDetail>("safety/permits", {
        ...form,
        personnelCount: Number(form.personnelCount) || 1,
        validFrom: form.validFrom ? new Date(form.validFrom).toISOString() : null,
        validTo: form.validTo ? new Date(form.validTo).toISOString() : null,
      })
      .then((detail) => {
        setSelected(detail);
        setShowForm(false);
        setForm(emptyForm);
        load();
      })
      .catch((cause: unknown) => setNotice(failureMessage(cause, "ثبت مجوز ناموفق بود.")))
      .finally(() => setBusy(false));
  };

  const addIsolation = (permitId: string): void => {
    setBusy(true);
    void api
      .post<PermitDetail>(`safety/permits/${permitId}/isolations`, isolationForm)
      .then((detail) => {
        setSelected(detail);
        setIsolationForm(emptyIsolation);
      })
      .catch((cause: unknown) => setNotice(failureMessage(cause, "ثبت نقطه جداسازی ناموفق بود.")))
      .finally(() => setBusy(false));
  };

  const isolationAction = (permitId: string, isolationId: string, action: string): void => {
    setBusy(true);
    setNotice("");
    void api
      .post<PermitDetail>(`safety/permits/${permitId}/isolations/${isolationId}/${action}`, {})
      .then((detail) => {
        setSelected(detail);
        load();
      })
      .catch((cause: unknown) => setNotice(failureMessage(cause, "انجام این عملیات ممکن نشد.")))
      .finally(() => setBusy(false));
  };

  const confirmPrecaution = (permitId: string, precautionId: string): void => {
    setBusy(true);
    void api
      .post<PermitDetail>(`safety/permits/${permitId}/precautions/${precautionId}/confirm`, {})
      .then(setSelected)
      .catch((cause: unknown) => setNotice(failureMessage(cause, "ثبت تأیید ناموفق بود.")))
      .finally(() => setBusy(false));
  };

  const items = payload?.items ?? [];
  const typeOptions = payload?.options.types ?? [];

  /** Permits that need somebody to do something, counted for the header. */
  const attentionCount = useMemo(
    () =>
      items.filter(
        (x) => x.validity.isOverdueWithWorkInProgress || x.validity.isExpiringSoon,
      ).length,
    [items],
  );

  const columns: DataTableColumn<PermitSummary>[] = [
    { key: "number", label: "شماره", accessor: (row) => row.number },
    { key: "title", label: "شرح کار", accessor: (row) => row.title },
    { key: "permitTypeLabel", label: "نوع", accessor: (row) => row.permitTypeLabel },
    {
      key: "riskLevel",
      label: "ریسک",
      render: (row) => <Badge tone={riskTones[row.riskLevel] ?? "neutral"}>{row.riskLabel}</Badge>,
    },
    {
      key: "status",
      label: "وضعیت",
      render: (row) => (
        <Badge tone={statusTones[row.status] ?? "neutral"}>{row.statusLabel}</Badge>
      ),
    },
    {
      key: "validity",
      label: "اعتبار",
      render: (row) => {
        const summary = validitySummary(row.validity);
        return <Badge tone={summary.tone}>{summary.text}</Badge>;
      },
    },
    { key: "requesterName", label: "درخواست‌کننده", accessor: (row) => row.requesterName || "—" },
    {
      key: "open",
      label: "",
      render: (row) => (
        <Button variant="ghost" onClick={() => openPermit(row.id)}>
          مشاهده
        </Button>
      ),
    },
  ];

  const selectedType = typeOptions.find((x) => x.value === form.permitType);

  return (
    <PermissionGuard permission={PERMISSIONS.safetyPermitView}>
      <div className="page">
        <Card>
          <CardHeader
            title="مجوز کار (Permit to Work)"
            subtitle="صدور، کنترل و بستن مجوزهای کار همراه با ثبت قفل‌گذاری و چک‌لیست ایمنی"
            action={
              <>
                <select
                  value={statusFilter}
                  onChange={(event) => setStatusFilter(event.target.value)}
                  aria-label="فیلتر وضعیت"
                >
                  <option value="">همه وضعیت‌ها</option>
                  {(payload?.options.statuses ?? []).map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
                <Button onClick={() => setShowForm((value) => !value)}>
                  {showForm ? "انصراف" : "مجوز جدید"}
                </Button>
              </>
            }
          />

          {attentionCount > 0 && (
            <p className="alert alert--warning" role="status">
              {faNumber(attentionCount)} مجوز نیازمند توجه است (نزدیک به انقضا یا منقضی‌شده با کار
              در جریان).
            </p>
          )}
          {notice && (
            <p className="alert" role="status">
              {notice}
            </p>
          )}

          {showForm && (
            <div className="form-grid">
              <label>
                نوع مجوز
                <select
                  value={form.permitType}
                  onChange={(event) => setForm({ ...form, permitType: event.target.value })}
                >
                  {typeOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              {selectedType && (
                // Stating the limits before the form is filled in, rather
                // than refusing afterwards.
                <p className="hint">
                  بیشترین مدت مجاز: {faNumber(selectedType.maxValidityHours)} ساعت
                  {selectedType.requiresIsolation
                    ? " — برای این نوع، ثبت و تأیید نقاط جداسازی الزامی است."
                    : ""}
                </p>
              )}
              <label>
                شرح کار
                <input
                  value={form.title}
                  onChange={(event) => setForm({ ...form, title: event.target.value })}
                />
              </label>
              <label>
                سطح ریسک
                <select
                  value={form.riskLevel}
                  onChange={(event) => setForm({ ...form, riskLevel: event.target.value })}
                >
                  {(payload?.options.riskLevels ?? []).map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                محل کار
                <input
                  value={form.locationName}
                  onChange={(event) => setForm({ ...form, locationName: event.target.value })}
                />
              </label>
              <label>
                مجری کار
                <input
                  value={form.performerName}
                  onChange={(event) => setForm({ ...form, performerName: event.target.value })}
                />
              </label>
              <label>
                پیمانکار
                <input
                  value={form.contractorName}
                  onChange={(event) => setForm({ ...form, contractorName: event.target.value })}
                />
              </label>
              <label>
                تعداد نفرات
                <input
                  type="number"
                  min={1}
                  value={form.personnelCount}
                  onChange={(event) => setForm({ ...form, personnelCount: event.target.value })}
                />
              </label>
              <label>
                شروع اعتبار
                <input
                  type="datetime-local"
                  value={form.validFrom}
                  onChange={(event) => setForm({ ...form, validFrom: event.target.value })}
                />
              </label>
              <label>
                پایان اعتبار
                <input
                  type="datetime-local"
                  value={form.validTo}
                  onChange={(event) => setForm({ ...form, validTo: event.target.value })}
                />
              </label>
              <Button onClick={createPermit} disabled={busy || !form.title.trim()}>
                ثبت پیش‌نویس مجوز
              </Button>
            </div>
          )}

          {error ? (
            <ErrorState title="خطا در دریافت اطلاعات" description={error} retry={load} />
          ) : loading ? (
            <EmptyState title="در حال دریافت…" />
          ) : (
            <DataTable columns={columns} data={items} rowKey={(row) => row.id} />
          )}
        </Card>

        {selected && (
          <Card>
            <CardHeader
              title={`${selected.number} — ${selected.title}`}
              subtitle={`${selected.permitTypeLabel} • ریسک ${selected.riskLabel} • ${selected.locationName || "بدون محل ثبت‌شده"}`}
              action={<Button variant="ghost" onClick={() => setSelected(null)}>بستن</Button>}
            />

            <p>
              <Badge tone={statusTones[selected.status] ?? "neutral"}>{selected.statusLabel}</Badge>{" "}
              <Badge tone={validitySummary(selected.validity).tone}>
                {validitySummary(selected.validity).text}
              </Badge>
            </p>
            <p className="hint">
              اعتبار از {formatDateTime(selected.validFrom)} تا {formatDateTime(selected.validTo)}
            </p>

            {/* Every reason the permit cannot be issued, together. */}
            {!selected.readiness.isReadyToIssue && (
              <div className="alert alert--warning">
                <strong>موارد باقی‌مانده پیش از صدور:</strong>
                <ul>
                  {selected.readiness.blockers.map((blocker) => (
                    <li key={blocker}>{blocker}</li>
                  ))}
                </ul>
              </div>
            )}
            {selected.rejectionReason && (
              <p className="alert alert--danger">دلیل رد: {selected.rejectionReason}</p>
            )}
            {selected.suspensionReason && (
              <p className="alert alert--warning">دلیل تعلیق: {selected.suspensionReason}</p>
            )}

            <div className="button-row">
              {selected.status === "draft" && (
                <Button onClick={() => runAction(selected.id, "submit")} disabled={busy}>
                  ارسال برای تأیید
                </Button>
              )}
              <PermissionGuard permission={PERMISSIONS.safetyPermitApprove} fallback="hide">
                {selected.status === "submitted" && (
                  <>
                    <Button
                      onClick={() => runAction(selected.id, "approve")}
                      disabled={busy || !selected.readiness.isReadyToIssue}
                      // Disabled is a courtesy; the server refuses too.
                      title={
                        selected.readiness.isReadyToIssue
                          ? "صدور مجوز"
                          : "تا تکمیل موارد بالا، صدور مجوز ممکن نیست"
                      }
                    >
                      تأیید و صدور
                    </Button>
                    <Button
                      variant="ghost"
                      onClick={() => askReasonThenRun(selected.id, "reject", "دلیل رد مجوز:")}
                      disabled={busy}
                    >
                      رد
                    </Button>
                  </>
                )}
                {selected.status === "active" && (
                  <Button
                    variant="ghost"
                    onClick={() => askReasonThenRun(selected.id, "suspend", "دلیل تعلیق:")}
                    disabled={busy}
                  >
                    تعلیق
                  </Button>
                )}
              </PermissionGuard>
              {selected.status === "approved" && (
                <Button onClick={() => runAction(selected.id, "activate")} disabled={busy}>
                  شروع کار
                </Button>
              )}
              {selected.status === "suspended" && (
                <Button onClick={() => runAction(selected.id, "resume")} disabled={busy}>
                  ازسرگیری
                </Button>
              )}
              {selected.status === "active" && (
                <Button onClick={() => runAction(selected.id, "complete")} disabled={busy}>
                  پایان کار
                </Button>
              )}
              <PermissionGuard permission={PERMISSIONS.safetyPermitClose} fallback="hide">
                {selected.status === "completed" && (
                  <Button onClick={() => runAction(selected.id, "close")} disabled={busy}>
                    بستن مجوز و تحویل تجهیز
                  </Button>
                )}
              </PermissionGuard>
            </div>

            <h3>چک‌لیست ایمنی</h3>
            <ul className="checklist">
              {selected.precautions.map((item) => (
                <li key={item.id}>
                  <Badge tone={item.confirmed ? "success" : item.isMandatory ? "danger" : "neutral"}>
                    {item.confirmed ? "تأیید شد" : item.isMandatory ? "الزامی" : "اختیاری"}
                  </Badge>{" "}
                  {item.text}
                  {item.confirmed ? (
                    <span className="hint">
                      {" "}
                      — {item.confirmedByName || "—"} • {formatDateTime(item.confirmedAt)}
                    </span>
                  ) : (
                    (selected.status === "draft" || selected.status === "submitted") && (
                      <Button
                        variant="ghost"
                        onClick={() => confirmPrecaution(selected.id, item.id)}
                        disabled={busy}
                      >
                        تأیید اقدام
                      </Button>
                    )
                  )}
                </li>
              ))}
            </ul>

            <h3>نقاط جداسازی (قفل‌گذاری و برچسب‌گذاری)</h3>
            {selected.isolations.length === 0 ? (
              <p className="hint">
                {selected.requiresIsolation
                  ? "برای این نوع مجوز، ثبت حداقل یک نقطه جداسازی الزامی است."
                  : "برای این مجوز نقطه جداسازی ثبت نشده است."}
              </p>
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th>نقطه</th>
                    <th>انرژی</th>
                    <th>اجرای قفل</th>
                    <th>تأیید مستقل</th>
                    <th>برداشتن</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {selected.isolations.map((point) => (
                    <tr key={point.id}>
                      <td>
                        {point.pointCode}
                        <div className="hint">{point.description}</div>
                      </td>
                      <td>{point.energyLabel}</td>
                      <td>{point.appliedByName || "—"}</td>
                      <td>{point.verifiedByName || "—"}</td>
                      <td>{point.removedByName || "—"}</td>
                      <td>
                        <PermissionGuard permission={PERMISSIONS.safetyPermitIsolate} fallback="hide">
                          {!point.isApplied && !point.isRemoved && (
                            <Button
                              variant="ghost"
                              onClick={() => isolationAction(selected.id, point.id, "apply")}
                              disabled={busy}
                            >
                              ثبت اجرا
                            </Button>
                          )}
                          {point.isApplied && !point.isVerified && (
                            <Button
                              variant="ghost"
                              onClick={() => isolationAction(selected.id, point.id, "verify")}
                              disabled={busy}
                            >
                              تأیید جداسازی
                            </Button>
                          )}
                          {point.isApplied && !point.isRemoved && (
                            <Button
                              variant="ghost"
                              onClick={() => isolationAction(selected.id, point.id, "remove")}
                              disabled={busy}
                            >
                              برداشتن قفل
                            </Button>
                          )}
                        </PermissionGuard>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            {(selected.status === "draft" || selected.status === "submitted") && (
              <PermissionGuard permission={PERMISSIONS.safetyPermitIsolate} fallback="hide">
                <div className="form-grid">
                  <label>
                    کد نقطه
                    <input
                      value={isolationForm.pointCode}
                      onChange={(event) =>
                        setIsolationForm({ ...isolationForm, pointCode: event.target.value })
                      }
                    />
                  </label>
                  <label>
                    شرح
                    <input
                      value={isolationForm.description}
                      onChange={(event) =>
                        setIsolationForm({ ...isolationForm, description: event.target.value })
                      }
                    />
                  </label>
                  <label>
                    نوع انرژی
                    <select
                      value={isolationForm.energyType}
                      onChange={(event) =>
                        setIsolationForm({ ...isolationForm, energyType: event.target.value })
                      }
                    >
                      {(payload?.options.energyTypes ?? []).map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    شماره قفل/برچسب
                    <input
                      value={isolationForm.lockTag}
                      onChange={(event) =>
                        setIsolationForm({ ...isolationForm, lockTag: event.target.value })
                      }
                    />
                  </label>
                  <Button
                    onClick={() => addIsolation(selected.id)}
                    disabled={
                      busy ||
                      !isolationForm.pointCode.trim() ||
                      !isolationForm.description.trim()
                    }
                  >
                    افزودن نقطه جداسازی
                  </Button>
                </div>
              </PermissionGuard>
            )}

            {/* On the same screen on purpose: an audit trail behind a
                second click is an audit trail nobody reads. */}
            <h3>سوابق مجوز</h3>
            <ul className="timeline">
              {selected.events.map((event) => (
                <li key={event.id}>
                  <span className="hint">{formatDateTime(event.occurredAt)}</span>{" "}
                  {event.toStatusLabel || event.action}
                  {event.actorName ? ` — ${event.actorName}` : ""}
                  {event.note ? <div className="hint">{event.note}</div> : null}
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>
    </PermissionGuard>
  );
}

export default SafetyPermitsPage;
