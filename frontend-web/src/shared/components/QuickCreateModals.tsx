import { useEffect, useState } from "react";
import { Modal } from "./overlays";
import { Button, TextInput } from "./primitives";
import { CreatableSelect } from "./CreatableSelect";
import { mergeOptions } from "../../features/maintenance/optionCatalog";
import { taxonomyLabel } from "../../core/localization/taxonomyLabel";
import { useLocalization } from "../../core/localization/localizationContext";
import {
  LOCATION_KINDS,
  MAINTENANCE_DEPARTMENTS,
  PART_UNITS,
  type LocationKind,
  type MaintenanceDepartment,
} from "../types/domain";

/**
 * Quick-create modals used by {@link QuickAddSelect}: when a record picker has
 * no matching record («➕ افزودن …» entry), one of these small dialogs collects
 * just the minimum fields, delegates persistence to the page via `onSave`
 * (which resolves to the new record id), and selects the record via
 * `onCreated` — both in demo mode (page-local data) and against the live API.
 */

interface QuickCreateModalProps<Input> {
  open: boolean;
  onClose: () => void;
  /** Persists the draft; resolves with the new record's id. Throws on failure. */
  onSave: (input: Input) => Promise<string>;
  /** Receives the new id so the page can select it in the source picker. */
  onCreated: (id: string) => void;
}

interface Submitter {
  busy: boolean;
  error: string;
  setBusy: (busy: boolean) => void;
  setError: (error: string) => void;
}

function useQuickSubmit(): Submitter {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return { busy, error, setBusy, setError };
}

function modalFooter(
  onClose: () => void,
  submit: () => void,
  busy: boolean,
  cancelLabel: string,
): JSX.Element {
  return (
    <>
      <Button variant="secondary" onClick={onClose}>
        {cancelLabel}
      </Button>
      <Button variant="primary" icon="plus" loading={busy} onClick={submit}>
        ثبت و انتخاب
      </Button>
    </>
  );
}

