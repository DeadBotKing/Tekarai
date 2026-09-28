// چک‌لیست بازرسی — قالب‌ها + اجرای بازرسی؛ در صورت fail دستور کار خودکار.
import { useCallback, useEffect, useMemo, useState } from "react";
import { useApiClient } from "../core/api/apiContext";
import { runtimeConfig } from "../app/configuration/runtimeConfig";
import { createMaintenanceService } from "../features/maintenance/maintenanceService";
import { demoDevices } from "../features/maintenance/maintenanceDemoData";
import {
  buildInspectionRecord,
  buildInspectionWorkOrderDraft,
  failedTemplateItems,
  type InspectionRecord,
  type InspectionRunItem,
  type InspectionTemplate,
} from "../features/maintenance/wave1";
import {
  deleteInspectionTemplate,
  listInspectionTemplates,
  newTemplateId,
  saveInspectionTemplate,
  syncInspectionTemplatesFromServer,
} from "../features/maintenance/inspectionsStore";
import {
  listInspectionRecords,
  newRecordId,
  saveInspectionRecord,
  syncInspectionRecordsFromServer,
} from "../features/maintenance/inspectionRecordsStore";
import { sessionStore } from "../core/auth/sessionStore";
import type { MaintenanceDevice } from "../shared/types/domain";
import { DataTable, type DataTableColumn } from "../shared/components/DataTable";
import { Modal, Toast } from "../shared/components/overlays";
import {
  Badge,
  Button,
  Card,
  SectionHeader,
  SelectInput,
  TextArea,
  TextInput,
} from "../shared/components/primitives";
import { faText } from "../core/localization/i18n";

const t = faText;

