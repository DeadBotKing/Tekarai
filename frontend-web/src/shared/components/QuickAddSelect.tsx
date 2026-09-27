import { useId } from "react";
import { Icon } from "./Icon";
import type { SelectOption } from "../../features/maintenance/optionCatalog";

/**
 * Sentinel option value — choosing it opens the quick-create flow instead of
 * selecting a real record.
 */
const ADD_SENTINEL = "__quickAddNew__";

export interface QuickAddSelectProps {
  label?: string;
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  /** Opens the quick-create flow (modal) for the referenced entity. */
  onQuickAdd: () => void;
  /** Text of the inline «➕ افزودن…» dropdown entry — e.g. «➕ افزودن دستگاه جدید…». */
  addLabel: string;
  name?: string;
  required?: boolean;
  disabled?: boolean;
  ariaLabel?: string;
  className?: string;
}

/**
 * A record picker whose last dropdown entry is a «➕ افزودن…» action: if the
 * record the user needs does not exist yet, they never leave the form — they
 * pick the entry, the quick-create modal opens, and the brand-new record is
 * selected automatically once saved. The same contract everywhere:
 * device, spare part, location and personnel pickers all use this component.
 */
export function QuickAddSelect({
  label,
  value,
  options,
  onChange,
  onQuickAdd,
  addLabel,
  name,
  required,
  disabled,
  ariaLabel,
  className = "",
}: QuickAddSelectProps): JSX.Element {
  const generatedId = useId().replace(/:/g, "");
  const inputId = `quick-add-${name ?? generatedId}`;

  return (
    <label className={`field ${className}`} htmlFor={inputId}>
      {label && (
        <span className="field__label">
          {label}
          {required && <span className="field__required">*</span>}
        </span>
      )}
      <span className="creatable-select">
        <span className="field__control field__control--select">
          <select
            id={inputId}
            name={name}
            value={value}
            disabled={disabled}
            required={required}
            aria-label={ariaLabel ?? label}
            onChange={(event) => {
              if (event.target.value === ADD_SENTINEL) {
                // Leave the current selection untouched; only open creation.
                onQuickAdd();
                return;
              }
              onChange(event.target.value);
            }}
          >
            {options.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
            <option value={ADD_SENTINEL}>{addLabel}</option>
          </select>
          <Icon name="chevronDown" className="field__select-icon" size={16} />
        </span>
      </span>
    </label>
  );
}
