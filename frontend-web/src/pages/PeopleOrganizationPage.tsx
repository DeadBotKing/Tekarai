import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useApiClient } from "../core/api/apiContext";
import { PERMISSIONS, usePermissions } from "../core/permissions/permissionContext";
import { createSecurityService, type UserAccount } from "../features/security/securityService";
import { DataTable, type DataTableColumn } from "../shared/components/DataTable";
import { Modal } from "../shared/components/overlays";
import { Button, Card, CardHeader, PermissionGuard, SectionHeader, SelectInput, TextInput } from "../shared/components/primitives";
import { OrganizationStructurePage } from "./OrganizationStructurePage";

type Department = { id: string; name: string; status: string };
type Position = { id: string; name: string; isActive: boolean };
type Assignment = { id: string; userId: string; departmentId: string; positionId: string; departmentName: string; positionName: string; isActive: boolean; isPrimary: boolean };
const emptyAccount = { username: "", displayName: "", email: "", password: "" };
const message = (error: unknown): string => error instanceof Error ? error.message : "عملیات ناموفق بود؛ دوباره تلاش کنید.";

export function PeopleOrganizationPage(): JSX.Element {
  const api = useApiClient();
  const service = useMemo(() => createSecurityService(api), [api]);
  const { has } = usePermissions();
  const [users, setUsers] = useState<UserAccount[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [orgError, setOrgError] = useState("");
  const [notice, setNotice] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(!has(PERMISSIONS.userList));
  const [search, setSearch] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [account, setAccount] = useState(emptyAccount);
  const [created, setCreated] = useState<UserAccount | null>(null);
  const [departmentId, setDepartmentId] = useState("");
  const [positionId, setPositionId] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState("");
  const [selected, setSelected] = useState<UserAccount | null>(null);
  const [editingAssignment, setEditingAssignment] = useState<string | null>(null);
  const [isPrimary, setIsPrimary] = useState(true);
  const requestVersion = useRef(0);
  const submitting = useRef(false);
  const canAssign = has(PERMISSIONS.organizationAssignmentManage);
  const canReadOrg = has(PERMISSIONS.organizationDepartmentView) && has(PERMISSIONS.organizationPositionView) && has(PERMISSIONS.organizationAssignmentView);
  const load = useCallback(async (): Promise<void> => {
    const version = ++requestVersion.current;
    setLoading(true);
    const userTask = has(PERMISSIONS.userList) ? service.listUsers() : Promise.resolve([]);
    const orgTask = canReadOrg ? Promise.all([
      api.get<{ items: Department[] }>("organization/departments"),
      api.get<{ items: Position[] }>("organization/positions"),
      api.get<{ items: Assignment[] }>("organization/assignments"),
    ]) : Promise.reject(new Error("برای مشاهده و انتخاب واحد و سمت، مجوز مشاهدهٔ واحدها، سمت‌ها و انتساب‌ها لازم است."));
    const [peopleResult, orgResult] = await Promise.allSettled([userTask, orgTask]);
    if (version !== requestVersion.current) return;
    if (peopleResult.status === "fulfilled") { setUsers(peopleResult.value); setError(""); }
    else setError(message(peopleResult.reason));
    if (orgResult.status === "fulfilled") {
      setDepartments(orgResult.value[0].items); setPositions(orgResult.value[1].items);
      setAssignments(orgResult.value[2].items.filter((item) => item.isActive)); setOrgError("");
    } else { setOrgError(message(orgResult.reason)); }
    setLoading(false);
  }, [api, service, canReadOrg, has]);
  useEffect(() => { void load(); return () => { requestVersion.current += 1; }; }, [load]);
  const activeDepartments = departments.filter((item) => item.status === "active");
  const activePositions = positions.filter((item) => item.isActive);
  const clearAssignmentForm = (): void => { setDepartmentId(""); setPositionId(""); setEditingAssignment(null); setIsPrimary(true); setFormError(""); };
  const openPerson = (user: UserAccount): void => { clearAssignmentForm(); setIsPrimary(!assignments.some((item) => item.userId === user.id && item.isPrimary)); setSelected(user); };
  const closeCreate = (): void => {
    if (busy) return;
    if (created) setNotice(`حساب «${created.displayName || created.username}» ساخته شده است؛ انتساب را بعداً از «مدیریت سمت‌ها» تکمیل کنید.`);
    setCreateOpen(false); setCreated(null); setAccount(emptyAccount); clearAssignmentForm(); void load();
  };
  const createPerson = async (): Promise<void> => {
    if (submitting.current) return;
    submitting.current = true; setBusy(true); setFormError("");
    let user = created;
    try {
      if (!user) {
        user = await service.inviteUser(account);
        setCreated(user);
        // Forget the password as soon as account creation succeeds.
        setAccount((current) => ({ ...current, password: "" }));
      }
      if (departmentId && positionId) {
        await api.post("organization/assignments", { userId: user.id, userDisplayName: user.displayName || user.username, departmentId, positionId });
      }
      setNotice(departmentId ? "فرد و جایگاه سازمانی ثبت شدند." : "حساب ثبت شد؛ می‌توانید بعداً از مدیریت سمت‌ها جایگاه سازمانی را تعیین کنید.");
      setCreateOpen(false); setCreated(null); setAccount(emptyAccount); clearAssignmentForm(); void load();
    } catch (cause) {
      setFormError(user ? `حساب ساخته شد، اما انتساب تکمیل نشد. با «تکمیل انتساب» دوباره تلاش کنید؛ حساب جدیدی ساخته نمی‌شود. ${message(cause)}` : message(cause));
      if (user) void load();
    } finally { submitting.current = false; setBusy(false); }
  };
  const saveAssignment = async (): Promise<void> => {
    if (!selected || submitting.current) return;
    submitting.current = true; setBusy(true); setFormError("");
    try {
      if (!assignmentValid) throw new Error("واحد و سمت فعال را انتخاب کنید.");
      if (assignments.some((item) => item.userId === selected.id && item.id !== editingAssignment && item.departmentId === departmentId && item.positionId === positionId)) throw new Error("این واحد و سمت قبلاً برای فرد ثبت شده است.");
      if (isPrimary && assignments.some((item) => item.userId === selected.id && item.isPrimary && item.id !== editingAssignment)) throw new Error("فرد انتساب اصلی دیگری دارد؛ ابتدا گزینهٔ اصلی را در انتساب قبلی بردارید یا این انتساب را غیراصلی ثبت کنید.");
      const payload = { departmentId, positionId, isPrimary };
      if (editingAssignment) await api.patch(`organization/assignments/${editingAssignment}`, payload);
      else await api.post("organization/assignments", { ...payload, userId: selected.id, userDisplayName: selected.displayName || selected.username });
      clearAssignmentForm(); setNotice("انتساب فرد ذخیره شد."); await load();
    } catch (cause) { setFormError(message(cause)); }
    finally { submitting.current = false; setBusy(false); }
  };
  const removeAssignment = async (item: Assignment): Promise<void> => {
    if (!window.confirm("این انتساب حذف شود؟ دسترسی‌های ناشی از آن قطع می‌شود؛ حساب فرد حذف نمی‌شود.")) return;
    if (submitting.current) return;
    submitting.current = true; setBusy(true); setFormError("");
    try { await api.delete(`organization/assignments/${item.id}`); clearAssignmentForm(); await load(); setNotice("انتساب حذف شد؛ حساب فرد حفظ شده است."); }
    catch (cause) { setFormError(message(cause)); }
    finally { submitting.current = false; setBusy(false); }
  };
  const userAssignments = (userId: string): Assignment[] => assignments.filter((item) => item.userId === userId).sort((a,b) => Number(b.isPrimary) - Number(a.isPrimary));
  const columns: DataTableColumn<UserAccount>[] = [
    { key: "name", label: "نام فرد", accessor: (row) => row.displayName || row.username, sortable: true },
    { key: "username", label: "نام کاربری", accessor: (row) => row.username },
    { key: "email", label: "ایمیل", accessor: (row) => row.email },
    { key: "organization", label: "واحد و سمت", accessor: (row) => userAssignments(row.id).map((item) => `${item.departmentName} — ${item.positionName}`).join("، "), render: (row) => orgError ? <span>دریافت انتساب‌ها در دسترس نیست</span> : userAssignments(row.id).length === 0 ? <span>بدون انتساب</span> : <div>{userAssignments(row.id).map((item) => <div key={item.id}>{item.departmentName} — <strong>{item.positionName}</strong>{item.isPrimary ? " (اصلی)" : ""}</div>)}</div> },
    { key: "status", label: "وضعیت", accessor: (row) => row.status, render: (row) => <span>{row.status === "active" ? "فعال" : row.status === "pending" ? "در انتظار" : row.status === "suspended" ? "معلق" : row.status}</span> },
    { key: "actions", label: "عملیات", render: (row) => <PermissionGuard permission={PERMISSIONS.organizationAssignmentManage} fallback="hide"><Button disabled={loading || !!orgError} onClick={() => openPerson(row)}>مدیریت سمت‌ها</Button></PermissionGuard> },
  ];
  const selectionFields = <>
    <SelectInput label="واحد سازمانی" value={departmentId} disabled={busy || loading || !!orgError} onChange={(event) => setDepartmentId(event.target.value)} options={[{value:"",label:"— انتخاب واحد —"}, ...activeDepartments.map((item) => ({value:item.id,label:item.name}))]} />
    <SelectInput label="سمت" value={positionId} disabled={busy || loading || !!orgError} onChange={(event) => setPositionId(event.target.value)} options={[{value:"",label:"— انتخاب سمت —"}, ...activePositions.map((item) => ({value:item.id,label:item.name}))]} />
  </>;
  const assignmentValid = !!departmentId && !!positionId && activeDepartments.some((item) => item.id === departmentId) && activePositions.some((item) => item.id === positionId);
  const partialSelection = !!departmentId !== !!positionId;
  return <div className="page">
    <SectionHeader eyebrow="مدیریت" title="افراد و سازمان" subtitle="حساب افراد، واحد و سمت آن‌ها را از همین‌جا مدیریت کنید." actions={<>
      <PermissionGuard permission={PERMISSIONS.organizationDepartmentView} fallback="hide"><Button variant="secondary" onClick={() => {setSettingsOpen((value) => !value); if(settingsOpen) void load();}}>{settingsOpen ? "بازگشت به فهرست افراد" : "تنظیمات سازمان و دسترسی"}</Button></PermissionGuard>
      <PermissionGuard permission={PERMISSIONS.userCreate} fallback="hide"><Button variant="primary" onClick={() => {setCreated(null);setAccount(emptyAccount);clearAssignmentForm();setCreateOpen(true);void load();}}>افزودن فرد</Button></PermissionGuard>
    </>} />
    {notice && <p role="status">{notice}</p>}
    {settingsOpen ? <OrganizationStructurePage embedded /> : <Card padding="none"><CardHeader title="فهرست افراد" subtitle="برای تغییر یا افزودن جایگاه سازمانی، مدیریت سمت‌های همان فرد را باز کنید." action={<Button disabled={loading} onClick={() => {void load();}}>تازه‌سازی</Button>} />
      <div className="card-pad"><TextInput label="جستجوی افراد" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="نام، نام کاربری یا ایمیل" /></div>
      {(error || orgError) && <p className="card-pad" role="alert">{error || orgError}</p>}
      <DataTable columns={columns} data={users.filter((row) => `${row.displayName} ${row.username} ${row.email}`.toLowerCase().includes(search.toLowerCase()))} rowKey={(row) => row.id} exportName="tekarai-people" empty={{title: loading ? "در حال دریافت افراد…" : error ? "دریافت افراد ناموفق بود" : "فردی پیدا نشد"}} />
    </Card>}
    <Modal open={createOpen} title="افزودن فرد و جایگاه سازمانی" onClose={closeCreate} footer={<><Button disabled={busy} onClick={closeCreate}>{created ? "تکمیل در زمان دیگر" : "انصراف"}</Button><Button variant="primary" loading={busy} disabled={busy || partialSelection || (!!departmentId && (!assignmentValid || !canAssign || !!orgError)) || (!created && (!account.username.trim() || !account.email.trim() || account.password.length < 12))} onClick={() => {void createPerson();}}>{created ? "تکمیل انتساب" : "ثبت فرد و انتساب"}</Button></>}>
      {formError && <p role="alert">{formError}</p>}
      {created && <p role="status">حساب {created.displayName || created.username} ایجاد شده؛ فقط مرحلهٔ انتساب باقی مانده است.</p>}
      <div className="form-grid"><TextInput label="نام و نام خانوادگی" disabled={busy || !!created} value={account.displayName} onChange={(event) => setAccount({...account,displayName:event.target.value})} />
      <TextInput label="نام کاربری" required disabled={busy || !!created} value={account.username} onChange={(event) => setAccount({...account,username:event.target.value})} />
      <TextInput label="ایمیل" type="email" required disabled={busy || !!created} value={account.email} onChange={(event) => setAccount({...account,email:event.target.value})} />
      {!created && <TextInput label="رمز عبور" type="password" required disabled={busy} hint="حداقل ۱۲ کاراکتر" value={account.password} onChange={(event) => setAccount({...account,password:event.target.value})} />}
      </div>
      <h3>جایگاه سازمانی</h3>
      {canAssign ? <><div className="form-grid">{selectionFields}</div><p>واحد و سمت را با هم انتخاب کنید؛ برای ساخت حساب بدون انتساب، هر دو را خالی بگذارید.</p>{orgError && <p role="alert">{orgError}</p>}</> : <p>مجوز انتساب ندارید؛ حساب را بسازید تا مسئول مجاز جایگاه را تعیین کند.</p>}
    </Modal>
    <Modal open={selected !== null} title={`مدیریت سمت‌ها — ${selected?.displayName || selected?.username || ""}`} onClose={() => {if(!busy) setSelected(null);}} footer={<Button disabled={busy} onClick={() => setSelected(null)}>بستن</Button>}>
      {formError && <p role="alert">{formError}</p>}
      {selected && userAssignments(selected.id).map((item) => <Card key={item.id}><p>{item.departmentName} — <strong>{item.positionName}</strong>{item.isPrimary ? " (اصلی)" : ""}</p><Button disabled={busy} onClick={() => {setEditingAssignment(item.id);setDepartmentId(item.departmentId);setPositionId(item.positionId);setIsPrimary(item.isPrimary);setFormError("");}}>ویرایش انتساب</Button> <Button disabled={busy} onClick={() => {void removeAssignment(item);}}>برداشتن انتساب</Button></Card>)}
      {selected && userAssignments(selected.id).length === 0 && <p>این فرد هنوز انتسابی ندارد.</p>}
      <h3>{editingAssignment ? "ویرایش انتساب انتخاب‌شده" : "افزودن سمت"}</h3>
      <div className="form-grid">{selectionFields}</div>
      <label><input type="checkbox" checked={isPrimary} disabled={busy} onChange={(event) => setIsPrimary(event.target.checked)} /> انتساب اصلی</label>
      <p>انتساب اصلی جایگاه پیش‌فرض فرد است. حذف انتساب، حساب کاربری را حذف نمی‌کند.</p>
      <Button variant="primary" disabled={busy || !canAssign || !assignmentValid || !!orgError} onClick={() => {void saveAssignment();}}>{editingAssignment ? "ذخیره تغییرات" : "افزودن انتساب"}</Button>
      {editingAssignment && <Button disabled={busy} onClick={clearAssignmentForm}>انصراف از ویرایش</Button>}
    </Modal>
  </div>;
}