export default function MaintenanceInspectionsPage(): JSX.Element {
  const api = useApiClient();
  const service = useMemo(() => createMaintenanceService(api), [api]);
  const [devices, setDevices] = useState<MaintenanceDevice[]>(runtimeConfig.demoMode ? demoDevices : []);
  const [templates, setTemplates] = useState<InspectionTemplate[]>(() => listInspectionTemplates());
  const [builderOpen, setBuilderOpen] = useState(false);
  const [runTemplate, setRunTemplate] = useState<InspectionTemplate | null>(null);
  const [formTitle, setFormTitle] = useState("");
  const [formDeviceCode, setFormDeviceCode] = useState("");
  const [formItems, setFormItems] = useState("");
  const [runDeviceId, setRunDeviceId] = useState("");
  const [runItems, setRunItems] = useState<InspectionRunItem[]>([]);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState("");
  const [records, setRecords] = useState<InspectionRecord[]>(() => listInspectionRecords());
  const [detailRecord, setDetailRecord] = useState<InspectionRecord | null>(null);

  useEffect(() => {
    if (runtimeConfig.demoMode) return;
    service.listDevices({}).then(setDevices).catch(() => setDevices([]));
  }, [service]);

  const refreshTemplates = useCallback((): void => setTemplates(listInspectionTemplates()), []);

  // هم‌گام‌سازی تیمی: قالب‌ها از سرور تازه شوند (در دمو/آفلاین مثل قبل محلی می‌ماند)
  useEffect(() => {
    void syncInspectionTemplatesFromServer().then((ok) => {
      if (ok) refreshTemplates();
    });
  }, [refreshTemplates]);

  useEffect(() => {
    void syncInspectionRecordsFromServer().then((ok) => {
      if (ok) setRecords(listInspectionRecords());
    });
  }, []);

  const openRun = (template: InspectionTemplate): void => {
    setRunTemplate(template);
    const preset = devices.find((device) => device.code === template.deviceCode);
    setRunDeviceId(preset?.id ?? devices[0]?.id ?? "");
    setRunItems(template.items.map((item) => ({ itemId: item.id, ok: true })));
  };

  const saveTemplate = (): void => {
    const items = formItems
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((text, index) => ({ id: `item-${index + 1}`, text }));
    if (!formTitle.trim() || !items.length) return;
    saveInspectionTemplate({ id: newTemplateId(), title: formTitle.trim(), deviceCode: formDeviceCode, items });
    refreshTemplates();
    setBuilderOpen(false);
    setFormTitle("");
    setFormDeviceCode("");
    setFormItems("");
    setToast(t("cmms.wave1.templateSaved"));
  };

  const completeRun = async (): Promise<void> => {
    if (!runTemplate) return;
    const failed = failedTemplateItems(runTemplate, runItems);
    const device = devices.find((item) => item.id === runDeviceId);
    // رکورد بازرسی همیشه ثبت می‌شود — مدرک مسئولیت همین‌جاست
    if (device) {
      saveInspectionRecord(
        buildInspectionRecord(
          newRecordId(),
          runTemplate,
          runItems,
          device.id,
          device.code,
          sessionStore.get()?.user.displayName ?? sessionStore.get()?.user.email ?? "",
        ),
      );
      setRecords(listInspectionRecords());
    }
    setSaving(true);
    try {
      if (failed.length && device) {
        const draft = buildInspectionWorkOrderDraft(device, runTemplate, failed);
        await service.submitWorkOrder({ ...draft, description: draft.description });
        setToast(t("cmms.wave1.woCreated"));
      } else {
        setToast(t("cmms.wave1.allOk"));
      }
      setRunTemplate(null);
    } catch {
      setToast(t("cmms.wave1.woFailed"));
    } finally {
      setSaving(false);
    }
  };

  const columns: DataTableColumn<InspectionTemplate>[] = useMemo(
    () => [
      { key: "title", label: t("cmms.wave1.colTitle"), accessor: (row) => row.title },
      {
        key: "device",
        label: t("cmms.wave1.colScope"),
        accessor: (row) => (row.deviceCode ? row.deviceCode : t("cmms.wave1.scopeAll")),
      },
      { key: "count", label: t("cmms.wave1.colItems"), accessor: (row) => row.items.length },
      {
        key: "actions",
        label: t("project.actions"),
        render: (row) => (
          <>
            <Button variant="primary" size="sm" icon="check" onClick={() => openRun(row)}>
              {t("cmms.wave1.run")}
            </Button>{" "}
            <Button
              variant="ghost"
              size="sm"
              icon="close"
              onClick={() => {
                deleteInspectionTemplate(row.id);
                refreshTemplates();
              }}
            >
              {t("common.delete")}
            </Button>
          </>
        ),
      },
    ],
    [devices],
  );

  /** رکوردهای کشیده از سرور عنوان/کد ندارند؛ در رندر از روی منابع محلی تکمیل می‌شود. */
  const historyColumns: DataTableColumn<InspectionRecord>[] = useMemo(() => {
    const titleOf = (record: InspectionRecord): string =>
      record.templateTitle ||
      templates.find((item) => item.id === record.templateId)?.title ||
      record.templateId;
    const codeOf = (record: InspectionRecord): string =>
      record.deviceCode || devices.find((item) => item.id === record.deviceId)?.code || "";
    return [
      {
        key: "at",
        label: t("cmms.wave1.colDate"),
        accessor: (row) => row.at,
        render: (row) => {
          const date = new Date(row.at);
          return Number.isNaN(date.getTime())
            ? row.at
            : `${date.toLocaleDateString("fa-IR")} ${date.toLocaleTimeString("fa-IR", { hour: "2-digit", minute: "2-digit" })}`;
        },
      },
      { key: "template", label: t("cmms.wave1.colTitle"), accessor: titleOf },
      { key: "device", label: t("cmms.wave1.colScope"), accessor: (row) => codeOf(row) || "—" },
      { key: "by", label: t("cmms.wave1.colInspector"), accessor: (row) => row.performedByName || "—" },
      {
        key: "result",
        label: t("project.status"),
        render: (row) =>
          row.failedChecks.length ? (
            <Badge tone="danger" dot>{t("cmms.wave1.resultNok").replace("{n}", String(row.failedChecks.length))}</Badge>
          ) : (
            <Badge tone="success" dot>{t("cmms.wave1.resultOk").replace("{n}", String(row.passedChecks.length))}</Badge>
          ),
      },
      {
        key: "detail",
        label: t("project.actions"),
        render: (row) => (
          <Button variant="ghost" size="sm" icon="search" onClick={() => setDetailRecord(row)}>
            {t("cmms.wave1.recordDetail")}
          </Button>
        ),
      },
    ];
  }, [devices, templates]);

  const failedCount = runTemplate ? failedTemplateItems(runTemplate, runItems).length : 0;

  return (
    <div className="page" dir="rtl">
      <SectionHeader
        eyebrow={t("cmms.wave1.eyebrow")}
        title={t("cmms.wave1.title")}
        subtitle={t("cmms.wave1.subtitle")}
        actions={
          <Button variant="primary" icon="plus" onClick={() => setBuilderOpen(true)}>
            {t("cmms.wave1.newTemplate")}
          </Button>
        }
      />
      <Card padding="none">
        <DataTable
          columns={columns}
          data={templates}
          rowKey={(row) => row.id}
          exportName="tekarai-inspections"
          empty={{ title: t("cmms.wave1.empty") }}
        />
      </Card>

      <Card padding="none">
        <div className="card__header" style={{ padding: "14px 16px" }}>
          <strong>{t("cmms.wave1.recordHistory")}</strong>
        </div>
        <DataTable
          columns={historyColumns}
          data={[...records].sort((a, b) => b.at.localeCompare(a.at))}
          rowKey={(row) => row.id}
          exportName="tekarai-inspection-history"
          empty={{ title: t("cmms.wave1.recordEmpty") }}
        />
      </Card>

      <Modal
        open={builderOpen}
        title={t("cmms.wave1.newTemplate")}
        onClose={() => setBuilderOpen(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setBuilderOpen(false)}>
              {t("cmms.common.cancel")}
            </Button>
            <Button variant="primary" disabled={!formTitle.trim() || !formItems.trim()} onClick={saveTemplate}>
              {t("common.save")}
            </Button>
          </>
        }
      >
        <div className="form-grid">
          <TextInput label={t("cmms.wave1.formTitle")} required value={formTitle} onChange={(event) => setFormTitle(event.target.value)} />
          <SelectInput
            label={t("cmms.wave1.formDevice")}
            value={formDeviceCode}
            onChange={(event) => setFormDeviceCode(event.target.value)}
            options={[
              { value: "", label: t("cmms.wave1.scopeAll") },
              ...devices.map((device) => ({ value: device.code, label: `${device.code} — ${device.name}` })),
            ]}
          />
          <TextArea
            label={t("cmms.wave1.formItems")}
            hint={t("cmms.wave1.formItemsHint")}
            value={formItems}
            onChange={(event) => setFormItems(event.target.value)}
            rows={6}
          />
        </div>
      </Modal>

      <Modal
        open={Boolean(runTemplate)}
        title={runTemplate ? `${t("cmms.wave1.run")} — ${runTemplate.title}` : ""}
        onClose={() => setRunTemplate(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setRunTemplate(null)}>
              {t("cmms.common.cancel")}
            </Button>
            <Button variant="primary" icon="check" loading={saving} onClick={() => void completeRun()}>
              {failedCount ? t("cmms.wave1.runCreateWo") : t("cmms.wave1.runFinish")}
            </Button>
          </>
        }
      >
        {runTemplate && !runTemplate.deviceCode && (
          <SelectInput
            label={t("cmms.wave1.runDevice")}
            required
            value={runDeviceId}
            onChange={(event) => setRunDeviceId(event.target.value)}
            options={devices.map((device) => ({ value: device.id, label: `${device.code} — ${device.name}` }))}
          />
        )}
        {runTemplate?.deviceCode && (
          <p className="muted-cell">
            {t("cmms.wave1.runBoundDevice")}: <strong>{runTemplate.deviceCode}</strong>
          </p>
        )}
        <div className="inspection-items">
          {runTemplate?.items.map((item) => {
            const state = runItems.find((run) => run.itemId === item.id);
            return (
              <div className="inspection-item" key={item.id}>
                <span>{item.text}</span>
                <div className="section-actions">
                  <Badge tone={state?.ok ? "success" : "neutral"} dot>
                    <button
                      type="button"
                      onClick={() =>
                        setRunItems((current) => current.map((run) => (run.itemId === item.id ? { ...run, ok: true } : run)))
                      }
                    >
                      {t("cmms.wave1.itemOk")}
                    </button>
                  </Badge>
                  <Badge tone={!state?.ok ? "danger" : "neutral"} dot>
                    <button
                      type="button"
                      onClick={() =>
                        setRunItems((current) => current.map((run) => (run.itemId === item.id ? { ...run, ok: false } : run)))
                      }
                    >
                      {t("cmms.wave1.itemFail")}
                    </button>
                  </Badge>
                </div>
              </div>
            );
          })}
        </div>
        {failedCount > 0 && (
          <p className="muted-cell">⚠ {t("cmms.wave1.failNotice").replace("{count}", String(failedCount))}</p>
        )}
      </Modal>
      <Modal
        open={Boolean(detailRecord)}
        title={detailRecord ? `${t("cmms.wave1.recordDetail")} — ${detailRecord.templateTitle || detailRecord.templateId}` : ""}
        onClose={() => setDetailRecord(null)}
      >
        {detailRecord && (
          <div className="form-grid">
            {detailRecord.passedChecks.map((text) => (
              <div className="inspection-item" key={`ok-${text}`}><Badge tone="success" dot>{text}</Badge></div>
            ))}
            {detailRecord.failedChecks.map((text) => (
              <div className="inspection-item" key={`nok-${text}`}><Badge tone="danger" dot>{text}</Badge></div>
            ))}
          </div>
        )}
      </Modal>
      {toast && <Toast message={toast} onClose={() => setToast("")} />}
    </div>
  );
}
