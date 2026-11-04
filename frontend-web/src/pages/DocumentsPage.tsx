import { metricDetail } from "../shared/components/metricDetails";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { runtimeConfig } from "../app/configuration/runtimeConfig";
import { useApiClient } from "../core/api/apiContext";
import { triggerDownload } from "../core/files/downloadUtils";
import { formatJalali } from "../core/localization/jalali";
import { PERMISSIONS, usePermissions } from "../core/permissions/permissionContext";
import { createDocumentService, type LibraryDocument, type RelatedDevice } from "../features/documents/documentService";
import { RelatedDevicePicker } from "../features/documents/RelatedDevicePicker";
import { createMaintenanceService } from "../features/maintenance/maintenanceService";
import { DataTable } from "../shared/components/DataTable";
import { FileUpload, UploadProgress } from "../shared/components/featureComponents";
import { Modal, Toast } from "../shared/components/overlays";
import { Badge, Button, Card, CardHeader, MetricCard, SectionHeader, SelectInput, TextInput } from "../shared/components/primitives";
import { demoDocuments } from "../features/demo/demoData";
import { demoDevices } from "../features/maintenance/maintenanceDemoData";

type PendingFile = { file: File; progress: number; state: "pending" | "uploading" | "complete" | "error" };
const formatBytes = (n: number): string => n < 1024 ? `${n} B` : n < 1048576 ? `${Math.round(n / 1024)} KB` : `${(n / 1048576).toFixed(1)} MB`;
const demoRows = (): LibraryDocument[] => demoDocuments.map((r, i) => ({ id: r.id ?? `demo-${i}`, name: r.name, contentType: "", sizeBytes: 0, category: r.category, description: "", uploadedByIdentifier: r.owner, uploadedAt: r.modifiedAt, relatedDevices: [] }));

