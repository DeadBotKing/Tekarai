import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Icon } from "./Icon";
import {
  JALALI_MONTHS,
  JALALI_WEEKDAYS,
  formatJalali,
  gregorianToJalali,
  isoToJalaliParts,
  jalaliMonthLength,
  jalaliPartsToIso,
  toPersianDigits,
} from "../../core/localization/jalali";

interface JalaliDatePickerProps {
  label?: string;
  value: string; // ISO Gregorian YYYY-MM-DD ("" = empty)
  onChange: (isoDate: string) => void;
  required?: boolean;
  error?: string;
  hint?: string;
  className?: string;
  placeholder?: string;
  clearable?: boolean;
}

/** Column offset (0=Saturday) of the 1st of a Jalali month in the calendar grid. */
function firstWeekdayOffset(jy: number, jm: number): number {
  const iso = jalaliPartsToIso(jy, jm, 1);
  const date = new Date(iso);
  // JS getDay(): 0=Sunday..6=Saturday. Persian week starts Saturday.
  return (date.getDay() + 1) % 7;
}

/**
 * A Persian (Jalali) date picker. Displays and lets the user pick dates on the
 * Jalali calendar, but reads/emits ISO Gregorian date strings (YYYY-MM-DD) so
 * the backend contract is unchanged.
 */
export function JalaliDatePicker({
  label,
  value,
  onChange,
  required = false,
  error,
  hint,
  className = "",
  placeholder = "انتخاب تاریخ",
  clearable = true,
}: JalaliDatePickerProps): JSX.Element {
  const generatedId = useId().replace(/:/g, "");
  const inputId = `jdp-${generatedId}`;
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const selected = useMemo(() => isoToJalaliParts(value), [value]);

  const todayParts = useMemo(() => {
    const now = new Date();
    return gregorianToJalali(now.getFullYear(), now.getMonth() + 1, now.getDate());
  }, []);

  // The month currently shown in the calendar grid.
  const [viewYear, setViewYear] = useState<number>(selected?.[0] ?? todayParts[0]);
  const [viewMonth, setViewMonth] = useState<number>(selected?.[1] ?? todayParts[1]);

  // Re-sync the visible month when the value changes while closed.
  useEffect(() => {
    if (selected) {
      setViewYear(selected[0]);
      setViewMonth(selected[1]);
    }
  }, [selected]);

  // Close on outside click / Escape.
  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent): void => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent): void => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const display = value ? formatJalali(value, { style: "long" }) : "";

  // NOTE: month/year are computed together OUTSIDE the state updaters.
  // (Calling setViewYear inside setViewMonth's functional updater is impure;
  // React StrictMode double-invokes updaters, which skipped a year on every
  // Esfand↔Farvardin crossing — only every other year was reachable.)
  const goPrevMonth = (): void => {
    if (viewMonth === 1) {
      setViewYear(viewYear - 1);
      setViewMonth(12);
    } else {
      setViewMonth(viewMonth - 1);
    }
  };
  const goNextMonth = (): void => {
    if (viewMonth === 12) {
      setViewYear(viewYear + 1);
      setViewMonth(1);
    } else {
      setViewMonth(viewMonth + 1);
    }
  };
  const goPrevYear = (): void => setViewYear(viewYear - 1);
  const goNextYear = (): void => setViewYear(viewYear + 1);

  const pick = (day: number): void => {
    onChange(jalaliPartsToIso(viewYear, viewMonth, day));
    setOpen(false);
  };

  const clear = (): void => {
    onChange("");
    setOpen(false);
  };

  const daysInMonth = jalaliMonthLength(viewYear, viewMonth);
  const offset = firstWeekdayOffset(viewYear, viewMonth);
  const cells: (number | null)[] = [
    ...Array.from({ length: offset }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];

  const isSelected = (day: number): boolean =>
    Boolean(selected && selected[0] === viewYear && selected[1] === viewMonth && selected[2] === day);
  const isToday = (day: number): boolean =>
    todayParts[0] === viewYear && todayParts[1] === viewMonth && todayParts[2] === day;

  return (
    <div className={`field jdp ${error ? "has-error" : ""} ${className}`} ref={rootRef}>
      {label && (
        <span className="field__label" id={`${inputId}-label`}>
          {label}
          {required && <span className="field__required">*</span>}
        </span>
      )}
      <div className="field__control jdp__control">
        <Icon name="calendar" className="field__icon" size={17} />
        <button
          type="button"
          id={inputId}
          className="jdp__trigger"
          aria-haspopup="dialog"
          aria-expanded={open}
          aria-labelledby={label ? `${inputId}-label` : undefined}
          onClick={() => setOpen((o) => !o)}
        >
          {display ? (
            <span className="jdp__value">{display}</span>
          ) : (
            <span className="jdp__placeholder">{placeholder}</span>
          )}
        </button>
        {clearable && value && (
          <button
            type="button"
            className="jdp__clear"
            aria-label="پاک کردن تاریخ"
            onClick={clear}
          >
            <Icon name="close" size={14} />
          </button>
        )}
      </div>

      {open && (
        <div className="jdp__popover" role="dialog" aria-modal="false">
          <div className="jdp__header">
            <button
              type="button"
              className="jdp__nav jdp__nav--year"
              aria-label="سال بعد"
              title="سال بعد"
              onClick={goNextYear}
            >
              <Icon name="chevronRight" size={13} />
              <Icon name="chevronRight" size={13} />
            </button>
            <button
              type="button"
              className="jdp__nav"
              aria-label="ماه بعد"
              title="ماه بعد"
              onClick={goNextMonth}
            >
              <Icon name="chevronRight" size={16} />
            </button>
            <span className="jdp__title">
              {JALALI_MONTHS[viewMonth - 1]} {toPersianDigits(viewYear)}
            </span>
            <button
              type="button"
              className="jdp__nav"
              aria-label="ماه قبل"
              title="ماه قبل"
              onClick={goPrevMonth}
            >
              <Icon name="chevronLeft" size={16} />
            </button>
            <button
              type="button"
              className="jdp__nav jdp__nav--year"
              aria-label="سال قبل"
              title="سال قبل"
              onClick={goPrevYear}
            >
              <Icon name="chevronLeft" size={13} />
              <Icon name="chevronLeft" size={13} />
            </button>
          </div>

          <div className="jdp__weekdays">
            {JALALI_WEEKDAYS.map((w, i) => (
              <span key={i} className="jdp__weekday">
                {w}
              </span>
            ))}
          </div>

          <div className="jdp__grid">
            {cells.map((day, i) =>
              day === null ? (
                <span key={`e${i}`} className="jdp__cell jdp__cell--empty" />
              ) : (
                <button
                  key={day}
                  type="button"
                  className={`jdp__cell${isSelected(day) ? " jdp__cell--selected" : ""}${
                    isToday(day) && !isSelected(day) ? " jdp__cell--today" : ""
                  }`}
                  onClick={() => pick(day)}
                >
                  {toPersianDigits(day)}
                </button>
              ),
            )}
          </div>

          <div className="jdp__footer">
            <button
              type="button"
              className="jdp__today-btn"
              onClick={() => {
                const now = new Date();
                onChange(
                  jalaliPartsToIso(...gregorianToJalali(now.getFullYear(), now.getMonth() + 1, now.getDate())),
                );
                setOpen(false);
              }}
            >
              امروز
            </button>
          </div>
        </div>
      )}

      {(hint || error) && (
        <span className={`field__message ${error ? "field__message--error" : ""}`}>
          {error ?? hint}
        </span>
      )}
    </div>
  );
}
