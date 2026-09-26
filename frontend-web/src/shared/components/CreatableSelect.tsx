import { useEffect, useId, useState } from "react";
import { Icon } from "./Icon";
import { useLocalization } from "../../core/localization/localizationContext";
import {
  MAX_OPTION_LENGTH,
  forgetOption,
  rememberOption,
  validateOption,
  type OptionCatalogKey,
  type SelectOption,
} from "../../features/maintenance/optionCatalog";

/** Sentinel option value — chosen from the list, it opens the inline editor. */
const ADD_SENTINEL = "__addOption__";

export interface CreatableSelectProps {
  label?: string;
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  /** Where locally added options are remembered (omit to keep them for this form only). */
  catalogKey?: OptionCatalogKey;
  /** Values that came with the product and therefore cannot be deleted. */
  canonical?: readonly string[];
  name?: string;
  required?: boolean;
  disabled?: boolean;
  error?: string;
  hint?: string;
  className?: string;
  /** Overrides the default «افزودن مورد جدید…» entry. */
  addLabel?: string;
}

/**
 * A dropdown that is not a closed list: the last entry opens a small inline
 * field where the user types a value of their own, which is then selected,
 * remembered for this browser, and sent to the API like any other value.
 */
export function CreatableSelect({
  label,
  value,
  options,
  onChange,
  catalogKey,
  canonical = [],
  name,
  required,
  disabled,
  error,
  hint,
  className = "",
  addLabel,
}: CreatableSelectProps): JSX.Element {
  const { t } = useLocalization();
  const generatedId = useId().replace(/:/g, "");
  const inputId = `creatable-${name ?? generatedId}`;
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState("");
  const [localError, setLocalError] = useState("");

  useEffect(() => {
    if (disabled) setAdding(false);
  }, [disabled]);

  const commit = (): void => {
    const outcome = validateOption(
      draft,
      options.map((option) => option.value),
    );
    if (!outcome.ok) {
      if (outcome.reason === "duplicate") {
        // Already in the list: just select it instead of complaining.
        const existing = options.find(
          (option) => option.value.toLocaleLowerCase() === draft.trim().toLocaleLowerCase(),
        );
        if (existing) {
          onChange(existing.value);
          setAdding(false);
          setDraft("");
          setLocalError("");
          return;
        }
      }
      setLocalError(
        outcome.reason === "tooLong"
          ? t("registry.option.tooLong")
          : t("registry.option.required"),
      );
      return;
    }
    if (catalogKey) rememberOption(catalogKey, outcome.value);
    onChange(outcome.value);
    setAdding(false);
    setDraft("");
    setLocalError("");
  };

  const cancel = (): void => {
    setAdding(false);
    setDraft("");
    setLocalError("");
  };

  const removeCurrent = (): void => {
    if (!catalogKey || !value) return;
    forgetOption(catalogKey, value);
    const fallback = options.find((option) => option.value !== value);
    onChange(fallback ? fallback.value : "");
  };

  const isCustomValue =
    Boolean(value) && !canonical.some((code) => code.toLocaleLowerCase() === value.toLocaleLowerCase());

  return (
    <label className={`field ${error || localError ? "has-error" : ""} ${className}`} htmlFor={inputId}>
      {label && (
        <span className="field__label">
          {label}
          {required && <span className="field__required">*</span>}
        </span>
      )}

      {adding ? (
        <span className="creatable-select__editor">
          <input
            id={inputId}
            className="creatable-select__input"
            value={draft}
            autoFocus
            maxLength={MAX_OPTION_LENGTH}
            placeholder={t("registry.option.placeholder")}
            aria-label={t("registry.option.newValue")}
            onChange={(event) => {
              setDraft(event.target.value);
              setLocalError("");
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                commit();
              }
              if (event.key === "Escape") {
                event.preventDefault();
                cancel();
              }
            }}
          />
          <button
            type="button"
            className="creatable-select__action creatable-select__action--confirm"
            onClick={commit}
            aria-label={t("registry.option.confirm")}
            title={t("registry.option.confirm")}
          >
            <Icon name="check" size={15} />
          </button>
          <button
            type="button"
            className="creatable-select__action"
            onClick={cancel}
            aria-label={t("registry.option.cancel")}
            title={t("registry.option.cancel")}
          >
            <Icon name="close" size={15} />
          </button>
        </span>
      ) : (
        <span className="creatable-select">
          <span className="field__control field__control--select">
            <select
              id={inputId}
              name={name}
              value={value}
              disabled={disabled}
              required={required}
              aria-invalid={Boolean(error || localError)}
              onChange={(event) => {
                if (event.target.value === ADD_SENTINEL) {
                  setAdding(true);
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
              <option value={ADD_SENTINEL}>{addLabel ?? t("registry.option.add")}</option>
            </select>
            <Icon name="chevronDown" className="field__select-icon" size={16} />
          </span>
          {isCustomValue && catalogKey && (
            <button
              type="button"
              className="creatable-select__action"
              onClick={removeCurrent}
              aria-label={t("registry.option.remove")}
              title={t("registry.option.remove")}
            >
              <Icon name="xCircle" size={15} />
            </button>
          )}
        </span>
      )}

      {(error || localError || hint) && (
        <span className={`field__message ${error || localError ? "field__message--error" : ""}`}>
          {error || localError || hint}
        </span>
      )}
    </label>
  );
}
