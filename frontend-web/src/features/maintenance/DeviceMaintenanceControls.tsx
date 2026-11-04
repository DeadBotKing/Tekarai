import { useState } from "react";
import { useLocalization } from "../../core/localization/localizationContext";
import { PERMISSIONS } from "../../core/permissions/permissionContext";
import { runtimeConfig } from "../../app/configuration/runtimeConfig";
import { Button, PermissionGuard, TextInput, SelectInput } from "../../shared/components/primitives";
import { CreatableSelect } from "../../shared/components/CreatableSelect";
import { mergeOptions } from "./optionCatalog";
import { Modal } from "../../shared/components/overlays";
import { JalaliDatePicker } from "../../shared/components/JalaliDatePicker";
import { taxonomyLabel } from "../../core/localization/taxonomyLabel";
import { todayIso } from "../../core/localization/jalali";
import { MAINTENANCE_DEPARTMENTS, type MaintenanceDevice, type DeviceStatus, type MaintenanceDepartment } from "../../shared/types/domain";
import type { createMaintenanceService } from "./maintenanceService";

type Props = {
  device: MaintenanceDevice;
  service: ReturnType<typeof createMaintenanceService>;
  onUpdate: (device: MaintenanceDevice) => void;
  onMessage: (message: string) => void;
};

/** The legacy device actions now belong to the device's single profile. */
export function DeviceMaintenanceControls({ device, service, onUpdate, onMessage }: Props): JSX.Element {
  const { t } = useLocalization();
  const [mode, setMode] = useState<"edit" | "pm" | null>(null);
  const [name, setName] = useState(device.name);
  const [location, setLocation] = useState(device.location);
  const [department, setDepartment] = useState(device.department);
  const [interval, setInterval] = useState(String(device.pmIntervalDays));
  const [status, setStatus] = useState(device.status);
  const [date, setDate] = useState(device.lastPmDate || todayIso());
  const [saving, setSaving] = useState(false);
  const openEdit = (): void => {
    setName(device.name); setLocation(device.location); setDepartment(device.department);
    setInterval(String(device.pmIntervalDays)); setStatus(device.status); setMode("edit");
  };
  const save = async (): Promise<void> => {
    if (saving) return;
    if (mode === "edit" && (!name.trim() || !Number.isInteger(Number(interval)) || Number(interval) < 0)) {
      onMessage("نام دستگاه و فاصلهٔ سرویس معتبر را وارد کنید."); return;
    }
    if (mode === "pm" && !date) { onMessage("تاریخ انجام سرویس را انتخاب کنید."); return; }
    setSaving(true);
    let detailsSaved = false;
    try {
      if (mode === "edit") {
        const input = { name: name.trim(), location: location.trim(), department, pmIntervalDays: Number(interval) };
        let updated = runtimeConfig.demoMode ? { ...device, ...input } : await service.updateDevice(device.id, input);
        onUpdate(updated);
        detailsSaved = true;
        if (status !== updated.status) {
          updated = runtimeConfig.demoMode ? { ...updated, status } : await service.changeDeviceStatus(device.id, status);
          onUpdate(updated);
        }
        onMessage(t("cmms.device.updateSuccess"));
      } else {
        let updated: MaintenanceDevice;
        if (runtimeConfig.demoMode) {
          const next = new Date(`${date}T12:00:00Z`);
          next.setUTCDate(next.getUTCDate() + device.pmIntervalDays);
          updated = { ...device, lastPmDate: date, nextDueDate: device.pmIntervalDays > 0 ? next.toISOString().slice(0, 10) : "", pmDue: false };
        } else updated = await service.recordPm(device.id, date);
        onUpdate(updated);
        onMessage(t("cmms.device.pmSuccess"));
      }
      setMode(null);
    } catch (error) {
      onMessage((detailsSaved ? "مشخصات ذخیره شد، اما تغییر وضعیت ناموفق بود. " : "") + (error instanceof Error ? error.message : t("registry.saveFailed")));
    } finally { setSaving(false); }
  };
  return <PermissionGuard permission={PERMISSIONS.maintenanceDeviceManage}>
    <Button variant="secondary" icon="edit" onClick={openEdit}>{t("cmms.device.editTitle")}</Button>
    <Button variant="secondary" icon="check" onClick={() => { setDate(device.lastPmDate || todayIso()); setMode("pm"); }}>{t("cmms.device.recordPm")}</Button>
    <Modal open={mode !== null} title={mode === "pm" ? t("cmms.device.recordPmTitle") : t("cmms.device.editTitle")}
      onClose={() => { if (!saving) setMode(null); }} footer={<>
        <Button variant="secondary" disabled={saving} onClick={() => setMode(null)}>{t("cmms.common.cancel")}</Button>
        <Button variant="primary" disabled={saving} onClick={() => void save()}>{saving ? t("common.loading") : t("cmms.device.save")}</Button>
      </>}>
      <p>{device.code} — {device.name}</p>
      {mode === "pm" ? <JalaliDatePicker label={t("cmms.device.performedOn")} value={date} onChange={setDate} /> : <>
        <TextInput label={t("cmms.device.name")} required value={name} onChange={(e) => setName(e.target.value)} />
        <TextInput label={t("cmms.device.location")} value={location} onChange={(e) => setLocation(e.target.value)} />
        <TextInput label={t("cmms.device.pmInterval")} type="number" min="0" value={interval} onChange={(e) => setInterval(e.target.value)} />
        <CreatableSelect label={t("cmms.device.department")} value={department} onChange={(value) => setDepartment(value as MaintenanceDepartment)} catalogKey="device.department" canonical={MAINTENANCE_DEPARTMENTS} options={mergeOptions({ canonical: MAINTENANCE_DEPARTMENTS, fromData: [device.department], current: department, catalogKey: "device.department", translate: (value) => taxonomyLabel(t, "cmms.department.", value) })} />
        <SelectInput label={t("cmms.device.changeStatus")} value={status} onChange={(e) => setStatus(e.target.value as DeviceStatus)} options={["operational", "underMaintenance", "outOfService", "retired"].map(value => ({ value, label: taxonomyLabel(t, "cmms.status.", value) }))} />
      </>}
    </Modal>
  </PermissionGuard>;
}
