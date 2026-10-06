import { useEffect, useMemo, useState } from "react";
import { runtimeConfig } from "../app/configuration/runtimeConfig";
import { useApiClient } from "../core/api/apiContext";
import { apiEndpoints } from "../core/api/endpoints";
import { createSecurityService } from "../features/security/securityService";
import { NavLink, useLocation } from "react-router-dom";
import { faText } from "../core/localization/i18n";
import { PERMISSIONS } from "../core/permissions/permissionContext";
import { demoActivity } from "../features/demo/demoData";
import { demoRoles } from "../features/demo/pageDemoFixtures";
import { demoTenants } from "../core/tenant/tenantContext";
import { DataTable, type DataTableColumn } from "../shared/components/DataTable";
import { ActivityFeed } from "../shared/components/featureComponents";
import { Modal, Toast } from "../shared/components/overlays";
import { Avatar, Badge, Button, Card, CardHeader, PermissionGuard, SectionHeader, StatusBadge, TextInput } from "../shared/components/primitives";
import { Icon } from "../shared/components/Icon";
import { ErrorState } from "../shared/components/ErrorState";
import { formatDate } from "../core/localization/format";

interface UserRecord { id: string; name: string; email: string; role: string; status: "active" | "pending" | "archived"; lastActive: string; access: string; }
const users: UserRecord[] = [
  { id: "u1", name: "Maya Chen", email: "maya.chen@example.test", role: "Platform Administrator", status: "active", lastActive: "Now", access: "All domains" },
  { id: "u2", name: "Jon Bell", email: "jon.bell@example.test", role: "Workspace Manager", status: "active", lastActive: "12 min ago", access: "Projects · Quality" },
  { id: "u3", name: "Sara Novak", email: "sara.novak@example.test", role: "Operations Lead", status: "active", lastActive: "2 hr ago", access: "Operations" },
  { id: "u4", name: "Owen Wright", email: "owen.wright@example.test", role: "Auditor", status: "active", lastActive: "Yesterday", access: "Read-only" },
  { id: "u5", name: "Leila Haddad", email: "leila.haddad@example.test", role: "Member", status: "pending", lastActive: "Invitation sent", access: "Service" },
];

export function AdministrationPage(): JSX.Element {
  const t = faText;
  const api = useApiClient();
  const service = useMemo(() => createSecurityService(api), [api]);
  const location = useLocation();
  const section = location.pathname.split("/").pop() ?? "users";
  const [addUserOpen, setAddUserOpen] = useState(false);
  const [inviteForm, setInviteForm] = useState({ username: "", email: "", password: "", displayName: "" });
  const [inviting, setInviting] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);
  const [toast, setToast] = useState("");

  const invite = (): void => {
    setInviting(true);
    service.inviteUser(inviteForm)
      .then(() => { setAddUserOpen(false); setInviteForm({ username: "", email: "", password: "", displayName: "" }); setReloadToken((value) => value + 1); setToast(t("admin.invited")); })
      .catch(() => setToast(t("admin.inviteFailed")))
      .finally(() => setInviting(false));
  };

  const nav = [{ id: "users", label: t("admin.users"), icon: "users" as const, path: "/app/administration/users" }, { id: "roles", label: t("admin.roles"), icon: "key" as const, path: "/app/administration/roles" }, { id: "tenants", label: t("admin.tenants"), icon: "building" as const, path: "/app/administration/tenants" }, { id: "audit", label: t("admin.audit"), icon: "activity" as const, path: "/app/administration/audit" }];
  return <div className="page"><SectionHeader eyebrow={t("nav.administration")} title={t("admin.title")} subtitle={t("admin.subtitle")} actions={<PermissionGuard permission={PERMISSIONS.userCreate}><Button variant="primary" icon="plus" onClick={() => setAddUserOpen(true)}>{t("admin.addUser")}</Button></PermissionGuard>} /><div className="admin-layout"><aside className="admin-nav">{nav.map((item) => <NavLink to={item.path} key={item.id} className={({ isActive }) => `admin-nav__item ${isActive ? "is-active" : ""}`}><Icon name={item.icon} size={17} /><span>{item.label}</span><Icon name="chevronRight" size={14} /></NavLink>)}</aside><div className="admin-content">{section === "roles" ? <Roles reloadToken={reloadToken} /> : section === "tenants" ? <Tenants /> : section === "audit" ? <Audit /> : <Users reloadToken={reloadToken} />}</div></div><Modal open={addUserOpen} title={t("admin.addUser")} onClose={() => setAddUserOpen(false)} footer={<><Button variant="secondary" onClick={() => setAddUserOpen(false)}>{t("common.cancel")}</Button><Button variant="primary" disabled={inviting || !inviteForm.username || !inviteForm.email || inviteForm.password.length < 12} onClick={invite}>{inviting ? t("common.loading") : t("common.save")}</Button></>}><div className="form-grid"><TextInput label={t("admin.username")} required value={inviteForm.username} onChange={(event) => setInviteForm({ ...inviteForm, username: event.target.value })} placeholder="ali.rezaei" /><TextInput label={t("account.displayName")} value={inviteForm.displayName} onChange={(event) => setInviteForm({ ...inviteForm, displayName: event.target.value })} /><TextInput label={t("account.email")} type="email" required value={inviteForm.email} onChange={(event) => setInviteForm({ ...inviteForm, email: event.target.value })} /><TextInput label={t("admin.password")} type="password" required hint="≥ 12" value={inviteForm.password} onChange={(event) => setInviteForm({ ...inviteForm, password: event.target.value })} /></div></Modal>{toast && <Toast message={toast} onClose={() => setToast("")} />}</div>;
}

