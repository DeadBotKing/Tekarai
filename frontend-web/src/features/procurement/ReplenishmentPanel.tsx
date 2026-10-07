import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiClientError } from "../../core/api/apiClient";
import { useApiClient } from "../../core/api/apiContext";
import { PERMISSIONS } from "../../core/permissions/permissionContext";
import { DataTable, type DataTableColumn } from "../../shared/components/DataTable";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  PermissionGuard,
} from "../../shared/components/primitives";

/**
 * The stock→purchase loop, on screen.
 *
 * The warehouse has always been able to say "this part is below its
 * minimum". What it could not say was "…so order 28 of them from این
 * تأمین‌کننده for this much", which is the sentence a buyer actually acts
 * on. This panel shows that sentence for every part at once, with the
 * arithmetic visible — on hand, already on order, net, suggested — so the
 * number is auditable rather than something a robot asserted.
 *
 * Deliberately fixture-free. The demo boundary spec forbids new files from
 * branching on the demo flag, because each such branch is a second
 * implementation that drifts from the real one. This panel therefore has
 * exactly one code path — the API — and under demo fixtures it shows its
 * error state rather than a fabricated shortage list.
 */

export interface ReplenishmentSuggestion {
  partId: string;
  partCode: string;
  partName: string;
  unit: string;
  quantityOnHand: string;
  minimumStock: string;
  onOrderQuantity: string;
  netAvailable: string;
  suggestedQuantity: string;
  estimatedUnitCost: string;
  estimatedTotal: string;
  urgency: string;
  reason: string;
  supplierId: string | null;
  supplierName: string;
  leadTimeDays: number;
}

interface ApplyResult {
  createdRequisitions: string[];
  createdRequisitionIds: string[];
  lineCount: number;
  estimatedTotal: string;
}

const urgencyLabels: Record<string, string> = {
  critical: "بحرانی",
  high: "بالا",
  normal: "عادی",
};

const urgencyTones: Record<string, "danger" | "warning" | "neutral"> = {
  critical: "danger",
  high: "warning",
  normal: "neutral",
};

/** Trim the stored 3-decimal precision down to something readable. */
export const formatQuantity = (raw: string | number): string => {
  const value = Number(raw);
  if (!Number.isFinite(value)) return String(raw);
  return value.toLocaleString("fa-IR", { maximumFractionDigits: 3 });
};

export const formatMoney = (raw: string | number): string => {
  const value = Number(raw);
  if (!Number.isFinite(value)) return "—";
  return Math.round(value).toLocaleString("fa-IR");
};

