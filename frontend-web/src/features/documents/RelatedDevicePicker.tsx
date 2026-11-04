import { useState } from "react";
import type { RelatedDevice } from "./documentService";
import { TextInput } from "../../shared/components/primitives";

export function RelatedDevicePicker({ devices, value, onChange, disabled = false }: {
  devices: RelatedDevice[]; value: string[]; onChange: (ids: string[]) => void; disabled?: boolean;
}): JSX.Element {
  const [search, setSearch] = useState("");
  const shown = devices.filter(d => `${d.code} ${d.name}`.toLowerCase().includes(search.toLowerCase()));
  return <fieldset disabled={disabled} style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 12 }}>
    <legend>دستگاه‌های مرتبط (اختیاری)</legend>
    <p className="muted-cell">می‌توانید چند دستگاه انتخاب کنید. بدون انتخاب دستگاه، مدرک عمومی خواهد بود.</p>
    <TextInput label="جست‌وجوی دستگاه" value={search} onChange={e => setSearch(e.target.value)} />
    <div style={{ maxHeight: 220, overflow: "auto", display: "grid", gap: 8, paddingBlock: 8 }}>
      {shown.map(d => <label key={d.id} style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <input type="checkbox" checked={value.includes(d.id)} onChange={e => onChange(e.target.checked ? [...value, d.id] : value.filter(id => id !== d.id))} />
        <span>{d.code} — {d.name}</span>
      </label>)}
      {!shown.length && <span className="muted-cell">دستگاهی در این فهرست نیست.</span>}
    </div>
    <span className="muted-cell">{value.length} دستگاه انتخاب شده</span>
  </fieldset>;
}
