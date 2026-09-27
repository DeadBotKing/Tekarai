import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApiClient } from "../core/api/apiContext";
import { useLocalization } from "../core/localization/localizationContext";
import { PERMISSIONS } from "../core/permissions/permissionContext";
import { runtimeConfig } from "../app/configuration/runtimeConfig";
import { createRegistryService } from "../features/maintenance/registryService";
import { createDemoRegistryService } from "../features/maintenance/registryDemoData";
import {
  MAINTENANCE_DEPARTMENTS,
  type MaintenanceDepartment,
  type MaintenancePersonnel,
} from "../shared/types/domain";
import { DataTable, type DataTableColumn } from "../shared/components/DataTable";
import { Modal, Toast } from "../shared/components/overlays";
import { taxonomyLabel } from "../core/localization/taxonomyLabel";
import {
  Badge,
  Button,
  Card,
  MetricCard,
  PermissionGuard,
  SectionHeader,
  SelectInput,
  TextArea,
  TextInput,
} from "../shared/components/primitives";
import { CreatableSelect } from "../shared/components/CreatableSelect";
import { mergeOptions } from "../features/maintenance/optionCatalog";

/** Directory of maintenance staff that devices and PM plans are assigned to. */
export function MaintenancePersonnelPage(): JSX.Element {
  const { t } = useLocalization();
  const navigate = useNavigate();
  const api = useApiClient();
  const registry = useMemo(
    () => (runtimeConfig.demoMode ? createDemoRegistryService() : createRegistryService(api)),
    [api],
  );

  const [people, setPeople] = useState<MaintenancePersonnel[]>([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState("");
  const [search, setSearch] = useState("");
  const [specialtyFilter, setSpecialtyFilter] = useState("all");
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<MaintenancePersonnel | null>(null);
  const [saving, setSaving] = useState(false);

  const [formCode, setFormCode] = useState("");
  const [formName, setFormName] = useState("");
  const [formSpecialty, setFormSpecialty] = useState<MaintenanceDepartment>("mechanical");
  const [formUnit, setFormUnit] = useState("");
  const [formPhone, setFormPhone] = useState("");
  const [formShift, setFormShift] = useState("");
  const [formSkills, setFormSkills] = useState("");
  const [formCertifications, setFormCertifications] = useState("");
  const [formActive, setFormActive] = useState(true);

  const refresh = useCallback(async (): Promise<void> => {
    try {
      setPeople(await registry.listPersonnel());
    } catch {
      setToast(t("registry.common.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [registry, t]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const filtered = useMemo(
    () =>
      people.filter(
        (person) =>
          (specialtyFilter === "all" || person.specialty === specialtyFilter) &&
          `${person.personnelCode} ${person.fullName} ${person.unit} ${person.skills.join(" ")}`
            .toLowerCase()
            .includes(search.toLowerCase()),
      ),
    [people, search, specialtyFilter],
  );

  const openCreate = (): void => {
    setEditing(null);
    setFormCode("");
    setFormName("");
    setFormSpecialty("mechanical");
    setFormUnit("");
    setFormPhone("");
    setFormShift("");
    setFormSkills("");
    setFormCertifications("");
    setFormActive(true);
    setModalOpen(true);
  };

  const openEdit = (person: MaintenancePersonnel): void => {
    setEditing(person);
    setFormCode(person.personnelCode);
    setFormName(person.fullName);
    setFormSpecialty(person.specialty);
    setFormUnit(person.unit);
    setFormPhone(person.phone);
    setFormShift(person.shift);
    setFormSkills(person.skills.join("\n"));
    setFormCertifications(person.certifications.join("\n"));
    setFormActive(person.active);
    setModalOpen(true);
  };

  const submit = async (): Promise<void> => {
    if (!formName.trim()) {
      setToast(t("registry.common.required"));
      return;
    }
    const lines = (value: string): string[] =>
      value
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean);
    const payload = {
      personnelCode: formCode.trim(),
      fullName: formName.trim(),
      specialty: formSpecialty,
      unit: formUnit.trim(),
      phone: formPhone.trim(),
      shift: formShift.trim(),
      skills: lines(formSkills),
      certifications: lines(formCertifications),
      active: formActive,
    };
    setSaving(true);
    try {
      if (editing) await registry.updatePersonnel(editing.id, payload);
      else await registry.createPersonnel(payload);
      setModalOpen(false);
      setToast(t("registry.personnel.saved"));
      await refresh();
    } catch (error) {
      setToast(error instanceof Error ? error.message : t("registry.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (person: MaintenancePersonnel): Promise<void> => {
    if (!window.confirm(t("registry.personnel.deleteConfirm"))) return;
    try {
      await registry.deletePersonnel(person.id);
      setToast(t("registry.personnel.deleted"));
      await refresh();
    } catch (error) {
      setToast(error instanceof Error ? error.message : t("registry.saveFailed"));
    }
  };

  const columns: DataTableColumn<MaintenancePersonnel>[] = [
    {
      key: "personnelCode",
      label: t("registry.personnel.code"),
      accessor: (row) => row.personnelCode,
      sortable: true,
      render: (row) => <strong>{row.personnelCode || t("registry.common.none")}</strong>,
    },
    {
      key: "fullName",
      label: t("registry.personnel.fullName"),
      accessor: (row) => row.fullName,
      sortable: true,
    },
    {
      key: "specialty",
      label: t("registry.personnel.specialty"),
      accessor: (row) => row.specialty,
      sortable: true,
      render: (row) => <Badge tone="info">{taxonomyLabel(t, "cmms.department.", row.specialty)}</Badge>,
    },
    {
      key: "unit",
      label: t("registry.personnel.unit"),
      accessor: (row) => row.unit,
      render: (row) => <span className="muted-cell">{row.unit || t("registry.common.none")}</span>,
    },
    {
      key: "shift",
      label: t("registry.personnel.shift"),
      accessor: (row) => row.shift,
      render: (row) => <span className="muted-cell">{row.shift || t("registry.common.none")}</span>,
    },
    {
      key: "phone",
      label: t("registry.personnel.phone"),
      accessor: (row) => row.phone,
      render: (row) => <span className="muted-cell">{row.phone || t("registry.common.none")}</span>,
    },
    {
      key: "skills",
      label: t("registry.personnel.skills"),
      accessor: (row) => row.skills.join("، "),
      render: (row) => (
        <span className="muted-cell">{row.skills.join("، ") || t("registry.common.none")}</span>
      ),
    },
    {
      key: "active",
      label: t("registry.personnel.active"),
      accessor: (row) => (row.active ? "1" : "0"),
      render: (row) => (
        <Badge tone={row.active ? "success" : "neutral"} dot>
          {row.active ? t("registry.personnel.active") : t("registry.personnel.inactive")}
        </Badge>
      ),
    },
    {
      key: "actions",
      label: t("registry.column.actions"),
      accessor: () => "",
      render: (row) => (
        <div className="cmms-row-actions">
          <PermissionGuard permission={PERMISSIONS.maintenanceDeviceManage}>
            <Button variant="ghost" size="sm" icon="edit" onClick={() => openEdit(row)}>
              {t("registry.common.edit")}
            </Button>
            <Button variant="ghost" size="sm" icon="close" onClick={() => remove(row)}>
              {t("registry.common.delete")}
            </Button>
          </PermissionGuard>
        </div>
      ),
    },
  ];

  return (
    <div className="page" dir="rtl">
      <SectionHeader
        eyebrow={t("nav.maintenance")}
        title={t("registry.personnel.pageTitle")}
        subtitle={t("registry.personnel.pageSubtitle")}
        actions={
          <div className="cmms-header-actions">
            <Button
              variant="secondary"
              icon="arrowRight"
              onClick={() => navigate("/app/maintenance/registry")}
            >
              {t("registry.profile.back")}
            </Button>
            <PermissionGuard permission={PERMISSIONS.maintenanceDeviceManage}>
              <Button variant="primary" icon="plus" onClick={openCreate}>
                {t("registry.personnel.add")}
              </Button>
            </PermissionGuard>
          </div>
        }
      />

      <div className="metric-grid">
        <MetricCard
          label={t("registry.personnel.pageTitle")}
          value={people.length}
          icon="users"
          tone="blue"
        />
        <MetricCard
          label={t("registry.personnel.active")}
          value={people.filter((person) => person.active).length}
          icon="checkCircle"
          tone="green"
        />
        <MetricCard
          label={t("registry.personnel.allSpecialties")}
          value={new Set(people.map((person) => person.specialty)).size}
          icon="layers"
          tone="purple"
        />
      </div>

      <Card className="content-card" padding="md">
        <div className="cmms-report-filter">
          <TextInput
            aria-label={t("registry.personnel.search")}
            placeholder={t("registry.personnel.search")}
            icon="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <SelectInput
            aria-label={t("registry.personnel.specialty")}
            value={specialtyFilter}
            onChange={(event) => setSpecialtyFilter(event.target.value)}
            options={[
              { value: "all", label: t("registry.personnel.allSpecialties") },
              ...mergeOptions({
                canonical: MAINTENANCE_DEPARTMENTS,
                translate: (department) => taxonomyLabel(t, "cmms.department.", department),
                fromData: people.map((person) => person.specialty),
                catalogKey: "personnel.specialty",
              }),
            ]}
          />
        </div>
        <DataTable
          columns={columns}
          data={filtered}
          rowKey={(row) => row.id}
          loading={loading}
          pageSize={10}
          empty={{ title: t("registry.personnel.empty") }}
          exportName="tekarai-maintenance-personnel"
        />
      </Card>

      <Modal
        open={modalOpen}
        title={editing ? t("registry.personnel.editTitle") : t("registry.personnel.createTitle")}
        onClose={() => setModalOpen(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setModalOpen(false)}>
              {t("registry.common.cancel")}
            </Button>
            <Button variant="primary" icon="check" loading={saving} onClick={submit}>
              {t("registry.common.save")}
            </Button>
          </>
        }
      >
        <div className="form-grid form-grid--compact">
          <TextInput
            label={t("registry.personnel.fullName")}
            required
            value={formName}
            onChange={(event) => setFormName(event.target.value)}
            autoFocus
          />
          <TextInput
            label={t("registry.personnel.code")}
            value={formCode}
            onChange={(event) => setFormCode(event.target.value)}
          />
          <CreatableSelect
            label={t("registry.personnel.specialty")}
            value={formSpecialty}
            onChange={(value) => setFormSpecialty(value as MaintenanceDepartment)}
            catalogKey="personnel.specialty"
            canonical={MAINTENANCE_DEPARTMENTS}
            options={mergeOptions({
              canonical: MAINTENANCE_DEPARTMENTS,
              translate: (department) => taxonomyLabel(t, "cmms.department.", department),
              fromData: people.map((person) => person.specialty),
              catalogKey: "personnel.specialty",
              current: formSpecialty,
            })}
          />
          <TextInput
            label={t("registry.personnel.unit")}
            value={formUnit}
            onChange={(event) => setFormUnit(event.target.value)}
          />
          <TextInput
            label={t("registry.personnel.phone")}
            value={formPhone}
            onChange={(event) => setFormPhone(event.target.value)}
          />
          <TextInput
            label={t("registry.personnel.shift")}
            value={formShift}
            onChange={(event) => setFormShift(event.target.value)}
          />
          <SelectInput
            label={t("registry.personnel.active")}
            value={formActive ? "yes" : "no"}
            onChange={(event) => setFormActive(event.target.value === "yes")}
            options={[
              { value: "yes", label: t("registry.personnel.active") },
              { value: "no", label: t("registry.personnel.inactive") },
            ]}
          />
        </div>
        <TextArea
          label={t("registry.personnel.skills")}
          value={formSkills}
          onChange={(event) => setFormSkills(event.target.value)}
        />
        <TextArea
          label={t("registry.personnel.certifications")}
          value={formCertifications}
          onChange={(event) => setFormCertifications(event.target.value)}
        />
      </Modal>

      {toast && <Toast message={toast} onClose={() => setToast("")} />}
    </div>
  );
}
