import { useEffect, useState } from "react";
import { JalaliDatePicker } from "./JalaliDatePicker";
import { TextInput } from "./primitives";

/** Local wall time in/out; the page retains the existing ISO/UTC API conversion. */
export function JalaliDateTimePicker({ label, value, onChange }: {
  label: string; value: string; onChange: (value: string) => void;
}): JSX.Element {
  const date = value.split("T")[0] || "";
  const [time, setTime] = useState(value.split("T")[1]?.slice(0, 5) || "00:00");
  useEffect(() => { setTime(value.split("T")[1]?.slice(0, 5) || "00:00"); }, [value]);
  return <fieldset className="permit-datetime">
    <legend>{label}</legend>
    <div className="permit-datetime__fields">
      <JalaliDatePicker label={`تاریخ ${label}`} value={date} onChange={(nextDate) => onChange(nextDate ? `${nextDate}T${time || "00:00"}` : "")} />
      <TextInput label={`ساعت ${label}`} type="time" step={60} dir="ltr" value={time} onChange={(event) => {
        setTime(event.target.value);
        if (date) onChange(event.target.value ? `${date}T${event.target.value}` : "");
      }} />
    </div>
  </fieldset>;
}
