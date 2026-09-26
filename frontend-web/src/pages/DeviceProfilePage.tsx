import { useCallback, useEffect, useMemo, useState } from "react";
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
  DEVICE_ASSIGNMENT_ROLES,
  EQUIPMENT_CRITICALITIES,
  MAINTENANCE_DEPARTMENTS,
  PM_FREQUENCY_UNITS,
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
import { formatJalali, todayIso } from "../core/localization/jalali";

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

  if (loading) return <LoadingState label={t("registry.profile.loading")} />;
  if (failed || !profile || !nameplate) {
    return (
      <div className="page" dir="rtl">
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
        <SelectInput
          label={t("registry.nameplate.criticality")}
          value={nameplate.criticality}
          onChange={(event) =>
            patchNameplate({ criticality: event.target.value as EquipmentCriticality })
          }
          options={EQUIPMENT_CRITICALITIES.map((level) => ({
            value: level,
            label: t(`registry.criticality.${level}`),
          }))}
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
                  <h3>{t(`cmms.department.${discipline}`)}</h3>
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
                  <td>{t(`cmms.department.${execution.discipline}`)}</td>
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
        <div>
          <span className="muted-cell">{t("registry.location.site")}</span>
          <strong>{profile.locationPath.split(" / ")[0] || t("registry.common.none")}</strong>
        </div>
        <div>
          <span className="muted-cell">{t("registry.location.building")}</span>
          <strong>{profile.locationPath.split(" / ")[1] || t("registry.common.none")}</strong>
        </div>
        <div>
          <span className="muted-cell">{t("registry.location.room")}</span>
          <strong>{profile.locationPath.split(" / ")[2] || t("registry.common.none")}</strong>
        </div>
      </div>
      <div className="form-grid form-grid--compact">
        <SelectInput
          label={t("registry.location.change")}
          value={nameplate.locationId}
          onChange={(event) => patchNameplate({ locationId: event.target.value })}
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
                    <SelectInput
                      aria-label={t("registry.assign.role")}
                      value={row.role}
                      onChange={(event) =>
                        setAssignmentRows((rows) =>
                          rows.map((item, position) =>
                            position === index
                              ? { ...item, role: event.target.value as DeviceAssignmentRole }
                              : item,
                          ),
                        )
                      }
                      options={DEVICE_ASSIGNMENT_ROLES.map((role) => ({
                        value: role,
                        label: t(`registry.role.${role}`),
                      }))}
                    />
                  </td>
                  <td>
                    <SelectInput
                      aria-label={t("registry.assign.person")}
                      value={row.personnelId ?? ""}
                      onChange={(event) => {
                        const person = personnel.find((item) => item.id === event.target.value);
                        setAssignmentRows((rows) =>
                          rows.map((item, position) =>
                            position === index
                              ? {
                                  ...item,
                                  personnelId: event.target.value,
                                  personnelName: person?.fullName ?? "",
                                  unit: item.unit || person?.unit || "",
                                }
                              : item,
                          ),
                        );
                      }}
                      options={[
                        { value: "", label: t("registry.assign.manual") },
                        ...personnel.map((person) => ({
                          value: person.id,
                          label: `${person.fullName} — ${t(`cmms.department.${person.specialty}`)}`,
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
                      <div className="muted-cell">{t(`registry.role.${assignment.role}`)}</div>
                      <div className="muted-cell">{assignment.unit || t("registry.common.none")}</div>
                      {person && (
                        <div className="muted-cell">
                          {t(`cmms.department.${person.specialty}`)}
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
    <div className="page" dir="rtl">
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
          </div>
        }
      />

      <div className="registry-hero">
        <Badge tone="info" dot>
          {t(`cmms.status.${device.status}`)}
        </Badge>
        <Badge tone="neutral">{t(`cmms.department.${device.department}`)}</Badge>
        <Badge tone="purple">
          {t("registry.column.criticality")}: {t(`registry.criticality.${nameplate.criticality}`)}
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
      {tab === "location" && renderLocation()}
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
          <SelectInput
            label={t("registry.pm.discipline")}
            value={planForm.discipline}
            onChange={(event) =>
              setPlanForm((form) => ({
                ...form,
                discipline: event.target.value as MaintenanceDepartment,
              }))
            }
            options={MAINTENANCE_DEPARTMENTS.map((department) => ({
              value: department,
              label: t(`cmms.department.${department}`),
            }))}
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
            <SelectInput
              label={t("registry.parts.part")}
              value={bomPartId}
              onChange={(event) => setBomPartId(event.target.value)}
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

      {toast && <Toast message={toast} onClose={() => setToast("")} />}
    </div>
  );
}
