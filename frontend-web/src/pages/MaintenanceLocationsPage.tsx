import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApiClient } from "../core/api/apiContext";
import { useLocalization } from "../core/localization/localizationContext";
import { PERMISSIONS } from "../core/permissions/permissionContext";
import { runtimeConfig } from "../app/configuration/runtimeConfig";
import { createRegistryService } from "../features/maintenance/registryService";
import { createDemoRegistryService } from "../features/maintenance/registryDemoData";
import {
  LOCATION_KINDS,
  type LocationKind,
  type MaintenanceLocation,
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
import { taxonomyLabel } from "../core/localization/taxonomyLabel";
import { CreatableSelect } from "../shared/components/CreatableSelect";
import { mergeOptions } from "../features/maintenance/optionCatalog";


const kindIcon = (kind: LocationKind): "building" | "home" | "grid" | "layers" =>
  kind === "site" ? "building" : kind === "building" ? "home" : kind === "area" ? "grid" : "layers";

/** Site → building → area → room tree used to place every device. */
export function MaintenanceLocationsPage(): JSX.Element {
  const { t } = useLocalization();
  const navigate = useNavigate();
  const api = useApiClient();
  const registry = useMemo(
    () => (runtimeConfig.demoMode ? createDemoRegistryService() : createRegistryService(api)),
    [api],
  );

  const [locations, setLocations] = useState<MaintenanceLocation[]>([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState("");
  const [search, setSearch] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<MaintenanceLocation | null>(null);
  const [saving, setSaving] = useState(false);

  const [formCode, setFormCode] = useState("");
  const [formName, setFormName] = useState("");
  const [formKind, setFormKind] = useState<LocationKind>("site");
  const [formParentId, setFormParentId] = useState("");
  const [formNote, setFormNote] = useState("");

  const refresh = useCallback(async (): Promise<void> => {
    try {
      setLocations(await registry.listLocations());
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
      locations.filter((location) =>
        `${location.code} ${location.name} ${location.path}`
          .toLowerCase()
          .includes(search.toLowerCase()),
      ),
    [locations, search],
  );

  const roots = filtered.filter((location) => !location.parentId);
  const childrenOf = (parentId: string): MaintenanceLocation[] =>
    filtered.filter((location) => location.parentId === parentId);

  const openCreate = (parentId = ""): void => {
    setEditing(null);
    setFormCode("");
    setFormName("");
    setFormKind(parentId ? "room" : "site");
    setFormParentId(parentId);
    setFormNote("");
    setModalOpen(true);
  };

  const openEdit = (location: MaintenanceLocation): void => {
    setEditing(location);
    setFormCode(location.code);
    setFormName(location.name);
    setFormKind(location.kind);
    setFormParentId(location.parentId);
    setFormNote(location.note);
    setModalOpen(true);
  };

  const submit = async (): Promise<void> => {
    if (!formName.trim()) {
      setToast(t("registry.common.required"));
      return;
    }
    const payload = {
      code: formCode.trim(),
      name: formName.trim(),
      kind: formKind,
      parentId: formParentId,
      note: formNote.trim(),
    };
    setSaving(true);
    try {
      if (editing) await registry.updateLocation(editing.id, payload);
      else await registry.createLocation(payload);
      setModalOpen(false);
      setToast(t("registry.location.saved"));
      await refresh();
    } catch (error) {
      setToast(error instanceof Error ? error.message : t("registry.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (location: MaintenanceLocation): Promise<void> => {
    if (!window.confirm(t("registry.location.deleteConfirm"))) return;
    try {
      await registry.deleteLocation(location.id);
      setToast(t("registry.location.deleted"));
      await refresh();
    } catch (error) {
      setToast(error instanceof Error ? error.message : t("registry.saveFailed"));
    }
  };

  const renderNode = (location: MaintenanceLocation, depth: number): JSX.Element => (
    <div key={location.id} className="registry-tree__node" style={{ marginInlineStart: depth * 20 }}>
      <div className="registry-tree__row">
        <Icon name={kindIcon(location.kind)} size={16} />
        <strong>{location.name}</strong>
        <Badge tone="neutral">{taxonomyLabel(t, "registry.location.", location.kind)}</Badge>
        {location.code && <span className="muted-cell">{location.code}</span>}
        <span className="muted-cell">
          {t("registry.location.deviceCount")}: {location.deviceCount}
        </span>
        <PermissionGuard permission={PERMISSIONS.maintenanceDeviceManage}>
          <Button variant="ghost" size="sm" icon="plus" onClick={() => openCreate(location.id)}>
            {t("registry.location.add")}
          </Button>
          <Button variant="ghost" size="sm" icon="edit" onClick={() => openEdit(location)}>
            {t("registry.common.edit")}
          </Button>
          <Button variant="ghost" size="sm" icon="close" onClick={() => remove(location)}>
            {t("registry.common.delete")}
          </Button>
        </PermissionGuard>
      </div>
      {location.note && <p className="muted-cell">{location.note}</p>}
      {childrenOf(location.id).map((child) => renderNode(child, depth + 1))}
    </div>
  );

  return (
    <div className="page" dir="rtl">
      <SectionHeader
        eyebrow={t("nav.maintenance")}
        title={t("registry.location.pageTitle")}
        subtitle={t("registry.location.pageSubtitle")}
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
              <Button variant="primary" icon="plus" onClick={() => openCreate("")}>
                {t("registry.location.add")}
              </Button>
            </PermissionGuard>
          </div>
        }
      />

      <div className="metric-grid">
        <MetricCard
          label={t("registry.location.site")}
          value={locations.filter((item) => item.kind === "site").length}
          icon="building"
          tone="blue"
        />
        <MetricCard
          label={t("registry.location.building")}
          value={locations.filter((item) => item.kind === "building").length}
          icon="home"
          tone="green"
        />
        <MetricCard
          label={t("registry.location.room")}
          value={locations.filter((item) => item.kind === "room").length}
          icon="layers"
          tone="purple"
        />
      </div>

      <Card className="content-card" padding="md">
        <TextInput
          aria-label={t("registry.search")}
          placeholder={t("registry.search")}
          icon="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        {loading ? (
          <LoadingState label={t("common.loading")} />
        ) : filtered.length === 0 ? (
          <EmptyState icon="building" title={t("registry.location.empty")} />
        ) : (
          <div className="registry-tree">
            {roots.map((location) => renderNode(location, 0))}
            {filtered
              .filter(
                (location) =>
                  location.parentId && !filtered.some((item) => item.id === location.parentId),
              )
              .map((location) => renderNode(location, 0))}
          </div>
        )}
      </Card>

      <Modal
        open={modalOpen}
        title={editing ? t("registry.location.editTitle") : t("registry.location.createTitle")}
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
            label={t("registry.location.name")}
            required
            value={formName}
            onChange={(event) => setFormName(event.target.value)}
            autoFocus
          />
          <TextInput
            label={t("registry.location.code")}
            value={formCode}
            onChange={(event) => setFormCode(event.target.value)}
          />
          <CreatableSelect
            label={t("registry.location.kind")}
            value={formKind}
            onChange={(value) => setFormKind(value as LocationKind)}
            catalogKey="location.kind"
            canonical={LOCATION_KINDS}
            options={mergeOptions({
              canonical: LOCATION_KINDS,
              translate: (kind) => taxonomyLabel(t, "registry.location.", kind),
              fromData: locations.map((location) => location.kind),
              catalogKey: "location.kind",
              current: formKind,
            })}
          />
          <SelectInput
            label={t("registry.location.parent")}
            value={formParentId}
            onChange={(event) => setFormParentId(event.target.value)}
            options={[
              { value: "", label: t("registry.location.noParent") },
              ...locations
                .filter((location) => location.id !== editing?.id)
                .map((location) => ({ value: location.id, label: location.path })),
            ]}
          />
        </div>
        <TextArea
          label={t("registry.location.note")}
          value={formNote}
          onChange={(event) => setFormNote(event.target.value)}
        />
      </Modal>

      {toast && <Toast message={toast} onClose={() => setToast("")} />}
    </div>
  );
}
