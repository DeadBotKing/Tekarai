import { useEffect, useMemo, useState } from "react";
import { runtimeConfig } from "../app/configuration/runtimeConfig";
import { ApiClientError } from "../core/api/apiClient";
import { useApiClient } from "../core/api/apiContext";
import { PERMISSIONS } from "../core/permissions/permissionContext";
import { formatJalali } from "../core/localization/jalali";
import { statusLabel, statusTone, waitingLabel } from "../features/procurement/requisitionPresentation";
import { JalaliDatePicker } from "../shared/components/JalaliDatePicker";
import { DataTable, type DataTableColumn } from "../shared/components/DataTable";
import { Modal, Toast } from "../shared/components/overlays";
import { Badge, Button, Card, CardHeader, PermissionGuard, SectionHeader, SelectInput, TextInput, TextArea } from "../shared/components/primitives";

type Supplier = { id: string; code: string; name: string; status: string; contactName: string; phone: string; defaultLeadTimeDays: number; currency: string };
type Line = { id?: string; partId: string; partCode: string; partName: string; unit: string; quantity: number | string; note?: string; estimatedUnitCost?: number | string; unitPrice?: number | string; orderedQuantity?: number | string; receivedQuantity?: number | string };
type DocumentRow = { id: string; number?: string; status: string; total?: string | number; createdAt?: string; supplierId?: string; requisitionId?: string; totalEstimated?: string | number; lines?: Line[]; isStale?: boolean; daysWaiting?: number; staleThresholdDays?: number; priority?: string; submittedAt?: string | null; purchasedAt?: string | null };
const demoSuppliers: Supplier[] = [{ id: "sup-demo", code: "SUP-001", name: "تأمین‌کننده نمونه", status: "active", contactName: "واحد فروش", phone: "", defaultLeadTimeDays: 7, currency: "IRR" }];
/**
 * The amount of a procurement document.
 *
 * Purchase orders and supplier invoices store `total`; a requisition stores
 * `totalEstimated`, because its price is a forecast until a supplier quotes
 * it. The shared table column only ever read `total`, so the مبلغ column was
 * blank on every single purchase request.
 */
const documentAmount = (row: DocumentRow): number | undefined => {
  const raw = row.total ?? row.totalEstimated;
  if (raw === undefined || raw === null || raw === "") return undefined;
  const value = Number(raw);
  return Number.isFinite(value) ? value : undefined;
};

const tabs = ["overview", "suppliers", "requisitions", "purchased", "orders", "receipts", "returns", "invoices"] as const;
/**
 * Eight equal tabs put a receipt-correction screen at the same weight as the
 * daily job of raising a request and checking what has been bought. The
 * first row is what the page is used for every day; the rest stay one click
 * away behind «بیشتر» instead of competing for attention.
 */
/**
 * Last entry of the part dropdown. Picking it opens the manual fields in
 * place rather than selecting a part, so a part that is not in the
 * warehouse yet can be typed without leaving the request.
 */
const ADD_PART_OPTION = "__addPart__";

const primaryTabs = ["overview", "requisitions", "purchased"] as const;
const secondaryTabs = ["orders", "receipts", "invoices", "returns", "suppliers"] as const;
const tabLabels: Record<Tab, string> = { overview: "نمای کلی", suppliers: "تأمین‌کنندگان", requisitions: "درخواست‌ها", purchased: "خریدشده", orders: "سفارش خرید", receipts: "رسید انبار", returns: "برگشت کالا", invoices: "فاکتورها" };
type Tab = typeof tabs[number];

