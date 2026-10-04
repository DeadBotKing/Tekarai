import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import QRCode from "qrcode";
import { useNavigate, useParams } from "react-router-dom";
import { useApiClient } from "../core/api/apiContext";
import { useLocalization } from "../core/localization/localizationContext";
import { PERMISSIONS } from "../core/permissions/permissionContext";
import { runtimeConfig } from "../app/configuration/runtimeConfig";
import { createMaintenanceService } from "../features/maintenance/maintenanceService";
import {
  createRegistryService,
  type AssignmentRowInput,
  type RegistryService,
  type SavePmPlanInput,
  type SpecificationRowInput,
} from "../features/maintenance/registryService";
import {
  createDemoRegistryService,
  demoSpareParts,
} from "../features/maintenance/registryDemoData";
import {
  ASSET_LEVELS,
  DEVICE_ASSIGNMENT_ROLES,
  EQUIPMENT_CRITICALITIES,
  MAINTENANCE_DEPARTMENTS,
  PM_FREQUENCY_UNITS,
  type AssetAncestry,
  type AssetMovement,
  type DeviceAnalytics,
  type DeviceAssignmentRole,
  type DeviceNameplate,
  type DeviceProfile,
  type EquipmentCriticality,
  type MaintenanceDepartment,
  type MaintenanceLocation,
  type MaintenancePersonnel,
  type PmFrequencyUnit,
  type PmPlan,
  type SparePart,
} from "../shared/types/domain";
import { Modal, Toast } from "../shared/components/overlays";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  LoadingState,
  MetricCard,
  PermissionGuard,
  SectionHeader,
  SelectInput,
  TextArea,
  TextInput,
} from "../shared/components/primitives";
import { Icon } from "../shared/components/Icon";
import { JalaliDatePicker } from "../shared/components/JalaliDatePicker";
import { deviceProfilePath, deviceQrPayload } from "../features/maintenance/deviceQr";
import { formatJalali, todayIso } from "../core/localization/jalali";
import { taxonomyLabel } from "../core/localization/taxonomyLabel";
import { CreatableSelect } from "../shared/components/CreatableSelect";
import { QuickAddSelect } from "../shared/components/QuickAddSelect";
import {
  QuickLocationModal,
  QuickPersonModal,
  QuickPartModal,
  type QuickLocationInput,
  type QuickPersonInput,
  type QuickPartInput,
} from "../shared/components/QuickCreateModals";
import { mergeOptions } from "../features/maintenance/optionCatalog";

type TabId =
  | "nameplate"
  | "specifications"
  | "pm"
  | "parts"
  | "location"
  | "personnel"
  | "analytics";

const TABS: { id: TabId; labelKey: string; icon: "file" | "table" | "calendar" | "layers" | "building" | "users" | "chart" }[] = [
  { id: "nameplate", labelKey: "registry.tab.nameplate", icon: "file" },
  { id: "specifications", labelKey: "registry.tab.specifications", icon: "table" },
  { id: "pm", labelKey: "registry.tab.pm", icon: "calendar" },
  { id: "parts", labelKey: "registry.tab.parts", icon: "layers" },
  { id: "location", labelKey: "registry.tab.location", icon: "building" },
  { id: "personnel", labelKey: "registry.tab.personnel", icon: "users" },
  { id: "analytics", labelKey: "registry.tab.analytics", icon: "chart" },
];

const emptyPlanForm = (): SavePmPlanInput & { checklistText: string } => ({
  title: "",
  discipline: "mechanical",
  description: "",
  checklist: [],
  checklistText: "",
  frequencyEvery: 1,
  frequencyUnit: "month",
  estimatedMinutes: 30,
  responsibleName: "",
  active: true,
});

const formatNumber = (value: number | null, digits = 1): string =>
  value === null || Number.isNaN(value) ? "—" : value.toFixed(digits);

const formatMoney = (value: number): string =>
  value ? new Intl.NumberFormat("fa-IR").format(Math.round(value)) : "۰";

