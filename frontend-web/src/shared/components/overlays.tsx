import { useEffect, type ReactNode } from "react";
import { Button, IconButton } from "./primitives";
import { Icon } from "./Icon";
import { useLocalization } from "../../core/localization/localizationContext";

export function Modal({ open, title, description, onClose, children, footer }: { open: boolean; title: string; description?: string; onClose: () => void; children: ReactNode; footer?: ReactNode }): JSX.Element | null {
  const { t } = useLocalization();
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent): void => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = previous; };
  }, [onClose, open]);
  if (!open) return null;
  return <div className="overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
      <header className="modal__header"><div><h2 id="modal-title">{title}</h2>{description && <p>{description}</p>}</div><IconButton icon="close" label={t("common.close")} onClick={onClose} /></header>
      <div className="modal__body">{children}</div>
      {footer && <footer className="modal__footer">{footer}</footer>}
    </section>
  </div>;
}

export function Drawer({ open, title, onClose, children, side = "end" }: { open: boolean; title: string; onClose: () => void; children: ReactNode; side?: "start" | "end" }): JSX.Element | null {
  const { t } = useLocalization();
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent): void => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose, open]);
  if (!open) return null;
  return <div className="overlay overlay--drawer" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <aside className={`drawer drawer--${side}`} role="dialog" aria-modal="true" aria-labelledby="drawer-title">
      <header className="drawer__header"><h2 id="drawer-title">{title}</h2><IconButton icon="close" label={t("common.close")} onClick={onClose} /></header>
      <div className="drawer__body">{children}</div>
    </aside>
  </div>;
}

export function ConfirmDialog({ open, title, description, onConfirm, onClose, danger = false }: { open: boolean; title: string; description: string; onConfirm: () => void; onClose: () => void; danger?: boolean }): JSX.Element | null {
  const { t } = useLocalization();
  return <Modal open={open} title={title} description={description} onClose={onClose} footer={<><Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button><Button variant={danger ? "danger" : "primary"} onClick={onConfirm}>{t("common.save")}</Button></>}><div className="confirm-dialog"><span className="confirm-dialog__icon"><Icon name={danger ? "warning" : "shield"} size={22} /></span><p>{description}</p></div></Modal>;
}

export function Toast({ message, tone = "success", onClose }: { message: string; tone?: "success" | "error" | "info"; onClose?: () => void }): JSX.Element {
  return <div className={`toast toast--${tone}`} role="status"><Icon name={tone === "success" ? "checkCircle" : tone === "error" ? "xCircle" : "bell"} size={17} /><span>{message}</span>{onClose && <button type="button" aria-label="Dismiss" className="toast__close" onClick={onClose}>×</button>}</div>;
}
