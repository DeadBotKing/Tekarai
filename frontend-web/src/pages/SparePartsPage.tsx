import { useEffect, useMemo, useRef, useState } from "react";
import { runtimeConfig } from "../app/configuration/runtimeConfig";
import { useApiClient } from "../core/api/apiContext";
import { faText } from "../core/localization/i18n";
import { PERMISSIONS } from "../core/permissions/permissionContext";
import { rowsToCsvBlob, triggerDownload } from "../core/files/downloadUtils";
import { parseImportFile, toNumber } from "../core/files/importUtils";
import { createMaintenanceService } from "../features/maintenance/maintenanceService";
import { buildReorderSuggestions } from "../features/maintenance/wave1";
import { activeReservedForPart, availableStock } from "../features/maintenance/wave2";
import { listReservations, syncReservationsFromServer } from "../features/maintenance/wave2Store";
import type { PartTransaction, PartTransactionType, SparePart } from "../shared/types/domain";
import { PART_UNITS } from "../shared/types/domain";
import { CreatableSelect } from "../shared/components/CreatableSelect";
import { mergeOptions } from "../features/maintenance/optionCatalog";
import { DataTable, type DataTableColumn } from "../shared/components/DataTable";
import { Modal, Toast } from "../shared/components/overlays";
import { Badge, Button, Card, CardHeader, PermissionGuard, SectionHeader, SelectInput, TextInput } from "../shared/components/primitives";
import { Icon } from "../shared/components/Icon";

export const demoParts: SparePart[] = [
  { id: "sp-1", code: "SAL-4021", name: "بلبرینگ 6204", unit: "عدد", quantityOnHand: 42, minimumStock: 20, unitCost: 185_000, lowStock: false, createdAt: "1405/05/12", updatedAt: "" },
  { id: "sp-2", code: "BLT-1180", name: "تسمه V118", unit: "عدد", quantityOnHand: 6, minimumStock: 10, unitCost: 320_000, lowStock: true, createdAt: "1405/05/12", updatedAt: "" },
  { id: "sp-3", code: "FLT-2200", name: "فیلتر روغن هیدرولیک", unit: "عدد", quantityOnHand: 15, minimumStock: 8, unitCost: 610_000, lowStock: false, createdAt: "1405/05/13", updatedAt: "" },
  { id: "sp-4", code: "OIL-5046", name: "روغن هیدرولیک ISO46", unit: "لیتر", quantityOnHand: 120, minimumStock: 60, unitCost: 340_000, lowStock: false, createdAt: "1405/05/14", updatedAt: "" },
  { id: "sp-5", code: "SL-3309", name: "سیل مکانیکی 45mm", unit: "عدد", quantityOnHand: 3, minimumStock: 5, unitCost: 1_850_000, lowStock: true, createdAt: "1405/05/15", updatedAt: "" },
  { id: "sp-6", code: "CNT-8800", name: "کنتاکتور 25A", unit: "عدد", quantityOnHand: 9, minimumStock: 4, unitCost: 2_400_000, lowStock: false, createdAt: "1405/05/15", updatedAt: "" },
];

interface PartFormState { code: string; name: string; unit: string; quantityOnHand: string; minimumStock: string; unitCost: string; }
const emptyForm: PartFormState = { code: "", name: "", unit: "عدد", quantityOnHand: "0", minimumStock: "0", unitCost: "0" };

interface TxFormState { transactionType: PartTransactionType; quantity: string; reference: string; note: string; }
const emptyTxForm: TxFormState = { transactionType: "RECEIPT", quantity: "", reference: "", note: "" };

/** دفتر نمایشی هر قطعه: دو ردیف منسجم که به موجودی فعلی می‌رسد. */
export function seedDemoLedger(part: SparePart): PartTransaction[] {
  const received: PartTransaction = { id: `${part.id}-t1`, partId: part.id, partCode: part.code, partName: part.name, unit: part.unit, transactionType: "RECEIPT", typeLabel: "رسید", quantity: part.quantityOnHand + 2, balanceAfter: part.quantityOnHand + 2, note: "موجودی اولیه", reference: "رسید ابتدایی", actorId: "", createdAt: part.createdAt };
  const counted: PartTransaction = { id: `${part.id}-t2`, partId: part.id, partCode: part.code, partName: part.name, unit: part.unit, transactionType: "ADJUSTMENT", typeLabel: "تعدیل", quantity: -2, balanceAfter: part.quantityOnHand, note: "انبارگردانی", reference: "", actorId: "", createdAt: part.createdAt };
  return [counted, received];
}

