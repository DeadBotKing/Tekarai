import { useEffect, useMemo, useState } from "react";
import { runtimeConfig } from "../app/configuration/runtimeConfig";
import { useApiClient } from "../core/api/apiContext";
import { apiEndpoints } from "../core/api/endpoints";
import { createSecurityService } from "../features/security/securityService";
import { formatJalali } from "../core/localization/jalali";
import { NavLink, useLocation } from "react-router-dom";
import { useLocalization } from "../core/localization/localizationContext";
import { PERMISSIONS } from "../core/permissions/permissionContext";
import { demoActivity } from "../features/demo/demoData";
import { demoTenants } from "../core/tenant/tenantContext";
import { DataTable, type DataTableColumn } from "../shared/components/DataTable";
import { ActivityFeed } from "../shared/components/featureComponents";
import { Modal, Toast } from "../shared/components/overlays";
import { Avatar, Badge, Button, Card, CardHeader, PermissionGuard, SectionHeader, StatusBadge, TextInput } from "../shared/components/primitives";
import { Icon } from "../shared/components/Icon";

interface UserRecord { id: string; name: string; email: string; role: string; status: "active" | "pending" | "archived"; lastActive: string; access: string; }
const users: UserRecord[] = [
  { id: "u1", name: "Maya Chen", email: "maya.chen@example.test", role: "Platform Administrator", status: "active", lastActive: "Now", access: "All domains" },
  { id: "u2", name: "Jon Bell", email: "jon.bell@example.test", role: "Workspace Manager", status: "active", lastActive: "12 min ago", access: "Projects · Quality" },
  { id: "u3", name: "Sara Novak", email: "sara.novak@example.test", role: "Operations Lead", status: "active", lastActive: "2 hr ago", access: "Operations" },
  { id: "u4", name: "Owen Wright", email: "owen.wright@example.test", role: "Auditor", status: "active", lastActive: "Yesterday", access: "Read-only" },
  { id: "u5", name: "Leila Haddad", email: "leila.haddad@example.test", role: "Member", status: "pending", lastActive: "Invitation sent", access: "Service" },
];

export function AdministrationPage(): JSX.Element {
  const { t } = useLocalization();
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
  return <div className="page"><SectionHeader eyebrow={t("nav.administration")} title={t("admin.title")} subtitle={t("admin.subtitle")} actions={<PermissionGuard permission={PERMISSIONS.userCreate}><Button variant="primary" icon="plus" onClick={() => setAddUserOpen(true)}>{t("admin.addUser")}</Button></PermissionGuard>} /><div className="admin-layout"><aside className="admin-nav">{nav.map((item) => <NavLink to={item.path} key={item.id} className={({ isActive }) => `admin-nav__item ${isActive ? "is-active" : ""}`}><Icon name={item.icon} size={17} /><span>{item.label}</span><Icon name="forward" size={14} /></NavLink>)}</aside><div className="admin-content">{section === "roles" ? <Roles reloadToken={reloadToken} /> : section === "tenants" ? <Tenants /> : section === "audit" ? <Audit /> : <Users reloadToken={reloadToken} />}</div></div><Modal open={addUserOpen} title={t("admin.addUser")} onClose={() => setAddUserOpen(false)} footer={<><Button variant="secondary" onClick={() => setAddUserOpen(false)}>{t("common.cancel")}</Button><Button variant="primary" disabled={inviting || !inviteForm.username || !inviteForm.email || inviteForm.password.length < 12} onClick={invite}>{inviting ? t("common.loading") : t("common.save")}</Button></>}><div className="form-grid"><TextInput label={t("admin.username")} required value={inviteForm.username} onChange={(event) => setInviteForm({ ...inviteForm, username: event.target.value })} placeholder="ali.rezaei" /><TextInput label={t("account.displayName")} value={inviteForm.displayName} onChange={(event) => setInviteForm({ ...inviteForm, displayName: event.target.value })} /><TextInput label={t("account.email")} type="email" required value={inviteForm.email} onChange={(event) => setInviteForm({ ...inviteForm, email: event.target.value })} /><TextInput label={t("admin.password")} type="password" required hint="≥ 12" value={inviteForm.password} onChange={(event) => setInviteForm({ ...inviteForm, password: event.target.value })} /></div></Modal>{toast && <Toast message={toast} onClose={() => setToast("")} />}</div>;
}

