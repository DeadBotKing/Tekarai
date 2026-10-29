import { useId, useMemo, useState } from "react";
import { TextInput } from "../../shared/components/primitives";
import { groupPermissionsFa, permissionLabelFa } from "./permissionLabelsFa";
import "./permissionsFa.css";

export function PermissionCatalogFa({ actions, selected, onToggle, disabled = false, roleNames }: {
  actions: string[];
  selected?: string[];
  onToggle?: (code: string, checked: boolean) => void;
  disabled?: boolean;
  roleNames?: Record<string, string[]>;
}): JSX.Element {
  const [search, setSearch] = useState("");
  const id = useId();
  const groups = useMemo(() => groupPermissionsFa(actions, search), [actions, search]);
  const visibleCount = groups.reduce((sum, group) => sum + group.actions.length, 0);
  return <div className="permissions-fa" dir="rtl">
    <TextInput label="جستجوی مجوزها" placeholder="نام فارسی، دسته یا کد فنی مجوز" value={search} onChange={(event) => setSearch(event.target.value)} />
    <p className="permissions-fa__summary" role="status">{visibleCount.toLocaleString("fa-IR")} مجوز در فهرست{selected ? ` · ${selected.length.toLocaleString("fa-IR")} مجوز انتخاب‌شده` : ""}</p>
    {groups.length === 0 && <p>مجوزی مطابق جستجو پیدا نشد.</p>}
    {groups.map((group, index) => <section className="permissions-fa__group" key={group.name} aria-labelledby={`${id}-${index}`}>
      <h3 id={`${id}-${index}`}>{group.name}<span>{group.actions.length.toLocaleString("fa-IR")}</span></h3>
      <div className="permissions-fa__grid">{group.actions.map((code) => {
        const content = <span className="permissions-fa__copy"><strong>{permissionLabelFa(code)}</strong><code dir="ltr">{code}</code>{roleNames?.[code] && <small>نقش‌ها: {roleNames[code].join("، ")}</small>}</span>;
        return onToggle ? <label key={code} className="permissions-fa__item"><input type="checkbox" checked={selected?.includes(code) ?? false} disabled={disabled} onChange={(event) => onToggle(code, event.target.checked)} />{content}</label> : <div key={code} className="permissions-fa__item">{content}</div>;
      })}</div>
    </section>)}
  </div>;
}
