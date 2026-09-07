import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useLocalization } from "../core/localization/localizationContext";
import { PERMISSIONS } from "../core/permissions/permissionContext";
import { demoDocuments } from "../features/demo/demoData";
import type { DocumentRecord } from "../shared/types/domain";
import { DataTable, type DataTableColumn } from "../shared/components/DataTable";
import { DocumentViewer, FileUpload, UploadProgress } from "../shared/components/featureComponents";
import { Modal, Toast } from "../shared/components/overlays";
import { Avatar, Button, Card, CardHeader, PermissionGuard, SectionHeader, SelectInput, StatusBadge } from "../shared/components/primitives";
import { Icon } from "../shared/components/Icon";

interface UploadItem { name: string; progress: number; state: "uploading" | "complete" | "error"; }

export function DocumentsPage(): JSX.Element {
  const { t } = useLocalization();
  const [searchParams, setSearchParams] = useSearchParams();
  const [documents, setDocuments] = useState<DocumentRecord[]>(demoDocuments);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("all");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [selected, setSelected] = useState<DocumentRecord | null>(null);
  const [toast, setToast] = useState("");
  useEffect(() => { if (searchParams.get("upload") === "1") { setUploadOpen(true); setSearchParams({}, { replace: true }); } }, [searchParams, setSearchParams]);
  const categories = [...new Set(documents.map((document) => document.category))];
  const columns = useMemo<DataTableColumn<DocumentRecord>[]>(() => [
    { key: "name", label: t("document.title"), accessor: (row) => `${row.name} ${row.type}`, sortable: true, width: "32%", render: (row) => <div className="document-cell"><span className={`document-cell__icon document-cell__icon--${row.type.toLowerCase()}`}><Icon name="file" size={18} /></span><div><strong>{row.name}</strong><span>{row.type}</span></div></div> },
    { key: "category", label: t("document.category"), accessor: (row) => row.category, sortable: true, render: (row) => <BadgeText tone="purple">{row.category}</BadgeText> },
    { key: "owner", label: t("document.owner"), accessor: (row) => row.owner, sortable: true, render: (row) => <div className="person-cell"><Avatar name={row.owner} size="sm" tone="purple" /><span>{row.owner}</span></div> },
    { key: "modifiedAt", label: t("document.modified"), accessor: (row) => row.modifiedAt, sortable: true },
    { key: "size", label: t("document.size"), accessor: (row) => row.size, sortable: true },
    { key: "status", label: t("project.status"), accessor: (row) => row.status, render: (row) => <StatusBadge status={row.status} /> },
    { key: "actions", label: t("project.actions"), hideable: false, render: (row) => <Button variant="ghost" size="sm" icon="external" onClick={() => setSelected(row)}>{t("common.view")}</Button> },
  ], [t]);
  const filtered = documents.filter((document) => (category === "all" || document.category === category) && `${document.name} ${document.owner} ${document.category}`.toLowerCase().includes(search.toLowerCase()));
  const handleFiles = (files: File[]): void => {
    setUploads(files.map((file) => ({ name: file.name, progress: 0, state: "uploading" })));
    files.forEach((file, index) => {
      let progress = 0;
      const interval = window.setInterval(() => {
        progress = Math.min(100, progress + 25);
        setUploads((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, progress, state: progress === 100 ? "complete" : "uploading" } : item));
        if (progress === 100) {
          window.clearInterval(interval);
          const record: DocumentRecord = { id: `doc-${Date.now()}-${index}`, name: file.name, type: extensionType(file.name), category: "Operations", owner: "Maya Chen", modifiedAt: "Just now", size: formatBytes(file.size), status: "active" };
          setDocuments((current) => [record, ...current]);
        }
      }, 110);
    });
  };
  const closeUpload = (): void => { setUploadOpen(false); setUploads([]); setToast(t("document.uploaded")); };

  return <div className="page"><SectionHeader eyebrow={t("nav.documents")} title={t("document.title")} subtitle={t("document.subtitle")} actions={<PermissionGuard permission={PERMISSIONS.documentUpload}><Button variant="primary" icon="upload" onClick={() => setUploadOpen(true)}>{t("document.upload")}</Button></PermissionGuard>} />
    <div className="file-stats"><div><span>{t("document.title")}</span><strong>{documents.length}</strong></div><div><span>Categories</span><strong>{categories.length}</strong></div><div><span>Storage used</span><strong>8.9 GB</strong></div><div><span>Governed</span><strong>100%</strong></div></div>
    <Card className="content-card" padding="none"><CardHeader title={`${filtered.length} ${t("document.title").toLowerCase()}`} action={<div className="list-toolbar"><div className="search-box"><Icon name="search" size={16} /><input value={search} aria-label={t("document.search")} placeholder={t("document.search")} onChange={(event) => setSearch(event.target.value)} /></div><SelectInput aria-label={t("document.category")} value={category} onChange={(event) => setCategory(event.target.value)} options={[{ value: "all", label: t("document.category") }, ...categories.map((item) => ({ value: item, label: item }))]} /></div>} /><DataTable columns={columns} data={filtered} rowKey={(row) => row.id} search="" onRowClick={setSelected} empty={{ title: t("document.noResults") }} exportName="tekarai-documents" /></Card>
    <Modal open={uploadOpen} title={t("document.uploadTitle")} onClose={closeUpload} footer={<Button variant="primary" onClick={closeUpload}>{t("common.close")}</Button>}><FileUpload onFiles={handleFiles} />{uploads.length > 0 && <div className="upload-list">{uploads.map((upload) => <UploadProgress key={upload.name} fileName={upload.name} progress={upload.progress} state={upload.state} />)}</div>}</Modal>
    {selected && <Modal open title={t("document.viewer")} onClose={() => setSelected(null)}><DocumentViewer document={selected} onClose={() => setSelected(null)} /></Modal>}
    {toast && <Toast message={toast} onClose={() => setToast("")} />}
  </div>;
}

function BadgeText({ children, tone }: { children: string; tone: "purple" | "blue" }): JSX.Element { return <span className={`badge badge--${tone}`}>{children}</span>; }
function extensionType(name: string): DocumentRecord["type"] { const extension = name.split(".").pop()?.toLowerCase(); return extension === "pdf" ? "PDF" : extension === "doc" || extension === "docx" ? "DOCX" : extension === "xls" || extension === "xlsx" ? "XLSX" : extension === "png" || extension === "jpg" || extension === "jpeg" ? "PNG" : "TXT"; }
function formatBytes(bytes: number): string { if (bytes < 1024) return `${bytes} B`; if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`; return `${(bytes / 1024 / 1024).toFixed(1)} MB`; }