function Users({ reloadToken = 0 }: { reloadToken?: number }): JSX.Element {
  const { t } = useLocalization();
  const api = useApiClient();
  const service = useMemo(() => createSecurityService(api), [api]);
  const [items, setItems] = useState<UserRecord[]>(users);
  const [loading, setLoading] = useState(!runtimeConfig.demoMode);
  useEffect(() => {
    if (runtimeConfig.demoMode) return;
    setLoading(true);
    service.listUsers()
      .then((rows) => setItems(rows.map((row) => ({ id: row.id, name: row.displayName || row.username, email: row.email, role: row.username, status: (row.status === "active" ? "active" : row.status === "pending" ? "pending" : "archived") as UserRecord["status"], lastActive: row.createdAt ? formatJalali(row.createdAt, { style: "short" }) : "", access: "" }))))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [service, reloadToken]);
  const columns = useMemo<DataTableColumn<UserRecord>[]>(() => [{ key: "name", label: t("admin.user"), accessor: (row) => `${row.name} ${row.email}`, sortable: true, width: "34%", render: (row) => <div className="person-cell"><Avatar name={row.name} size="sm" tone="purple" /><div><strong>{row.name}</strong><span>{row.email}</span></div></div> }, { key: "role", label: t("admin.username"), accessor: (row) => row.role, sortable: true }, { key: "status", label: t("project.status"), accessor: (row) => row.status, render: (row) => <StatusBadge status={row.status} /> }, { key: "lastActive", label: t("admin.lastActive"), accessor: (row) => row.lastActive }], [t]);
  return <div className="admin-section"><Card padding="none"><CardHeader title={t("admin.users")} subtitle={t("admin.usersSubtitle")} /><DataTable columns={columns} data={items} rowKey={(row) => row.id} exportName="tekarai-users" empty={{ title: loading ? t("common.loading") : t("admin.loadFailed") }} /></Card></div>;
}

function Roles({ reloadToken = 0 }: { reloadToken?: number }): JSX.Element {
  const { t } = useLocalization();
  const api = useApiClient();
  const service = useMemo(() => createSecurityService(api), [api]);
  const [roles, setRoles] = useState<{ name: string; code: string; permissions: number; scope: string; actions: string[] }[]>([]);
  useEffect(() => {
    if (runtimeConfig.demoMode) { setRoles([]); return; }
    service.listRoles()
      .then((rows) => setRoles(rows.map((row) => ({ name: row.name, code: row.code, permissions: row.actions.length, scope: row.scopeType, actions: row.actions }))))
      .catch(() => setRoles([]));
  }, [service, reloadToken]);
  const demoFallback = [{ name: "مدیر سکو", code: "platformAdmin", permissions: 8, scope: "GLOBAL", actions: ["user.create", "user.list", "role.list", "audit.view"] }, { name: "عضو", code: "member", permissions: 4, scope: "TENANT", actions: ["project.view", "task.view"] }];
  const rows = runtimeConfig.demoMode ? demoFallback : roles;
  return <div className="admin-section"><Card padding="md"><CardHeader title={t("admin.roles")} subtitle={t("admin.rolesSubtitle")} /><div className="role-list">{rows.map((role) => <div className="role-row" key={role.code}><span className="role-row__icon"><Icon name="key" size={17} /></span><div><strong>{role.name}</strong><span>{role.code} · {role.scope} · {role.permissions} {t("admin.actions")}</span></div></div>)}</div></Card><Card padding="md"><CardHeader title={t("admin.permissions")} /><div className="permission-matrix">{rows.flatMap((role) => role.actions.map((action) => ({ code: role.code, action }))).slice(0, 40).map((item, index) => <div key={`${item.code}-${item.action}-${index}`}><code>{item.action}</code><span><i className="status-dot status-dot--green" />{item.code}</span></div>)}</div></Card></div>;
}

function Tenants(): JSX.Element { const { t } = useLocalization(); return <div className="admin-section"><Card padding="md"><CardHeader title={t("admin.tenants")} subtitle="Global platform operators can manage tenant lifecycle and isolation." /><div className="tenant-admin-list">{demoTenants.map((tenant) => <div className="tenant-admin-row" key={tenant.id}><span className="tenant-avatar tenant-avatar--large">{tenant.name.slice(0, 1)}</span><div><strong>{tenant.name}</strong><span>{tenant.code} · {tenant.industry}</span></div><Badge tone="success" dot>{tenant.status}</Badge><span>{tenant.members} members</span><Button variant="ghost" size="sm" icon="settings">{t("common.view")}</Button></div>)}</div></Card></div>; }

function Audit(): JSX.Element {
  const { t } = useLocalization();
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
  return <div className="admin-section"><Card padding="md"><CardHeader title={t("admin.audit")} subtitle="Immutable activity records with correlation and tenant context." action={<Button variant="secondary" size="sm" icon="download">{t("common.export")}</Button>} />{loading ? <p>Loading audit events…</p> : <ActivityFeed items={items.length ? items : demoActivity} />}</Card><Card padding="md"><CardHeader title="Audit controls" /><div className="audit-controls"><div><Icon name="shield" size={20} /><strong>Append-only stream</strong><span>Audit records cannot be edited from the GUI.</span></div><div><Icon name="lock" size={20} /><strong>Tenant-scoped</strong><span>Queries require a valid tenant context and audit.view.</span></div><div><Icon name="clock" size={20} /><strong>Retention governed</strong><span>Retention follows platform and tenant policy.</span></div></div></Card></div>;
}