export function ReplenishmentPanel({
  onApplied,
}: {
  /** Lets the host page refresh its requisition list and dashboard counters. */
  onApplied?: (result: ApplyResult) => void;
}): JSX.Element {
  const api = useApiClient();
  const [rows, setRows] = useState<ReplenishmentSuggestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState("");

  const load = useCallback(() => {
    setLoading(true);
    void api
      .get<ReplenishmentSuggestion[]>("procurement/replenishment")
      .then((data) => {
        setRows(Array.isArray(data) ? data : []);
        setError(null);
      })
      .catch((cause: unknown) =>
        setError(
          cause instanceof ApiClientError && cause.message
            ? cause.message
            : "دریافت پیشنهادهای تأمین ناموفق بود.",
        ),
      )
      .finally(() => setLoading(false));
  }, [api]);

  useEffect(load, [load]);

  const apply = (): void => {
    setApplying(true);
    setNotice("");
    void api
      .post<ApplyResult>("procurement/replenishment", {})
      .then((result) => {
        const count = result.createdRequisitions.length;
        setNotice(
          count === 0
            ? "چیزی برای سفارش نبود."
            : `${count.toLocaleString("fa-IR")} پیش‌نویس درخواست خرید ساخته شد: ${result.createdRequisitions.join("، ")}`,
        );
        onApplied?.(result);
        // Re-read rather than clearing the table: the new drafts now count
        // as stock on order, so the correct next view is whatever is still
        // short — which is normally nothing.
        load();
      })
      .catch((cause: unknown) =>
        setNotice(
          cause instanceof ApiClientError && cause.message
            ? cause.message
            : "ساخت درخواست‌ها ناموفق بود.",
        ),
      )
      .finally(() => setApplying(false));
  };

  const totalEstimated = useMemo(
    () => rows.reduce((sum, row) => sum + (Number(row.estimatedTotal) || 0), 0),
    [rows],
  );

  const columns = useMemo<DataTableColumn<ReplenishmentSuggestion>[]>(
    () => [
      {
        key: "part",
        label: "قطعه",
        accessor: (r) => `${r.partCode} ${r.partName}`,
        render: (r) => (
          <span>
            <strong>{r.partCode}</strong> — {r.partName}
          </span>
        ),
      },
      {
        key: "urgency",
        label: "فوریت",
        accessor: (r) => r.urgency,
        render: (r) => (
          <Badge tone={urgencyTones[r.urgency] ?? "neutral"}>
            {urgencyLabels[r.urgency] ?? r.urgency}
          </Badge>
        ),
      },
      { key: "onHand", label: "موجودی", accessor: (r) => formatQuantity(r.quantityOnHand) },
      { key: "minimum", label: "حداقل", accessor: (r) => formatQuantity(r.minimumStock) },
      {
        key: "onOrder",
        label: "در راه",
        accessor: (r) => formatQuantity(r.onOrderQuantity),
        render: (r) =>
          Number(r.onOrderQuantity) > 0 ? (
            <span>{formatQuantity(r.onOrderQuantity)}</span>
          ) : (
            <span className="muted">—</span>
          ),
      },
      { key: "net", label: "خالص", accessor: (r) => formatQuantity(r.netAvailable) },
      {
        key: "suggested",
        label: "پیشنهاد سفارش",
        accessor: (r) => formatQuantity(r.suggestedQuantity),
        render: (r) => (
          <strong>
            {formatQuantity(r.suggestedQuantity)} {r.unit}
          </strong>
        ),
      },
      {
        key: "supplier",
        label: "تأمین‌کننده",
        accessor: (r) => r.supplierName,
        render: (r) =>
          r.supplierName ? (
            <span>
              {r.supplierName}
              {r.leadTimeDays > 0 ? (
                <small className="muted"> ({r.leadTimeDays.toLocaleString("fa-IR")} روز)</small>
              ) : null}
            </span>
          ) : (
            // Not an error — the part can still be requested, the buyer
            // just has to choose who from.
            <span className="muted">تعیین‌نشده</span>
          ),
      },
      {
        key: "total",
        label: "برآورد مبلغ",
        accessor: (r) => Number(r.estimatedTotal) || 0,
        render: (r) => <>{formatMoney(r.estimatedTotal)}</>,
      },
    ],
    [],
  );

  if (error) return <ErrorState title="خطا" description={error} retry={load} />;

  return (
    <Card padding="none">
      <CardHeader
        title="تأمین انبار"
        subtitle="قطعه‌هایی که با احتساب کالای در راه به حداقل موجودی رسیده‌اند."
        action={
          <PermissionGuard permission={PERMISSIONS.procurementRequisitionCreate}>
            <Button
              size="sm"
              variant="primary"
              disabled={applying || loading || rows.length === 0}
              onClick={apply}
            >
              {applying ? "در حال ساخت…" : "ساخت درخواست‌های خرید"}
            </Button>
          </PermissionGuard>
        }
      />
      {notice ? (
        <p className="replenishment-notice" role="status">
          {notice}
        </p>
      ) : null}
      {!loading && rows.length === 0 ? (
        <EmptyState
          icon="check"
          title="همه‌چیز بالای حداقل است"
          description="هیچ قطعه‌ای با احتساب سفارش‌های باز به نقطه‌ی سفارش نرسیده است."
        />
      ) : (
        <>
          <DataTable
            columns={columns}
            data={rows}
            rowKey={(r) => r.partId}
            pageSize={10}
            loading={loading}
            empty={{ title: loading ? "در حال بارگذاری…" : "موردی نیست" }}
          />
          {rows.length > 0 ? (
            <p className="replenishment-summary">
              {rows.length.toLocaleString("fa-IR")} قلم — برآورد کل{" "}
              <strong>{formatMoney(totalEstimated)}</strong>
            </p>
          ) : null}
        </>
      )}
    </Card>
  );
}
