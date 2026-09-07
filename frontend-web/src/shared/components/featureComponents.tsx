import { useRef, useState, type ChangeEvent, type ReactNode } from "react";
import { useLocalization } from "../../core/localization/localizationContext";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import type { ActivityItem, DocumentRecord } from "../types/domain";
import { Button, Card, ProgressBar, SelectInput } from "./primitives";
import { Icon } from "./Icon";

export function SearchBox({ value, onChange, placeholder, onSubmit, autoFocus = false }: { value: string; onChange: (value: string) => void; placeholder: string; onSubmit?: (value: string) => void; autoFocus?: boolean }): JSX.Element {
  const { t } = useLocalization();
  const debouncedValue = useDebouncedValue(value, 280);
  return <div className="search-box"><Icon name="search" size={17} /><input value={value} autoFocus={autoFocus} aria-label={placeholder} placeholder={placeholder} onChange={(event) => { onChange(event.target.value); onSubmit?.(event.target.value); }} onKeyDown={(event) => { if (event.key === "Enter") onSubmit?.(debouncedValue); }} /><span className="search-box__shortcut">⌘ K</span>{value && <button type="button" className="search-box__clear" aria-label={t("common.clear")} onClick={() => onChange("")}>×</button>}</div>;
}

export function FilterPanel({ children, onClear, onApply }: { children: ReactNode; onClear?: () => void; onApply?: () => void }): JSX.Element {
  const { t } = useLocalization();
  return <div className="filter-panel"><div className="filter-panel__fields">{children}</div><div className="filter-panel__actions">{onClear && <Button variant="ghost" size="sm" onClick={onClear}>{t("common.clear")}</Button>}{onApply && <Button variant="primary" size="sm" onClick={onApply}>{t("common.apply")}</Button>}</div></div>;
}

export function ActivityFeed({ items, compact = false }: { items: ActivityItem[]; compact?: boolean }): JSX.Element {
  return <div className={`activity-feed ${compact ? "activity-feed--compact" : ""}`}>{items.map((item) => <div className="activity-item" key={item.id}><span className={`activity-item__marker activity-item__marker--${item.tone}`}><Icon name={item.tone === "green" ? "check" : item.tone === "amber" ? "lightbulb" : item.tone === "purple" ? "file" : "activity"} size={14} /></span><div className="activity-item__body"><p><strong>{item.actor}</strong> {item.action} <strong>{item.resource}</strong></p><span>{item.timestamp}</span></div></div>)}</div>;
}

export function Timeline({ events }: { events: { date: string; title: string; description: string; tone?: "blue" | "green" | "amber" }[] }): JSX.Element {
  return <div className="timeline">{events.map((event) => <div className="timeline-item" key={`${event.date}-${event.title}`}><span className={`timeline-item__dot timeline-item__dot--${event.tone ?? "blue"}`} /><div><span className="timeline-item__date">{event.date}</span><h3>{event.title}</h3><p>{event.description}</p></div></div>)}</div>;
}

export function FileUpload({ onFiles, maxSizeMb = 25, accept = ".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.txt" }: { onFiles: (files: File[]) => void; maxSizeMb?: number; accept?: string }): JSX.Element {
  const { t } = useLocalization();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");
  const handleFiles = (fileList: FileList | null): void => {
    const files = Array.from(fileList ?? []);
    const accepted = files.filter((file) => file.size <= maxSizeMb * 1024 * 1024);
    if (accepted.length !== files.length) setError(`Files must be smaller than ${maxSizeMb} MB.`);
    else setError("");
    if (accepted.length > 0) onFiles(accepted);
  };
  return <div className={`file-drop ${dragging ? "is-dragging" : ""} ${error ? "has-error" : ""}`} onDragEnter={(event) => { event.preventDefault(); setDragging(true); }} onDragOver={(event) => event.preventDefault()} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); handleFiles(event.dataTransfer.files); }}>
    <input ref={inputRef} type="file" hidden multiple accept={accept} onChange={(event) => handleFiles(event.target.files)} />
    <span className="file-drop__icon"><Icon name="upload" size={24} /></span><strong>{t("document.drop")}</strong><span>{t("document.dropHint")}</span><Button variant="secondary" size="sm" icon="folder" onClick={() => inputRef.current?.click()}>{t("document.browse")}</Button>{error && <span className="field__message field__message--error">{error}</span>}
  </div>;
}

export function UploadProgress({ fileName, progress, state }: { fileName: string; progress: number; state: "uploading" | "complete" | "error" }): JSX.Element {
  return <div className="upload-row"><span className="upload-row__icon"><Icon name={state === "complete" ? "checkCircle" : state === "error" ? "xCircle" : "file"} size={19} /></span><div className="upload-row__main"><div><strong>{fileName}</strong><span>{state === "complete" ? "Uploaded" : state === "error" ? "Upload failed" : `${progress}%`}</span></div><ProgressBar value={progress} showValue={false} tone={state === "error" ? "amber" : "blue"} /></div></div>;
}

export function DocumentViewer({ document, onClose }: { document: DocumentRecord; onClose: () => void }): JSX.Element {
  const { t } = useLocalization();
  return <div className="document-viewer"><div className="document-viewer__preview"><span className="document-viewer__large-icon"><Icon name="file" size={46} /></span><span>{document.type} preview</span><small>Preview is capability-aware. The original file remains in governed storage.</small></div><div className="document-viewer__meta"><div><span className="eyebrow">{t("document.viewer")}</span><h2>{document.name}</h2><p>{document.category} · {document.size}</p></div><Button variant="secondary" icon="download">{t("common.export")}</Button></div><div className="document-viewer__facts"><div><span>Owner</span><strong>{document.owner}</strong></div><div><span>Modified</span><strong>{document.modifiedAt}</strong></div><div><span>Classification</span><strong>Internal</strong></div></div><Button variant="ghost" onClick={onClose}>{t("common.close")}</Button></div>;
}

export function Stepper({ steps, current }: { steps: string[]; current: number }): JSX.Element {
  return <div className="stepper" aria-label="Progress"><ol>{steps.map((step, index) => <li key={step} className={index === current ? "is-current" : index < current ? "is-complete" : ""}><span>{index < current ? "✓" : index + 1}</span><strong>{step}</strong></li>)}</ol></div>;
}

export function MiniSelect({ value, onChange, options, label }: { value: string; onChange: (value: string) => void; options: { value: string; label: string }[]; label: string }): JSX.Element {
  return <SelectInput aria-label={label} value={value} onChange={(event: ChangeEvent<HTMLSelectElement>) => onChange(event.target.value)} options={options} />;
}

export function FileStat({ label, value, icon }: { label: string; value: string; icon: "file" | "clock" | "cloud" }): JSX.Element {
  return <Card className="file-stat" padding="sm"><Icon name={icon} size={18} /><div><strong>{value}</strong><span>{label}</span></div></Card>;
}
