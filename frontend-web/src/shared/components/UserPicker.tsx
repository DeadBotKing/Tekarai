import { useEffect, useId, useRef, useState } from "react";

export interface UserPickerUser {
  id: string;
  username: string;
  displayName: string;
  status?: string;
}

export interface UserPickerProps {
  label?: string;
  browse?: boolean;
  /** The chosen user, or null while nobody is picked. */
  value: UserPickerUser | null;
  /** Receives the picked user; null when the choice is cleared or retyped away. */
  onSelect: (user: UserPickerUser | null) => void;
  /** Runs the actual search — supplied by the page so the component stays presentational. */
  search: (query: string) => Promise<UserPickerUser[]>;
  placeholder?: string;
  hint?: string;
  disabled?: boolean;
  className?: string;
}

const MIN_QUERY = 2;
const DEBOUNCE_MS = 200;

/**
 * A person picker, not an id field. The user types a name or a username,
 * the matching accounts arrive below, and picking one keeps the id entirely
 * behind the scenes — the caller receives a whole person (id, name,
 * username) and never asks anyone to read or paste a UUID.
 *
 * The markup follows the shared field conventions (`.field`,
 * `.field__label`, `.field__control`) so it sits in a form grid like any
 * other input.
 */
export function UserPicker({
  label,
  browse = false,
  value,
  onSelect,
  search,
  placeholder = "جستجوی نام / نام کاربری…",
  hint,
  disabled,
  className = "",
}: UserPickerProps): JSX.Element {
  const generatedId = useId().replace(/:/g, "");
  const inputId = `user-picker-${generatedId}`;
  const listboxId = `${inputId}-listbox`;

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<UserPickerUser[]>([]);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  const resultsRef = useRef<UserPickerUser[]>([]);
  resultsRef.current = results;

  // Held in a ref so an unstable `search` identity (an inline arrow in a
  // caller's render) cannot retrigger the effect and loop the fetch.
  const searchRef = useRef(search);
  searchRef.current = search;

  // Debounced search; a newer keystroke cancels the previous answer.
  useEffect(() => {
    const trimmed = query.trim();
    if (!open || (!browse && trimmed.length < MIN_QUERY)) {
      setResults([]);
      setActiveIndex(-1);
      setLoading(false);
      return;
    }
    let stale = false;
    setLoading(true);
    setFailed(false);
    const timer = window.setTimeout(() => {
      searchRef.current(trimmed)
        .then((found) => {
          if (stale) return;
          setResults(found);
          setActiveIndex(found.length > 0 ? 0 : -1);
          setLoading(false);
        })
        .catch(() => {
          if (stale) return;
          setResults([]);
          setActiveIndex(-1);
          setLoading(false);
          setFailed(true);
        });
    }, DEBOUNCE_MS);
    return () => {
      stale = true;
      window.clearTimeout(timer);
    };
  }, [query, open, browse]);

  const pick = (user: UserPickerUser): void => {
    setQuery(user.displayName.trim() !== "" ? user.displayName : user.username);
    setResults([]);
    setActiveIndex(-1);
    setOpen(false);
    onSelect(user);
  };

  const clear = (): void => {
    setQuery("");
    setResults([]);
    setActiveIndex(-1);
    setOpen(false);
    onSelect(null);
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>): void => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!open) {
        setOpen(true);
        return;
      }
      setActiveIndex((current) => Math.min(current + 1, resultsRef.current.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((current) => Math.max(current - 1, 0));
    } else if (event.key === "Enter") {
      if (open && activeIndex >= 0 && activeIndex < resultsRef.current.length) {
        event.preventDefault();
        pick(resultsRef.current[activeIndex]);
      }
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  };

  const trimmed = query.trim();
  const showMinHint = !browse && open && trimmed.length > 0 && trimmed.length < MIN_QUERY;

  return (
    <div className={`user-picker ${className}`}>
      <label className="field" htmlFor={inputId}>
        {label && <span className="field__label">{label}</span>}
        <span className="field__control">
          <input
            id={inputId}
            type="text"
            role="combobox"
            aria-expanded={open}
            aria-controls={listboxId}
            aria-autocomplete="list"
            aria-activedescendant={
              open && activeIndex >= 0 ? `${listboxId}-option-${activeIndex}` : undefined
            }
            aria-describedby={hint && value === null ? `${inputId}-hint` : undefined}
            autoComplete="off"
            value={query}
            placeholder={placeholder}
            disabled={disabled}
            onFocus={() => setOpen(true)}
            onBlur={() => setOpen(false)}
            onChange={(event) => {
              // Typing after a pick drops the previous person — a name in
              // the box is a choice, not text the user is committed to.
              if (value !== null) onSelect(null);
              setOpen(true);
              setQuery(event.target.value);
            }}
            onKeyDown={onKeyDown}
          />
          {value !== null ? (
            <button
              type="button"
              className="user-picker__clear"
              aria-label="پاک‌کردن انتخاب کاربر"
              disabled={disabled}
              // Keep focus on the input so the menu does not flicker; the
              // click itself closes it.
              onMouseDown={(event) => event.preventDefault()}
              onClick={clear}
            >
              ×
            </button>
          ) : null}
        </span>
      </label>
      {/* Outside the label on purpose: a hint inside it would become part
          of the label text and break label-based queries for screen
          readers and tests alike. */}
      {hint && value === null ? (
        <span id={`${inputId}-hint`} className="field__message">
          {hint}
        </span>
      ) : null}
      {open ? (
        <div className="user-picker__menu" style={{ maxHeight: "320px", overflowY: "auto" }} id={listboxId} role="listbox">
          {showMinHint ? (
            <p className="user-picker__state">حداقل دو حرف تایپ کنید…</p>
          ) : loading ? (
            <p className="user-picker__state">در حال جستجو…</p>
          ) : failed ? (
            <p className="user-picker__state user-picker__state--error">جستجوی کاربر ناموفق بود؛ دوباره تایپ کنید.</p>
          ) : results.length === 0 ? (
            <p className="user-picker__state">کاربری با این نام پیدا نشد.</p>
          ) : (
            <ul className="user-picker__options">
              {results.map((user, index) => (
                <li
                  key={user.id}
                  id={`${listboxId}-option-${index}`}
                  role="option"
                  aria-selected={index === activeIndex}
                  className={`user-picker__option ${index === activeIndex ? "user-picker__option--active" : ""}`}
                  // Without this the click would blur the input first and
                  // the menu would be gone before the click lands.
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => pick(user)}
                >
                  <span className="user-picker__name">
                    {user.displayName.trim() !== "" ? user.displayName : user.username}
                  </span>
                  <span className="user-picker__username">{user.username}</span>
                  {user.status && user.status !== "active" ? (
                    <span className="user-picker__flag">غیرفعال</span>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
}