function Users({ reloadToken = 0 }: { reloadToken?: number }): JSX.Element {
  const t = faText;
  const api = useApiClient();
  const service = useMemo(() => createSecurityService(api), [api]);
  const [items, setItems] = useState<UserRecord[]>(users);
  const [loading, setLoading] = useState(!runtimeConfig.demoMode);
  const [loadError, setLoadError] = useState<string | null>(null);
  useEffect(() => {
    if (runtimeConfig.demoMode) return;
    setLoading(true);
    service.listUsers()
      .then((rows) => setItems(rows.map((row) => ({ id: row.id, name: row.displayName || row.username, email: row.email, role: row.username, status: (row.status === "active" ? "active" : row.status === "pending" ? "pending" : "archived") as UserRecord["status"], lastActive: formatDate(row.createdAt, "fa", { style: "short", fallback: "" }), access: "" }))))
      .catch((error: unknown) => setLoadError(error instanceof Error ? error.message : "خطای نامشخص"))
      .finally(() => setLoading(false));
  }, [service, reloadToken]);
  const columns = useMemo<DataTableColumn<UserRecord>[]>(() => [{ key: "name", label: t("admin.user"), accessor: (row) => `${row.name} ${row.email}`, sortable: true, width: "34%", render: (row) => <div className="person-cell"><Avatar name={row.name} size="sm" tone="purple" /><div><strong>{row.name}</strong><span>{row.email}</span></div></div> }, { key: "role", label: t("admin.username"), accessor: (row) => row.role, sortable: true }, { key: "status", label: t("project.status"), accessor: (row) => row.status, render: (row) => <StatusBadge status={row.status} /> }, { key: "lastActive", label: t("admin.lastActive"), accessor: (row) => row.lastActive }], [t]);
  return <div className="admin-section"><Card padding="none"><CardHeader title={t("admin.users")} subtitle={t("admin.usersSubtitle")} />{loadError ? <div className="card-pad"><ErrorState detail={loadError} onRetry={() => setLoadError(null)} /></div> : <DataTable columns={columns} data={items} rowKey={(row) => row.id} exportName="tekarai-users" empty={{ title: loading ? t("common.loading") : t("admin.loadFailed") }} />}</Card></div>;
}

