import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApiClient } from "../../core/api/apiContext";
import { triggerDownload } from "../../core/files/downloadUtils";
import { PERMISSIONS, usePermissions } from "../../core/permissions/permissionContext";
import { runtimeConfig } from "../../app/configuration/runtimeConfig";
import { Button } from "../../shared/components/primitives";
import { createDocumentService, type LibraryDocument } from "./documentService";

/** Read-only equipment projection. Upload/edit/delete exist only in Documents. */
export function DeviceDocuments({ deviceId, onMessage }: { deviceId: string; onMessage: (message: string) => void }): JSX.Element {
  const api = useApiClient();
  const service = useMemo(() => createDocumentService(api), [api]);
  const navigate = useNavigate();
  const { has } = usePermissions();
  const [documents, setDocuments] = useState<LibraryDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setDocuments([]); setLoading(true); setFailed(false);
    if (runtimeConfig.demoMode) { setLoading(false); return; }
    service.list({ deviceId }, controller.signal).then(rows => { if (!controller.signal.aborted) setDocuments(rows); })
      .catch(() => { if (!controller.signal.aborted) { setFailed(true); onMessage("دریافت مدارک مرتبط ناموفق بود."); } })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [deviceId, service, onMessage]);
  const download = async (doc: LibraryDocument): Promise<void> => {
    try { triggerDownload(await service.download(doc.id), doc.name); }
    catch { onMessage("دریافت مدرک ناموفق بود."); }
  };
  return <div>
    <p className="muted-cell">مدارک این دستگاه از اسناد مرکزی نمایش داده می‌شوند. ثبت و مدیریت مدرک فقط در بخش «اسناد» انجام می‌شود.</p>
    {has(PERMISSIONS.maintenanceDocumentView) && <Button variant="secondary" icon="file" onClick={() => navigate(`/app/documents?deviceId=${encodeURIComponent(deviceId)}`)}>رفتن به اسناد این دستگاه</Button>}
    {loading ? <p>در حال بارگذاری…</p> : failed ? <p>بارگذاری مدارک ناموفق بود؛ صفحه را دوباره باز کنید.</p> : !documents.length ? <p>مدرک مرتبطی برای نمایش وجود ندارد.</p> : <ul className="registry-plan-list">{documents.map(doc => <li key={doc.id}>
      <div><strong>{doc.name}</strong><p className="muted-cell">{doc.category}{doc.description ? ` — ${doc.description}` : ""}</p></div>
      <Button variant="ghost" icon="download" onClick={() => void download(doc)}>دریافت مدرک</Button>
    </li>)}</ul>}
  </div>;
}
