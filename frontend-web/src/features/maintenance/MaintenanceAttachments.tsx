import { useCallback, useEffect, useId, useState } from "react";
import { runtimeConfig } from "../../app/configuration/runtimeConfig";
import { formatJalali } from "../../core/localization/jalali";
import { PERMISSIONS } from "../../core/permissions/permissionContext";
import type {
  MaintenanceAttachment,
  MaintenanceAttachmentCategory,
} from "../../shared/types/domain";
import { Icon } from "../../shared/components/Icon";
import { Badge, Button, PermissionGuard, SelectInput } from "../../shared/components/primitives";
import type { MaintenanceService } from "./maintenanceService";

interface MaintenanceAttachmentsProps {
  targetType: "device" | "workOrder";
  targetId: string;
  service: MaintenanceService;
  onMessage: (message: string) => void;
}

const CATEGORY_OPTIONS: { value: MaintenanceAttachmentCategory; label: string }[] = [
  { value: "failurePhoto", label: "عکس خرابی" },
  { value: "manual", label: "دفترچه راهنما" },
  { value: "invoice", label: "فاکتور" },
  { value: "other", label: "سایر" },
];

const categoryLabel = (category: MaintenanceAttachmentCategory): string =>
  CATEGORY_OPTIONS.find((item) => item.value === category)?.label ?? "سایر";

const fileSize = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} بایت`;
  if (bytes < 1024 * 1024) return `${Math.ceil(bytes / 1024)} کیلوبایت`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} مگابایت`;
};

