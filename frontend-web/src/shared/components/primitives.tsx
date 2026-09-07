import { forwardRef, useId, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from "react";
import { Icon, type IconName } from "./Icon";
import { useLocalization } from "../../core/localization/localizationContext";
import type { TranslationKey } from "../../core/localization/i18n";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "subtle";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: "sm" | "md" | "lg";
  icon?: IconName;
  iconAfter?: IconName;
  loading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button({
  children, variant = "secondary", size = "md", icon, iconAfter, loading = false, className = "", disabled, ...props
}, ref) {
  return (
    <button ref={ref} className={`button button--${variant} button--${size} ${className}`} disabled={disabled || loading} {...props}>
      {loading && <span className="spinner spinner--inline" aria-hidden="true" />}
      {!loading && icon && <Icon name={icon} size={size === "sm" ? 15 : 17} />}
      <span>{children}</span>
      {!loading && iconAfter && <Icon name={iconAfter} size={size === "sm" ? 15 : 17} />}
    </button>
  );
});

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon: IconName;
  label: string;
  active?: boolean;
  size?: "sm" | "md" | "lg";
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton({ icon, label, active = false, size = "md", className = "", ...props }, ref) {
  return (
    <button ref={ref} type="button" aria-label={label} title={label} className={`icon-button icon-button--${size} ${active ? "is-active" : ""} ${className}`} {...props}>
      <Icon name={icon} size={size === "sm" ? 16 : size === "lg" ? 22 : 18} />
    </button>
  );
});

interface TextInputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: string;
  error?: string;
  icon?: IconName;
  trailing?: ReactNode;
}

export const TextInput = forwardRef<HTMLInputElement, TextInputProps>(function TextInput({ label, hint, error, icon, trailing, id, className = "", ...props }, ref) {
  const generatedId = useId().replace(/:/g, "");
  const inputId = id ?? `input-${props.name ?? generatedId}`;
  return (
    <label className={`field ${error ? "has-error" : ""} ${className}`} htmlFor={inputId}>
      {label && <span className="field__label">{label}{props.required && <span className="field__required">*</span>}</span>}
      <span className="field__control">
        {icon && <Icon name={icon} className="field__icon" size={17} />}
        <input ref={ref} id={inputId} aria-invalid={Boolean(error)} aria-describedby={hint || error ? `${inputId}-hint` : undefined} {...props} />
        {trailing}
      </span>
      {(hint || error) && <span id={`${inputId}-hint`} className={`field__message ${error ? "field__message--error" : ""}`}>{error ?? hint}</span>}
    </label>
  );
});

interface SelectInputProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
  options: { value: string; label: string }[];
}

export const SelectInput = forwardRef<HTMLSelectElement, SelectInputProps>(function SelectInput({ label, error, options, id, className = "", ...props }, ref) {
  const generatedId = useId().replace(/:/g, "");
  const inputId = id ?? `select-${props.name ?? generatedId}`;
  return (
    <label className={`field ${error ? "has-error" : ""} ${className}`} htmlFor={inputId}>
      {label && <span className="field__label">{label}{props.required && <span className="field__required">*</span>}</span>}
      <span className="field__control field__control--select">
        <select ref={ref} id={inputId} aria-invalid={Boolean(error)} {...props}>
          {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
        <Icon name="chevronDown" className="field__select-icon" size={16} />
      </span>
      {error && <span className="field__message field__message--error">{error}</span>}
    </label>
  );
});

interface TextAreaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  hint?: string;
  error?: string;
}

export const TextArea = forwardRef<HTMLTextAreaElement, TextAreaProps>(function TextArea({ label, hint, error, id, className = "", ...props }, ref) {
  const generatedId = useId().replace(/:/g, "");
  const inputId = id ?? `textarea-${props.name ?? generatedId}`;
  return (
    <label className={`field ${error ? "has-error" : ""} ${className}`} htmlFor={inputId}>
      {label && <span className="field__label">{label}{props.required && <span className="field__required">*</span>}</span>}
      <textarea ref={ref} id={inputId} aria-invalid={Boolean(error)} aria-describedby={hint || error ? `${inputId}-hint` : undefined} {...props} />
      {(hint || error) && <span id={`${inputId}-hint`} className={`field__message ${error ? "field__message--error" : ""}`}>{error ?? hint}</span>}
    </label>
  );
});

export function Card({ children, className = "", padding = "md", ...props }: { children: ReactNode; className?: string; padding?: "none" | "sm" | "md" | "lg" } & React.HTMLAttributes<HTMLElement>): JSX.Element {
  return <section className={`card card--padding-${padding} ${className}`} {...props}>{children}</section>;
}

export function CardHeader({ title, subtitle, action, icon }: { title: string; subtitle?: string; action?: ReactNode; icon?: IconName }): JSX.Element {
  return <header className="card__header">
    <div className="card__heading">
      {icon && <span className="card__heading-icon"><Icon name={icon} size={17} /></span>}
      <div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>
    </div>
    {action && <div className="card__action">{action}</div>}
  </header>;
}