export function signedQuantity(type: PartTransactionType, amount: number): number {
  if (type === "ISSUE") return -Math.abs(amount);
  if (type === "ADJUSTMENT") return amount;
  return Math.abs(amount);
}

export function SparePartsPage(): JSX.Element {
  const t = faText;
  const api = useApiClient();
  const service = useMemo(() => createMaintenanceService(api), [api]);
  const [reservationsTick, setReservationsTick] = useState(0);

  const [parts, setParts] = useState<SparePart[]>(runtimeConfig.demoMode ? demoParts : []);
  const [search, setSearch] = useState("");
  const [lowOnly, setLowOnly] = useState(false);
  const [loading, setLoading] = useState(!runtimeConfig.demoMode);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<SparePart | null>(null);
  const [form, setForm] = useState<PartFormState>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [importReport, setImportReport] = useState<{ created: number; errors: string[] } | null>(null);
  const [toast, setToast] = useState("");
  const fileInput = useRef<HTMLInputElement | null>(null);
  const [ledgerPart, setLedgerPart] = useState<SparePart | null>(null);
  const [ledgerRows, setLedgerRows] = useState<PartTransaction[]>([]);
  const [ledgerLoading, setLedgerLoading] = useState(false);
  const [txForm, setTxForm] = useState<TxFormState>(emptyTxForm);
  const [txSaving, setTxSaving] = useState(false);

  const refresh = (searchText = search): void => {
    if (runtimeConfig.demoMode) return;
    setLoading(true);
    service.listSpareParts(searchText)
      .then(setParts)
      .catch(() => setToast(t("warehouse.loadFailed")))
      .finally(() => setLoading(false));
  };
  useEffect(() => { refresh(""); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);
  useEffect(() => {
    if (runtimeConfig.demoMode) return;
    const timer = window.setTimeout(() => refresh(search), 350);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const filtered = parts.filter((part) => {
    const matchesSearch = !search || `${part.code} ${part.name}`.toLowerCase().includes(search.toLowerCase());
    return matchesSearch && (!lowOnly || lowStock(part));
  });
  function lowStock(part: SparePart): boolean { return part.lowStock || part.quantityOnHand < part.minimumStock; }

  const lowCount = parts.filter(lowStock).length;
  const totalValue = parts.reduce((sum, part) => sum + part.quantityOnHand * part.unitCost, 0);

  const openCreate = (): void => { setEditing(null); setForm(emptyForm); setModalOpen(true); };
  const openEdit = (part: SparePart): void => {
    setEditing(part);
    setForm({ code: part.code, name: part.name, unit: part.unit, quantityOnHand: String(part.quantityOnHand), minimumStock: String(part.minimumStock), unitCost: String(part.unitCost) });
    setModalOpen(true);
  };

  const save = (): void => {
    setSaving(true);
    const payload = {
      name: form.name.trim(),
      unit: form.unit.trim() || "عدد",
      quantityOnHand: toNumber(form.quantityOnHand),
      minimumStock: toNumber(form.minimumStock),
      unitCost: toNumber(form.unitCost),
    };
    if (runtimeConfig.demoMode) {
      if (editing) setParts((current) => current.map((part) => part.id === editing.id ? { ...part, ...payload } : part));
      else setParts((current) => [{ id: `sp-${Date.now()}`, code: form.code.trim(), lowStock: payload.quantityOnHand < payload.minimumStock, createdAt: "", updatedAt: "", ...payload }, ...current]);
      setSaving(false); setModalOpen(false); setToast(t("warehouse.saved"));
      return;
    }
    const task = editing
      ? service.updateSparePart(editing.id, payload)
      : service.createSparePart({ code: form.code.trim(), ...payload });
    task
      .then(() => { setModalOpen(false); setToast(t("warehouse.saved")); refresh(); })
      .catch(() => setToast(t("warehouse.saveFailed")))
      .finally(() => setSaving(false));
  };

  const openLedger = (part: SparePart): void => {
    setLedgerPart(part); setTxForm(emptyTxForm);
    if (runtimeConfig.demoMode) { setLedgerRows(seedDemoLedger(part)); setLedgerLoading(false); return; }
    setLedgerLoading(true);
    service.listPartTransactions(part.id)
      .then(setLedgerRows)
      .catch(() => setToast(t("warehouse.loadFailed")))
      .finally(() => setLedgerLoading(false));
  };

  const submitTransaction = (): void => {
    if (!ledgerPart) return;
    const amount = Number(txForm.quantity);
    if (!Number.isFinite(amount) || amount === 0) return;
    setTxSaving(true);
    const signed = signedQuantity(txForm.transactionType, amount);
    const refreshParts = (): void => setParts((current) => current.map((row) => {
      if (row.id !== ledgerPart.id) return row;
      const quantityOnHand = row.quantityOnHand + signed;
      return { ...row, quantityOnHand, lowStock: quantityOnHand < row.minimumStock };
    }));
    if (runtimeConfig.demoMode) {
      const balanceAfter = ledgerPart.quantityOnHand + signed;
      if (balanceAfter < 0) { setTxSaving(false); setToast(t("warehouse.ledgerFailed")); return; }
      const row: PartTransaction = {
        id: `tx-${Date.now()}`, partId: ledgerPart.id, partCode: ledgerPart.code, partName: ledgerPart.name, unit: ledgerPart.unit,
        transactionType: txForm.transactionType, typeLabel: t(`warehouse.ledger${txForm.transactionType === "RECEIPT" ? "Receipt" : txForm.transactionType === "ISSUE" ? "Issue" : txForm.transactionType === "RETURN" ? "Return" : "Adjustment"}` as Parameters<typeof t>[0]),
        quantity: signed, balanceAfter,
        note: txForm.note.trim(), reference: txForm.reference.trim(), actorId: "",
        createdAt: new Date().toISOString().slice(0, 10),
      };
      setLedgerRows((current) => [row, ...current]);
      refreshParts(); setLedgerPart({ ...ledgerPart, quantityOnHand: balanceAfter });
      setTxForm(emptyTxForm); setTxSaving(false); setToast(t("warehouse.ledgerSaved"));
      return;
    }
    service.recordPartTransaction(ledgerPart.id, {
      transactionType: txForm.transactionType,
      quantity: txForm.transactionType === "ADJUSTMENT" ? amount : Math.abs(amount),
      note: txForm.note.trim(),
      reference: txForm.reference.trim(),
    })
      .then((row) => {
        setLedgerRows((current) => [row, ...current]);
        refresh(); setLedgerPart({ ...ledgerPart, quantityOnHand: row.balanceAfter });
        setTxForm(emptyTxForm); setToast(t("warehouse.ledgerSaved"));
      })
      .catch(() => setToast(t("warehouse.ledgerFailed")))
      .finally(() => setTxSaving(false));
  };

  const downloadTemplate = (): void => {
    const rows = [["code", "name", "unit", "quantityOnHand", "minimumStock", "unitCost"], ["SAL-4021", "بلبرینگ 6204", "عدد", "42", "20", "185000"]];
    triggerDownload(rowsToCsvBlob(rows), "spare-parts-import-template.csv");
  };

  const runImport = async (file: File): Promise<void> => {
    let rows;
    try { rows = await parseImportFile(file); }
    catch { setToast(t("warehouse.importInvalid")); return; }
    let created = 0;
    const errors: string[] = [];
    for (const [index, row] of rows.entries()) {
      const code = row.code ?? ""; const name = row.name ?? "";
      if (!code || !name) { errors.push(t("warehouse.importRowError").replace("{row}", String(index + 1))); continue; }
      if (runtimeConfig.demoMode) {
        setParts((current) => current.some((part) => part.code === code) ? current : [{ id: `imp-${index}-${Date.now()}`, code, name, unit: row.unit || "عدد", quantityOnHand: toNumber(row.quantityonhand), minimumStock: toNumber(row.minimumstock), unitCost: toNumber(row.unitcost), lowStock: false, createdAt: "", updatedAt: "" }, ...current]);
        created += 1; continue;
      }
      try {
        await service.createSparePart({ code, name, unit: row.unit || "عدد", quantityOnHand: toNumber(row.quantityonhand), minimumStock: toNumber(row.minimumstock), unitCost: toNumber(row.unitcost) });
        created += 1;
      } catch { errors.push(t("warehouse.importRowError").replace("{row}", String(index + 1))); }
    }
    setImportReport({ created, errors });
    if (!runtimeConfig.demoMode) refresh();
  };

  // هم‌گام‌سازی تیمی رزروها از سرور در باز شدن صفحه
  useEffect(() => {
    void syncReservationsFromServer().then((ok) => {
      if (ok) setReservationsTick((tick) => tick + 1);
    });
  }, []);
  const columns = useMemo<DataTableColumn<SparePart>[]>(() => [
    { key: "code", label: t("registry.code"), accessor: (row) => row.code, sortable: true, width: "14%", render: (row) => <strong>{row.code}</strong> },
    { key: "name", label: t("registry.name"), accessor: (row) => row.name, sortable: true },
    { key: "unit", label: t("warehouse.unit"), accessor: (row) => row.unit, sortable: true, width: "10%" },
    { key: "quantityOnHand", label: t("warehouse.stock"), accessor: (row) => row.quantityOnHand, sortable: true, width: "12%", render: (row) => <strong>{row.quantityOnHand.toLocaleString()}</strong> },
    { key: "minimumStock", label: t("warehouse.minimum"), accessor: (row) => row.minimumStock, sortable: true, width: "12%" },
    { key: "unitCost", label: t("warehouse.unitCost"), accessor: (row) => row.unitCost, sortable: true, width: "14%", render: (row) => `${row.unitCost.toLocaleString()} ${t("warehouse.currency")}` },
    { key: "state", label: t("project.status"), accessor: (row) => (lowStock(row) ? "low" : "ok"), sortable: true, width: "12%", render: (row) => lowStock(row) ? <Badge tone="warning" dot>{t("warehouse.lowStock")}</Badge> : <Badge tone="success" dot>{t("warehouse.inStock")}</Badge> },
    ...(runtimeConfig.demoMode || undefined ? [{ key: "action" as const, label: t("project.actions"), hideable: false, render: (row: SparePart) => <span className="row-actions"><PermissionGuard permission={PERMISSIONS.maintenanceInventoryManage}><Button variant="ghost" size="sm" icon="edit" onClick={() => openEdit(row)}>{t("common.edit")}</Button></PermissionGuard>
      <Button variant="ghost" size="sm" icon="book" title={t("warehouse.ledger")} onClick={() => openLedger(row)} aria-label={`${t("warehouse.ledger")} ${row.code}`}> </Button>
    </span> }] : []),
    { key: "reserved", label: t("warehouse.reserved"), accessor: (row) => activeReservedForPart(listReservations(), row.code) || "" },
    { key: "available", label: t("warehouse.available"), render: (row) => {
        const reserved = activeReservedForPart(listReservations(), row.code);
        const available = availableStock(row.quantityOnHand, reserved);
        return <Badge tone={available <= 0 ? "danger" : "neutral"}>{available} {row.unit}</Badge>;
      } },
  ], [t, reservationsTick]);

  return <div className="page" dir="rtl">
    <SectionHeader eyebrow={t("nav.warehouse")} title={t("warehouse.title")} subtitle={t("warehouse.subtitle")} actions={<>
      <PermissionGuard permission={PERMISSIONS.maintenanceInventoryManage}>
        <Button variant="secondary" icon="upload" onClick={() => { setImportOpen(true); setImportReport(null); }}>{t("warehouse.import")}</Button>
      </PermissionGuard>
      <PermissionGuard permission={PERMISSIONS.maintenanceInventoryManage}>
        <Button variant="primary" icon="plus" onClick={openCreate}>{t("warehouse.addPart")}</Button>
      </PermissionGuard>
    </>} />
    <div className="file-stats">
      <div><span>{t("warehouse.totalParts")}</span><strong>{parts.length}</strong></div>
      <div><span>{t("warehouse.lowStock")}</span><strong>{lowCount}</strong></div>
      <div><span>{t("warehouse.stockValue")}</span><strong>{totalValue.toLocaleString()}</strong></div>
      <div><span>{t("warehouse.totalStock")}</span><strong>{parts.reduce((sum, part) => sum + part.quantityOnHand, 0).toLocaleString()}</strong></div>
    </div>
    {(() => {
      const suggestions = buildReorderSuggestions(parts);
      if (!suggestions.length) return null;
      return (
        <Card className="content-card" padding="md">
          <CardHeader title={t("cmms.wave1.reorderTitle")} subtitle={t("cmms.wave1.reorderSubtitle")} icon="warning" />
          <div className="reorder-list">
            {suggestions.map((item) => (
              <div className="inspection-item" key={item.partCode}>
                <span><Icon name="layers" size={14} /> <strong>{item.partCode}</strong> — {item.partName}</span>
                <div className="section-actions">
                  <Badge tone="danger" dot>{t("warehouse.stock")}: {item.quantityOnHand} {item.unit}</Badge>
                  <Badge tone="neutral" dot>{t("warehouse.minimum")}: {item.minimumStock}</Badge>
                  <Badge tone="warning" dot>{t("cmms.wave1.colSuggested")}: {item.suggestedOrder} {item.unit}</Badge>
                </div>
              </div>
            ))}
          </div>
        </Card>
      );
    })()}
    <Card className="content-card" padding="none">
      <CardHeader title={`${filtered.length} ${t("warehouse.title").toLowerCase()}`} action={<div className="list-toolbar">
        <div className="search-box"><Icon name="search" size={16} /><input value={search} aria-label={t("warehouse.search")} placeholder={t("warehouse.search")} onChange={(event) => setSearch(event.target.value)} /></div>
        <Button variant={lowOnly ? "secondary" : "ghost"} size="sm" icon="warning" onClick={() => setLowOnly((current) => !current)}>{t("warehouse.lowOnly")}</Button>
      </div>} />
      <DataTable columns={columns} data={filtered} rowKey={(row) => row.id} search="" exportName="tekarai-spare-parts" empty={{ title: loading ? t("common.loading") : t("warehouse.empty") }} />
    </Card>
    <Modal open={modalOpen} title={editing ? t("warehouse.editPart") : t("warehouse.addPart")} onClose={() => setModalOpen(false)} footer={<>
      <Button variant="secondary" onClick={() => setModalOpen(false)}>{t("common.cancel")}</Button>
      <Button variant="primary" disabled={saving || !form.name.trim() || (!editing && !form.code.trim())} onClick={save}>{saving ? t("common.loading") : t("common.save")}</Button>
    </>}>
      <div className="form-grid">
        {!editing && <TextInput label={t("registry.code")} required value={form.code} onChange={(event) => setForm({ ...form, code: event.target.value })} placeholder="SAL-4021" />}
        <TextInput label={t("registry.name")} required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
        <CreatableSelect
          label={t("warehouse.unit")}
          required
          value={form.unit}
          onChange={(value) => setForm({ ...form, unit: value })}
          catalogKey="part.unit"
          canonical={PART_UNITS}
          addLabel="➕ افزودن واحد جدید…"
          options={mergeOptions({ canonical: PART_UNITS, translate: (value) => value, catalogKey: "part.unit", current: form.unit })}
        />
        <TextInput label={t("warehouse.stock")} type="number" value={form.quantityOnHand} onChange={(event) => setForm({ ...form, quantityOnHand: event.target.value })} />
        <TextInput label={t("warehouse.minimum")} type="number" value={form.minimumStock} onChange={(event) => setForm({ ...form, minimumStock: event.target.value })} />
        <TextInput label={t("warehouse.unitCost")} type="number" value={form.unitCost} onChange={(event) => setForm({ ...form, unitCost: event.target.value })} />
      </div>
    </Modal>
    <Modal open={Boolean(ledgerPart)} wide title={`${t("warehouse.ledger")} — ${ledgerPart?.code ?? ""}`} onClose={() => setLedgerPart(null)} footer={<Button variant="primary" onClick={() => setLedgerPart(null)}>{t("common.close")}</Button>}>
      {ledgerPart && <div className="ledger" dir="rtl">
        <p className="muted-cell">{t("warehouse.ledgerHint")} · <strong>{ledgerPart.name}</strong> — {t("warehouse.stock")}: <strong>{ledgerPart.quantityOnHand.toLocaleString()} {ledgerPart.unit}</strong></p>
        <PermissionGuard permission={PERMISSIONS.maintenanceInventoryManage}>
          <form className="ledger-form" onSubmit={(event) => { event.preventDefault(); submitTransaction(); }}>
            <SelectInput label={t("warehouse.ledgerType")} value={txForm.transactionType} onChange={(event) => setTxForm({ ...txForm, transactionType: event.target.value as PartTransactionType })} options={[
              { value: "RECEIPT", label: t("warehouse.ledgerReceipt") },
              { value: "ISSUE", label: t("warehouse.ledgerIssue") },
              { value: "RETURN", label: t("warehouse.ledgerReturn") },
              { value: "ADJUSTMENT", label: t("warehouse.ledgerAdjustment") },
            ]} />
            <TextInput label={`${t("warehouse.ledgerQuantity")} (${ledgerPart.unit})`} type="number" step="any" required value={txForm.quantity} onChange={(event) => setTxForm({ ...txForm, quantity: event.target.value })} />
            <TextInput label={t("warehouse.ledgerReference")} value={txForm.reference} onChange={(event) => setTxForm({ ...txForm, reference: event.target.value })} />
            <TextInput label={t("warehouse.ledgerNote")} value={txForm.note} onChange={(event) => setTxForm({ ...txForm, note: event.target.value })} />
            <div className="ledger-form__action"><Button variant="primary" size="sm" icon="plus" type="submit" disabled={txSaving || !Number(txForm.quantity)}>{t("warehouse.ledgerNew")}</Button></div>
          </form>
        </PermissionGuard>
        {ledgerLoading ? <p className="muted-cell">{t("common.loading")}</p> : ledgerRows.length === 0 ? (
          <p className="muted-cell">{t("warehouse.ledgerEmpty")}</p>
        ) : (
          <div className="table-scroll"><table className="data-table ledger-table">
            <thead><tr>
              <th>{t("warehouse.ledgerType")}</th>
              <th>{t("warehouse.ledgerQuantity")}</th>
              <th>{t("warehouse.ledgerBalance")}</th>
              <th>{t("warehouse.ledgerReference")}</th>
              <th>{t("warehouse.ledgerNote")}</th>
              <th>{t("warehouse.ledgerDate")}</th>
            </tr></thead>
            <tbody>
              {ledgerRows.map((row) => <tr key={row.id}>
                <td><Badge tone={row.quantity >= 0 ? "success" : "warning"} dot>{row.typeLabel}</Badge></td>
                <td><strong dir="ltr">{row.quantity > 0 ? `+${row.quantity.toLocaleString()}` : row.quantity.toLocaleString()}</strong> <span className="muted-cell">{row.unit}</span></td>
                <td><strong>{row.balanceAfter.toLocaleString()}</strong> <span className="muted-cell">{row.unit}</span></td>
                <td className="muted-cell">{row.reference || "—"}</td>
                <td className="muted-cell">{row.note || "—"}</td>
                <td className="muted-cell">{row.createdAt.slice(0, 10)}</td>
              </tr>)}
            </tbody>
          </table></div>
        )}
      </div>}
    </Modal>
    <Modal open={importOpen} title={t("warehouse.importTitle")} onClose={() => setImportOpen(false)} footer={<Button variant="primary" onClick={() => setImportOpen(false)}>{t("common.close")}</Button>}>
      <p className="muted-cell">{t("warehouse.importHint")}</p>
      <div className="list-toolbar">
        <Button variant="secondary" icon="download" onClick={downloadTemplate}>{t("warehouse.downloadTemplate")}</Button>
        <Button variant="primary" icon="upload" onClick={() => fileInput.current?.click()}>{t("warehouse.chooseFile")}</Button>
        <input ref={fileInput} type="file" accept=".csv,.xlsx,.xls" style={{ display: "none" }} onChange={(event) => { const file = event.target.files?.[0]; if (file) void runImport(file); event.target.value = ""; }} />
      </div>
      {importReport && <div className="form-grid">
        <Badge tone="success" dot>{t("warehouse.importCreated").replace("{count}", String(importReport.created))}</Badge>
        {importReport.errors.slice(0, 5).map((error) => <Badge key={error} tone="warning" dot>{error}</Badge>)}
      </div>}
    </Modal>
    {toast && <Toast message={toast} onClose={() => setToast("")} />}
  </div>;
}
