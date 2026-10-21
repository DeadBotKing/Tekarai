import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { Button, IconButton } from "./primitives";
import { Icon } from "./Icon";
import { useLocalization } from "../../core/localization/localizationContext";

/**
 * Activation-ordered layers for open dialogs. Keep the order stable across
 * parent re-renders: inline `onClose` callbacks change identity on each
 * render and must not cause an already-open dialog to re-enter the stack.
 */
const activeModalLayers = new Map<string, number>();
let nextModalLayer = 0;
let bodyOverflowBeforeFirstModal: string | null = null;

export function Modal({ open, title, description, onClose, children, footer, wide = false, className = "" }: { open: boolean; title: string; description?: string; onClose: () => void; children: ReactNode; footer?: ReactNode; wide?: boolean; className?: string }): JSX.Element | null {
  const { t } = useLocalization();
  // Unique per instance: two open modals both using id="modal-title" made
  // `aria-labelledby` ambiguous, so screen readers announced the wrong one.
  const titleId = useId();
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const [depth, setDepth] = useState(0);
  useLayoutEffect(() => {
    if (!open) return;
    if (activeModalLayers.size === 0) {
      bodyOverflowBeforeFirstModal = document.body.style.overflow;
      document.body.style.overflow = "hidden";
    }
    const layer = ++nextModalLayer;
    activeModalLayers.set(titleId, layer);
    setDepth(layer);
    const onKey = (event: KeyboardEvent): void => {
      if (event.key !== "Escape") return;
      const topLayer = Math.max(...activeModalLayers.values());
      if (activeModalLayers.get(titleId) === topLayer) onCloseRef.current();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      activeModalLayers.delete(titleId);
      if (activeModalLayers.size === 0) {
        document.body.style.overflow = bodyOverflowBeforeFirstModal ?? "";
        bodyOverflowBeforeFirstModal = null;
        nextModalLayer = 0;
      }
    };
  }, [open, titleId]);
  if (!open) return null;
  return <div className="overlay" role="presentation" style={depth > 1 ? { zIndex: `calc(var(--z-overlay) + ${depth})` } : undefined} onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className={["modal", wide ? "modal--wide" : "", className].filter(Boolean).join(" ")} role="dialog" aria-modal="true" aria-labelledby={titleId}>
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

export function Toast({ message, tone = "success", onClose, sticker }: { message: string; tone?: "success" | "error" | "info"; onClose?: () => void; sticker?: ReactNode }): JSX.Element {
  return <div className={`toast toast--${tone}`} role="status">{sticker ? <span className="toast__sticker">{sticker}</span> : <Icon name={tone === "success" ? "checkCircle" : tone === "error" ? "xCircle" : "bell"} size={17} />}<span>{message}</span>{onClose && <button type="button" aria-label="Dismiss" className="toast__close" onClick={onClose}>×</button>}</div>;
}