export function Badge({ children, tone = "neutral", dot = false, className = "" }: { children: ReactNode; tone?: "neutral" | "success" | "warning" | "danger" | "info" | "purple"; dot?: boolean; className?: string }): JSX.Element {
  return <span className={`badge badge--${tone} ${className}`}>{dot && <span className="badge__dot" aria-hidden="true" />}{children}</span>;
}

export function StatusBadge({ status }: { status: string }): JSX.Element {
  const { t } = useLocalization();
  const statusKey: Record<string, TranslationKey> = {
    active: "common.status.active", inProgress: "common.status.inProgress", completed: "common.status.completed", atRisk: "common.status.atRisk", pending: "common.status.pending", archived: "common.status.archived", queued: "common.status.queued", running: "common.status.running", failed: "common.status.failed",
  };
  const tone = status === "atRisk" || status === "failed" ? "danger" : status === "pending" || status === "queued" ? "warning" : status === "completed" || status === "active" ? "success" : "info";
  return <Badge tone={tone} dot>{t(statusKey[status] ?? "common.status.pending")}</Badge>;
}

export function ProgressBar({ value, tone = "blue", label, showValue = true }: { value: number; tone?: "blue" | "green" | "amber" | "purple"; label?: string; showValue?: boolean }): JSX.Element {
  const safeValue = Math.max(0, Math.min(100, value));
  return <div className="progress-wrap">
    {(label || showValue) && <div className="progress-wrap__meta">{label && <span>{label}</span>}{showValue && <strong>{safeValue}%</strong>}</div>}
    <div className="progress" role="progressbar" aria-valuenow={safeValue} aria-valuemin={0} aria-valuemax={100} aria-label={label}><span className={`progress__bar progress__bar--${tone}`} style={{ width: `${safeValue}%` }} /></div>
  </div>;
}

export function Avatar({ name, size = "md", tone = "blue", src }: { name: string; size?: "sm" | "md" | "lg"; tone?: "blue" | "green" | "purple" | "amber" | "pink"; src?: string }): JSX.Element {
  const initials = name.split(" ").map((part) => part[0]).join("").slice(0, 2).toUpperCase();
  return src ? <img className={`avatar avatar--${size}`} src={src} alt={name} /> : <span className={`avatar avatar--${size} avatar--${tone}`} aria-label={name} title={name}>{initials}</span>;
}

export function MetricCard({ label, value, trend, trendLabel, icon, tone = "blue" }: { label: string; value: string | number; trend?: string; trendLabel?: string; icon: IconName; tone?: "blue" | "green" | "purple" | "amber" }): JSX.Element {
  return <Card className="metric-card" padding="md">
    <div className="metric-card__top"><span className={`metric-card__icon metric-card__icon--${tone}`}><Icon name={icon} size={19} /></span>{trend && <span className={`metric-card__trend ${trend.startsWith("-") ? "is-negative" : ""}`}><Icon name={trend.startsWith("-") ? "arrowDown" : "arrowUp"} size={13} />{trend}</span>}</div>
    <div className="metric-card__value">{value}</div>
    <div className="metric-card__label">{label}</div>
    {trendLabel && <div className="metric-card__hint">{trendLabel}</div>}
  </Card>;
}

export function SectionHeader({ eyebrow, title, subtitle, actions }: { eyebrow?: string; title: string; subtitle?: string; actions?: ReactNode }): JSX.Element {
  return <div className="section-header">
    <div><div className="section-header__eyebrow">{eyebrow}</div><h1>{title}</h1>{subtitle && <p>{subtitle}</p>}</div>
    {actions && <div className="section-header__actions">{actions}</div>}
  </div>;
}

export function LoadingState({ label }: { label: string }): JSX.Element {
  return <div className="state state--loading" role="status"><span className="spinner" aria-hidden="true" /><span>{label}</span></div>;
}

export function EmptyState({ icon = "folder", title, description, action }: { icon?: IconName; title: string; description?: string; action?: ReactNode }): JSX.Element {
  return <div className="state state--empty"><span className="state__icon"><Icon name={icon} size={24} /></span><h3>{title}</h3>{description && <p>{description}</p>}{action}</div>;
}

export function ErrorState({ title, description, retry }: { title: string; description: string; retry?: () => void }): JSX.Element {
  return <div className="state state--error" role="alert"><span className="state__icon"><Icon name="warning" size={24} /></span><h3>{title}</h3><p>{description}</p>{retry && <Button variant="secondary" icon="refresh" onClick={retry}>Retry</Button>}</div>;
}

export function Divider(): JSX.Element { return <div className="divider" />; }

export { PermissionGuard } from "./PermissionGuard";
