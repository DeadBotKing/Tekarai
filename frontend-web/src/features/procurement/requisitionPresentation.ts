/**
 * Presentation helpers for purchase documents.
 *
 * Kept out of the page component so the labels and the "how long has this
 * been waiting" wording can be unit-tested without rendering the whole
 * procurement screen.
 */

/** Shape the procurement list endpoint returns for a requisition row. */
export interface RequisitionAgeing {
  status: string;
  isStale?: boolean;
  daysWaiting?: number;
  staleThresholdDays?: number;
  submittedAt?: string | null;
}

/**
 * Persian labels for the requisition and purchase-order vocabularies.
 *
 * The tables used to print the raw English enum value into an otherwise
 * Persian page, so a buyer saw "partiallyReceived" in the status column.
 */
export const statusLabels: Record<string, string> = {
  draft: "پیش‌نویس",
  submitted: "ارسال‌شده",
  approved: "تأییدشده",
  rejected: "ردشده",
  cancelled: "لغوشده",
  ordered: "سفارش داده شد",
  purchased: "خریدشده",
  partiallyReceived: "تحویل جزئی",
  received: "تحویل‌شده",
  posted: "ثبت‌شده",
  paid: "پرداخت‌شده",
  disputed: "مورد اختلاف",
};

/** Label for a status, falling back to the raw value rather than blank. */
export function statusLabel(status: string): string {
  return statusLabels[status] ?? status;
}

/**
 * How long a request has been waiting, in words.
 *
 * A requisition that was never submitted has no clock running — saying
 * "0 روز" there would imply it is being worked on, when in fact nobody has
 * been asked to buy anything yet.
 */
export function waitingLabel(row: RequisitionAgeing): string {
  if (!row.submittedAt) return "ارسال نشده";
  const days = row.daysWaiting ?? 0;
  return row.isStale ? `${days} روز معطل` : `${days} روز`;
}

/** Tone for a document status badge. */
export function statusTone(status: string): "success" | "danger" | "warning" {
  if (status === "approved" || status === "received" || status === "purchased") return "success";
  if (status === "rejected" || status === "cancelled") return "danger";
  return "warning";
}
