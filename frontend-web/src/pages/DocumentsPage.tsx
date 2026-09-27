import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { runtimeConfig } from "../app/configuration/runtimeConfig";
import { useApiClient } from "../core/api/apiContext";
import { triggerDownload } from "../core/files/downloadUtils";
import { formatJalali } from "../core/localization/jalali";
import { faText } from "../core/localization/i18n";
import { PERMISSIONS } from "../core/permissions/permissionContext";
import { createDocumentService, type LibraryDocument } from "../features/documents/documentService";
import { DataTable } from "../shared/components/DataTable";
import { DocumentViewer, FileUpload, UploadProgress } from "../shared/components/featureComponents";
import { Modal, Toast } from "../shared/components/overlays";
import { Badge, Button, Card, CardHeader, PermissionGuard, SectionHeader, SelectInput, TextInput } from "../shared/components/primitives";
import { Icon } from "../shared/components/Icon";
import { demoDocuments } from "../features/demo/demoData";

interface UploadItem { name: string; progress: number; state: "uploading" | "complete" | "error"; }

const EXTENSION_COLOR: Record<string, string> = { pdf: "pdf", docx: "docx", xlsx: "xlsx", png: "png", jpg: "png", jpeg: "png" };

export function DocumentsPage(): JSX.Element {
  const t = faText;
  const api = useApiClient();
  const service = useMemo(() => createDocumentService(api), [api]);
  const [searchParams, setSearchParams] = useSearchParams();
  const [documents, setDocuments] = useState<LibraryDocument[]>([]);
  const [loading, setLoading] = useState(!runtimeConfig.demoMode);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("all");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadCategory, setUploadCategory] = useState("");
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [selected, setSelected] = useState<LibraryDocument | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<LibraryDocument | null>(null);
  const [toast, setToast] = useState("");

  useEffect(() => {
    if (searchParams.get("upload") === "1") { setUploadOpen(true); setSearchParams({}, { replace: true }); }
  }, [searchParams, setSearchParams]);

  const refresh = (filters?: { search?: string; category?: string }): void => {
    if (runtimeConfig.demoMode) {
      setDocuments(demoDocuments.map((row, index) => ({ id: row.id ?? `demo-${index}`, name: row.name, contentType: "", sizeBytes: 0, category: row.category, description: "", uploadedByIdentifier: row.owner, uploadedAt: row.modifiedAt })));
      return;
    }
    setLoading(true);
    service.list({
      search: filters?.search ?? search,
      category: (filters?.category ?? category) === "all" ? "" : (filters?.category ?? category),
    })
      .then(setDocuments)
      .catch(() => setToast(t("document.loadFailed")))
      .finally(() => setLoading(false));
  };
  useEffect(() => { refresh({ search: "", category: "all" }); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);
  useEffect(() => {
    if (runtimeConfig.demoMode) return;
    const timer = window.setTimeout(() => refresh(), 350);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, category]);

  const categories = [...new Set(documents.map((document) => document.category).filter(Boolean))];

  const handleFiles = (files: File[]): void => {
    setUploads(files.map((file) => ({ name: file.name, progress: 0, state: "uploading" })));
    files.forEach((file, index) => {
      service.upload(file, { category: uploadCategory }, (progress) => {
        setUploads((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, progress } : item));
      })
        .then(() => {
          setUploads((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, progress: 100, state: "complete" } : item));
          refresh();
        })
        .catch(() => {
          setUploads((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, state: "error" } : item));
          setToast(t("document.uploadFailed"));
        });
    });
  };

  const closeUpload = (): void => {
    const completed = uploads.some((upload) => upload.state === "complete");
    setUploadOpen(false); setUploads([]);
    if (completed) setToast(t("document.uploaded"));
  };

  const download = (document: LibraryDocument): void => {
    if (runtimeConfig.demoMode) return;
    service.download(document.id)
      .then((blob) => triggerDownload(blob, document.name))
      .catch(() => setToast(t("document.loadFailed")));
  };

  const remove = (): void => {
    if (!confirmDelete) return;
    if (runtimeConfig.demoMode) { setConfirmDelete(null); return; }
    service.remove(confirmDelete.id)
      .then(() => { setConfirmDelete(null); setToast(t("document.deleted")); refresh(); })
      .catch(() => { setConfirmDelete(null); setToast(t("document.loadFailed")); });
  };

  const columns = useMemo(() => [
    { key: "name", label: t("document.title"), accessor: (row: LibraryDocument) => row.name, sortable: true, width: "34%", render: (row: LibraryDocument) => {
      const ext = row.name.split(".").pop()?.toLowerCase() ?? "";
      const iconClass = EXTENSION_COLOR[ext] ?? "txt";
      return <div className="document-cell"><span className={`document-cell__icon document-cell__icon--${iconClass}`}><Icon name="file" size={18} /></span><div><strong>{row.name}</strong><span>{row.contentType || ext.toUpperCase()}</span></div></div>;
    } },
    { key: "category", label: t("document.category"), accessor: (row: LibraryDocument) => row.category, sortable: true, render: (row: LibraryDocument) => row.category ? <Badge tone="purple">{row.category}</Badge> : <span className="muted-cell">—</span> },
    { key: "uploader", label: t("document.uploader"), accessor: (row: LibraryDocument) => row.uploadedByIdentifier, sortable: true, render: (row: LibraryDocument) => <span>{row.uploadedByIdentifier || "—"}</span> },
    { key: "uploadedAt", label: t("document.modified"), accessor: (row: LibraryDocument) => row.uploadedAt, sortable: true, render: (row: LibraryDocument) => <span>{formatJalali(row.uploadedAt, { withTime: true })}</span> },
    { key: "size", label: t("document.size"), accessor: (row: LibraryDocument) => row.sizeBytes, sortable: true, render: (row: LibraryDocument) => <span>{formatBytes(row.sizeBytes)}</span> },
    { key: "actions", label: t("project.actions"), hideable: false, render: (row: LibraryDocument) => <div className="list-toolbar">
      <Button variant="ghost" size="sm" icon="download" onClick={() => download(row)}>{t("document.download")}</Button>
      <PermissionGuard permission={PERMISSIONS.maintenanceDocumentManage}>
        <Button variant="ghost" size="sm" icon="close" onClick={() => setConfirmDelete(row)}>{t("document.delete")}</Button>
      </PermissionGuard>
    </div> },
  // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [t]);

  return <div className="page">
    <SectionHeader eyebrow={t("nav.documents")} title={t("document.title")} subtitle={t("document.subtitle")} actions={<PermissionGuard permission={PERMISSIONS.maintenanceDocumentUpload}><Button variant="primary" icon="upload" onClick={() => setUploadOpen(true)}>{t("document.upload")}</Button></PermissionGuard>} />
    <div className="file-stats">
      <div><span>{t("document.title")}</span><strong>{documents.length}</strong></div>
      <div><span>{t("document.category")}</span><strong>{categories.length}</strong></div>
      <div><span>{t("document.size")}</span><strong>{formatBytes(documents.reduce((sum, doc) => sum + doc.sizeBytes, 0))}</strong></div>
    </div>
    <Card className="content-card" padding="none"><CardHeader title={`${documents.length} ${t("document.title").toLowerCase()}`} action={<div className="list-toolbar">
      <div className="search-box"><Icon name="search" size={16} /><input value={search} aria-label={t("document.search")} placeholder={t("document.search")} onChange={(event) => setSearch(event.target.value)} /></div>
      <SelectInput aria-label={t("document.category")} value={category} onChange={(event) => setCategory(event.target.value)} options={[{ value: "all", label: t("document.category") }, ...categories.map((item) => ({ value: item, label: item }))]} />
    </div>} />
      <DataTable columns={columns} data={documents} rowKey={(row) => row.id} search="" exportName="tekarai-documents" empty={{ title: loading ? t("common.loading") : t("document.empty") }} />
    </Card>
    <Modal open={uploadOpen} title={t("document.uploadTitle")} onClose={closeUpload} footer={<Button variant="primary" onClick={closeUpload}>{t("common.close")}</Button>}>
      <TextInput label={t("document.category")} placeholder={t("document.category")} value={uploadCategory} onChange={(event) => setUploadCategory(event.target.value)} />
      <FileUpload onFiles={handleFiles} />
      {uploads.length > 0 && <div className="upload-list">{uploads.map((upload) => <UploadProgress key={upload.name} fileName={upload.name} progress={upload.progress} state={upload.state} />)}</div>}
    </Modal>
    <Modal open={confirmDelete !== null} title={t("document.delete")} onClose={() => setConfirmDelete(null)} footer={<>
      <Button variant="secondary" onClick={() => setConfirmDelete(null)}>{t("common.cancel")}</Button>
      <Button variant="primary" onClick={remove}>{t("document.delete")}</Button>
    </>}><p>{t("document.deleteConfirm")}</p><p><strong>{confirmDelete?.name}</strong></p></Modal>
    {selected && <Modal open title={t("document.title")} onClose={() => setSelected(null)}><DocumentViewer document={selected as never} onClose={() => setSelected(null)} /></Modal>}
    {toast && <Toast message={toast} onClose={() => setToast("")} />}
  </div>;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