export function ProcurementPage(): JSX.Element {
  const api = useApiClient(); const [tab, setTab] = useState<Tab>("overview");
  const [suppliers, setSuppliers] = useState<Supplier[]>(runtimeConfig.demoMode ? demoSuppliers : []);
  const [rows, setRows] = useState<DocumentRow[]>([]); const [loading, setLoading] = useState(!runtimeConfig.demoMode); const [toast, setToast] = useState("");
  const [supplierOpen, setSupplierOpen] = useState(false); const [supplierForm, setSupplierForm] = useState({ code: "", name: "", contactName: "", phone: "", defaultLeadTimeDays: "7", paymentTerms: "", currency: "IRR" });
  // Defining a part from inside the requisition used to open a second modal
  // on top of the first. The requisition path now expands the fields in
  // place; the standalone modal stays for the returns form.
  const [partInline, setPartInline] = useState(false);
  const [partOpen, setPartOpen] = useState(false); const [partForm, setPartForm] = useState({ code: "", name: "", unit: "عدد", quantityOnHand: "0", minimumStock: "0", unitCost: "0" });
  // A requisition carries many lines: the API has always accepted
  // `lines: [...]` and totalled across them, but the form could only ever
  // build one, so ordering three parts meant raising three requests.
  // `reqForm` is the row being composed; `reqLines` is what will be sent.
  const [reqOpen, setReqOpen] = useState(false); const [reqForm, setReqForm] = useState({ partId: "", partCode: "", partName: "", unit: "عدد", quantity: "1", estimatedUnitCost: "0", note: "", priority: "normal", justification: "" });
  const [reqLines, setReqLines] = useState<Line[]>([]);
  const [poOpen, setPoOpen] = useState(false); const [poForm, setPoForm] = useState({ supplierId: "", requisitionId: "", expectedDate: "", unitPrice: "0", taxAmount: "0" });
  const [receiptOpen, setReceiptOpen] = useState(false); const [receiptForm, setReceiptForm] = useState({ purchaseOrderId: "", purchaseOrderLineId: "", quantity: "1", rejectedQuantity: "0", unitCost: "0" });
  const [returnOpen, setReturnOpen] = useState(false); const [returnForm, setReturnForm] = useState({ supplierId: "", purchaseOrderId: "", partId: "", quantity: "1", unitCost: "0", reason: "" });
  const [invoiceOpen, setInvoiceOpen] = useState(false); const [invoiceForm, setInvoiceForm] = useState({ invoiceNumber: "", supplierId: "", purchaseOrderId: "", subtotal: "0", taxAmount: "0", total: "0", dueDate: "" });
  const [dashboard, setDashboard] = useState<Record<string, string | number>>({});
  const [moreOpen, setMoreOpen] = useState(false);
  // Surfaced on the tab itself: a stalled request is the thing the page
  // exists to catch, and it was previously only visible after clicking in.
  // Read from the dashboard so it is right whichever tab is open — the
  // row-level `staleCount` below only sees the rows currently loaded.
  const staleBadge = Number(dashboard.staleRequisitions ?? 0);
  const [historyOpen, setHistoryOpen] = useState(false); const [historyRows, setHistoryRows] = useState<Array<Record<string, unknown>>>([]); const [historyTitle, setHistoryTitle] = useState("");
  const [parts, setParts] = useState<Array<{ id: string; code: string; name: string; unit: string; unitCost: number }>>([]);
  const endpointFor = (target: Tab): string => target === "requisitions" ? "procurement/requisitions" : target === "purchased" ? "procurement/requisitions?status=purchased" : target === "orders" ? "procurement/purchase-orders" : target === "receipts" ? "procurement/receipts" : target === "returns" ? "procurement/returns" : "procurement/invoices";
  const refreshDashboard = (): void => { if (!runtimeConfig.demoMode) void api.get<Record<string, string | number>>("procurement/dashboard").then(setDashboard).catch(() => undefined); };
  const load = (target: Tab = tab): void => { if (runtimeConfig.demoMode || target === "overview") return; setLoading(true); void api.get<DocumentRow[]>(target === "suppliers" ? "procurement/suppliers" : endpointFor(target)).then((data) => target === "suppliers" ? setSuppliers(data as unknown as Supplier[]) : setRows(data)).catch(() => setToast("دریافت اطلاعات ناموفق بود.")).finally(() => setLoading(false)); };
  useEffect(() => { if (runtimeConfig.demoMode) { setParts([{ id: "sp-demo", code: "DEMO-001", name: "قطعه نمونه", unit: "عدد", unitCost: 100000 }]); return; } refreshDashboard(); void api.get<Array<{ id: string; code: string; name: string; unit: string; unitCost: number }>>("maintenance/spare-parts").then(setParts).catch(() => undefined); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api]);
  useEffect(() => { if (tab === "overview") refreshDashboard(); else load(tab); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);
  const openHistory = (documentType: "requisition" | "purchaseOrder", id: string, title: string): void => { setHistoryTitle(title); if (runtimeConfig.demoMode) { setHistoryRows([]); setHistoryOpen(true); return; } void api.get<Array<Record<string, unknown>>>(`procurement/approval-history/${documentType}/${id}`).then(setHistoryRows).catch(() => setHistoryRows([])).finally(() => setHistoryOpen(true)); };
  const action = (id: string, verb: string, nextTab: Tab): void => { if (runtimeConfig.demoMode) { setRows((current) => current.map((x) => x.id === id ? { ...x, status: verb === "submit" ? "submitted" : verb === "approve" ? "approved" : verb === "reject" ? "rejected" : x.status } : x)); setToast("عملیات انجام شد."); return; } void api.post(`procurement/${nextTab === "requisitions" ? "requisitions" : "purchase-orders"}/${id}/${verb}`, {}).then(() => { setToast("عملیات با موفقیت انجام شد."); load(nextTab); refreshDashboard(); }).catch(() => setToast("عملیات انجام نشد.")); };
  const saveSupplier = (): void => { const payload = { ...supplierForm, defaultLeadTimeDays: Number(supplierForm.defaultLeadTimeDays) }; if (runtimeConfig.demoMode) { setSuppliers((x) => [...x, { id: `demo-${Date.now()}`, ...payload, status: "active" }]); setSupplierOpen(false); setToast("تأمین‌کننده اضافه شد."); return; } void api.post<Supplier>("procurement/suppliers", payload).then((item) => { setSuppliers((x) => [...x, item]); setSupplierOpen(false); setToast("تأمین‌کننده اضافه شد."); }).catch(() => setToast("ذخیره ناموفق بود.")); };
  const savePart = (): void => {
    if (!partForm.code.trim() || !partForm.name.trim()) { setToast("کد و نام قطعه الزامی است."); return; }
    const payload = { ...partForm, quantityOnHand: Number(partForm.quantityOnHand), minimumStock: Number(partForm.minimumStock), unitCost: Number(partForm.unitCost) };
    if (runtimeConfig.demoMode) { const item = { id: `demo-part-${Date.now()}`, ...payload }; setParts((current) => [...current, item]); setReqForm((current) => ({ ...current, partId: item.id, partCode: item.code, partName: item.name, unit: item.unit, estimatedUnitCost: String(item.unitCost) })); setPartOpen(false); setPartInline(false); setPartForm({ code: "", name: "", unit: "عدد", quantityOnHand: "0", minimumStock: "0", unitCost: "0" }); setToast("قطعه در انبار ثبت و برای این درخواست انتخاب شد."); return; }
    void api.post<{ id: string; code: string; name: string; unit: string; unitCost: number }>("maintenance/spare-parts", payload).then((item) => { setParts((current) => [...current, item]); setReqForm((current) => ({ ...current, partId: item.id, partCode: item.code, partName: item.name, unit: item.unit, estimatedUnitCost: String(item.unitCost) })); setPartOpen(false); setPartInline(false); setPartForm({ code: "", name: "", unit: "عدد", quantityOnHand: "0", minimumStock: "0", unitCost: "0" }); setToast("قطعه در انبار ثبت و برای این درخواست انتخاب شد."); }).catch(() => setToast("ثبت قطعه ناموفق بود."));
  };
  /** Move the composed row into the basket, merging a repeated part. */
  const addRequisitionLine = (): void => {
    if (!reqForm.partId) { setToast("اول قطعه را انتخاب کن."); return; }
    const quantity = Number(reqForm.quantity);
    if (!Number.isFinite(quantity) || quantity <= 0) { setToast("تعداد باید بزرگ‌تر از صفر باشد."); return; }
    const cost = Number(reqForm.estimatedUnitCost) || 0;
    setReqLines((current) => {
      // Two rows for the same part would be accepted by the API but make a
      // confusing document; add the quantities instead.
      const existing = current.findIndex((line) => line.partId === reqForm.partId);
      const note = reqForm.note.trim();
      if (existing >= 0) {
        const merged = [...current];
        const previous = (merged[existing].note ?? "").trim();
        // Keep both notes when the quantities are merged, so no explanation
        // the user typed is silently thrown away.
        const combined = previous && note && previous !== note ? `${previous} — ${note}` : previous || note;
        merged[existing] = { ...merged[existing], quantity: Number(merged[existing].quantity) + quantity, estimatedUnitCost: cost, note: combined };
        return merged;
      }
      return [...current, { partId: reqForm.partId, partCode: reqForm.partCode, partName: reqForm.partName, unit: reqForm.unit, quantity, estimatedUnitCost: cost, note }];
    });
    setReqForm((current) => ({ ...current, partId: "", partCode: "", partName: "", unit: "عدد", quantity: "1", estimatedUnitCost: "0", note: "" }));
  };
  const removeRequisitionLine = (partId: string): void => setReqLines((current) => current.filter((line) => line.partId !== partId));
  const reqLinesTotal = reqLines.reduce((sum, line) => sum + Number(line.quantity) * Number(line.estimatedUnitCost ?? 0), 0);
  const closeRequisition = (): void => { setReqOpen(false); setReqLines([]); setReqForm({ partId: "", partCode: "", partName: "", unit: "عدد", quantity: "1", estimatedUnitCost: "0", note: "", priority: "normal", justification: "" }); };

  const saveRequisition = (): void => {
    // Allow submitting straight from the composer without forcing the user
    // to press "add" first when the request is a single part.
    const pending = reqForm.partId && Number(reqForm.quantity) > 0
      ? [{ partId: reqForm.partId, partCode: reqForm.partCode, partName: reqForm.partName, unit: reqForm.unit, quantity: Number(reqForm.quantity), estimatedUnitCost: Number(reqForm.estimatedUnitCost) || 0, note: reqForm.note.trim() }]
      : [];
    const merged: Line[] = [...reqLines];
    pending.forEach((line) => {
      const existing = merged.findIndex((x) => x.partId === line.partId);
      if (existing >= 0) merged[existing] = { ...merged[existing], quantity: Number(merged[existing].quantity) + Number(line.quantity) };
      else merged.push(line);
    });
    if (merged.length === 0) { setToast("حداقل یک قطعه به درخواست اضافه کن."); return; }
    const lines = merged.map((line) => ({ partId: line.partId, partCode: line.partCode, partName: line.partName, unit: line.unit, quantity: Number(line.quantity), estimatedUnitCost: Number(line.estimatedUnitCost ?? 0), note: (line.note ?? "").trim() }));
    const total = lines.reduce((sum, line) => sum + line.quantity * line.estimatedUnitCost, 0);
    const payload = { priority: reqForm.priority, justification: reqForm.justification, lines };
    if (runtimeConfig.demoMode) {
      const created: DocumentRow = { id: `demo-pr-${Date.now()}`, number: `PR-DEMO-${Date.now().toString().slice(-5)}`, status: "draft", total, createdAt: new Date().toISOString(), priority: reqForm.priority, lines };
      setRows((current) => [created, ...current]);
      setDashboard((current) => ({ ...current, openRequisitions: Number(current.openRequisitions ?? 2) + 1 }));
      closeRequisition(); setTab("requisitions");
      setToast(`درخواست خرید با ${lines.length} قلم ایجاد شد.`);
      return;
    }
    void api.post<DocumentRow>("procurement/requisitions", payload).then((created) => {
      closeRequisition(); setRows((current) => [created, ...current]); setTab("requisitions"); load("requisitions"); refreshDashboard();
      setToast(`درخواست خرید با ${lines.length} قلم ایجاد شد.`);
    }).catch(() => setToast("ذخیره ناموفق بود."));
  };
  const createOrder = (): void => { const req = rows.find((x) => x.id === poForm.requisitionId); const lines = req?.lines ?? []; if (!poForm.supplierId || !req || !lines.length) { setToast("یک درخواست تأییدشده و تأمین‌کننده انتخاب کن."); return; } const payload = { supplierId: poForm.supplierId, requisitionId: req.id, expectedDate: poForm.expectedDate || null, taxAmount: Number(poForm.taxAmount), lines: lines.map((line) => ({ partId: line.partId, partCode: line.partCode, partName: line.partName, unit: line.unit, quantity: Number(line.quantity), unitPrice: Number(poForm.unitPrice) })) }; void api.post("procurement/purchase-orders", payload).then(() => { setPoOpen(false); setToast("سفارش خرید ایجاد شد."); setTab("orders"); }).catch(() => setToast("ایجاد سفارش خرید ناموفق بود.")); };
  const postReceipt = (): void => { if (!receiptForm.purchaseOrderId || !receiptForm.purchaseOrderLineId) { setToast("سفارش و قلم سفارش را انتخاب کن."); return; } void api.post("procurement/receipts", { purchaseOrderId: receiptForm.purchaseOrderId, receiverName: "", lines: [{ purchaseOrderLineId: receiptForm.purchaseOrderLineId, quantity: Number(receiptForm.quantity), rejectedQuantity: Number(receiptForm.rejectedQuantity), unitCost: Number(receiptForm.unitCost) }] }).then(() => { setReceiptOpen(false); setToast("رسید انبار ثبت شد و موجودی به‌روزرسانی شد."); setTab("receipts"); }).catch((error: unknown) => setToast(refusalReason(error, "ثبت رسید ناموفق بود."))); };
  const postReturn = (): void => { if (!returnForm.supplierId || !returnForm.partId) { setToast("تأمین‌کننده و قطعه را انتخاب کن."); return; } void api.post("procurement/returns", { ...returnForm, purchaseOrderId: returnForm.purchaseOrderId || null, quantity: Number(returnForm.quantity), unitCost: Number(returnForm.unitCost), lines: [{ partId: returnForm.partId, quantity: Number(returnForm.quantity), unitCost: Number(returnForm.unitCost) }] }).then(() => { setReturnOpen(false); setToast("برگشت کالا ثبت شد و موجودی کم شد."); setTab("returns"); }).catch(() => setToast("ثبت برگشت ناموفق بود.")); };
  const postInvoice = (): void => { if (!invoiceForm.invoiceNumber || !invoiceForm.supplierId) { setToast("شماره فاکتور و تأمین‌کننده الزامی است."); return; } void api.post("procurement/invoices", { ...invoiceForm, subtotal: Number(invoiceForm.subtotal), taxAmount: Number(invoiceForm.taxAmount), total: Number(invoiceForm.total), purchaseOrderId: invoiceForm.purchaseOrderId || null, invoiceDate: null, dueDate: invoiceForm.dueDate || null }).then(() => { setInvoiceOpen(false); setToast("فاکتور ثبت شد."); setTab("invoices"); }).catch(() => setToast("ثبت فاکتور ناموفق بود.")); };
  // The server explains *why* a delivery was refused — too many pieces, more
  // rejected than delivered, a cancelled order. Swallowing that and showing
  // "failed" would leave the storekeeper with nothing to act on.
  const refusalReason = (error: unknown, fallback: string): string =>
    error instanceof ApiClientError && error.message ? error.message : fallback;

  const docColumns = useMemo<DataTableColumn<DocumentRow>[]>(() => {
    const base: DataTableColumn<DocumentRow>[] = [{ key: "number", label: "شماره", accessor: (r) => r.number ?? r.id }, { key: "status", label: "وضعیت", accessor: (r) => r.status, render: (r) => <Badge tone={statusTone(r.status)}>{statusLabel(r.status)}</Badge> }, { key: "total", label: "مبلغ", accessor: (r) => documentAmount(r) ?? "—", render: (r) => { const amount = documentAmount(r); return <>{amount === undefined ? "—" : amount.toLocaleString("fa-IR")}</>; } }];
    // Without this the per-line note is write-only: typed once, never read.
    if (tab === "requisitions" || tab === "purchased") base.splice(2, 0, { key: "items", label: "اقلام", accessor: (r) => (r.lines ?? []).map((line) => line.partName).join("، "), render: (r) => { const lines = r.lines ?? []; if (!lines.length) return <span className="muted">—</span>; return <ul className="doc-lines">{lines.map((line, index) => <li key={line.id ?? `${line.partId}-${index}`}><span className="doc-lines__part">{line.partName} × {Number(line.quantity).toLocaleString("fa-IR")} {line.unit}</span>{line.note ? <span className="doc-lines__note">{line.note}</span> : null}</li>)}</ul>; } });
    if (tab === "requisitions") base.push({ key: "waiting", label: "انتظار", accessor: (r) => r.daysWaiting ?? 0, render: (r) => r.isStale ? <Badge tone="danger">{waitingLabel(r)}</Badge> : <span>{waitingLabel(r)}</span> });
    if (tab === "purchased") base.push({ key: "purchasedAt", label: "تاریخ خرید", accessor: (r) => r.purchasedAt ? formatJalali(r.purchasedAt, { withTime: true }) : "—" });
    base.push({ key: "createdAt", label: "تاریخ ساخت", accessor: (r) => r.createdAt ? formatJalali(r.createdAt, { withTime: true }) : "—" });
    return base;
  }, [tab]);
  const reqRows = rows.filter((x) => tab !== "requisitions" || x.status !== "rejected");
  const staleCount = rows.filter((x) => x.isStale).length; const chosenPo = rows.find((x) => x.id === receiptForm.purchaseOrderId); const chosenReq = rows.find((x) => x.id === poForm.requisitionId);
  return <div className="page procurement-page"><SectionHeader eyebrow="CMMS" title="تدارکات و خرید" subtitle="چرخه‌ی تأمین قطعه از تأمین‌کننده تا رسید انبار و فاکتور." actions={<><PermissionGuard permission={PERMISSIONS.procurementSupplierManage}><Button variant="secondary" onClick={() => setSupplierOpen(true)}>افزودن تأمین‌کننده</Button></PermissionGuard><PermissionGuard permission={PERMISSIONS.procurementRequisitionCreate}><Button variant="primary" onClick={() => setReqOpen(true)}>درخواست خرید جدید</Button></PermissionGuard></>} />
    <div className="procurement-tabs">
      <div className="segmented-control" role="tablist">{primaryTabs.map((item) => <button type="button" role="tab" aria-selected={tab === item} className={tab === item ? "is-active" : ""} onClick={() => setTab(item)} key={item}>{tabLabels[item]}{item === "requisitions" && staleBadge > 0 ? <span className="procurement-tabs__badge" title="درخواست معطل‌مانده">{staleBadge.toLocaleString("fa-IR")}</span> : null}</button>)}</div>
      <div className="procurement-tabs__more">
        <button type="button" className={moreOpen || (secondaryTabs as readonly Tab[]).includes(tab) ? "procurement-tabs__moreButton is-active" : "procurement-tabs__moreButton"} aria-expanded={moreOpen} aria-haspopup="true" onClick={() => setMoreOpen((v) => !v)}>{(secondaryTabs as readonly Tab[]).includes(tab) ? tabLabels[tab] : "بیشتر"} ▾</button>
        {moreOpen && <div className="procurement-tabs__menu" role="menu">{secondaryTabs.map((item) => <button type="button" role="menuitem" key={item} className={tab === item ? "is-active" : ""} onClick={() => { setTab(item); setMoreOpen(false); }}>{tabLabels[item]}</button>)}</div>}
      </div>
    </div>
    {tab === "overview" ? <div className="stats-grid"><Card padding="md"><strong>{runtimeConfig.demoMode ? 1 : dashboard.suppliers ?? 0}</strong><span>تأمین‌کننده فعال</span></Card><Card padding="md"><strong>{runtimeConfig.demoMode ? dashboard.openRequisitions ?? 2 : dashboard.openRequisitions ?? 0}</strong><span>درخواست باز</span></Card><Card padding="md" className={Number(dashboard.staleRequisitions ?? 0) > 0 ? "stat-alert" : undefined}><strong>{runtimeConfig.demoMode ? 1 : dashboard.staleRequisitions ?? 0}</strong><span>درخواست معطل</span></Card><Card padding="md"><strong>{runtimeConfig.demoMode ? 0 : dashboard.purchasedRequisitions ?? 0}</strong><span>خریدشده</span></Card><Card padding="md"><strong>{runtimeConfig.demoMode ? 1 : dashboard.openPurchaseOrders ?? 0}</strong><span>سفارش باز</span></Card><Card padding="md"><strong>{runtimeConfig.demoMode ? 0 : dashboard.pendingReceipts ?? 0}</strong><span>رسید در انتظار</span></Card></div> : tab === "suppliers" ? <Card padding="none"><CardHeader title="فهرست تأمین‌کنندگان" action={<PermissionGuard permission={PERMISSIONS.procurementSupplierManage}><Button size="sm" variant="secondary" onClick={() => setSupplierOpen(true)}>افزودن</Button></PermissionGuard>} /><DataTable columns={[{ key: "code", label: "کد", accessor: (r: Supplier) => r.code }, { key: "name", label: "نام", accessor: (r: Supplier) => r.name }, { key: "contact", label: "تماس", accessor: (r: Supplier) => `${r.contactName} ${r.phone}` }, { key: "lead", label: "Lead time", accessor: (r: Supplier) => `${r.defaultLeadTimeDays} روز` }, { key: "status", label: "وضعیت", accessor: (r: Supplier) => r.status }]} data={suppliers} rowKey={(r) => r.id} empty={{ title: loading ? "در حال بارگذاری…" : "تأمین‌کننده‌ای ثبت نشده است" }} /></Card> : <Card padding="none"><CardHeader title={({ requisitions: "درخواست‌های خرید", purchased: "درخواست‌های خریدشده", orders: "سفارش‌های خرید", receipts: "رسیدهای انبار", returns: "برگشت کالا", invoices: "فاکتورهای تأمین‌کننده" } as Record<string, string>)[tab]} action={<>{tab === "requisitions" && <PermissionGuard permission={PERMISSIONS.procurementPurchaseOrderCreate}><Button size="sm" variant="secondary" onClick={() => setPoOpen(true)}>ساخت سفارش خرید</Button></PermissionGuard>}{tab === "orders" && <PermissionGuard permission={PERMISSIONS.procurementReceiptPost}><Button size="sm" variant="secondary" onClick={() => setReceiptOpen(true)}>ثبت رسید انبار</Button></PermissionGuard>}{tab === "receipts" && <PermissionGuard permission={PERMISSIONS.procurementReturnPost}><Button size="sm" variant="secondary" onClick={() => setReturnOpen(true)}>ثبت برگشت کالا</Button></PermissionGuard>}{tab === "orders" && <PermissionGuard permission={PERMISSIONS.procurementInvoiceManage}><Button size="sm" variant="secondary" onClick={() => setInvoiceOpen(true)}>ثبت فاکتور</Button></PermissionGuard>}</>} /><DataTable columns={docColumns} data={reqRows} rowKey={(r) => r.id} empty={{ title: loading ? "در حال بارگذاری…" : "موردی ثبت نشده است" }} /></Card>}
    {tab === "requisitions" && staleCount > 0 && <Card padding="md" className="stat-alert"><strong>{staleCount} درخواست خرید از مهلت اولویت خود گذشته و هنوز خریداری نشده است.</strong></Card>}
    {tab === "requisitions" && <div className="procurement-action-list">{rows.map((item) => <div key={item.id} className="procurement-action-row"><span>{item.number ?? item.id}</span><Badge tone={statusTone(item.status)}>{statusLabel(item.status)}</Badge>{item.isStale && <Badge tone="danger">{waitingLabel(item)}</Badge>}<Button size="sm" variant="ghost" onClick={() => openHistory("requisition", item.id, item.number ?? item.id)}>تاریخچه</Button><PermissionGuard permission={PERMISSIONS.procurementRequisitionCreate}>{item.status === "draft" && <Button size="sm" variant="ghost" onClick={() => action(item.id, "submit", "requisitions")}>ارسال برای بررسی</Button>}</PermissionGuard><PermissionGuard permission={PERMISSIONS.procurementRequisitionApprove}>{item.status === "submitted" && <><Button size="sm" variant="ghost" onClick={() => action(item.id, "approve", "requisitions")}>تأیید</Button><Button size="sm" variant="ghost" onClick={() => action(item.id, "reject", "requisitions")}>رد</Button></>}</PermissionGuard></div>)}</div>}
    {tab === "orders" && <div className="procurement-action-list">{rows.map((item) => <div key={item.id} className="procurement-action-row"><span>{item.number ?? item.id}</span><Badge tone={statusTone(item.status)}>{statusLabel(item.status)}</Badge><Button size="sm" variant="ghost" onClick={() => openHistory("purchaseOrder", item.id, item.number ?? item.id)}>تاریخچه</Button><PermissionGuard permission={PERMISSIONS.procurementPurchaseOrderApprove}>{item.status === "draft" && <Button size="sm" variant="ghost" onClick={() => action(item.id, "submit", "orders")}>ارسال سفارش</Button>}{item.status === "submitted" && <><Button size="sm" variant="ghost" onClick={() => action(item.id, "approve", "orders")}>تأیید سفارش</Button><Button size="sm" variant="ghost" onClick={() => action(item.id, "cancel", "orders")}>لغو سفارش</Button></>}</PermissionGuard></div>)}</div>}
    <Modal open={partOpen} title="افزودن قطعه به انبار" onClose={() => setPartOpen(false)} footer={<><Button variant="secondary" onClick={() => setPartOpen(false)}>انصراف</Button><Button variant="primary" onClick={savePart}>ثبت قطعه</Button></>}><div className="form-grid"><TextInput label="کد قطعه" required value={partForm.code} onChange={(e) => setPartForm({ ...partForm, code: e.target.value })} /><TextInput label="نام قطعه" required value={partForm.name} onChange={(e) => setPartForm({ ...partForm, name: e.target.value })} /><TextInput label="واحد" value={partForm.unit} onChange={(e) => setPartForm({ ...partForm, unit: e.target.value })} /><TextInput label="موجودی اولیه" type="number" value={partForm.quantityOnHand} onChange={(e) => setPartForm({ ...partForm, quantityOnHand: e.target.value })} /><TextInput label="حداقل موجودی" type="number" value={partForm.minimumStock} onChange={(e) => setPartForm({ ...partForm, minimumStock: e.target.value })} /><TextInput label="قیمت واحد" type="number" value={partForm.unitCost} onChange={(e) => setPartForm({ ...partForm, unitCost: e.target.value })} /></div></Modal>
    <Modal open={supplierOpen} title="افزودن تأمین‌کننده" onClose={() => setSupplierOpen(false)} footer={<><Button variant="secondary" onClick={() => setSupplierOpen(false)}>انصراف</Button><Button variant="primary" onClick={saveSupplier}>ذخیره</Button></>}><div className="form-grid"><TextInput label="کد تأمین‌کننده" required value={supplierForm.code} onChange={(e) => setSupplierForm({ ...supplierForm, code: e.target.value })} /><TextInput label="نام تأمین‌کننده" required value={supplierForm.name} onChange={(e) => setSupplierForm({ ...supplierForm, name: e.target.value })} /><TextInput label="نام تماس" value={supplierForm.contactName} onChange={(e) => setSupplierForm({ ...supplierForm, contactName: e.target.value })} /><TextInput label="تلفن" value={supplierForm.phone} onChange={(e) => setSupplierForm({ ...supplierForm, phone: e.target.value })} /><TextInput label="Lead time روز" type="number" value={supplierForm.defaultLeadTimeDays} onChange={(e) => setSupplierForm({ ...supplierForm, defaultLeadTimeDays: e.target.value })} /><SelectInput label="ارز" value={supplierForm.currency} onChange={(e) => setSupplierForm({ ...supplierForm, currency: e.target.value })} options={[{ value: "IRR", label: "ریال" }, { value: "USD", label: "دلار" }, { value: "EUR", label: "یورو" }]} /><TextInput label="شرایط پرداخت" value={supplierForm.paymentTerms} onChange={(e) => setSupplierForm({ ...supplierForm, paymentTerms: e.target.value })} /></div></Modal>
    <Modal wide open={reqOpen} title="درخواست خرید جدید" description="می‌توانی چند قطعه را در همین یک درخواست ثبت کنی." onClose={closeRequisition} footer={<><span className="req-footer__summary">{reqLines.length > 0 ? `${reqLines.length.toLocaleString("fa-IR")} قلم — جمع ${reqLinesTotal.toLocaleString("fa-IR")}` : "هنوز قلمی اضافه نشده"}</span><Button variant="secondary" onClick={closeRequisition}>انصراف</Button><Button variant="primary" onClick={saveRequisition}>ثبت درخواست</Button></>}>
      <div className="req-step">
        <h3 className="req-step__title"><span className="req-step__num">۱</span> قطعه‌ها را اضافه کن</h3>
        <div className="form-grid">
          <SelectInput label="قطعه انبار" value={reqForm.partId} onChange={(e) => { if (e.target.value === ADD_PART_OPTION) { setPartInline(true); return; } const part = parts.find((item) => item.id === e.target.value); setReqForm({ ...reqForm, partId: e.target.value, partCode: part?.code ?? "", partName: part?.name ?? "", unit: part?.unit ?? "عدد", estimatedUnitCost: String(part?.unitCost ?? 0) }); }} options={[{ value: "", label: parts.length ? "انتخاب قطعه…" : "قطعه‌ای در انبار ثبت نشده" }, ...parts.map((part) => ({ value: part.id, label: `${part.code} — ${part.name}` })), { value: ADD_PART_OPTION, label: "➕ افزودن قطعه جدید…" }]} />
          <TextInput label="تعداد" type="number" value={reqForm.quantity} onChange={(e) => setReqForm({ ...reqForm, quantity: e.target.value })} />
          <TextInput label="برآورد قیمت واحد" type="number" value={reqForm.estimatedUnitCost} onChange={(e) => setReqForm({ ...reqForm, estimatedUnitCost: e.target.value })} />
          <TextInput className="form-grid__full" label="توضیحات این قطعه" placeholder="مثلاً: برای پمپ خط ۳ — جنس استیل" value={reqForm.note} onChange={(e) => setReqForm({ ...reqForm, note: e.target.value })} />
          <div className="form-grid__full req-lines__add"><Button type="button" variant="secondary" onClick={addRequisitionLine}>➕ افزودن به درخواست</Button></div>
        </div>
        {partInline && <div className="req-inline-part">
          <div className="req-inline-part__head"><strong>قطعه جدید — دستی وارد کن</strong><button type="button" className="req-step__link" onClick={() => setPartInline(false)}>بستن این بخش</button></div>
          <p className="req-inline-part__note">قطعه در انبار ثبت می‌شود و بلافاصله برای همین درخواست انتخاب می‌گردد.</p>
          <div className="form-grid">
            <TextInput label="کد قطعه" required value={partForm.code} onChange={(e) => setPartForm({ ...partForm, code: e.target.value })} />
            <TextInput label="نام قطعه" required value={partForm.name} onChange={(e) => setPartForm({ ...partForm, name: e.target.value })} />
            <TextInput label="واحد" value={partForm.unit} onChange={(e) => setPartForm({ ...partForm, unit: e.target.value })} />
            <TextInput label="قیمت واحد" type="number" value={partForm.unitCost} onChange={(e) => setPartForm({ ...partForm, unitCost: e.target.value })} />
          </div>
          <Button type="button" size="sm" variant="secondary" onClick={savePart}>ثبت قطعه و انتخاب آن</Button>
        </div>}
      </div>
      {reqLines.length > 0 && <div className="req-step">
        <h3 className="req-step__title"><span className="req-step__num">۲</span> قلم‌های این درخواست</h3>
        <table className="req-lines"><thead><tr><th>قطعه</th><th>توضیحات</th><th>تعداد</th><th>قیمت واحد</th><th>جمع</th><th aria-label="حذف" /></tr></thead>
          <tbody>{reqLines.map((line) => <tr key={line.partId}><td>{line.partCode} — {line.partName}</td><td className="req-lines__note">{line.note ? line.note : "—"}</td><td>{Number(line.quantity).toLocaleString("fa-IR")} {line.unit}</td><td>{Number(line.estimatedUnitCost ?? 0).toLocaleString("fa-IR")}</td><td>{(Number(line.quantity) * Number(line.estimatedUnitCost ?? 0)).toLocaleString("fa-IR")}</td><td><Button type="button" size="sm" variant="ghost" onClick={() => removeRequisitionLine(line.partId)} aria-label={`حذف ${line.partName}`}>حذف</Button></td></tr>)}</tbody>
          <tfoot><tr><td colSpan={4}>جمع کل ({reqLines.length.toLocaleString("fa-IR")} قلم)</td><td colSpan={2}>{reqLinesTotal.toLocaleString("fa-IR")}</td></tr></tfoot>
        </table>
      </div>}
      <div className="req-step">
        <h3 className="req-step__title"><span className="req-step__num">۳</span> جزئیات درخواست</h3>
        <div className="form-grid">
          <SelectInput label="اولویت" value={reqForm.priority} onChange={(e) => setReqForm({ ...reqForm, priority: e.target.value })} options={[{ value: "low", label: "کم — هشدار پس از ۱۴ روز" }, { value: "normal", label: "عادی — هشدار پس از ۷ روز" }, { value: "high", label: "بالا — هشدار پس از ۴ روز" }, { value: "critical", label: "بحرانی — هشدار پس از ۲ روز" }]} />
          <TextArea label="دلیل درخواست" value={reqForm.justification} onChange={(e) => setReqForm({ ...reqForm, justification: e.target.value })} />
        </div>
      </div>
    </Modal>
    <Modal open={poOpen} title="ساخت سفارش خرید" onClose={() => setPoOpen(false)} footer={<><Button variant="secondary" onClick={() => setPoOpen(false)}>انصراف</Button><Button variant="primary" onClick={createOrder}>ثبت سفارش خرید</Button></>}><div className="form-grid"><SelectInput label="درخواست تأییدشده" value={poForm.requisitionId} onChange={(e) => setPoForm({ ...poForm, requisitionId: e.target.value })} options={[{ value: "", label: "انتخاب درخواست…" }, ...rows.filter((x) => x.status === "approved").map((x) => ({ value: x.id, label: x.number ?? x.id }))]} /><div className="select-with-action"><SelectInput label="تأمین‌کننده" value={poForm.supplierId} onChange={(e) => setPoForm({ ...poForm, supplierId: e.target.value })} options={[{ value: "", label: suppliers.length ? "انتخاب تأمین‌کننده…" : "تأمین‌کننده‌ای ثبت نشده" }, ...suppliers.map((x) => ({ value: x.id, label: `${x.code} — ${x.name}` }))]} /><Button type="button" size="sm" variant="ghost" onClick={() => setSupplierOpen(true)}>افزودن تأمین‌کننده</Button></div><TextInput label="قیمت واحد" type="number" value={poForm.unitPrice} onChange={(e) => setPoForm({ ...poForm, unitPrice: e.target.value })} /><JalaliDatePicker label="تاریخ مورد انتظار تحویل" value={poForm.expectedDate} onChange={(value) => setPoForm({ ...poForm, expectedDate: value })} /><TextInput label="مالیات" type="number" value={poForm.taxAmount} onChange={(e) => setPoForm({ ...poForm, taxAmount: e.target.value })} />{chosenReq?.lines?.[0] && <p>قطعه: {chosenReq.lines[0].partName} — تعداد: {chosenReq.lines[0].quantity}</p>}</div></Modal>
    <Modal open={receiptOpen} title="ثبت رسید انبار" onClose={() => setReceiptOpen(false)} footer={<><Button variant="secondary" onClick={() => setReceiptOpen(false)}>انصراف</Button><Button variant="primary" onClick={postReceipt}>ثبت رسید</Button></>}><div className="form-grid"><SelectInput label="سفارش خرید" value={receiptForm.purchaseOrderId} onChange={(e) => { const po = rows.find((x) => x.id === e.target.value); setReceiptForm({ ...receiptForm, purchaseOrderId: e.target.value, purchaseOrderLineId: po?.lines?.[0]?.id ?? "", unitCost: String(po?.lines?.[0]?.unitPrice ?? 0) }); }} options={[{ value: "", label: "انتخاب سفارش…" }, ...rows.filter((x) => x.status === "approved" || x.status === "partiallyReceived").map((x) => ({ value: x.id, label: x.number ?? x.id }))]} />{chosenPo?.lines?.[0] && <p>قطعه: {chosenPo.lines[0].partName}</p>}<TextInput label="مقدار دریافتی" type="number" value={receiptForm.quantity} onChange={(e) => setReceiptForm({ ...receiptForm, quantity: e.target.value })} /><TextInput label="مقدار مردودی" type="number" value={receiptForm.rejectedQuantity} onChange={(e) => setReceiptForm({ ...receiptForm, rejectedQuantity: e.target.value })} /></div></Modal>
    <Modal open={returnOpen} title="ثبت برگشت کالا" onClose={() => setReturnOpen(false)} footer={<><Button variant="secondary" onClick={() => setReturnOpen(false)}>انصراف</Button><Button variant="primary" onClick={postReturn}>ثبت برگشت</Button></>}><div className="form-grid"><div className="select-with-action"><SelectInput label="تأمین‌کننده" value={returnForm.supplierId} onChange={(e) => setReturnForm({ ...returnForm, supplierId: e.target.value })} options={[{ value: "", label: suppliers.length ? "انتخاب تأمین‌کننده…" : "تأمین‌کننده‌ای ثبت نشده" }, ...suppliers.map((x) => ({ value: x.id, label: x.name }))]} /><Button type="button" size="sm" variant="ghost" onClick={() => setSupplierOpen(true)}>افزودن تأمین‌کننده</Button></div><div className="select-with-action"><SelectInput label="قطعه" value={returnForm.partId} onChange={(e) => setReturnForm({ ...returnForm, partId: e.target.value })} options={[{ value: "", label: parts.length ? "انتخاب قطعه…" : "قطعه‌ای ثبت نشده" }, ...parts.map((x) => ({ value: x.id, label: `${x.code} — ${x.name}` }))]} /><Button type="button" size="sm" variant="ghost" onClick={() => setPartOpen(true)}>افزودن قطعه</Button></div><TextInput label="مقدار" type="number" value={returnForm.quantity} onChange={(e) => setReturnForm({ ...returnForm, quantity: e.target.value })} /><TextArea label="دلیل برگشت" value={returnForm.reason} onChange={(e) => setReturnForm({ ...returnForm, reason: e.target.value })} /></div></Modal>
    <Modal open={historyOpen} title={`تاریخچه تأیید — ${historyTitle}`} onClose={() => setHistoryOpen(false)} footer={<Button variant="primary" onClick={() => setHistoryOpen(false)}>بستن</Button>}><div className="procurement-history">{historyRows.length ? historyRows.map((item, index) => <div key={String(item.id ?? index)}><strong>{String(item.action ?? "activity")}</strong><span>{String(item.actorName ?? "System")}</span><small>{String(item.actedAt ?? item.createdAt ?? "")}</small><p>{String(item.comment ?? "")}</p></div>) : <p>هنوز سابقه‌ای ثبت نشده است.</p>}</div></Modal>
    <Modal open={invoiceOpen} title="ثبت فاکتور تأمین‌کننده" onClose={() => setInvoiceOpen(false)} footer={<><Button variant="secondary" onClick={() => setInvoiceOpen(false)}>انصراف</Button><Button variant="primary" onClick={postInvoice}>ثبت فاکتور</Button></>}><div className="form-grid"><TextInput label="شماره فاکتور" required value={invoiceForm.invoiceNumber} onChange={(e) => setInvoiceForm({ ...invoiceForm, invoiceNumber: e.target.value })} /><div className="select-with-action"><SelectInput label="تأمین‌کننده" value={invoiceForm.supplierId} onChange={(e) => setInvoiceForm({ ...invoiceForm, supplierId: e.target.value })} options={[{ value: "", label: suppliers.length ? "انتخاب تأمین‌کننده…" : "تأمین‌کننده‌ای ثبت نشده" }, ...suppliers.map((x) => ({ value: x.id, label: x.name }))]} /><Button type="button" size="sm" variant="ghost" onClick={() => setSupplierOpen(true)}>افزودن تأمین‌کننده</Button></div><TextInput label="مبلغ پایه" type="number" value={invoiceForm.subtotal} onChange={(e) => setInvoiceForm({ ...invoiceForm, subtotal: e.target.value })} /><TextInput label="مالیات" type="number" value={invoiceForm.taxAmount} onChange={(e) => setInvoiceForm({ ...invoiceForm, taxAmount: e.target.value })} /><TextInput label="مبلغ کل" type="number" value={invoiceForm.total} onChange={(e) => setInvoiceForm({ ...invoiceForm, total: e.target.value })} /><JalaliDatePicker label="سررسید فاکتور" value={invoiceForm.dueDate} onChange={(value) => setInvoiceForm({ ...invoiceForm, dueDate: value })} /></div></Modal>{toast && <Toast message={toast} onClose={() => setToast("")} />}</div>;
}