export function MaintenanceAttachments({
  targetType,
  targetId,
  service,
  onMessage,
}: MaintenanceAttachmentsProps): JSX.Element {
  const inputId = `maintenance-attachment-${useId().replace(/:/g, "")}`;
  const [attachments, setAttachments] = useState<MaintenanceAttachment[]>([]);
  const [category, setCategory] = useState<MaintenanceAttachmentCategory>("failurePhoto");
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [loading, setLoading] = useState(!runtimeConfig.demoMode);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);

  const load = useCallback(async (): Promise<void> => {
    if (runtimeConfig.demoMode) return;
    setLoading(true);
    try {
      setAttachments(await service.listAttachments(targetType, targetId));
    } catch (error) {
      onMessage(error instanceof Error ? error.message : "بارگذاری پیوست‌ها ناموفق بود.");
    } finally {
      setLoading(false);
    }
  }, [onMessage, service, targetId, targetType]);

  useEffect(() => {
    void load();
  }, [load]);

  const upload = async (): Promise<void> => {
    if (selectedFiles.length === 0) return;
    setUploading(true);
    setProgress(0);
    try {
      if (runtimeConfig.demoMode) {
        const now = new Date().toISOString();
        setAttachments((current) => [
          ...selectedFiles.map((file, index) => ({
            id: `attachment-${Date.now()}-${index}`,
            targetType,
            targetId,
            category,
            originalName: file.name,
            mimeType: file.type,
            sizeBytes: file.size,
            uploadedAt: now,
            downloadUrl: "",
          })),
          ...current,
        ]);
      } else {
        for (let index = 0; index < selectedFiles.length; index += 1) {
          const file = selectedFiles[index];
          await service.uploadAttachment(
            targetType,
            targetId,
            category,
            file,
            (fileProgress) =>
              setProgress(Math.round(((index + fileProgress / 100) / selectedFiles.length) * 100)),
          );
        }
        await load();
      }
      setSelectedFiles([]);
      setProgress(100);
      onMessage("فایل با موفقیت پیوست شد.");
    } catch (error) {
      onMessage(error instanceof Error ? error.message : "بارگذاری فایل ناموفق بود.");
    } finally {
      setUploading(false);
    }
  };

  const openAttachment = async (attachment: MaintenanceAttachment): Promise<void> => {
    if (runtimeConfig.demoMode) {
      onMessage("پیش‌نمایش فایل در حالت نمایشی در دسترس نیست.");
      return;
    }
    const previewable =
      attachment.mimeType.startsWith("image/") || attachment.mimeType === "application/pdf";
    const previewWindow = previewable ? window.open("", "_blank") : null;
    try {
      const blob = await service.downloadAttachment(attachment.id);
      const url = URL.createObjectURL(blob);
      if (previewWindow) {
        previewWindow.location.href = url;
      } else {
        const link = document.createElement("a");
        link.href = url;
        link.download = attachment.originalName;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      }
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (error) {
      previewWindow?.close();
      onMessage(error instanceof Error ? error.message : "دریافت فایل ناموفق بود.");
    }
  };

  const removeAttachment = async (attachment: MaintenanceAttachment): Promise<void> => {
    if (!window.confirm(`پیوست «${attachment.originalName}» حذف شود؟`)) return;
    try {
      if (!runtimeConfig.demoMode) await service.deleteAttachment(attachment.id);
      setAttachments((current) => current.filter((item) => item.id !== attachment.id));
      onMessage("پیوست حذف شد.");
    } catch (error) {
      onMessage(error instanceof Error ? error.message : "حذف پیوست ناموفق بود.");
    }
  };

  return (
    <section className="maintenance-attachments">
      <div className="maintenance-attachments__heading">
        <div>
          <h4>پیوست‌ها</h4>
          <p>عکس خرابی، دفترچه راهنما، فاکتور یا سایر اسناد مرتبط</p>
        </div>
        <Badge tone="neutral">{attachments.length} فایل</Badge>
      </div>

      <PermissionGuard permission={PERMISSIONS.maintenanceAttachmentManage}>
        <div className="maintenance-attachments__upload">
          <SelectInput
            label="نوع پیوست"
            value={category}
            onChange={(event) => setCategory(event.target.value as MaintenanceAttachmentCategory)}
            options={CATEGORY_OPTIONS}
          />
          <div className="field">
            <span className="field__label">انتخاب فایل</span>
            <label className="attachment-file-picker" htmlFor={inputId}>
              <Icon name="paperclip" size={17} />
              <span>
                {selectedFiles.length > 0
                  ? `${selectedFiles.length} فایل انتخاب شد`
                  : "انتخاب عکس یا سند"}
              </span>
            </label>
            <input
              id={inputId}
              className="attachment-file-input"
              type="file"
              multiple
              accept="image/jpeg,image/png,image/webp,application/pdf,.doc,.docx,.xls,.xlsx,.txt"
              onChange={(event) => setSelectedFiles(Array.from(event.target.files ?? []))}
            />
          </div>
          <Button
            variant="primary"
            icon="upload"
            disabled={selectedFiles.length === 0 || uploading}
            onClick={upload}
          >
            {uploading ? `در حال بارگذاری ${progress}٪` : "پیوست فایل"}
          </Button>
        </div>
        {selectedFiles.length > 0 && (
          <div className="attachment-selection">
            {selectedFiles.map((file) => (
              <span key={`${file.name}-${file.lastModified}`}>{file.name} · {fileSize(file.size)}</span>
            ))}
          </div>
        )}
      </PermissionGuard>

      {loading ? (
        <p className="detail-panel__description">در حال بارگذاری پیوست‌ها…</p>
      ) : attachments.length === 0 ? (
        <div className="attachment-empty">
          <Icon name="paperclip" size={21} />
          <span>هنوز فایلی پیوست نشده است.</span>
        </div>
      ) : (
        <div className="attachment-list">
          {attachments.map((attachment) => (
            <article className="attachment-item" key={attachment.id}>
              <span className="attachment-item__icon">
                <Icon name={attachment.mimeType.startsWith("image/") ? "file" : "paperclip"} size={18} />
              </span>
              <div className="attachment-item__body">
                <strong>{attachment.originalName}</strong>
                <span>
                  {categoryLabel(attachment.category)} · {fileSize(attachment.sizeBytes)} ·{" "}
                  {formatJalali(attachment.uploadedAt, { withTime: true })}
                </span>
              </div>
              <Button variant="ghost" size="sm" icon="download" onClick={() => void openAttachment(attachment)}>
                مشاهده
              </Button>
              <PermissionGuard permission={PERMISSIONS.maintenanceAttachmentManage}>
                <Button variant="ghost" size="sm" icon="close" onClick={() => void removeAttachment(attachment)}>
                  حذف
                </Button>
              </PermissionGuard>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
