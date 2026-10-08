import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiClientError } from "../core/api/apiClient";
import { useApiClient } from "../core/api/apiContext";
import { PERMISSIONS } from "../core/permissions/permissionContext";
import { DataTable, type DataTableColumn } from "../shared/components/DataTable";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  PermissionGuard,
  SelectInput,
  TextInput,
} from "../shared/components/primitives";

/**
 * ساختار سازمانی و دسترسی‌ها — units, positions and the permission matrix.
 *
 * Three tabs, in the order the work actually happens: define the units,
 * define the titles, then say what each title may do inside each unit.
 *
 * The decisions worth knowing about this screen:
 *
 * * **The matrix is rendered from the catalogue the server sends**, never
 *   from a hardcoded list of columns. A verb a capability does not support
 *   is not drawable, because a tick that grants nothing is worse than no
 *   tick at all.
 * * **Scope is part of the cell, not a separate screen.** Each granted
 *   cell shows a dropdown — خودش / تیم / واحد / کل کارخانه — so «دسترسی
 *   دارد» can never be recorded without answering «تا کجا».
 * * **Unit-specific overrides are visibly different from inherited
 *   defaults.** An administrator looking at QC must be able to tell which
 *   cells were decided for QC and which came from the organisation-wide
 *   row, or they will edit the wrong one.
 * * **Seeded units and positions cannot be deleted, only deactivated**,
 *   and the delete button says so rather than failing on click.
 * * **Every refusal from the server is shown verbatim.** The rules live in
 *   the domain; this screen's job is to explain them, not restate them.
 */

interface DepartmentRow {
  id: string;
  code: string;
  name: string;
  description: string;
  status: string;
  statusLabel: string;
  parentId: string | null;
  managerName: string;
  isSystem: boolean;
  memberCount: number | null;
}

interface PositionRow {
  id: string;
  code: string;
  name: string;
  description: string;
  level: number;
  isActive: boolean;
  isSystem: boolean;
  memberCount: number | null;
}

interface AssignmentRow {
  id: string;
  userId: string;
  userDisplayName: string;
  departmentId: string;
  departmentName: string;
  positionId: string;
  positionName: string;
  isPrimary: boolean;
  isActive: boolean;
}

interface CapabilityAction {
  value: string;
  label: string;
}

interface CapabilityRow {
  key: string;
  label: string;
  group: string;
  scoped: boolean;
  actions: CapabilityAction[];
}

interface ScopeOption {
  value: string;
  label: string;
}

type MatrixShape = Record<string, Record<string, Record<string, string>>>;

interface MatrixPayload {
  departmentId: string | null;
  matrix: MatrixShape;
  positions: PositionRow[];
  capabilities: CapabilityRow[];
  scopes: ScopeOption[];
}

const emptyDepartmentForm = { name: "", code: "", description: "", parentId: "" };
const emptyPositionForm = { name: "", code: "", level: "40", description: "" };
const emptyAssignmentForm = {
  userId: "",
  userDisplayName: "",
  departmentId: "",
  positionId: "",
};

type TabKey = "departments" | "positions" | "matrix";

const TABS: { key: TabKey; label: string }[] = [
  { key: "departments", label: "واحدها" },
  { key: "positions", label: "سمت‌ها" },
  { key: "matrix", label: "ماتریس دسترسی" },
];

