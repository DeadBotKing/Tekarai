import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Button, IconButton } from "./primitives";
import { Icon } from "./Icon";
import { useLocalization } from "../../core/localization/localizationContext";

/**
 * How many modals are open right now. A modal opened from inside another
 * one (the warehouse part form launched from the purchase requisition
 * form) used to render at the same `--z-overlay` as its parent, so
 * whichever happened to sit later in the JSX painted on top — the nested
 * dialog could open *behind* the one that launched it. Each level now
 * stacks one step higher.
 */
let openModalCount = 0;

export function Modal({ open, title, description, onClose, children, footer, wide = false }: { open: boolean; title: string; description?: string; onClose: () => void; children: ReactNode; footer?: ReactNode; wide?: boolean }): JSX.Element | null {
  const { t } = useLocalization();
  // Unique per instance: two open modals both using id="modal-title" made
  // `aria-labelledby` ambiguous, so screen readers announced the wrong one.
  const titleId = useId();
  const [depth, setDepth] = useState(0);
  const bodyOverflow = useRef("");
  useEffect(() => {
    if (!open) return;
    openModalCount += 1;
    setDepth(openModalCount);
    const onKey = (event: KeyboardEvent): void => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    // Only the first modal owns the scroll lock, so closing a nested dialog
    // cannot hand scrolling back while its parent is still open.
    if (openModalCount === 1) { bodyOverflow.current = document.body.style.overflow; document.body.style.overflow = "hidden"; }
    return () => {
      document.removeEventListener("keydown", onKey);
      openModalCount = Math.max(0, openModalCount - 1);
      if (openModalCount === 0) document.body.style.overflow = bodyOverflow.current;
    };
  }, [onClose, open]);
  if (!open) return null;
  return <div className="overlay" role="presentation" style={depth > 1 ? { zIndex: `calc(var(--z-overlay) + ${depth})` } : undefined} onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className={wide ? "modal modal--wide" : "modal"} role="dialog" aria-modal="true" aria-labelledby={titleId}>
      <header className="modal__header"><div><h2 id={titleId}>{title}</h2>{description && <p>{description}</p>}</div><IconButton icon="close" label={t("common.close")} onClick={onClose} /></header>
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