function Roles({ reloadToken = 0 }: { reloadToken?: number }): JSX.Element {
  const t = faText;
  const api = useApiClient();
  const service = useMemo(() => createSecurityService(api), [api]);
  const [roles, setRoles] = useState<import("../features/security/securityService").RoleRecord[]>([]);
  const [rolesError, setRolesError] = useState<string | null>(null);
  const [editing, setEditing] = useState<import("../features/security/securityService").RoleRecord | null>(null);
  const [name, setName] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState("");
  useEffect(() => {
    if (runtimeConfig.demoMode) return;
    service.listRoles()
      .then((items) => { setRoles(items); setRolesError(null); })
      // An empty role list is a real, alarming answer. Do not fake it from a
      // failed request.
      .catch((error: unknown) => setRolesError(error instanceof Error ? error.message : "خطای نامشخص"));
  }, [service, reloadToken]);
  const allActions = Array.from(new Set(roles.flatMap((role) => role.actions))).sort();
  const openEdit = (role: import("../features/security/securityService").RoleRecord): void => { setEditing(role); setName(role.name); setSelected(role.actions); };
  const save = (): void => { if (!editing || !name.trim()) return; setSaving(true); service.updateRole(editing.id, { name: name.trim(), actions: selected }).then((updated) => { setRoles((items) => items.map((item) => item.id === updated.id ? updated : item)); setEditing(null); setToast("نقش و مجوزهای آن ذخیره شد."); }).catch(() => setToast("ذخیره نقش ناموفق بود.")).finally(() => setSaving(false)); };
  const rows = runtimeConfig.demoMode ? demoRoles : roles;
  return <div className="admin-section"><Card padding="md"><CardHeader title={t("admin.roles")} subtitle="نقش‌ها را ببین، ویرایش کن و مجوزهای هر نقش را مدیریت کن." />
    {rolesError ? <ErrorState detail={rolesError} compact /> : null}
    <div className="role-list">{rows.map((role) => <div className="role-row" key={role.code}><span className="role-row__icon"><Icon name="key" size={17} /></span><div><strong>{role.name}</strong><span>{role.code} · {role.scopeType} · {role.actions.length} مجوز</span></div>{!runtimeConfig.demoMode && <Button variant="ghost" size="sm" icon="edit" onClick={() => openEdit(role)}>ویرایش مجوزها</Button>}</div>)}</div>
  </Card><Card padding="md"><CardHeader title="فهرست مجوزهای موجود" /><div className="permission-matrix">{rows.flatMap((role) => role.actions.map((action) => ({ code: role.code, action }))).slice(0, 100).map((item, index) => <div key={`${item.code}-${item.action}-${index}`}><code>{item.action}</code><span><i className="status-dot status-dot--green" />{item.code}</span></div>)}</div></Card>
  <Modal open={Boolean(editing)} title={`ویرایش نقش ${editing?.name ?? ""}`} onClose={() => setEditing(null)} footer={<><Button variant="secondary" onClick={() => setEditing(null)}>انصراف</Button><Button variant="primary" loading={saving} onClick={save}>ذخیره مجوزها</Button></>}><TextInput label="نام نقش" value={name} onChange={(event) => setName(event.target.value)} /><div className="permission-checklist">{allActions.map((action) => <label key={action} className="checkbox-label"><input type="checkbox" checked={selected.includes(action)} onChange={(event) => setSelected((current) => event.target.checked ? [...current, action] : current.filter((item) => item !== action))} /><code>{action}</code></label>)}</div></Modal>{toast && <Toast message={toast} onClose={() => setToast("")} />}</div>;
}

function Tenants(): JSX.Element { const t = faText; return <div className="admin-section"><Card padding="md"><CardHeader title={t("admin.tenants")} subtitle="اپراتورهای سراسری سکو، چرخه‌ی حیات و جداسازی tenantها را مدیریت می‌کنند." /><div className="tenant-admin-list">{demoTenants.map((tenant) => <div className="tenant-admin-row" key={tenant.id}><span className="tenant-avatar tenant-avatar--large">{tenant.name.slice(0, 1)}</span><div><strong>{tenant.name}</strong><span>{tenant.code} · {tenant.industry}</span></div><Badge tone="success" dot>{tenant.status}</Badge><span>{tenant.members} عضو</span><Button variant="ghost" size="sm" icon="settings">{t("common.view")}</Button></div>)}</div></Card></div>; }

function Audit(): JSX.Element {
  const t = faText;
  const api = useApiClient();
  const [items, setItems] = useState<typeof demoActivity>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    void api.get<Array<Record<string, unknown>>>(apiEndpoints.audit, { query: { pageSize: 50 } })
      .then((rows) => setItems(rows.map((row, index) => ({
        id: String(row.id ?? row.eventId ?? index),
        actor: String(row.actor ?? row.actorId ?? "System"),
        action: String(row.action ?? row.eventName ?? row.operation ?? "activity"),
        resource: String(row.resource ?? row.resourceType ?? "platform"),
        timestamp: String(row.timestamp ?? row.occurredAt ?? row.createdAt ?? ""),
        tone: index % 4 === 0 ? "blue" : index % 4 === 1 ? "green" : index % 4 === 2 ? "amber" : "purple",
      }))))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [api]);
  return <div className="admin-section"><Card padding="md"><CardHeader title={t("admin.audit")} subtitle="Immutable activity records with correlation and tenant context." action={<Button variant="secondary" size="sm" icon="download">{t("common.export")}</Button>} />{loading ? <p>Loading audit events…</p> : <ActivityFeed items={items.length ? items : demoActivity} />}</Card><Card padding="md"><CardHeader title="Audit controls" /><div className="audit-controls"><div><Icon name="shield" size={20} /><strong>جریان فقط افزودنی</strong><span>Audit records cannot be edited from the GUI.</span></div><div><Icon name="lock" size={20} /><strong>محدود به tenant</strong><span>Queries require a valid tenant context and audit.view.</span></div><div><Icon name="clock" size={20} /><strong>نگهداری مدیریت‌شده</strong><span>Retention follows platform and tenant policy.</span></div></div></Card></div>;
}