export function OrganizationStructurePage(): JSX.Element {
  const api = useApiClient();
  const [tab, setTab] = useState<TabKey>("departments");
  const [departments, setDepartments] = useState<DepartmentRow[]>([]);
  const [positions, setPositions] = useState<PositionRow[]>([]);
  const [assignments, setAssignments] = useState<AssignmentRow[]>([]);
  const [matrix, setMatrix] = useState<MatrixPayload | null>(null);
  const [matrixUnitId, setMatrixUnitId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [showDepartmentForm, setShowDepartmentForm] = useState(false);
  const [showPositionForm, setShowPositionForm] = useState(false);
  const [showAssignmentForm, setShowAssignmentForm] = useState(false);
  const [departmentForm, setDepartmentForm] = useState(emptyDepartmentForm);
  const [positionForm, setPositionForm] = useState(emptyPositionForm);
  const [assignmentForm, setAssignmentForm] = useState(emptyAssignmentForm);

  const failureMessage = (cause: unknown, fallback: string): string =>
    cause instanceof ApiClientError && cause.message ? cause.message : fallback;

  const load = useCallback(() => {
    setLoading(true);
    void Promise.all([
      api.get<{ items: DepartmentRow[] }>("organization/departments"),
      api.get<{ items: PositionRow[] }>("organization/positions"),
      api.get<{ items: AssignmentRow[] }>("organization/assignments"),
    ])
      .then(([departmentPayload, positionPayload, assignmentPayload]) => {
        setDepartments(departmentPayload.items);
        setPositions(positionPayload.items);
        setAssignments(assignmentPayload.items);
        setError(null);
      })
      .catch((cause: unknown) =>
        setError(failureMessage(cause, "دریافت ساختار سازمانی ناموفق بود.")),
      )
      .finally(() => setLoading(false));
  }, [api]);

  useEffect(load, [load]);

  const loadMatrix = useCallback(() => {
    const query = matrixUnitId ? `?departmentId=${encodeURIComponent(matrixUnitId)}` : "";
    void api
      .get<MatrixPayload>(`organization/access-matrix${query}`)
      .then((data) => {
        setMatrix(data);
        setError(null);
      })
      .catch((cause: unknown) =>
        setError(failureMessage(cause, "دریافت ماتریس دسترسی ناموفق بود.")),
      );
  }, [api, matrixUnitId]);

  useEffect(() => {
    if (tab === "matrix") {
      loadMatrix();
    }
  }, [tab, loadMatrix]);

  const memberCountOf = useCallback(
    (departmentId: string): number =>
      assignments.filter((row) => row.departmentId === departmentId && row.isActive).length,
    [assignments],
  );

  const submitDepartment = (): void => {
    setBusy(true);
    setNotice("");
    void api
      .post("organization/departments", {
        name: departmentForm.name,
        code: departmentForm.code,
        description: departmentForm.description,
        parentId: departmentForm.parentId || null,
      })
      .then(() => {
        setDepartmentForm(emptyDepartmentForm);
        setShowDepartmentForm(false);
        setNotice("واحد جدید ثبت شد.");
        load();
      })
      .catch((cause: unknown) => setError(failureMessage(cause, "ثبت واحد ناموفق بود.")))
      .finally(() => setBusy(false));
  };

  const submitPosition = (): void => {
    setBusy(true);
    setNotice("");
    void api
      .post("organization/positions", {
        name: positionForm.name,
        code: positionForm.code,
        level: Number(positionForm.level) || 0,
        description: positionForm.description,
      })
      .then(() => {
        setPositionForm(emptyPositionForm);
        setShowPositionForm(false);
        setNotice("سمت جدید ثبت شد. تا زمانی که در ماتریس دسترسی تعیین نشود، هیچ اختیاری ندارد.");
        load();
      })
      .catch((cause: unknown) => setError(failureMessage(cause, "ثبت سمت ناموفق بود.")))
      .finally(() => setBusy(false));
  };

  const submitAssignment = (): void => {
    setBusy(true);
    setNotice("");
    void api
      .post("organization/assignments", {
        userId: assignmentForm.userId,
        userDisplayName: assignmentForm.userDisplayName,
        departmentId: assignmentForm.departmentId,
        positionId: assignmentForm.positionId,
      })
      .then(() => {
        setAssignmentForm(emptyAssignmentForm);
        setShowAssignmentForm(false);
        setNotice("کاربر به واحد و سمت منتسب شد.");
        load();
      })
      .catch((cause: unknown) => setError(failureMessage(cause, "ثبت انتساب ناموفق بود.")))
      .finally(() => setBusy(false));
  };

  const toggleStatus = (row: DepartmentRow): void => {
    setBusy(true);
    void api
      .patch(`organization/departments/${row.id}`, {
        status: row.status === "active" ? "inactive" : "active",
      })
      .then(() => {
        setNotice(
          row.status === "active"
            ? `واحد «${row.name}» غیرفعال شد؛ دسترسی اعضای آن بلافاصله قطع می‌شود.`
            : `واحد «${row.name}» فعال شد.`,
        );
        load();
      })
      .catch((cause: unknown) => setError(failureMessage(cause, "تغییر وضعیت ناموفق بود.")))
      .finally(() => setBusy(false));
  };

  const removeDepartment = (row: DepartmentRow): void => {
    setBusy(true);
    void api
      .delete(`organization/departments/${row.id}`)
      .then(() => {
        setNotice(`واحد «${row.name}» حذف شد.`);
        load();
      })
      .catch((cause: unknown) => setError(failureMessage(cause, "حذف واحد ناموفق بود.")))
      .finally(() => setBusy(false));
  };

  const writeCell = (
    positionId: string,
    capability: string,
    action: string,
    scope: string,
    granted: boolean,
  ): void => {
    setBusy(true);
    setNotice("");
    void api
      .post<{ matrix: MatrixShape }>("organization/access-matrix", {
        positionId,
        capability,
        action,
        scope,
        granted,
        departmentId: matrixUnitId || null,
      })
      .then((data) => {
        setMatrix((current) => (current ? { ...current, matrix: data.matrix } : current));
        setNotice(granted ? "دسترسی ثبت شد و بلافاصله اعمال می‌شود." : "دسترسی برداشته شد.");
        setError(null);
      })
      .catch((cause: unknown) => setError(failureMessage(cause, "تغییر دسترسی ناموفق بود.")))
      .finally(() => setBusy(false));
  };

  const departmentColumns: DataTableColumn<DepartmentRow>[] = useMemo(
    () => [
      { key: "code", label: "کد", accessor: (row) => row.code },
      { key: "name", label: "واحد", accessor: (row) => row.name },
      {
        key: "parent",
        label: "واحد بالادست",
        render: (row) => (
          <span>{departments.find((item) => item.id === row.parentId)?.name ?? "—"}</span>
        ),
      },
      {
        key: "members",
        label: "تعداد اعضا",
        render: (row) => <span>{row.memberCount ?? memberCountOf(row.id)}</span>,
      },
      {
        key: "status",
        label: "وضعیت",
        render: (row) => (
          <Badge tone={row.status === "active" ? "success" : "neutral"}>{row.statusLabel}</Badge>
        ),
      },
      {
        key: "actions",
        label: "عملیات",
        render: (row) => (
          <PermissionGuard permission={PERMISSIONS.organizationDepartmentManage} fallback="hide">
            <div className="row-actions">
              <Button variant="ghost" disabled={busy} onClick={() => toggleStatus(row)}>
                {row.status === "active" ? "غیرفعال‌سازی" : "فعال‌سازی"}
              </Button>
              <Button
                variant="ghost"
                disabled={busy || row.isSystem}
                title={row.isSystem ? "واحد پیش‌فرض حذف نمی‌شود؛ آن را غیرفعال کنید." : undefined}
                onClick={() => removeDepartment(row)}
              >
                حذف
              </Button>
            </div>
          </PermissionGuard>
        ),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [departments, busy, memberCountOf],
  );

  const positionColumns: DataTableColumn<PositionRow>[] = useMemo(
    () => [
      { key: "code", label: "کد", accessor: (row) => row.code },
      { key: "name", label: "سمت", accessor: (row) => row.name },
      { key: "level", label: "سطح", accessor: (row) => row.level },
      {
        key: "members",
        label: "تعداد افراد",
        render: (row) => <span>{row.memberCount ?? 0}</span>,
      },
      {
        key: "state",
        label: "وضعیت",
        render: (row) => (
          <Badge tone={row.isActive ? "success" : "neutral"}>
            {row.isActive ? "فعال" : "غیرفعال"}
          </Badge>
        ),
      },
    ],
    [],
  );

  const assignmentColumns: DataTableColumn<AssignmentRow>[] = useMemo(
    () => [
      {
        key: "user",
        label: "کاربر",
        accessor: (row) => row.userDisplayName || row.userId,
      },
      { key: "department", label: "واحد", accessor: (row) => row.departmentName },
      { key: "position", label: "سمت", accessor: (row) => row.positionName },
      {
        key: "primary",
        label: "انتساب اصلی",
        render: (row) => (row.isPrimary ? <Badge tone="info">اصلی</Badge> : <span>—</span>),
      },
    ],
    [],
  );

  if (error !== null && departments.length === 0 && !loading) {
    return (
      <ErrorState
        title="ساختار سازمانی در دسترس نیست"
        description={error}
        retry={load}
      />
    );
  }

  const activeDepartments = departments.filter((row) => row.status === "active");

  return (
    <div className="page organization-page">
      <Card>
        <CardHeader
          title="ساختار سازمانی و دسترسی‌ها"
          subtitle="دسترسی از ترکیب «کاربر + واحد + سمت» ساخته می‌شود، نه از سمت به‌تنهایی."
          icon="users"
        />
        <div className="tab-bar" role="tablist">
          {TABS.map((item) => (
            <button
              key={item.key}
              type="button"
              role="tab"
              aria-selected={tab === item.key}
              className={tab === item.key ? "tab tab-active" : "tab"}
              onClick={() => setTab(item.key)}
            >
              {item.label}
            </button>
          ))}
        </div>
        {notice !== "" ? <p className="notice">{notice}</p> : null}
        {error !== null ? <p className="form-error">{error}</p> : null}
      </Card>

      {tab === "departments" ? (
        <Card>
          <CardHeader
            title="واحدها"
            subtitle="هر واحد کد و وضعیت خودش را دارد. غیرفعال‌کردن یک واحد، دسترسی اعضای آن را فوراً قطع می‌کند."
            action={
              <PermissionGuard
                permission={PERMISSIONS.organizationDepartmentManage}
                fallback="hide"
              >
                <Button onClick={() => setShowDepartmentForm((open) => !open)}>
                  {showDepartmentForm ? "بستن" : "＋ افزودن واحد"}
                </Button>
              </PermissionGuard>
            }
          />
          {showDepartmentForm ? (
            <div className="inline-form">
              <TextInput
                label="نام واحد"
                value={departmentForm.name}
                onChange={(event) =>
                  setDepartmentForm({ ...departmentForm, name: event.target.value })
                }
              />
              <TextInput
                label="کد (اختیاری)"
                hint="در صورت خالی‌بودن از روی نام ساخته می‌شود."
                value={departmentForm.code}
                onChange={(event) =>
                  setDepartmentForm({ ...departmentForm, code: event.target.value })
                }
              />
              <SelectInput
                label="واحد بالادست"
                value={departmentForm.parentId}
                options={[
                  { value: "", label: "— بدون واحد بالادست —" },
                  ...activeDepartments.map((row) => ({ value: row.id, label: row.name })),
                ]}
                onChange={(event) =>
                  setDepartmentForm({ ...departmentForm, parentId: event.target.value })
                }
              />
              <Button disabled={busy || departmentForm.name.trim() === ""} onClick={submitDepartment}>
                ثبت واحد
              </Button>
            </div>
          ) : null}
          <DataTable
            columns={departmentColumns}
            data={departments}
            rowKey={(row: DepartmentRow) => row.id}
            loading={loading}
            empty={{
              title: "هنوز واحدی تعریف نشده است",
              description: "با «افزودن واحد» شروع کنید یا ساختار پیش‌فرض را از تنظیمات ایجاد کنید.",
            }}
          />
        </Card>
      ) : null}

      {tab === "positions" ? (
        <>
          <Card>
            <CardHeader
              title="سمت‌ها"
              subtitle="سمت به‌تنهایی دسترسی نمی‌دهد؛ اختیارات آن در ماتریس و برای هر واحد تعیین می‌شود."
              action={
                <PermissionGuard
                  permission={PERMISSIONS.organizationPositionManage}
                  fallback="hide"
                >
                  <Button onClick={() => setShowPositionForm((open) => !open)}>
                    {showPositionForm ? "بستن" : "＋ افزودن سمت"}
                  </Button>
                </PermissionGuard>
              }
            />
            {showPositionForm ? (
              <div className="inline-form">
                <TextInput
                  label="نام سمت"
                  value={positionForm.name}
                  onChange={(event) =>
                    setPositionForm({ ...positionForm, name: event.target.value })
                  }
                />
                <TextInput
                  label="کد (اختیاری)"
                  value={positionForm.code}
                  onChange={(event) =>
                    setPositionForm({ ...positionForm, code: event.target.value })
                  }
                />
                <TextInput
                  label="سطح"
                  type="number"
                  hint="فقط برای ترتیب نمایش؛ سطح بالاتر به‌خودی‌خود دسترسی بیشتری نمی‌دهد."
                  value={positionForm.level}
                  onChange={(event) =>
                    setPositionForm({ ...positionForm, level: event.target.value })
                  }
                />
                <Button disabled={busy || positionForm.name.trim() === ""} onClick={submitPosition}>
                  ثبت سمت
                </Button>
              </div>
            ) : null}
            <DataTable
              columns={positionColumns}
              data={positions}
              rowKey={(row: PositionRow) => row.id}
              loading={loading}
              empty={{ title: "سمتی تعریف نشده است" }}
            />
          </Card>

          <Card>
            <CardHeader
              title="انتساب کاربران"
              subtitle="«علی، واحد فنی و مهندسی، سمت مدیر» با «رضا، همان واحد، سمت تکنسین» دو دسترسی کاملاً متفاوت است."
              action={
                <PermissionGuard
                  permission={PERMISSIONS.organizationAssignmentManage}
                  fallback="hide"
                >
                  <Button onClick={() => setShowAssignmentForm((open) => !open)}>
                    {showAssignmentForm ? "بستن" : "＋ انتساب کاربر"}
                  </Button>
                </PermissionGuard>
              }
            />
            {showAssignmentForm ? (
              <div className="inline-form">
                <TextInput
                  label="شناسه کاربر"
                  value={assignmentForm.userId}
                  onChange={(event) =>
                    setAssignmentForm({ ...assignmentForm, userId: event.target.value })
                  }
                />
                <TextInput
                  label="نام نمایشی"
                  value={assignmentForm.userDisplayName}
                  onChange={(event) =>
                    setAssignmentForm({
                      ...assignmentForm,
                      userDisplayName: event.target.value,
                    })
                  }
                />
                <SelectInput
                  label="واحد"
                  value={assignmentForm.departmentId}
                  options={[
                    { value: "", label: "— انتخاب واحد —" },
                    ...activeDepartments.map((row) => ({ value: row.id, label: row.name })),
                  ]}
                  onChange={(event) =>
                    setAssignmentForm({ ...assignmentForm, departmentId: event.target.value })
                  }
                />
                <SelectInput
                  label="سمت"
                  value={assignmentForm.positionId}
                  options={[
                    { value: "", label: "— انتخاب سمت —" },
                    ...positions
                      .filter((row) => row.isActive)
                      .map((row) => ({ value: row.id, label: row.name })),
                  ]}
                  onChange={(event) =>
                    setAssignmentForm({ ...assignmentForm, positionId: event.target.value })
                  }
                />
                <Button
                  disabled={
                    busy ||
                    assignmentForm.userId.trim() === "" ||
                    assignmentForm.departmentId === "" ||
                    assignmentForm.positionId === ""
                  }
                  onClick={submitAssignment}
                >
                  ثبت انتساب
                </Button>
              </div>
            ) : null}
            <DataTable
              columns={assignmentColumns}
              data={assignments}
              rowKey={(row: AssignmentRow) => row.id}
              loading={loading}
              empty={{ title: "هنوز کاربری منتسب نشده است" }}
            />
          </Card>
        </>
      ) : null}

      {tab === "matrix" ? (
        <Card>
          <CardHeader
            title="ماتریس دسترسی"
            subtitle="برای هر سمت، در هر واحد، مشخص کنید چه کاری مجاز است و تا چه محدوده‌ای."
            action={
              <SelectInput
                label="واحد"
                value={matrixUnitId}
                options={[
                  { value: "", label: "پیش‌فرض کل سازمان" },
                  ...activeDepartments.map((row) => ({ value: row.id, label: row.name })),
                ]}
                onChange={(event) => setMatrixUnitId(event.target.value)}
              />
            }
          />
          {matrixUnitId !== "" ? (
            <p className="hint">
              سلول‌هایی که برای این واحد تعیین شوند، جایگزین پیش‌فرض کل سازمان می‌شوند — حتی اگر
              محدودتر باشند.
            </p>
          ) : null}
          {matrix === null ? (
            <EmptyState icon="folder" title="در حال دریافت ماتریس…" />
          ) : (
            <AccessMatrixGrid
              payload={matrix}
              busy={busy}
              onWrite={writeCell}
            />
          )}
        </Card>
      ) : null}
    </div>
  );
}

function AccessMatrixGrid({
  payload,
  busy,
  onWrite,
}: {
  payload: MatrixPayload;
  busy: boolean;
  onWrite: (
    positionId: string,
    capability: string,
    action: string,
    scope: string,
    granted: boolean,
  ) => void;
}): JSX.Element {
  const groups = useMemo(() => {
    const result = new Map<string, CapabilityRow[]>();
    payload.capabilities.forEach((capability) => {
      const bucket = result.get(capability.group) ?? [];
      bucket.push(capability);
      result.set(capability.group, bucket);
    });
    return [...result.entries()];
  }, [payload.capabilities]);

  if (payload.positions.length === 0) {
    return <EmptyState icon="users" title="ابتدا یک سمت تعریف کنید" />;
  }

  return (
    <div className="matrix-scroll">
      {groups.map(([group, capabilities]) => (
        <table key={group} className="access-matrix" data-group={group}>
          <caption>{group}</caption>
          <thead>
            <tr>
              <th scope="col">قابلیت</th>
              <th scope="col">عملیات</th>
              {payload.positions.map((position) => (
                <th key={position.id} scope="col">
                  {position.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {capabilities.flatMap((capability) =>
              capability.actions.map((action) => (
                <tr key={`${capability.key}-${action.value}`}>
                  <th scope="row">{capability.label}</th>
                  <td>{action.label}</td>
                  {payload.positions.map((position) => {
                    const scope =
                      payload.matrix[position.id]?.[capability.key]?.[action.value] ?? "";
                    const granted = scope !== "";
                    return (
                      <td key={position.id} data-granted={granted ? "yes" : "no"}>
                        <label className="matrix-cell">
                          <input
                            type="checkbox"
                            checked={granted}
                            disabled={busy}
                            aria-label={`${capability.label} — ${action.label} — ${position.name}`}
                            onChange={(event) =>
                              onWrite(
                                position.id,
                                capability.key,
                                action.value,
                                capability.scoped ? "department" : "all",
                                event.target.checked,
                              )
                            }
                          />
                          {granted && capability.scoped ? (
                            <select
                              value={scope}
                              disabled={busy}
                              aria-label={`محدوده ${capability.label} — ${action.label} — ${position.name}`}
                              onChange={(event) =>
                                onWrite(
                                  position.id,
                                  capability.key,
                                  action.value,
                                  event.target.value,
                                  true,
                                )
                              }
                            >
                              {payload.scopes.map((option) => (
                                <option key={option.value} value={option.value}>
                                  {option.label}
                                </option>
                              ))}
                            </select>
                          ) : null}
                          {granted && !capability.scoped ? (
                            <span className="scope-fixed">کل کارخانه</span>
                          ) : null}
                        </label>
                      </td>
                    );
                  })}
                </tr>
              )),
            )}
          </tbody>
        </table>
      ))}
    </div>
  );
}

export default OrganizationStructurePage;