/** The complete equipment file: nameplate, specs, PM, parts, location, people, KPIs. */
export function DeviceProfilePage(): JSX.Element {
  const { t } = useLocalization();
  const navigate = useNavigate();
  const { deviceId = "" } = useParams<{ deviceId: string }>();
  const api = useApiClient();
  const maintenance = useMemo(() => createMaintenanceService(api), [api]);
  const registry: RegistryService = useMemo(
    () => (runtimeConfig.demoMode ? createDemoRegistryService() : createRegistryService(api)),
    [api],
  );

  const [profile, setProfile] = useState<DeviceProfile | null>(null);
  const [locations, setLocations] = useState<MaintenanceLocation[]>([]);
  const [personnel, setPersonnel] = useState<MaintenancePersonnel[]>([]);
  const [spareParts, setSpareParts] = useState<SparePart[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [tab, setTab] = useState<TabId>("nameplate");
  const [toast, setToast] = useState("");
  const [qrOpen, setQrOpen] = useState(false);
  const qrCanvas = useRef<HTMLCanvasElement | null>(null);
  const [saving, setSaving] = useState(false);

  const [nameplate, setNameplate] = useState<DeviceNameplate | null>(null);
  const [specRows, setSpecRows] = useState<SpecificationRowInput[]>([]);
  const [assignmentRows, setAssignmentRows] = useState<AssignmentRowInput[]>([]);

  const [planModalOpen, setPlanModalOpen] = useState(false);
  const [editingPlan, setEditingPlan] = useState<PmPlan | null>(null);
  const [planForm, setPlanForm] = useState(emptyPlanForm());

  const [executePlan, setExecutePlan] = useState<PmPlan | null>(null);
  const [executionDate, setExecutionDate] = useState(todayIso());
  const [executionBy, setExecutionBy] = useState("");
  const [executionMinutes, setExecutionMinutes] = useState("30");
  const [executionFindings, setExecutionFindings] = useState("");

  const [bomOpen, setBomOpen] = useState(false);
  const [bomPartId, setBomPartId] = useState("");
  const [bomPosition, setBomPosition] = useState("");
  const [bomQuantity, setBomQuantity] = useState("1");
  const [bomNote, setBomNote] = useState("");

  // -- Phase 27 asset hierarchy --------------------------------------------
  const [ancestry, setAncestry] = useState<AssetAncestry | null>(null);
  const [movements, setMovements] = useState<AssetMovement[]>([]);
  const [moveOpen, setMoveOpen] = useState(false);
  const [moveLocationId, setMoveLocationId] = useState("");
  const [moveDate, setMoveDate] = useState("");
  const [moveReason, setMoveReason] = useState("");
  const [moveBy, setMoveBy] = useState("");
  const [moveUpdateInstalled, setMoveUpdateInstalled] = useState(false);
  const [retireOpen, setRetireOpen] = useState(false);
  const [retireDate, setRetireDate] = useState("");
  const [retireReason, setRetireReason] = useState("");
  const [retireChildren, setRetireChildren] = useState(false);
  const [hierarchyBusy, setHierarchyBusy] = useState(false);
  const [quickLocationOpen, setQuickLocationOpen] = useState(false);
  const [quickPersonTarget, setQuickPersonTarget] = useState<number | null>(null);
  const [quickPartOpen, setQuickPartOpen] = useState(false);

  const load = useCallback(async (): Promise<void> => {
    if (!deviceId) return;
    try {
      const [loaded, locationList, personnelList] = await Promise.all([
        registry.getDeviceProfile(deviceId),
        registry.listLocations(),
        registry.listPersonnel(),
      ]);
      setProfile(loaded);
      setNameplate(loaded.nameplate);
      setSpecRows(
        loaded.specifications.map((row) => ({
          label: row.label,
          value: row.value,
          unit: row.unit,
          sortOrder: row.sortOrder,
        })),
      );
      setAssignmentRows(
        loaded.assignments.map((row) => ({
          personnelId: row.personnelId,
          personnelName: row.personnelName,
          role: row.role,
          unit: row.unit,
          fromDate: row.fromDate,
          toDate: row.toDate,
        })),
      );
      setLocations(locationList);
      setPersonnel(personnelList);
      setFailed(false);
      // The hierarchy is supporting detail: if it fails the profile still
      // renders, it just shows no chain.
      try {
        const [chain, ledger] = await Promise.all([
          registry.getAssetAncestry(deviceId),
          registry.listAssetMovements(deviceId),
        ]);
        setAncestry(chain);
        setMovements(ledger);
      } catch {
        setAncestry(null);
        setMovements([]);
      }
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, [deviceId, registry]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    let active = true;
    const loadParts = async (): Promise<void> => {
      if (runtimeConfig.demoMode) {
        setSpareParts(demoSpareParts);
        return;
      }
      try {
        const parts = await maintenance.listSpareParts();
        if (active) setSpareParts(parts);
      } catch {
        if (active) setSpareParts([]);
      }
    };
    void loadParts();
    return () => {
      active = false;
    };
  }, [maintenance]);

  // QR باید قبل از خروجی زودهنگام (loading/failed) ثبت شود تا ترتیب هوک‌ها ثابت بماند.
  const qrDeviceId = profile?.device.id ?? "";
  useEffect(() => {
    if (!qrOpen || !qrCanvas.current || !qrDeviceId) return;
    void QRCode.toCanvas(qrCanvas.current, deviceQrPayload(qrDeviceId), {
      width: 196,
      margin: 1,
      errorCorrectionLevel: "M",
      color: { dark: "#101828", light: "#ffffff" },
    });
  }, [qrOpen, qrDeviceId]);

  if (loading) return <LoadingState label={t("registry.profile.loading")} />;
  if (failed || !profile || !nameplate) {
    return (
      <div className="page">
        <EmptyState
          icon="warning"
          title={t("registry.profile.notFound")}
          action={
            <Button variant="secondary" icon="arrowRight" onClick={() => navigate("/app/maintenance/registry")}>
              {t("registry.profile.back")}
            </Button>
          }
        />
      </div>
    );
  }

  const device = profile.device;
  const analytics: DeviceAnalytics | null = profile.analytics;

  const patchNameplate = (values: Partial<DeviceNameplate>): void =>
    setNameplate((current) => (current ? { ...current, ...values } : current));

  const saveNameplate = async (): Promise<void> => {
    setSaving(true);
    try {
      await registry.updateNameplate(device.id, nameplate);
      setToast(t("registry.nameplate.saved"));
      await load();
    } catch (error) {
      setToast(error instanceof Error ? error.message : t("registry.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const saveSpecifications = async (): Promise<void> => {
    const rows = specRows.filter((row) => row.label.trim());
    setSaving(true);
    try {
      await registry.saveSpecifications(device.id, rows);
      setToast(t("registry.spec.saved"));
      await load();
    } catch (error) {
      setToast(error instanceof Error ? error.message : t("registry.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const openPlanModal = (plan: PmPlan | null, discipline: MaintenanceDepartment): void => {
    setEditingPlan(plan);
    setPlanForm(
      plan
        ? {
            title: plan.title,
            discipline: plan.discipline,
            description: plan.description,
            checklist: plan.checklist,
            checklistText: plan.checklist.join("\n"),
            frequencyEvery: plan.frequencyEvery,
            frequencyUnit: plan.frequencyUnit,
            estimatedMinutes: plan.estimatedMinutes,
            responsibleName: plan.responsibleName,
            active: plan.active,
          }
        : { ...emptyPlanForm(), discipline },
    );
    setPlanModalOpen(true);
  };

  const savePlan = async (): Promise<void> => {
    if (!planForm.title.trim()) {
      setToast(t("registry.common.required"));
      return;
    }
    const payload: SavePmPlanInput = {
      title: planForm.title.trim(),
      discipline: planForm.discipline,
      description: planForm.description ?? "",
      checklist: planForm.checklistText
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean),
      frequencyEvery: Number(planForm.frequencyEvery) || 1,
      frequencyUnit: planForm.frequencyUnit,
      estimatedMinutes: Number(planForm.estimatedMinutes) || 0,
      responsibleName: planForm.responsibleName ?? "",
      active: planForm.active ?? true,
    };
    setSaving(true);
    try {
      if (editingPlan) await registry.updatePmPlan(editingPlan.id, payload);
      else await registry.createPmPlan(device.id, payload);
      setPlanModalOpen(false);
      setToast(t("registry.pm.saved"));
      await load();
    } catch (error) {
      setToast(error instanceof Error ? error.message : t("registry.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const deletePlan = async (plan: PmPlan): Promise<void> => {
    if (!window.confirm(t("registry.pm.deleteConfirm"))) return;
    try {
      await registry.deletePmPlan(plan.id);
      setToast(t("registry.pm.deleted"));
      await load();
    } catch (error) {
      setToast(error instanceof Error ? error.message : t("registry.saveFailed"));
    }
  };

  const submitExecution = async (): Promise<void> => {
    if (!executePlan) return;
    setSaving(true);
    try {
      await registry.recordPmExecution(executePlan.id, {
        performedOn: executionDate,
        performedByName: executionBy,
        durationMinutes: Number(executionMinutes) || 0,
        findings: executionFindings,
      });
      setExecutePlan(null);
      setExecutionFindings("");
      setToast(t("registry.pm.executed"));
      await load();
    } catch (error) {
      setToast(error instanceof Error ? error.message : t("registry.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const addBomItem = async (): Promise<void> => {
    if (!bomPartId) {
      setToast(t("registry.common.required"));
      return;
    }
    setSaving(true);
    try {
      await registry.addBomItem(device.id, {
        partId: bomPartId,
        position: bomPosition,
        standardQuantity: bomQuantity || "1",
        note: bomNote,
      });
      setBomOpen(false);
      setBomPartId("");
      setBomPosition("");
      setBomQuantity("1");
      setBomNote("");
      setToast(t("registry.parts.added"));
      await load();
    } catch (error) {
      setToast(error instanceof Error ? error.message : t("registry.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  /** «➕ افزودن محل جدید…» from the nameplate's location-change picker. */
  const saveQuickLocation = async (input: QuickLocationInput): Promise<string> => {
    const created = await registry.createLocation({
      code: input.code,
      name: input.name,
      kind: input.kind,
      note: input.note,
    });
    setLocations(await registry.listLocations());
    setToast("محل ثبت شد و انتخاب گردید.");
    return created.id;
  };

  /** «➕ افزودن فرد جدید…» from an assignment row's person picker. */
  const saveQuickPerson = async (input: QuickPersonInput): Promise<string> => {
    const created = await registry.createPersonnel({
      fullName: input.fullName,
      specialty: input.specialty,
      unit: input.unit ?? "",
      phone: input.phone ?? "",
      shift: "",
    });
    setPersonnel(await registry.listPersonnel());
    if (quickPersonTarget !== null) {
      const target = quickPersonTarget;
      setAssignmentRows((rows) =>
        rows.map((item, position) =>
          position === target
            ? {
                ...item,
                personnelId: created.id,
                personnelName: created.fullName,
                unit: item.unit || created.unit || "",
              }
            : item,
        ),
      );
    }
    setToast("فرد ثبت شد و در ردیف انتخاب گردید.");
    return created.id;
  };

  /** «➕ افزودن قطعه‌ی جدید…» from the BOM part picker. */
  const saveQuickPart = async (input: QuickPartInput): Promise<string> => {
    if (runtimeConfig.demoMode) {
      const part: SparePart = {
        id: `part-${Date.now()}`,
        code: input.code.toUpperCase(),
        name: input.name,
        unit: input.unit,
        quantityOnHand: input.quantityOnHand,
        minimumStock: input.minimumStock,
        unitCost: input.unitCost,
        lowStock: input.quantityOnHand <= input.minimumStock,
        createdAt: new Date().toISOString(),
        updatedAt: "",
      };
      setSpareParts((current) => [...current, part]);
      setToast("قطعه ثبت شد و در فرم انتخاب گردید.");
      return part.id;
    }
    const created = await maintenance.createSparePart(input);
    setSpareParts(await maintenance.listSpareParts());
    setToast("قطعه ثبت شد و در فرم انتخاب گردید.");
    return created.id;
  };

  const removeBomItem = async (partId: string): Promise<void> => {
    if (!window.confirm(t("registry.parts.removeConfirm"))) return;
    try {
      await registry.removeBomItem(device.id, partId);
      setToast(t("registry.parts.removed"));
      await load();
    } catch (error) {
      setToast(error instanceof Error ? error.message : t("registry.saveFailed"));
    }
  };

  const saveAssignments = async (): Promise<void> => {
    const rows = assignmentRows.filter((row) => row.personnelId || (row.personnelName ?? "").trim());
    setSaving(true);
    try {
      await registry.saveAssignments(device.id, rows);
      setToast(t("registry.assign.saved"));
      await load();
    } catch (error) {
      setToast(error instanceof Error ? error.message : t("registry.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const printQrLabel = (): void => {
    document.body.classList.add("printing-qr-label");
    window.print();
    window.setTimeout(() => document.body.classList.remove("printing-qr-label"), 200);
  };

  const plansByDiscipline = (discipline: MaintenanceDepartment): PmPlan[] =>
    profile.pmPlans.filter((plan) => plan.discipline === discipline);

  const renderNameplate = (): JSX.Element => (
    <Card className="content-card" padding="md">
      <SectionHeader title={t("registry.nameplate.title")} subtitle={device.name} />
      <div className="form-grid form-grid--compact">
        <TextInput
          label={t("registry.nameplate.manufacturer")}
          value={nameplate.manufacturer}
          onChange={(event) => patchNameplate({ manufacturer: event.target.value })}
        />
        <TextInput
          label={t("registry.nameplate.modelNumber")}
          value={nameplate.modelNumber}
          onChange={(event) => patchNameplate({ modelNumber: event.target.value })}
        />
        <TextInput
          label={t("registry.nameplate.serialNumber")}
          value={nameplate.serialNumber}
          onChange={(event) => patchNameplate({ serialNumber: event.target.value })}
        />
        <TextInput
          label={t("registry.nameplate.assetType")}
          value={nameplate.assetType}
          onChange={(event) => patchNameplate({ assetType: event.target.value })}
        />
        <TextInput
          label={t("registry.nameplate.manufactureYear")}
          value={nameplate.manufactureYear}
          onChange={(event) => patchNameplate({ manufactureYear: event.target.value })}
        />
        <TextInput
          label={t("registry.nameplate.capacity")}
          value={nameplate.capacity}
          onChange={(event) => patchNameplate({ capacity: event.target.value })}
        />
        <TextInput
          label={t("registry.nameplate.powerRating")}
          value={nameplate.powerRating}
          onChange={(event) => patchNameplate({ powerRating: event.target.value })}
        />
        <TextInput
          label={t("registry.nameplate.electricalSpec")}
          value={nameplate.electricalSpec}
          onChange={(event) => patchNameplate({ electricalSpec: event.target.value })}
        />
        <CreatableSelect
          label={t("registry.nameplate.criticality")}
          value={nameplate.criticality}
          onChange={(value) => patchNameplate({ criticality: value as EquipmentCriticality })}
          catalogKey="device.criticality"
          canonical={EQUIPMENT_CRITICALITIES}
          options={mergeOptions({
            canonical: EQUIPMENT_CRITICALITIES,
            translate: (level) => taxonomyLabel(t, "registry.criticality.", level),
            catalogKey: "device.criticality",
            current: nameplate.criticality,
          })}
        />
        <TextInput
          label={t("registry.nameplate.supplier")}
          value={nameplate.supplier}
          onChange={(event) => patchNameplate({ supplier: event.target.value })}
        />
        <JalaliDatePicker
          label={t("registry.nameplate.purchasedOn")}
          value={nameplate.purchasedOn}
          onChange={(value) => patchNameplate({ purchasedOn: value })}
        />
        <JalaliDatePicker
          label={t("registry.nameplate.installedOn")}
          value={nameplate.installedOn}
          onChange={(value) => patchNameplate({ installedOn: value })}
        />
        <JalaliDatePicker
          label={t("registry.nameplate.commissionedOn")}
          value={nameplate.commissionedOn}
          onChange={(value) => patchNameplate({ commissionedOn: value })}
        />
        <JalaliDatePicker
          label={t("registry.nameplate.warrantyUntil")}
          value={nameplate.warrantyUntil}
          onChange={(value) => patchNameplate({ warrantyUntil: value })}
        />
        <TextInput
          label={t("registry.nameplate.purchaseCost")}
          value={nameplate.purchaseCost}
          onChange={(event) => patchNameplate({ purchaseCost: event.target.value })}
        />
        <TextInput
          label={t("registry.nameplate.runningHours")}
          value={nameplate.runningHours}
          onChange={(event) => patchNameplate({ runningHours: event.target.value })}
        />
      </div>
      <TextArea
        label={t("registry.nameplate.notes")}
        value={nameplate.notes}
        onChange={(event) => patchNameplate({ notes: event.target.value })}
      />
      <PermissionGuard permission={PERMISSIONS.maintenanceDeviceManage}>
        <div className="cmms-header-actions">
          <Button variant="primary" icon="check" loading={saving} onClick={saveNameplate}>
            {t("registry.common.save")}
          </Button>
        </div>
      </PermissionGuard>
    </Card>
  );

  const renderSpecifications = (): JSX.Element => (
    <Card className="content-card" padding="md">
      <SectionHeader
        title={t("registry.spec.title")}
        subtitle={t("registry.spec.subtitle")}
        actions={
          <PermissionGuard permission={PERMISSIONS.maintenanceDeviceManage}>
            <Button
              variant="secondary"
              icon="plus"
              onClick={() =>
                setSpecRows((rows) => [...rows, { label: "", value: "", unit: "", sortOrder: rows.length }])
              }
            >
              {t("registry.spec.addRow")}
            </Button>
          </PermissionGuard>
        }
      />
      {specRows.length === 0 ? (
        <EmptyState icon="table" title={t("registry.spec.empty")} />
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>{t("registry.spec.label")}</th>
              <th>{t("registry.spec.value")}</th>
              <th>{t("registry.spec.unit")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {specRows.map((row, index) => (
              <tr key={`spec-${index}`}>
                <td>
                  <TextInput
                    aria-label={t("registry.spec.label")}
                    value={row.label}
                    onChange={(event) =>
                      setSpecRows((rows) =>
                        rows.map((item, position) =>
                          position === index ? { ...item, label: event.target.value } : item,
                        ),
                      )
                    }
                  />
                </td>
                <td>
                  <TextInput
                    aria-label={t("registry.spec.value")}
                    value={row.value ?? ""}
                    onChange={(event) =>
                      setSpecRows((rows) =>
                        rows.map((item, position) =>
                          position === index ? { ...item, value: event.target.value } : item,
                        ),
                      )
                    }
                  />
                </td>
                <td>
                  <TextInput
                    aria-label={t("registry.spec.unit")}
                    value={row.unit ?? ""}
                    onChange={(event) =>
                      setSpecRows((rows) =>
                        rows.map((item, position) =>
                          position === index ? { ...item, unit: event.target.value } : item,
                        ),
                      )
                    }
                  />
                </td>
                <td>
                  <Button
                    variant="ghost"
                    size="sm"
                    icon="close"
                    onClick={() =>
                      setSpecRows((rows) => rows.filter((_, position) => position !== index))
                    }
                  >
                    {t("registry.spec.removeRow")}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <PermissionGuard permission={PERMISSIONS.maintenanceDeviceManage}>
        <div className="cmms-header-actions">
          <Button variant="primary" icon="check" loading={saving} onClick={saveSpecifications}>
            {t("registry.common.save")}
          </Button>
        </div>
      </PermissionGuard>
    </Card>
  );

  const renderPm = (): JSX.Element => (
    <div className="registry-pm">
      <Card className="content-card" padding="md">
        <SectionHeader title={t("registry.pm.title")} subtitle={t("registry.pm.subtitle")} />
        {profile.pmPlans.length === 0 && <EmptyState icon="calendar" title={t("registry.pm.emptyAll")} />}
        <div className="registry-discipline-grid">
          {MAINTENANCE_DEPARTMENTS.map((discipline) => {
            const plans = plansByDiscipline(discipline);
            return (
              <Card key={discipline} padding="sm" className="registry-discipline">
                <div className="registry-discipline__head">
                  <h3>{taxonomyLabel(t, "cmms.department.", discipline)}</h3>
                  <Badge tone={plans.length ? "info" : "neutral"}>
                    {t("registry.pm.planCount")}: {plans.length}
                  </Badge>
                </div>
                {plans.length === 0 ? (
                  <p className="muted-cell">{t("registry.pm.empty")}</p>
                ) : (
                  <ul className="registry-plan-list">
                    {plans.map((plan) => (
                      <li key={plan.id}>
                        <div className="registry-plan-list__main">
                          <strong>{plan.title}</strong>
                          <span className="muted-cell">
                            {t("registry.pm.frequencyEvery")} {plan.frequencyEvery}{" "}
                            {t(`registry.pm.unit.${plan.frequencyUnit}`)}
                            {plan.responsibleName ? ` — ${plan.responsibleName}` : ""}
                          </span>
                          <span className="muted-cell">
                            {t("registry.pm.lastExecuted")}:{" "}
                            {plan.lastExecutedOn
                              ? formatJalali(plan.lastExecutedOn, { style: "short" })
                              : t("registry.common.none")}
                            {plan.nextDueOn
                              ? ` · ${t("registry.pm.nextDue")}: ${formatJalali(plan.nextDueOn, { style: "short" })}`
                              : ""}
                          </span>
                          {plan.checklist.length > 0 && (
                            <ul className="registry-checklist">
                              {plan.checklist.map((item) => (
                                <li key={item}>{item}</li>
                              ))}
                            </ul>
                          )}
                        </div>
                        <div className="registry-plan-list__side">
                          {plan.overdue && <Badge tone="danger" dot>{t("registry.pm.overdue")}</Badge>}
                          {!plan.active && <Badge tone="neutral">{t("registry.pm.inactive")}</Badge>}
                          <PermissionGuard permission={PERMISSIONS.maintenanceDeviceManage}>
                            <Button
                              variant="ghost"
                              size="sm"
                              icon="check"
                              onClick={() => {
                                setExecutionDate(todayIso());
                                setExecutionBy(plan.responsibleName);
                                setExecutionMinutes(String(plan.estimatedMinutes || 30));
                                setExecutePlan(plan);
                              }}
                            >
                              {t("registry.pm.execute")}
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              icon="edit"
                              onClick={() => openPlanModal(plan, discipline)}
                            >
                              {t("registry.common.edit")}
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              icon="close"
                              onClick={() => deletePlan(plan)}
                            >
                              {t("registry.common.delete")}
                            </Button>
                          </PermissionGuard>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
                <PermissionGuard permission={PERMISSIONS.maintenanceDeviceManage}>
                  <Button
                    variant="subtle"
                    size="sm"
                    icon="plus"
                    onClick={() => openPlanModal(null, discipline)}
                  >
                    {t("registry.pm.add")}
                  </Button>
                </PermissionGuard>
              </Card>
            );
          })}
        </div>
      </Card>

      <Card className="content-card" padding="md">
        <SectionHeader title={t("registry.pm.history")} />
        {profile.pmExecutions.length === 0 ? (
          <EmptyState icon="clock" title={t("registry.pm.historyEmpty")} />
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>{t("registry.pm.performedOn")}</th>
                <th>{t("registry.pm.discipline")}</th>
                <th>{t("registry.pm.performedBy")}</th>
                <th>{t("registry.pm.durationMinutes")}</th>
                <th>{t("registry.pm.onTime")}</th>
                <th>{t("registry.pm.findings")}</th>
              </tr>
            </thead>
            <tbody>
              {profile.pmExecutions.map((execution) => (
                <tr key={execution.id}>
                  <td>{formatJalali(execution.performedOn, { style: "short" })}</td>
                  <td>{taxonomyLabel(t, "cmms.department.", execution.discipline)}</td>
                  <td>{execution.performedByName || t("registry.common.none")}</td>
                  <td>{execution.durationMinutes}</td>
                  <td>
                    <Badge tone={execution.onTime ? "success" : "warning"}>
                      {execution.onTime ? t("registry.pm.onTime") : t("registry.pm.late")}
                    </Badge>
                  </td>
                  <td className="muted-cell">{execution.findings || t("registry.common.none")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );

  const renderParts = (): JSX.Element => (
    <Card className="content-card" padding="md">
      <SectionHeader
        title={t("registry.parts.title")}
        subtitle={t("registry.parts.subtitle")}
        actions={
          <PermissionGuard permission={PERMISSIONS.maintenanceDeviceManage}>
            <Button variant="primary" icon="plus" onClick={() => setBomOpen(true)}>
              {t("registry.parts.add")}
            </Button>
          </PermissionGuard>
        }
      />
      {profile.bom.length === 0 ? (
        <EmptyState icon="layers" title={t("registry.parts.empty")} />
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>{t("registry.parts.part")}</th>
              <th>{t("registry.parts.position")}</th>
              <th>{t("registry.parts.standardQuantity")}</th>
              <th>{t("registry.parts.onHand")}</th>
              <th>{t("registry.parts.usageCount")}</th>
              <th>{t("registry.parts.lastUsed")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {profile.bom.map((item) => (
              <tr key={item.id}>
                <td>
                  <strong>{item.partCode}</strong>
                  <div className="muted-cell">{item.partName}</div>
                </td>
                <td className="muted-cell">{item.position || t("registry.common.none")}</td>
                <td>
                  {item.standardQuantity} {item.unit}
                </td>
                <td>
                  {item.quantityOnHand} {item.unit}{" "}
                  {item.lowStock && <Badge tone="danger">{t("registry.parts.lowStock")}</Badge>}
                </td>
                <td>
                  {item.usageCount} ({item.usedQuantity} {item.unit})
                </td>
                <td className="muted-cell">
                  {item.lastUsedAt
                    ? formatJalali(item.lastUsedAt.slice(0, 10), { style: "short" })
                    : t("registry.common.none")}
                </td>
                <td>
                  <PermissionGuard permission={PERMISSIONS.maintenanceDeviceManage}>
                    <Button
                      variant="ghost"
                      size="sm"
                      icon="close"
                      onClick={() => removeBomItem(item.partId)}
                    >
                      {t("registry.common.delete")}
                    </Button>
                  </PermissionGuard>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );

  const renderLocation = (): JSX.Element => (
    <Card className="content-card" padding="md">
      <SectionHeader title={t("registry.location.title")} subtitle={t("registry.location.subtitle")} />
      <div className="registry-summary-grid">
        <div>
          <span className="muted-cell">{t("registry.location.current")}</span>
          <strong>{profile.locationPath || device.location || t("registry.common.none")}</strong>
        </div>
        {/*
          These used to be positional — path segment 0 was labelled "site", 1
          "building", 2 "room". That only held for a three-deep tree; once a
          plant models سایت ← ساختمان ← سالن ← خط ← سیستم, segment 2 is a hall
          being labelled an اتاق. Each level is now read from the real
          location chain and labelled with its own kind, and the list simply
          ends wherever the plant's tree ends.
        */}
        {(ancestry?.locationChain ?? []).map((link) => (
          <div key={link.id}>
            <span className="muted-cell">
              {taxonomyLabel(t, "registry.location.", link.kind ?? "")}
            </span>
            <strong>{link.name}</strong>
          </div>
        ))}
      </div>
      <div className="form-grid form-grid--compact">
        <QuickAddSelect
          label={t("registry.location.change")}
          value={nameplate.locationId}
          onChange={(value) => patchNameplate({ locationId: value })}
          addLabel="➕ افزودن محل جدید…"
          onQuickAdd={() => setQuickLocationOpen(true)}
          options={[
            { value: "", label: t("registry.nameplate.noLocation") },
            ...locations.map((location) => ({ value: location.id, label: location.path })),
          ]}
        />
        <TextInput
          label={t("registry.nameplate.operatorUnit")}
          value={nameplate.operatorUnit}
          onChange={(event) => patchNameplate({ operatorUnit: event.target.value })}
        />
      </div>
      <PermissionGuard permission={PERMISSIONS.maintenanceDeviceManage}>
        <div className="cmms-header-actions">
          <Button variant="primary" icon="check" loading={saving} onClick={saveNameplate}>
            {t("registry.common.save")}
          </Button>
          <Button
            variant="secondary"
            icon="building"
            onClick={() => navigate("/app/maintenance/locations")}
          >
            {t("registry.location.pageTitle")}
          </Button>
        </div>
      </PermissionGuard>
    </Card>
  );

  const submitMove = async (): Promise<void> => {
    if (!deviceId) return;
    setHierarchyBusy(true);
    try {
      await registry.moveAsset(deviceId, {
        toLocationId: moveLocationId,
        movedOn: moveDate,
        reason: moveReason,
        performedBy: moveBy,
        updateInstalledOn: moveUpdateInstalled,
      });
      setMoveOpen(false);
      setMoveLocationId("");
      setMoveReason("");
      setMoveBy("");
      setMoveUpdateInstalled(false);
      setToast(t("assets.move.success"));
      await load();
    } catch (error) {
      setToast((error as Error).message || t("error.networkBody"));
    } finally {
      setHierarchyBusy(false);
    }
  };

  const submitRetire = async (): Promise<void> => {
    if (!deviceId) return;
    setHierarchyBusy(true);
    try {
      await registry.retireAsset(deviceId, {
        retiredOn: retireDate,
        reason: retireReason,
        retireChildren,
      });
      setRetireOpen(false);
      setRetireReason("");
      setRetireChildren(false);
      setToast(t("assets.retire.success"));
      await load();
    } catch (error) {
      setToast((error as Error).message || t("error.networkBody"));
    } finally {
      setHierarchyBusy(false);
    }
  };

  const submitReinstate = async (): Promise<void> => {
    if (!deviceId) return;
    setHierarchyBusy(true);
    try {
      await registry.reinstateAsset(deviceId, "operational");
      setToast(t("assets.reinstate.success"));
      await load();
    } catch (error) {
      setToast((error as Error).message || t("error.networkBody"));
    } finally {
      setHierarchyBusy(false);
    }
  };

  /**
   * The asset's place in the plant chain, and the two writes that change it.
   *
   * The device row only ever holds *where it is now*; the ledger below is
   * what makes "محل نصب قبلی" answerable after the second transfer.
   */
  const renderHierarchy = (): JSX.Element => {
    const isRetired = device.status === "retired";
    const chain = [...(ancestry?.locationChain ?? []), ...(ancestry?.deviceChain ?? [])];
    return (
      <Card className="content-card" padding="md">
        <SectionHeader
          title={t("assets.tree.title")}
          subtitle={t("assets.tree.subtitle")}
          actions={
            <PermissionGuard permission={PERMISSIONS.maintenanceDeviceManage}>
              <div className="cmms-header-actions">
                <Button
                  variant="secondary"
                  icon="layers"
                  onClick={() => navigate("/app/maintenance/asset-tree")}
                >
                  {t("assets.tree.nav")}
                </Button>
                {isRetired ? (
                  <Button
                    variant="secondary"
                    icon="refresh"
                    loading={hierarchyBusy}
                    onClick={submitReinstate}
                  >
                    {t("assets.reinstate.action")}
                  </Button>
                ) : (
                  <>
                    <Button
                      variant="secondary"
                      icon="arrowLeft"
                      onClick={() => {
                        setMoveDate(todayIso());
                        setMoveOpen(true);
                      }}
                    >
                      {t("assets.move.action")}
                    </Button>
                    <Button
                      variant="danger"
                      icon="xCircle"
                      onClick={() => {
                        setRetireDate(todayIso());
                        setRetireOpen(true);
                      }}
                    >
                      {t("assets.retire.action")}
                    </Button>
                  </>
                )}
              </div>
            </PermissionGuard>
          }
        />

        <div className="registry-summary-grid">
          <div>
            <span className="muted-cell">{t("assets.level.label")}</span>
            <strong>
              {taxonomyLabel(t, "assets.level.", nameplate.assetLevel || "mainEquipment")}
            </strong>
          </div>
          <div>
            <span className="muted-cell">{t("assets.previousLocation")}</span>
            <strong>
              {ancestry?.previousLocation?.locationPath || t("assets.previousLocation.none")}
            </strong>
          </div>
          <div>
            <span className="muted-cell">{t("assets.installedOn")}</span>
            <strong>
              {nameplate.installedOn
                ? formatJalali(nameplate.installedOn)
                : t("registry.common.none")}
            </strong>
          </div>
          <div>
            <span className="muted-cell">{t("assets.costCenter")}</span>
            <strong>
              {nameplate.costCenterCode
                ? `${nameplate.costCenterCode} — ${nameplate.costCenterName}`
                : t("assets.costCenter.none")}
            </strong>
          </div>
        </div>

        {chain.length > 0 ? (
          <div className="asset-chain">
            <span className="muted-cell">{t("assets.upstream")}</span>
            <div className="asset-chain__links">
              {chain.map((node) => (
                <span key={`${node.nodeType}-${node.id}`} className="asset-chain__link">
                  <Icon name={node.nodeType === "device" ? "cpu" : "building"} size={13} />
                  {node.name}
                </span>
              ))}
            </div>
          </div>
        ) : (
          <p className="muted-cell">{t("assets.upstream.none")}</p>
        )}

        <div className="form-grid form-grid--compact">
          <SelectInput
            label={t("assets.level.label")}
            value={nameplate.assetLevel || "mainEquipment"}
            onChange={(event) => patchNameplate({ assetLevel: event.target.value })}
            options={ASSET_LEVELS.map((level) => ({
              value: level,
              label: taxonomyLabel(t, "assets.level.", level),
            }))}
          />
          <TextInput
            label={t("assets.costCenter.code")}
            value={nameplate.costCenterCode}
            onChange={(event) => patchNameplate({ costCenterCode: event.target.value })}
          />
          <TextInput
            label={t("assets.costCenter.name")}
            value={nameplate.costCenterName}
            onChange={(event) => patchNameplate({ costCenterName: event.target.value })}
          />
        </div>
        <PermissionGuard permission={PERMISSIONS.maintenanceDeviceManage}>
          <div className="cmms-header-actions">
            <Button variant="primary" icon="check" loading={saving} onClick={saveNameplate}>
              {t("registry.common.save")}
            </Button>
          </div>
        </PermissionGuard>

        <SectionHeader
          title={t("assets.children")}
          subtitle={ancestry ? `${ancestry.descendantCount}` : ""}
        />
        {(ancestry?.children.length ?? 0) === 0 ? (
          <EmptyState icon="cpu" title={t("assets.children.none")} />
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>{t("registry.column.code")}</th>
                <th>{t("registry.column.name")}</th>
                <th>{t("assets.level.label")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(ancestry?.children ?? []).map((child) => (
                <tr key={child.id}>
                  <td className="plaintext">{child.code}</td>
                  <td>{child.name}</td>
                  <td>{taxonomyLabel(t, "assets.level.", child.assetLevel)}</td>
                  <td>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() =>
                        navigate(`/app/maintenance/devices/${child.id}/profile`)
                      }
                    >
                      {t("registry.openProfile")}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <SectionHeader
          title={t("assets.movements.title")}
          subtitle={t("assets.movements.subtitle")}
        />
        {movements.length === 0 ? (
          <EmptyState icon="clock" title={t("assets.movements.empty")} />
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>{t("assets.movements.date")}</th>
                <th>{t("assets.movements.from")}</th>
                <th>{t("assets.movements.to")}</th>
                <th>{t("assets.movements.reason")}</th>
                <th>{t("assets.movements.performedBy")}</th>
              </tr>
            </thead>
            <tbody>
              {movements.map((row) => (
                <tr key={row.id}>
                  <td>{formatJalali(row.movedOn)}</td>
                  <td>{row.fromLocationPath || "—"}</td>
                  <td>{row.toLocationPath || "—"}</td>
                  <td>{row.reason || "—"}</td>
                  <td>{row.performedBy || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    );
  };

  const renderPersonnel = (): JSX.Element => (
    <div className="registry-pm">
      <Card className="content-card" padding="md">
        <SectionHeader
          title={t("registry.assign.title")}
          subtitle={t("registry.assign.subtitle")}
          actions={
            <PermissionGuard permission={PERMISSIONS.maintenanceDeviceManage}>
              <Button
                variant="secondary"
                icon="plus"
                onClick={() =>
                  setAssignmentRows((rows) => [
                    ...rows,
                    { personnelId: "", personnelName: "", role: "technician", unit: "", fromDate: "", toDate: "" },
                  ])
                }
              >
                {t("registry.assign.addRow")}
              </Button>
            </PermissionGuard>
          }
        />
        {assignmentRows.length === 0 ? (
          <EmptyState icon="users" title={t("registry.assign.empty")} />
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>{t("registry.assign.role")}</th>
                <th>{t("registry.assign.person")}</th>
                <th>{t("registry.assign.unit")}</th>
                <th>{t("registry.assign.fromDate")}</th>
                <th>{t("registry.assign.toDate")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {assignmentRows.map((row, index) => (
                <tr key={`assign-${index}`}>
                  <td>
                    <CreatableSelect
                      label={t("registry.assign.role")}
                      value={row.role}
                      onChange={(value) =>
                        setAssignmentRows((rows) =>
                          rows.map((item, position) =>
                            position === index
                              ? { ...item, role: value as DeviceAssignmentRole }
                              : item,
                          ),
                        )
                      }
                      catalogKey="assignment.role"
                      canonical={DEVICE_ASSIGNMENT_ROLES}
                      options={mergeOptions({
                        canonical: DEVICE_ASSIGNMENT_ROLES,
                        translate: (role) => taxonomyLabel(t, "registry.role.", role),
                        fromData: assignmentRows.map((item) => item.role),
                        catalogKey: "assignment.role",
                        current: row.role,
                      })}
                    />
                  </td>
                  <td>
                    <QuickAddSelect
                      ariaLabel={t("registry.assign.person")}
                      value={row.personnelId ?? ""}
                      onChange={(value) => {
                        const person = personnel.find((item) => item.id === value);
                        setAssignmentRows((rows) =>
                          rows.map((item, position) =>
                            position === index
                              ? {
                                  ...item,
                                  personnelId: value,
                                  personnelName: person?.fullName ?? "",
                                  unit: item.unit || person?.unit || "",
                                }
                              : item,
                          ),
                        );
                      }}
                      addLabel="➕ افزودن فرد جدید…"
                      onQuickAdd={() => setQuickPersonTarget(index)}
                      options={[
                        { value: "", label: t("registry.assign.manual") },
                        ...personnel.map((person) => ({
                          value: person.id,
                          label: `${person.fullName} — ${taxonomyLabel(t, "cmms.department.", person.specialty)}`,
                        })),
                      ]}
                    />
                    {!row.personnelId && (
                      <TextInput
                        aria-label={t("registry.assign.manual")}
                        value={row.personnelName ?? ""}
                        onChange={(event) =>
                          setAssignmentRows((rows) =>
                            rows.map((item, position) =>
                              position === index
                                ? { ...item, personnelName: event.target.value }
                                : item,
                            ),
                          )
                        }
                      />
                    )}
                  </td>
                  <td>
                    <TextInput
                      aria-label={t("registry.assign.unit")}
                      value={row.unit ?? ""}
                      onChange={(event) =>
                        setAssignmentRows((rows) =>
                          rows.map((item, position) =>
                            position === index ? { ...item, unit: event.target.value } : item,
                          ),
                        )
                      }
                    />
                  </td>
                  <td>
                    <JalaliDatePicker
                      label=""
                      value={row.fromDate ?? ""}
                      onChange={(value) =>
                        setAssignmentRows((rows) =>
                          rows.map((item, position) =>
                            position === index ? { ...item, fromDate: value } : item,
                          ),
                        )
                      }
                    />
                  </td>
                  <td>
                    <JalaliDatePicker
                      label=""
                      value={row.toDate ?? ""}
                      onChange={(value) =>
                        setAssignmentRows((rows) =>
                          rows.map((item, position) =>
                            position === index ? { ...item, toDate: value } : item,
                          ),
                        )
                      }
                    />
                  </td>
                  <td>
                    <Button
                      variant="ghost"
                      size="sm"
                      icon="close"
                      onClick={() =>
                        setAssignmentRows((rows) => rows.filter((_, position) => position !== index))
                      }
                    >
                      {t("registry.common.delete")}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <PermissionGuard permission={PERMISSIONS.maintenanceDeviceManage}>
          <div className="cmms-header-actions">
            <Button variant="primary" icon="check" loading={saving} onClick={saveAssignments}>
              {t("registry.common.save")}
            </Button>
            <Button
              variant="secondary"
              icon="users"
              onClick={() => navigate("/app/maintenance/personnel")}
            >
              {t("registry.personnel.directory")}
            </Button>
          </div>
        </PermissionGuard>
      </Card>

      <Card className="content-card" padding="md">
        <SectionHeader title={t("registry.personnel.assignedTo")} />
        {profile.assignments.length === 0 ? (
          <EmptyState icon="users" title={t("registry.assign.empty")} />
        ) : (
          <div className="registry-people-grid">
            {profile.assignments.map((assignment) => {
              const person = personnel.find((item) => item.id === assignment.personnelId);
              return (
                <Card key={assignment.id} padding="sm">
                  <div className="registry-person">
                    <Icon name="user" size={22} />
                    <div>
                      <strong>{assignment.personnelName || t("registry.common.none")}</strong>
                      <div className="muted-cell">{taxonomyLabel(t, "registry.role.", assignment.role)}</div>
                      <div className="muted-cell">{assignment.unit || t("registry.common.none")}</div>
                      {person && (
                        <div className="muted-cell">
                          {taxonomyLabel(t, "cmms.department.", person.specialty)}
                          {person.phone ? ` · ${person.phone}` : ""}
                          {person.shift ? ` · ${person.shift}` : ""}
                        </div>
                      )}
                    </div>
                    <Badge tone={assignment.current ? "success" : "neutral"}>
                      {assignment.current ? t("registry.assign.current") : t("registry.assign.past")}
                    </Badge>
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );

  const renderAnalytics = (): JSX.Element => (
    <Card className="content-card" padding="md">
      <SectionHeader
        title={t("registry.analytics.title")}
        subtitle={t("registry.analytics.subtitle")}
        actions={
          <Button
            variant="secondary"
            icon="chart"
            onClick={() => navigate(`/app/maintenance/devices/${device.id}/report`)}
          >
            {t("cmms.report.action")}
          </Button>
        }
      />
      {!analytics ? (
        <EmptyState icon="chart" title={t("registry.analytics.noData")} />
      ) : (
        <>
          <div className="metric-grid">
            <MetricCard
              label={t("registry.analytics.mtbf")}
              value={formatNumber(analytics.mtbfHours)}
              icon="clock"
              tone="blue"
            />
            <MetricCard
              label={t("registry.analytics.mttr")}
              value={formatNumber(analytics.mttrHours)}
              icon="refresh"
              tone="amber"
            />
            <MetricCard
              label={t("registry.analytics.availability")}
              value={formatNumber(analytics.availabilityPercent)}
              icon="activity"
              tone="green"
            />
            <MetricCard
              label={t("registry.analytics.pmCompliance")}
              value={formatNumber(analytics.pmCompliancePercent)}
              icon="checkCircle"
              tone="purple"
            />
          </div>
          <div className="registry-summary-grid">
            <div>
              <span className="muted-cell">{t("registry.analytics.repairs")}</span>
              <strong>{analytics.repairCount}</strong>
            </div>
            <div>
              <span className="muted-cell">{t("registry.analytics.preventive")}</span>
              <strong>{analytics.preventiveCount}</strong>
            </div>
            <div>
              <span className="muted-cell">{t("registry.analytics.repeatFailures")}</span>
              <strong>{analytics.repeatFailures}</strong>
            </div>
            <div>
              <span className="muted-cell">{t("registry.analytics.downtime")}</span>
              <strong>{formatNumber(analytics.totalDowntimeHours)}</strong>
            </div>
            <div>
              <span className="muted-cell">{t("registry.analytics.labourCost")}</span>
              <strong>{formatMoney(analytics.labourCost)}</strong>
            </div>
            <div>
              <span className="muted-cell">{t("registry.analytics.partsCost")}</span>
              <strong>{formatMoney(analytics.partsCost)}</strong>
            </div>
            <div>
              <span className="muted-cell">{t("registry.analytics.cost")}</span>
              <strong>{formatMoney(analytics.totalCost)}</strong>
            </div>
          </div>
          <div className="registry-discipline-grid">
            {[
              { title: t("registry.analytics.byFailureType"), rows: analytics.byFailureType },
              { title: t("registry.analytics.byComponent"), rows: analytics.byFailedComponent },
              { title: t("registry.analytics.byRootCause"), rows: analytics.byRootCause },
            ].map((group) => (
              <Card key={group.title} padding="sm">
                <h3>{group.title}</h3>
                {group.rows.length === 0 ? (
                  <p className="muted-cell">{t("registry.analytics.noData")}</p>
                ) : (
                  <ul className="registry-checklist">
                    {group.rows.map((row) => (
                      <li key={`${group.title}-${row.label}`}>
                        {row.label} — {row.count}
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            ))}
          </div>
          {analytics.technicians.length > 0 && (
            <>
              <h3>{t("registry.analytics.technicians")}</h3>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{t("registry.assign.person")}</th>
                    <th>{t("registry.analytics.repairs")}</th>
                    <th>{t("registry.analytics.preventive")}</th>
                    <th>{t("registry.analytics.mttr")}</th>
                  </tr>
                </thead>
                <tbody>
                  {analytics.technicians.map((technician) => (
                    <tr key={technician.name}>
                      <td>{technician.name}</td>
                      <td>{technician.correctiveOrders}</td>
                      <td>{technician.preventiveOrders}</td>
                      <td>{formatNumber(technician.averageRepairHours)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </>
      )}
    </Card>
  );

  return (
    <div className="page">
      <SectionHeader
        eyebrow={t("registry.profile.title")}
        title={`${device.code} — ${device.name}`}
        subtitle={profile.locationPath || device.location}
        actions={
          <div className="cmms-header-actions">
            <Button
              variant="secondary"
              icon="arrowRight"
              onClick={() => navigate("/app/maintenance/registry")}
            >
              {t("registry.profile.back")}
            </Button>
            <Button
              variant="secondary"
              icon="clock"
              onClick={() => navigate(`/app/maintenance/devices/${device.id}/timeline`)}
            >
              {t("cmms.timeline.action")}
            </Button>
            <Button variant="secondary" icon="grid" onClick={() => setQrOpen(true)}>
              {t("registry.qr.button")}
            </Button>
          </div>
        }
      />

      <div className="registry-hero">
        <Badge tone="info" dot>
          {taxonomyLabel(t, "cmms.status.", device.status)}
        </Badge>
        <Badge tone="neutral">{taxonomyLabel(t, "cmms.department.", device.department)}</Badge>
        <Badge tone="purple">
          {t("registry.column.criticality")}: {taxonomyLabel(t, "registry.criticality.", nameplate.criticality)}
        </Badge>
        <span className="muted-cell">
          {nameplate.manufacturer || t("registry.common.none")}
          {nameplate.modelNumber ? ` / ${nameplate.modelNumber}` : ""}
          {nameplate.serialNumber ? ` · ${t("registry.column.serial")}: ${nameplate.serialNumber}` : ""}
        </span>
      </div>

      <div className="registry-tabs" role="tablist">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            className={`registry-tab ${tab === item.id ? "registry-tab--active" : ""}`}
            onClick={() => setTab(item.id)}
          >
            <Icon name={item.icon} size={16} />
            <span>{t(item.labelKey as Parameters<typeof t>[0])}</span>
          </button>
        ))}
      </div>

      {tab === "nameplate" && renderNameplate()}
      {tab === "specifications" && renderSpecifications()}
      {tab === "pm" && renderPm()}
      {tab === "parts" && renderParts()}
      {tab === "location" && (
        <>
          {renderLocation()}
          {renderHierarchy()}
        </>
      )}
      {tab === "personnel" && renderPersonnel()}
      {tab === "analytics" && renderAnalytics()}

      <Modal
        open={planModalOpen}
        title={editingPlan ? t("registry.pm.editTitle") : t("registry.pm.createTitle")}
        onClose={() => setPlanModalOpen(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setPlanModalOpen(false)}>
              {t("registry.common.cancel")}
            </Button>
            <Button variant="primary" icon="check" loading={saving} onClick={savePlan}>
              {t("registry.common.save")}
            </Button>
          </>
        }
      >
        <TextInput
          label={t("registry.pm.planTitle")}
          required
          value={planForm.title}
          onChange={(event) => setPlanForm((form) => ({ ...form, title: event.target.value }))}
        />
        <div className="form-grid form-grid--compact">
          <CreatableSelect
            label={t("registry.pm.discipline")}
            value={planForm.discipline}
            onChange={(value) =>
              setPlanForm((form) => ({ ...form, discipline: value as MaintenanceDepartment }))
            }
            catalogKey="pm.discipline"
            canonical={MAINTENANCE_DEPARTMENTS}
            options={mergeOptions({
              canonical: MAINTENANCE_DEPARTMENTS,
              translate: (department) => taxonomyLabel(t, "cmms.department.", department),
              fromData: profile.pmPlans.map((plan) => plan.discipline),
              catalogKey: "pm.discipline",
              current: planForm.discipline,
            })}
          />
          <TextInput
            label={t("registry.pm.frequencyEvery")}
            type="number"
            value={String(planForm.frequencyEvery)}
            onChange={(event) =>
              setPlanForm((form) => ({ ...form, frequencyEvery: Number(event.target.value) || 1 }))
            }
          />
          <SelectInput
            label={t("registry.pm.frequencyUnit")}
            value={planForm.frequencyUnit}
            onChange={(event) =>
              setPlanForm((form) => ({
                ...form,
                frequencyUnit: event.target.value as PmFrequencyUnit,
              }))
            }
            options={PM_FREQUENCY_UNITS.map((unit) => ({
              value: unit,
              label: t(`registry.pm.unit.${unit}`),
            }))}
          />
          <TextInput
            label={t("registry.pm.estimatedMinutes")}
            type="number"
            value={String(planForm.estimatedMinutes)}
            onChange={(event) =>
              setPlanForm((form) => ({
                ...form,
                estimatedMinutes: Number(event.target.value) || 0,
              }))
            }
          />
          <TextInput
            label={t("registry.pm.responsible")}
            value={planForm.responsibleName ?? ""}
            onChange={(event) =>
              setPlanForm((form) => ({ ...form, responsibleName: event.target.value }))
            }
          />
          <SelectInput
            label={t("registry.pm.active")}
            value={planForm.active ? "yes" : "no"}
            onChange={(event) =>
              setPlanForm((form) => ({ ...form, active: event.target.value === "yes" }))
            }
            options={[
              { value: "yes", label: t("registry.pm.active") },
              { value: "no", label: t("registry.pm.inactive") },
            ]}
          />
        </div>
        <TextArea
          label={t("registry.pm.description")}
          value={planForm.description ?? ""}
          onChange={(event) => setPlanForm((form) => ({ ...form, description: event.target.value }))}
        />
        <TextArea
          label={t("registry.pm.checklist")}
          value={planForm.checklistText}
          onChange={(event) =>
            setPlanForm((form) => ({ ...form, checklistText: event.target.value }))
          }
        />
      </Modal>

      <Modal
        open={Boolean(executePlan)}
        title={t("registry.pm.executeTitle")}
        description={executePlan?.title}
        onClose={() => setExecutePlan(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setExecutePlan(null)}>
              {t("registry.common.cancel")}
            </Button>
            <Button variant="primary" icon="check" loading={saving} onClick={submitExecution}>
              {t("registry.common.save")}
            </Button>
          </>
        }
      >
        <JalaliDatePicker
          label={t("registry.pm.performedOn")}
          value={executionDate}
          onChange={setExecutionDate}
        />
        <div className="form-grid form-grid--compact">
          <TextInput
            label={t("registry.pm.performedBy")}
            value={executionBy}
            onChange={(event) => setExecutionBy(event.target.value)}
          />
          <TextInput
            label={t("registry.pm.durationMinutes")}
            type="number"
            value={executionMinutes}
            onChange={(event) => setExecutionMinutes(event.target.value)}
          />
        </div>
        <TextArea
          label={t("registry.pm.findings")}
          value={executionFindings}
          onChange={(event) => setExecutionFindings(event.target.value)}
        />
      </Modal>

      <Modal
        open={bomOpen}
        title={t("registry.parts.add")}
        onClose={() => setBomOpen(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setBomOpen(false)}>
              {t("registry.common.cancel")}
            </Button>
            <Button variant="primary" icon="check" loading={saving} onClick={addBomItem}>
              {t("registry.common.save")}
            </Button>
          </>
        }
      >
        {spareParts.length === 0 ? (
          <p className="muted-cell">{t("registry.parts.noCatalog")}</p>
        ) : (
          <>
            <QuickAddSelect
              label={t("registry.parts.part")}
              value={bomPartId}
              onChange={setBomPartId}
              addLabel="➕ افزودن قطعه‌ی جدید…"
              onQuickAdd={() => setQuickPartOpen(true)}
              options={[
                { value: "", label: t("registry.common.none") },
                ...spareParts.map((part) => ({
                  value: part.id,
                  label: `${part.code} — ${part.name}`,
                })),
              ]}
            />
            <div className="form-grid form-grid--compact">
              <TextInput
                label={t("registry.parts.position")}
                value={bomPosition}
                onChange={(event) => setBomPosition(event.target.value)}
              />
              <TextInput
                label={t("registry.parts.standardQuantity")}
                value={bomQuantity}
                onChange={(event) => setBomQuantity(event.target.value)}
              />
            </div>
            <TextArea
              label={t("registry.parts.note")}
              value={bomNote}
              onChange={(event) => setBomNote(event.target.value)}
            />
          </>
        )}
      </Modal>

      <Modal
        open={moveOpen}
        title={t("assets.move.title")}
        description={t("assets.movements.subtitle")}
        onClose={() => setMoveOpen(false)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setMoveOpen(false)}>
              {t("registry.common.cancel")}
            </Button>
            <Button
              variant="primary"
              icon="check"
              loading={hierarchyBusy}
              disabled={!moveLocationId}
              onClick={submitMove}
            >
              {t("assets.move.submit")}
            </Button>
          </>
        }
      >
        <div className="form-grid form-grid--compact">
          <SelectInput
            label={t("assets.move.toLocation")}
            value={moveLocationId}
            onChange={(event) => setMoveLocationId(event.target.value)}
            options={[
              { value: "", label: t("registry.nameplate.noLocation") },
              ...locations
                .filter((location) => location.id !== nameplate.locationId)
                .map((location) => ({ value: location.id, label: location.path })),
            ]}
          />
          <JalaliDatePicker
            label={t("assets.movements.date")}
            value={moveDate}
            onChange={setMoveDate}
          />
          <TextInput
            label={t("assets.movements.reason")}
            value={moveReason}
            onChange={(event) => setMoveReason(event.target.value)}
          />
          <TextInput
            label={t("assets.movements.performedBy")}
            value={moveBy}
            onChange={(event) => setMoveBy(event.target.value)}
          />
        </div>
        <label className="checkbox-field">
          <input
            type="checkbox"
            checked={moveUpdateInstalled}
            onChange={(event) => setMoveUpdateInstalled(event.target.checked)}
          />
          <span>{t("assets.move.updateInstalledOn")}</span>
        </label>
      </Modal>

      <Modal
        open={retireOpen}
        title={t("assets.retire.title")}
        onClose={() => setRetireOpen(false)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setRetireOpen(false)}>
              {t("registry.common.cancel")}
            </Button>
            <Button
              variant="danger"
              icon="xCircle"
              loading={hierarchyBusy}
              onClick={submitRetire}
            >
              {t("assets.retire.submit")}
            </Button>
          </>
        }
      >
        <div className="form-grid form-grid--compact">
          <JalaliDatePicker
            label={t("assets.retire.date")}
            value={retireDate}
            onChange={setRetireDate}
          />
          <TextInput
            label={t("assets.retire.reason")}
            value={retireReason}
            onChange={(event) => setRetireReason(event.target.value)}
          />
        </div>
        {(ancestry?.descendantCount ?? 0) > 0 ? (
          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={retireChildren}
              onChange={(event) => setRetireChildren(event.target.checked)}
            />
            <span>{t("assets.retire.withChildren")}</span>
          </label>
        ) : null}
      </Modal>

      <QuickLocationModal
        open={quickLocationOpen}
        onClose={() => setQuickLocationOpen(false)}
        onSave={saveQuickLocation}
        onCreated={(id) => patchNameplate({ locationId: id })}
      />

      <QuickPersonModal
        open={quickPersonTarget !== null}
        onClose={() => setQuickPersonTarget(null)}
        onSave={saveQuickPerson}
        onCreated={() => setQuickPersonTarget(null)}
      />

      <QuickPartModal
        open={quickPartOpen}
        onClose={() => setQuickPartOpen(false)}
        onSave={saveQuickPart}
        onCreated={setBomPartId}
      />

      <Modal
        open={qrOpen}
        title={t("registry.qr.title")}
        onClose={() => setQrOpen(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setQrOpen(false)}>
              {t("common.close")}
            </Button>
            <Button variant="primary" icon="file" onClick={printQrLabel}>
              {t("registry.qr.print")}
            </Button>
          </>
        }
      >
        <div className="qr-label-wrap" dir="rtl">
          <div className="qr-label">
            <div className="qr-label__head">
              <strong>{device.code}</strong>
              <span>{device.name}</span>
            </div>
            <canvas ref={qrCanvas} className="qr-label__canvas" aria-label={t("registry.qr.title")} />
            <small dir="ltr">{deviceProfilePath(device.id)}</small>
          </div>
          <p className="muted-cell">{t("registry.qr.hint")}</p>
        </div>
      </Modal>

      {toast && <Toast message={toast} onClose={() => setToast("")} />}
    </div>
  );
}