function ErrorLine({ error }: { error: string }): JSX.Element | null {
  if (!error) return null;
  return (
    <span className="field__message field__message--error" role="alert">
      {error}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Device — used in the work-order create form and anywhere a device is picked.
// ---------------------------------------------------------------------------

export interface QuickDeviceInput {
  code: string;
  name: string;
  location?: string;
  department?: MaintenanceDepartment | "";
  pmIntervalDays?: number;
}

export function QuickDeviceModal({
  open,
  onClose,
  onSave,
  onCreated,
}: QuickCreateModalProps<QuickDeviceInput>): JSX.Element {
  const { t } = useLocalization();
  const { busy, error, setBusy, setError } = useQuickSubmit();
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [location, setLocation] = useState("");
  const [department, setDepartment] = useState<MaintenanceDepartment | "">("");
  const [pmInterval, setPmInterval] = useState("30");

  useEffect(() => {
    if (!open) return;
    setCode("");
    setName("");
    setLocation("");
    setDepartment("");
    setPmInterval("30");
    setError("");
  }, [open, setError]);

  const submit = async (): Promise<void> => {
    if (!code.trim() || !name.trim()) {
      setError("کد و نام دستگاه الزامی است.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const id = await onSave({
        code: code.trim(),
        name: name.trim(),
        location: location.trim() || undefined,
        department: department || undefined,
        pmIntervalDays: Number(pmInterval) > 0 ? Number(pmInterval) : undefined,
      });
      onCreated(id);
      onClose();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "ثبت دستگاه انجام نشد.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      title="افزودن سریع دستگاه"
      onClose={onClose}
      footer={modalFooter(onClose, () => void submit(), busy, t("cmms.common.cancel"))}
    >
      <TextInput
        label="کد دستگاه"
        required
        value={code}
        onChange={(event) => setCode(event.target.value)}
        autoFocus
      />
      <TextInput
        label="نام دستگاه"
        required
        value={name}
        onChange={(event) => setName(event.target.value)}
      />
      <div className="form-grid form-grid--compact">
        <TextInput
          label="محل نصب"
          value={location}
          onChange={(event) => setLocation(event.target.value)}
        />
        <TextInput
          label={t("cmms.device.pmInterval")}
          type="number"
          min="1"
          value={pmInterval}
          onChange={(event) => setPmInterval(event.target.value)}
        />
      </div>
      <CreatableSelect
        label={t("cmms.device.department")}
        value={department}
        onChange={(value) => setDepartment(value as MaintenanceDepartment | "")}
        catalogKey="device.department"
        canonical={MAINTENANCE_DEPARTMENTS}
        options={[
          { value: "", label: t("registry.common.none") },
          ...mergeOptions({
            canonical: MAINTENANCE_DEPARTMENTS,
            translate: (department) => taxonomyLabel(t, "cmms.department.", department),
            catalogKey: "device.department",
            current: department,
          }),
        ]}
      />
      <ErrorLine error={error} />
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Spare part — used in the consume form and the BOM picker.
// ---------------------------------------------------------------------------

export interface QuickPartInput {
  code: string;
  name: string;
  unit: string;
  quantityOnHand: number;
  minimumStock: number;
  unitCost: number;
}

export function QuickPartModal({
  open,
  onClose,
  onSave,
  onCreated,
}: QuickCreateModalProps<QuickPartInput>): JSX.Element {
  const { t } = useLocalization();
  const { busy, error, setBusy, setError } = useQuickSubmit();
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [unit, setUnit] = useState("عدد");
  const [stock, setStock] = useState("0");
  const [minimum, setMinimum] = useState("0");
  const [unitCost, setUnitCost] = useState("0");

  useEffect(() => {
    if (!open) return;
    setCode("");
    setName("");
    setUnit("عدد");
    setStock("0");
    setMinimum("0");
    setUnitCost("0");
    setError("");
  }, [open, setError]);

  const submit = async (): Promise<void> => {
    if (!code.trim() || !name.trim()) {
      setError("کد و نام قطعه الزامی است.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const id = await onSave({
        code: code.trim(),
        name: name.trim(),
        unit: unit.trim() || "عدد",
        quantityOnHand: Number(stock),
        minimumStock: Number(minimum),
        unitCost: Number(unitCost),
      });
      onCreated(id);
      onClose();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "ثبت قطعه انجام نشد.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      title="افزودن سریع قطعه"
      onClose={onClose}
      footer={modalFooter(onClose, () => void submit(), busy, t("cmms.common.cancel"))}
    >
      <TextInput
        label="کد قطعه"
        required
        value={code}
        onChange={(event) => setCode(event.target.value)}
        autoFocus
      />
      <TextInput
        label="نام قطعه"
        required
        value={name}
        onChange={(event) => setName(event.target.value)}
      />
      <div className="form-grid form-grid--compact">
        <CreatableSelect
          label="واحد"
          value={unit}
          onChange={setUnit}
          catalogKey="part.unit"
          canonical={PART_UNITS}
          options={mergeOptions({
            canonical: PART_UNITS,
            translate: (item) => item,
            catalogKey: "part.unit",
            current: unit,
          })}
        />
        <TextInput
          label="موجودی اولیه"
          type="number"
          min="0"
          step="0.001"
          value={stock}
          onChange={(event) => setStock(event.target.value)}
        />
        <TextInput
          label="حداقل موجودی"
          type="number"
          min="0"
          step="0.001"
          value={minimum}
          onChange={(event) => setMinimum(event.target.value)}
        />
        <TextInput
          label={t("cmms.cost.unitPrice")}
          type="number"
          min="0"
          step="1000"
          value={unitCost}
          onChange={(event) => setUnitCost(event.target.value)}
        />
      </div>
      <ErrorLine error={error} />
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Location — used in registry, work-order routing and device nameplate.
// ---------------------------------------------------------------------------

export interface QuickLocationInput {
  code?: string;
  name: string;
  kind: LocationKind;
  parentId?: string;
  note?: string;
}

export function QuickLocationModal({
  open,
  onClose,
  onSave,
  onCreated,
}: QuickCreateModalProps<QuickLocationInput>): JSX.Element {
  const { t } = useLocalization();
  const { busy, error, setBusy, setError } = useQuickSubmit();
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [kind, setKind] = useState<LocationKind>("site");
  const [note, setNote] = useState("");

  useEffect(() => {
    if (!open) return;
    setCode("");
    setName("");
    setKind("site");
    setNote("");
    setError("");
  }, [open, setError]);

  const submit = async (): Promise<void> => {
    if (!name.trim()) {
      setError("نام محل الزامی است.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const id = await onSave({
        code: code.trim() || undefined,
        name: name.trim(),
        kind,
        note: note.trim() || undefined,
      });
      onCreated(id);
      onClose();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "ثبت محل انجام نشد.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      title="افزودن سریع محل"
      onClose={onClose}
      footer={modalFooter(onClose, () => void submit(), busy, t("cmms.common.cancel"))}
    >
      <TextInput
        label="نام محل"
        required
        value={name}
        onChange={(event) => setName(event.target.value)}
        autoFocus
      />
      <div className="form-grid form-grid--compact">
        <TextInput
          label="کد محل"
          value={code}
          onChange={(event) => setCode(event.target.value)}
        />
        <CreatableSelect
          label="نوع محل"
          value={kind}
          onChange={(value) => setKind(value as LocationKind)}
          catalogKey="location.kind"
          canonical={LOCATION_KINDS}
          options={mergeOptions({
            canonical: LOCATION_KINDS,
            translate: (item) => taxonomyLabel(t, "registry.location.", item),
            catalogKey: "location.kind",
            current: kind,
          })}
        />
      </div>
      <TextInput
        label="یادداشت"
        value={note}
        onChange={(event) => setNote(event.target.value)}
      />
      <ErrorLine error={error} />
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Personnel — used in device assignments.
// ---------------------------------------------------------------------------

export interface QuickPersonInput {
  fullName: string;
  specialty: MaintenanceDepartment;
  unit?: string;
  phone?: string;
}

export function QuickPersonModal({
  open,
  onClose,
  onSave,
  onCreated,
}: QuickCreateModalProps<QuickPersonInput>): JSX.Element {
  const { t } = useLocalization();
  const { busy, error, setBusy, setError } = useQuickSubmit();
  const [fullName, setFullName] = useState("");
  const [specialty, setSpecialty] = useState<MaintenanceDepartment>("mechanical");
  const [unit, setUnit] = useState("");
  const [phone, setPhone] = useState("");

  useEffect(() => {
    if (!open) return;
    setFullName("");
    setSpecialty("mechanical");
    setUnit("");
    setPhone("");
    setError("");
  }, [open, setError]);

  const submit = async (): Promise<void> => {
    if (!fullName.trim()) {
      setError("نام فرد الزامی است.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const id = await onSave({
        fullName: fullName.trim(),
        specialty,
        unit: unit.trim() || undefined,
        phone: phone.trim() || undefined,
      });
      onCreated(id);
      onClose();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "ثبت فرد انجام نشد.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      title="افزودن سریع فرد"
      onClose={onClose}
      footer={modalFooter(onClose, () => void submit(), busy, t("cmms.common.cancel"))}
    >
      <TextInput
        label="نام و نام خانوادگی"
        required
        value={fullName}
        onChange={(event) => setFullName(event.target.value)}
        autoFocus
      />
      <CreatableSelect
        label="تخصص"
        value={specialty}
        onChange={(value) => setSpecialty(value as MaintenanceDepartment)}
        catalogKey="personnel.specialty"
        canonical={MAINTENANCE_DEPARTMENTS}
        options={mergeOptions({
          canonical: MAINTENANCE_DEPARTMENTS,
          translate: (department) => taxonomyLabel(t, "cmms.department.", department),
          catalogKey: "personnel.specialty",
          current: specialty,
        })}
      />
      <div className="form-grid form-grid--compact">
        <TextInput
          label="واحد/تیم"
          value={unit}
          onChange={(event) => setUnit(event.target.value)}
        />
        <TextInput
          label="تلفن"
          value={phone}
          onChange={(event) => setPhone(event.target.value)}
        />
      </div>
      <ErrorLine error={error} />
    </Modal>
  );
}