export function DocumentsPage(): JSX.Element {
  const api = useApiClient();
  const service = useMemo(() => createDocumentService(api), [api]);
  const maintenance = useMemo(() => createMaintenanceService(api), [api]);
  const { has } = usePermissions();
  const canChooseDevices = has(PERMISSIONS.maintenanceDeviceList);
  const [params, setParams] = useSearchParams();
  const deviceFilter = params.get("deviceId") || "";
  const [documents, setDocuments] = useState<LibraryDocument[]>([]);
  const [devices, setDevices] = useState<RelatedDevice[]>([]);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const [modal, setModal] = useState<"upload" | LibraryDocument | null>(null);
  const [metaCategory, setMetaCategory] = useState("");
  const [description, setDescription] = useState("");
  const [deviceIds, setDeviceIds] = useState<string[]>([]);
  const [files, setFiles] = useState<PendingFile[]>([]);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [deleting, setDeleting] = useState<LibraryDocument | null>(null);
  const [toast, setToast] = useState("");
  const refresh = useCallback(() => setRevision(n => n + 1), []);
  useEffect(() => {
    const controller = new AbortController();
    if (!canChooseDevices) { setDevices([]); return; }
    if (runtimeConfig.demoMode) { setDevices(demoDevices); return; }
    maintenance.listDevices({}, controller.signal).then(setDevices).catch(() => { if (!controller.signal.aborted) setToast("دریافت فهرست دستگاه‌ها ناموفق بود؛ دوباره صفحه را باز کنید."); });
    return () => controller.abort();
  }, [maintenance, canChooseDevices]);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    const timer = window.setTimeout(() => {
      if (runtimeConfig.demoMode) {
        setDocuments(current => {
          const source = current.length ? current : demoRows();
          return source.filter(d => d.name.includes(search) && (!category || d.category === category) && (!deviceFilter || d.relatedDevices?.some(x => x.id === deviceFilter)));
        }); setLoading(false); return;
      }
      service.list({ search, category, deviceId: deviceFilter || undefined }, controller.signal)
        .then(rows => { if (!controller.signal.aborted) setDocuments(rows); })
        .catch(() => { if (!controller.signal.aborted) { setDocuments([]); setToast("بارگذاری اسناد ناموفق بود."); } })
        .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, 200);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [service, search, category, deviceFilter, revision]);
  const open = (document: LibraryDocument | "upload"): void => {
    setModal(document); setFiles([]);
    setMetaCategory(document === "upload" ? "" : document.category);
    setDescription(document === "upload" ? "" : document.description);
    setDeviceIds(document === "upload" ? (canChooseDevices && devices.some(d => d.id === deviceFilter) ? [deviceFilter] : []) : (document.relatedDevices ?? []).map(d => d.id));
  };
  useEffect(() => {
    if (params.get("upload") !== "1") return;
    if (has(PERMISSIONS.maintenanceDocumentUpload)) open("upload");
    const next = new URLSearchParams(params); next.delete("upload"); setParams(next, { replace: true });
    // Initial app shortcut, not a second upload location.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params, setParams]);
  const close = (): void => { if (!busyRef.current) { setModal(null); setFiles([]); } };
  const editable = (doc: LibraryDocument): boolean => has(PERMISSIONS.maintenanceDocumentManage) && (!doc.legacyDeviceDocument || has(PERMISSIONS.maintenanceAttachmentManage));
  const save = async (): Promise<void> => {
    if (!modal || busyRef.current) return;
    if (modal === "upload" && !files.some(f => f.state === "pending" || f.state === "error")) { setToast("ابتدا فایل را انتخاب کنید."); return; }
    busyRef.current = true; setBusy(true);
    try {
      if (modal !== "upload") {
        const oldIds = (modal.relatedDevices ?? []).map(d => d.id).sort().join();
        const changed = [...deviceIds].sort().join() !== oldIds;
        const metadata = { category: metaCategory, description, ...(changed ? { deviceIds } : {}) };
        if (runtimeConfig.demoMode) setDocuments(rows => rows.map(d => d.id === modal.id ? { ...d, category: metaCategory, description, relatedDevices: devices.filter(x => deviceIds.includes(x.id)) } : d));
        else await service.update(modal.id, metadata);
        setModal(null); setToast("مشخصات و دستگاه‌های مرتبط ذخیره شد."); if (!runtimeConfig.demoMode) refresh();
      } else {
        let failures = 0;
        for (let i = 0; i < files.length; i++) {
          if (files[i].state === "complete") continue;
          const update = (patch: Partial<PendingFile>): void => setFiles(rows => rows.map((f, index) => index === i ? { ...f, ...patch } : f));
          update({ state: "uploading", progress: 0 });
          try {
            if (runtimeConfig.demoMode) {
              setDocuments(rows => [{ id: `demo-${Date.now()}-${i}`, name: files[i].file.name, category: metaCategory, description, sizeBytes: files[i].file.size, contentType: files[i].file.type, uploadedByIdentifier: "نمایشی", uploadedAt: new Date().toISOString(), relatedDevices: devices.filter(x => deviceIds.includes(x.id)) }, ...rows]);
            } else await service.upload(files[i].file, { category: metaCategory, description, deviceIds }, progress => update({ progress }));
            update({ state: "complete", progress: 100 });
          } catch { failures++; update({ state: "error" }); }
        }
        if (!runtimeConfig.demoMode) refresh();
        setToast(failures ? "بعضی فایل‌ها ثبت نشدند؛ فقط موارد ناموفق را دوباره ثبت کنید." : "مدارک در اسناد ثبت شدند.");
      }
    } catch (error) { setToast(error instanceof Error ? error.message : "ذخیرهٔ سند ناموفق بود."); }
    finally { busyRef.current = false; setBusy(false); }
  };
  const download = async (doc: LibraryDocument): Promise<void> => {
    if (runtimeConfig.demoMode) { setToast("دانلود فایل در حالت نمایشی فعال نیست."); return; }
    try { triggerDownload(await service.download(doc.id), doc.name); }
    catch { setToast("دریافت فایل ناموفق بود."); }
  };
  const remove = async (): Promise<void> => {
    if (!deleting || busyRef.current) return;
    busyRef.current = true; setBusy(true);
    try {
      if (runtimeConfig.demoMode) setDocuments(rows => rows.filter(d => d.id !== deleting.id));
      else { await service.remove(deleting.id); refresh(); }
      setDeleting(null); setToast("سند از بایگانی فعال حذف شد.");
    } catch { setToast("حذف سند ناموفق بود."); }
    finally { busyRef.current = false; setBusy(false); }
  };
  const categories = [...new Set([category, ...documents.map(d => d.category)].filter(Boolean))];
  const knownDevices = [...new Map([...devices, ...documents.flatMap(d => d.relatedDevices ?? [])].map(d => [d.id, d])).values()];
  const pickerDevices = [...new Map([...devices, ...(modal && modal !== "upload" ? modal.relatedDevices ?? [] : [])].map(d => [d.id, d])).values()];
  const columns = [
    { key: "name", label: "نام مدرک", accessor: (d: LibraryDocument) => d.name, sortable: true, render: (d: LibraryDocument) => <div><strong>{d.name}</strong>{d.description && <p className="muted-cell">{d.description}</p>}</div> },
    { key: "category", label: "دسته‌بندی", accessor: (d: LibraryDocument) => d.category, sortable: true },
    { key: "devices", label: "دستگاه‌های مرتبط", accessor: (d: LibraryDocument) => (d.relatedDevices ?? []).map(x => `${x.code} ${x.name}`).join("، "), render: (d: LibraryDocument) => <div>{d.relatedDevices?.length ? d.relatedDevices.map(x => <Badge key={x.id} tone="neutral">{x.code} — {x.name}</Badge>) : <span className="muted-cell">عمومی</span>}</div> },
    { key: "uploader", label: "ثبت‌کننده", accessor: (d: LibraryDocument) => d.uploadedByIdentifier || "—" },
    { key: "date", label: "تاریخ ثبت", accessor: (d: LibraryDocument) => d.uploadedAt, sortable: true, render: (d: LibraryDocument) => formatJalali(d.uploadedAt, { withTime: true }) },
    { key: "size", label: "حجم", accessor: (d: LibraryDocument) => d.sizeBytes, render: (d: LibraryDocument) => formatBytes(d.sizeBytes) },
    { key: "actions", label: "عملیات", render: (d: LibraryDocument) => <div className="list-toolbar">
      <Button variant="ghost" size="sm" icon="download" onClick={() => void download(d)}>دانلود</Button>
      {editable(d) && <><Button variant="ghost" size="sm" icon="edit" onClick={() => open(d)}>ویرایش ارتباطات و مشخصات</Button><Button variant="ghost" size="sm" icon="close" onClick={() => setDeleting(d)}>حذف</Button></>}
    </div> },
  ];
  return <div className="page">
    <SectionHeader title="اسناد" subtitle="مرکز ثبت و مدیریت همهٔ مدارک؛ هر مدرک می‌تواند به چند دستگاه مرتبط باشد." actions={has(PERMISSIONS.maintenanceDocumentUpload) && <Button variant="primary" icon="upload" onClick={() => open("upload")}>ثبت مدرک</Button>} />
    <div className="file-stats">
      <MetricCard compact icon="file" label="مدارک نمایش‌داده‌شده" value={documents.length} detail={metricDetail(documents, [["name", "مدرک"], ["category", "دسته‌بندی"], ["uploadedAt", "تاریخ ثبت"]])} />
      <MetricCard compact icon="layers" label="دسته‌بندی‌ها" value={new Set(documents.map(d => d.category).filter(Boolean)).size} detail={metricDetail(Array.from(new Set(documents.map(d => d.category).filter(Boolean))).map(category => ({category, count: documents.filter(d => d.category === category).length})), [["category", "دسته‌بندی"], ["count", "تعداد مدارک"]])} />
      <MetricCard compact icon="file" label="حجم مدارک نمایش‌داده‌شده" value={formatBytes(documents.reduce((sum, d) => sum + d.sizeBytes, 0))} detail={metricDetail(documents.map(d => ({name: d.name, size: formatBytes(d.sizeBytes)})), [["name", "مدرک"], ["size", "حجم"]])} />
    </div>
    <Card padding="none" className="content-card"><CardHeader title={`${documents.length} مدرک`} action={<div className="list-toolbar">
      <TextInput label="جست‌وجوی اسناد" value={search} onChange={e => setSearch(e.target.value)} />
      <SelectInput label="دسته‌بندی" value={category} onChange={e => setCategory(e.target.value)} options={[{ value: "", label: "همهٔ دسته‌ها" }, ...categories.map(value => ({ value, label: value }))]} />
      <SelectInput label="فیلتر دستگاه" value={deviceFilter} onChange={e => { const next = new URLSearchParams(params); if (e.target.value) next.set("deviceId", e.target.value); else next.delete("deviceId"); setParams(next); }} options={[{ value: "", label: "همهٔ دستگاه‌ها و اسناد عمومی" }, ...knownDevices.map(d => ({ value: d.id, label: `${d.code} — ${d.name}` }))]} />
    </div>} /><DataTable columns={columns} data={documents} rowKey={d => d.id} search="" exportName="tekarai-documents" empty={{ title: loading ? "در حال بارگذاری…" : "مدرکی یافت نشد." }} /></Card>
    <Modal open={modal !== null} title={modal === "upload" ? "ثبت مدرک در اسناد" : "ویرایش مشخصات و ارتباطات مدرک"} onClose={close} footer={<>
      <Button variant="secondary" disabled={busy} onClick={close}>بستن</Button><Button variant="primary" disabled={busy || (modal === "upload" && (!files.length || files.every(f => f.state === "complete")))} onClick={() => void save()}>{busy ? "در حال ذخیره…" : "ذخیره"}</Button>
    </>}>
      {modal && modal !== "upload" && <p>{modal.name}</p>}
      <TextInput label="دسته‌بندی مدرک" maxLength={80} disabled={busy || files.some(f => f.state === "complete")} value={metaCategory} onChange={e => setMetaCategory(e.target.value)} />
      <TextInput label="توضیحات" maxLength={2000} disabled={busy || files.some(f => f.state === "complete")} value={description} onChange={e => setDescription(e.target.value)} />
      {canChooseDevices ? <RelatedDevicePicker devices={pickerDevices} value={deviceIds} onChange={setDeviceIds} disabled={busy || files.some(f => f.state === "complete")} /> : <p>برای انتخاب دستگاه، دسترسی فهرست تجهیزات لازم است.</p>}
      {modal === "upload" && <>
        {!busy && !files.some(f => f.state === "complete") && <FileUpload onFiles={chosen => setFiles(chosen.map(file => ({ file, progress: 0, state: "pending" })))} />}
        {files.map((f, i) => f.state === "pending" ? <p key={i}>{f.file.name} — آمادهٔ ثبت</p> : <UploadProgress key={i} fileName={f.file.name} progress={f.progress} state={f.state} />)}
      </>}
    </Modal>
    <Modal open={deleting !== null} title="حذف سند" onClose={() => { if (!busy) setDeleting(null); }} footer={<><Button disabled={busy} onClick={() => setDeleting(null)}>انصراف</Button><Button disabled={busy} onClick={() => void remove()}>حذف</Button></>}>
      <p>این مدرک از اسناد و نمایش تمام دستگاه‌های مرتبط حذف شود؟</p><strong>{deleting?.name}</strong>
    </Modal>
    {toast && <Toast message={toast} onClose={() => setToast("")} />}
  </div>;
}
