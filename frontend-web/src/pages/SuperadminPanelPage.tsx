import { useOrganizationWorkspace } from '../core/tenant/organizationWorkspace';
import { OrganizationWorkspaceEditor } from './OrganizationWorkspaceEditor';
import { useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { useApiClient } from '../core/api/apiContext';
import { useAuth } from '../core/auth/authContext';
import { permissionLabelFa, PERMISSION_LABELS_FA } from '../features/security/permissionLabelsFa';
import './SuperadminPanelPage.css';
import {SuperadminDatabaseTools} from './SuperadminDatabaseTools';
import { AuditReports, PersonDiagnostics, ReviewDialog, needsReview, type ReviewPreview } from './SuperadminReviewTools';

type Appearance = { displayName: string; logoData: string; primaryColor: string; theme: string; revision: number };
type Tenant = { id: string; code: string; name: string; status: string; appearance: Appearance };
type Person = { id: string; tenantId: string; displayName: string; username: string; email: string; phone: string; status: string; unit?: string; position?: string; roles: string[]; administration?: { username: string; status: string; ready: boolean } };
type Role = { id: string; name: string; code: string; scopeType: string; actions: string[] };
type Panel = { users: Person[]; roles: Role[]; tenants: Tenant[]; ownerUserId: string; legacyRetired: boolean; audit: { id: string; time: string; action: string; resource: string; actorId: string; resourceId: string }[] };
const statusFa = (value: string) => ({ active: 'فعال', suspended: 'موقتاً غیرفعال', disabled: 'بایگانی', closed: 'بسته' }[value] ?? value);

export function SuperadminPanelPage(): JSX.Element {
  const api = useApiClient();
  const { logout } = useAuth();
  const {workspace}=useOrganizationWorkspace();
  const [panel, setPanel] = useState<Panel | null>(null);
  const [tab, setTab] = useState('users');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [secret, setSecret] = useState<{ temporaryPassword: string; user?: Person; temporaryExpiresAt?: string } | null>(null);
  const [tenantId, setTenantId] = useState('');
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState('');
  const [operation, setOperation] = useState('suspend');
  const [roleId, setRoleId] = useState('');
  const [phone, setPhone] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [confirm, setConfirm] = useState(false);
  const [repairMembership, setRepairMembership] = useState(false);
  const [code, setCode] = useState('');
  const [newUser, setNewUser] = useState({ displayName: '', username: '', email: '', phone: '' });
  const [newTenant, setNewTenant] = useState({ code: '', name: '' });
  const [appearance, setAppearance] = useState<Appearance | null>(null);
  const [roleForm, setRoleForm] = useState({ id: '', code: '', name: '', actions: [] as string[] });
  const [adminName, setAdminName] = useState('');
  const [temporary, setTemporary] = useState('');
  const [adminOperation, setAdminOperation] = useState('create');
  const [tenantOperation, setTenantOperation] = useState('suspend');
  const [recovery, setRecovery] = useState('');
  const [pendingReview, setPendingReview] = useState<{payload:Record<string,unknown>;preview:ReviewPreview}|null>(null);
  const [reviewRevision,setReviewRevision] = useState(0);

  async function load(): Promise<void> {
    const result = await api.get<Panel>('superadmin/panel', { retry: 0 });
    setPanel(result);
    setTenantId(previous => previous || result.tenants[0]?.id || '');
  }
  useEffect(() => { load().catch(e => setError(e.message)); }, [api]);
  useEffect(() => { setAppearance(panel?.tenants.find(t => t.id === tenantId)?.appearance ?? null); }, [tenantId, panel]);
  const person = panel?.users.find(u => u.id === selected);
  const tenant = panel?.tenants.find(t => t.id === tenantId);

  async function send(payload: Record<string, unknown>, reviewed?:{token:string;reason:string}): Promise<boolean> {
    setError(''); setMessage(''); setBusy(true); setSecret(null);
    try {
      if (!reviewed && needsReview(payload)) {
        const preview=await api.post<ReviewPreview>('superadmin/panel/preview',{request:payload},{retry:0});
        setPendingReview({payload:{...payload},preview});
        return false;
      }
      const response = await api.post<any>(reviewed ? 'superadmin/panel/commit' : 'superadmin/panel', reviewed ? {request:payload,token:reviewed.token,reason:reviewed.reason,confirm:true} : payload, { retry: 0 });
      setPendingReview(null);setReviewRevision(n=>n+1);
      if (response.temporaryPassword) setSecret(response);
      setTemporary(''); setCode(''); setRecovery(''); setConfirmation(''); setConfirm(false); setRepairMembership(false);
      setMessage(payload.operation === 'restoreArchive' ? 'همان حساب از بایگانی بازگردانده شد؛ نام کاربری و سوابق حفظ شده‌اند. برای ورود از رمز قبلی استفاده کنید؛ اگر رمز موقت منقضی یا فراموش شده، رمز موقت جایگزین صادر کنید.' : 'عملیات با موفقیت ثبت شد.');
      await load();
      if (payload.operation === 'appearance') window.dispatchEvent(new Event('tekarai:appearance-updated'));
      return true;
    } catch (caught) { if(reviewed)setPendingReview(null);setError(caught instanceof Error ? caught.message : 'عملیات انجام نشد.'); return false; }
    finally { setBusy(false); }
  }
  const submitUser = (e: FormEvent) => { e.preventDefault(); void send({kind: operation === 'erase' ? 'erase' : 'user', operation, userId: selected, roleId, phone, confirmation, confirm, ...(operation === 'restoreArchive' ? {repairMembership} : {})}); };
  const selectTenant = <label>سازمان<select value={tenantId} onChange={e => { setTenantId(e.target.value); setSelected(''); setConfirmation(''); setConfirm(false); setRepairMembership(false); }}>{panel?.tenants.map(t => <option value={t.id} key={t.id}>{t.name} — {statusFa(t.status)}</option>)}</select></label>;
  async function upload(file?: File): Promise<void> {
    if (!file) return;
    if (!['image/png', 'image/jpeg'].includes(file.type) || file.size > 512000) { setError('لوگو PNG یا JPEG و حداکثر ۵۰۰ کیلوبایت باشد.'); return; }
    const reader = new FileReader();
    reader.onload = () => setAppearance(previous => previous ? { ...previous, logoData: String(reader.result) } : null);
    reader.readAsDataURL(file);
  }

  return <main className="superadmin" dir="rtl">
    <header><div><small>TEKARAI · مدیریت مستقل</small><h1>مدیریت کل سامانه</h1></div><nav><Link to="/app/dashboard">ورود به محیط کاری</Link><Link to="/superadmin/login">ورود مجدد مدیریت</Link><button onClick={() => void logout()}>خروج</button></nav></header>
    <p className="sa-note">حساب اصلی افراد، سابقه سازمانی و ورود مدیریت کل مستقل‌اند. رمز شخصی هیچ فردی نمایش داده نمی‌شود. تأیید حساس پس از ده دقیقه باید تازه شود.</p>
    <form className="sa-stepup" onSubmit={e => { e.preventDefault(); void send({kind:'stepup', code}); }}>
      <label>تأیید تازه مدیریت<input dir="ltr" autoComplete="one-time-code" value={code} onChange={e => setCode(e.target.value)} placeholder="کد برنامه یا کد بازیابی" required /></label><button disabled={busy}>تأیید مجدد</button>
    </form>
    {error && <p className="sa-error" role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    {pendingReview && <ReviewDialog key={pendingReview.preview.token} preview={pendingReview.preview} busy={busy} onCancel={()=>setPendingReview(null)} onConfirm={reason=>void send(pendingReview.payload,{token:pendingReview.preview.token,reason})}/>}
    {secret && <section className="sa-secret"><h2>تحویل دستی رمز موقت — فقط همین‌بار</h2><p>نام کاربری: <b dir="ltr">{secret.user?.username}</b></p><pre dir="ltr">{secret.temporaryPassword}</pre><p>فرد باید در اولین ورود رمز شخصی تعیین کند. رمز را در پیام عمومی یا گروه ارسال نکنید.</p><button onClick={() => setSecret(null)}>تحویل دادم؛ بستن نمایش</button></section>}
    <nav className="sa-tabs">{[['users','افراد و دسترسی'],['organizations','سازمان‌ها و ظاهر'],['roles','نقش‌ها و اختیارات'],['administrators','ورودهای مدیریت کل'],['database','داده‌های سامانه'],['audit','رویدادهای مدیریتی']].map(([id,label]) => <button key={id} aria-pressed={tab === id} onClick={() => setTab(id)}>{label}</button>)}</nav>
    {!panel ? <p>برای مشاهده پنل، ورود مستقل مدیریت و تأیید دومرحله‌ای لازم است.</p> : <>
      {!panel.legacyRetired && <details className="sa-card"><summary>تحویل امن مدیریت از ورود قدیمی به ورود مستقل</summary><p>فقط پس از ورود موفق مستقل و ذخیره کدهای بازیابی انجام دهید. ورود روزمره و مدیریت سازمان حفظ می‌شود؛ دسترسی سراسری ورود قدیمی و نشست‌های دیگر مالک بسته می‌شوند.</p><form onSubmit={e => { e.preventDefault(); void send({kind:'handoff', confirmation, confirm, recoveryCode: recovery}); }}><label>نام کاربری اصلی مالک<input required value={confirmation} onChange={e => setConfirmation(e.target.value)} /></label><label>یکی از کدهای بازیابی ذخیره‌شده<input dir="ltr" required autoComplete="off" value={recovery} onChange={e => setRecovery(e.target.value)} /></label><label><input type="checkbox" checked={confirm} onChange={e => setConfirm(e.target.checked)} /> انتقال دسترسی سراسری و خروج نشست‌های دیگر را تأیید می‌کنم.</label><button disabled={busy || !confirm}>تحویل امن و حفظ حساب اصلی</button></form></details>}
      {tab === 'users' && <>
        <section className="sa-card"><h2>افراد در همه سازمان‌ها</h2>{selectTenant}<label>جست‌وجو<input value={query} onChange={e => setQuery(e.target.value)} placeholder="نام، نام کاربری یا موبایل" /></label><div className="sa-table"><table><thead><tr><th>انتخاب</th><th>شخص</th><th>موبایل</th><th>واحد / سمت</th><th>وضعیت</th><th>نقش‌ها</th></tr></thead><tbody>{panel.users.filter(u => (!tenantId || u.tenantId === tenantId) && `${u.displayName} ${u.username} ${u.phone}`.includes(query)).map(u => <tr key={u.id}><td><input type="radio" name="person" aria-label={`انتخاب ${u.username}`} checked={selected === u.id} onChange={() => { setSelected(u.id); setPhone(u.phone); setConfirmation(''); setConfirm(false); setRepairMembership(false); }} /></td><td>{u.displayName}<small dir="ltr">{u.username}</small></td><td dir="ltr">{u.phone || '—'}</td><td>{u.unit || '—'} / {u.position || '—'}</td><td>{statusFa(u.status)}</td><td>{u.roles.map(id => panel.roles.find(r => r.id === id)?.name).join('، ')}</td></tr>)}</tbody></table></div></section>
        <PersonDiagnostics userId={selected} revision={reviewRevision}/>
        <section className="sa-card"><h2>عملیات حساب انتخاب‌شده {person ? `— ${person.displayName || person.username}` : ''}</h2><form onSubmit={submitUser}><label>عملیات<select value={operation} onChange={e => { setOperation(e.target.value); setConfirm(false); setConfirmation(''); setRepairMembership(false); }}><option value="suspend">غیرفعال‌سازی موقت و خروج نشست‌ها</option><option value="activate" disabled={person?.status === 'disabled'}>فعال‌سازی دوباره حساب معلق</option><option value="restoreArchive" disabled={person?.status !== 'disabled'}>بازگردانی از بایگانی — همان حساب و شماره</option><option value="reset">صدور رمز موقت جایگزین و خروج نشست‌ها</option><option value="mobile">اصلاح موبایل یکتا</option><option value="assignRole">افزودن نقش سازمانی</option><option value="removeRole">برداشتن نقش</option><option value="archive">بایگانی حساب با حفظ سوابق</option><option value="erase">حذف دائمی اطلاعات حساب بدون سابقه</option></select></label>{operation === 'mobile' && <label>موبایل<input dir="ltr" required value={phone} onChange={e => setPhone(e.target.value)} /></label>}{['assignRole','removeRole'].includes(operation) && <label>نقش<select required value={roleId} onChange={e => setRoleId(e.target.value)}><option value="">انتخاب کنید</option>{panel.roles.filter(r => operation === 'removeRole' ? person?.roles.includes(r.id) : r.scopeType === 'TENANT').map(r => <option key={r.id} value={r.id}>{r.name}</option>)}</select></label>}{['archive','erase','reset','suspend','removeRole','restoreArchive'].includes(operation) && <><label>برای تأیید، نام کاربری شخص را وارد کنید<input required value={confirmation} onChange={e => setConfirmation(e.target.value)} /></label><label><input type="checkbox" checked={confirm} onChange={e => setConfirm(e.target.checked)} /> پیامد عملیات را تأیید می‌کنم.</label></>}{operation === 'restoreArchive' && <label><input type="checkbox" checked={repairMembership} onChange={e => setRepairMembership(e.target.checked)} /> ترمیم عضویت همین سازمان در صورت نیاز؛ نقش‌های قبلی را بررسی کرده‌ام.</label>}{person?.status === 'disabled' && <p>این حساب بایگانی شده است؛ برای همین فرد حساب جدید نسازید. «بازگردانی از بایگانی» همان شماره، نام کاربری و سوابق را نگه می‌دارد. نشست‌ها و کلیدهای API قدیمی بسته می‌مانند؛ نقش‌های قبلی را پیش از تأیید بررسی کنید. اگر عضویت فعال پیدا نشد، پس از بررسی سازمان و نقش‌ها تیک ترمیم عضویت را بزنید؛ سابقهٔ پایان عضویت پاک نمی‌شود و دسترسی سازمان دیگری تغییر نمی‌کند. برای تغییر واقعی شماره، «اصلاح موبایل یکتا» را انتخاب کنید.</p>}{operation === 'erase' && <p>فقط پس از بایگانی و اثبات نبود ورود و سابقه. اطلاعات و اعتبار ورود پاک می‌شود؛ صرفاً شناسه فنی غیرشخصی برای جلوگیری از شکستن ارجاع‌ها باقی می‌ماند. در صورت ابهام، سرور حذف را رد می‌کند.</p>}<button disabled={busy || !selected || (operation === 'restoreArchive' && person?.status !== 'disabled') || (['archive','erase','reset','suspend','removeRole','restoreArchive'].includes(operation) && (!confirm || confirmation !== person?.username))}>اجرای عملیات</button></form></section>
        <details className="sa-card"><summary>ایجاد شخص جدید در سازمان انتخاب‌شده</summary><p>فقط مدیر حساب می‌سازد. رمز موقت پس از ایجاد، یک‌بار برای تحویل دستی نشان داده می‌شود. برای تعیین سمت، همان شخص موجود را در «افراد و سازمان» انتخاب کنید.</p><form onSubmit={e => { e.preventDefault(); void send({kind:'user',operation:'create',tenantId,...newUser}); }}>{(['displayName','username','phone','email'] as const).map((key,index) => <label key={key}>{['نام و نام خانوادگی','نام کاربری (اختیاری)','موبایل یکتا','ایمیل'][index]}<input required={key !== 'username'} type={key === 'email' ? 'email' : 'text'} value={newUser[key]} onChange={e => setNewUser({...newUser,[key]:e.target.value})} /></label>)}<button disabled={busy || !tenantId}>ایجاد و دریافت رمز موقت</button></form></details>
      </>}
      {tab === 'organizations' && <>
        <OrganizationWorkspaceEditor key={tenantId} tenantId={tenantId}/>
        <section className="sa-card"><h2>مدیریت سازمان</h2>{selectTenant}<p>کد ورود: <b dir="ltr">{tenant?.code}</b> — وضعیت: {statusFa(tenant?.status || '')}</p><form onSubmit={e => { e.preventDefault(); void send({kind:'tenant',operation:tenantOperation,tenantId,userId:selected}); }}><label>عملیات<select value={tenantOperation} onChange={e => setTenantOperation(e.target.value)}><option value="suspend">توقف سازمان و خروج نشست‌ها</option><option value="activate">فعال‌سازی سازمان</option><option value="close">بستن سازمان با حفظ داده</option><option value="assignManager">تعیین مدیر سازمان</option><option value="removeManager">برداشتن مدیر پس از تعیین جایگزین</option></select></label>{tenantOperation.includes('Manager') && <label>شخص موجود همین سازمان<select required value={selected} onChange={e => setSelected(e.target.value)}><option value="">انتخاب کنید</option>{panel.users.filter(u => u.tenantId === tenantId && u.status === 'active').map(u => <option key={u.id} value={u.id}>{u.displayName || u.username}</option>)}</select></label>}<button disabled={busy}>اجرای عملیات سازمان</button></form></section>
        <details className="sa-card"><summary>ایجاد سازمان جدید</summary><form onSubmit={e => { e.preventDefault(); void send({kind:'tenant',operation:'create',...newTenant}); }}><label>کد انگلیسی یکتا<input dir="ltr" required value={newTenant.code} onChange={e => setNewTenant({...newTenant,code:e.target.value})} /></label><label>نام سازمان<input required value={newTenant.name} onChange={e => setNewTenant({...newTenant,name:e.target.value})} /></label><button disabled={busy}>ایجاد سازمان</button></form></details>
        {appearance && <section className="sa-card"><h2>ظاهر زنده سازمان — بدون ZIP جدید</h2><form onSubmit={e => { e.preventDefault(); void send({kind:'tenant',operation:'appearance',tenantId,...appearance}); }}><label>نام نمایشی<input required maxLength={160} value={appearance.displayName} onChange={e => setAppearance({...appearance,displayName:e.target.value})} /></label><label>رنگ اصلی<input type="color" value={appearance.primaryColor} onChange={e => setAppearance({...appearance,primaryColor:e.target.value})} /></label><label>قالب<select value={appearance.theme} onChange={e => setAppearance({...appearance,theme:e.target.value})}><option value="warm">گرم و آرام</option><option value="light">روشن و خنثی</option><option value="forest">سبز ملایم</option></select></label><label>لوگو (PNG / JPEG، حداکثر ۵۰۰ کیلوبایت)<input type="file" accept="image/png,image/jpeg" onChange={e => void upload(e.target.files?.[0])} /></label><button type="button" onClick={() => setAppearance({...appearance,logoData:''})}>حذف لوگوی سفارشی</button><aside className="sa-preview" style={{borderColor:appearance.primaryColor,background:appearance.theme === 'forest' ? '#edf4ef' : appearance.theme === 'light' ? '#fff' : '#faf7ef'}}>{appearance.logoData && <img alt="پیش‌نمایش لوگو" src={appearance.logoData} />}<h3 style={{color:appearance.primaryColor}}>{appearance.displayName}</h3><p>پیش‌نمایش؛ هنوز ذخیره نشده است</p><span style={{background:appearance.primaryColor,color:'#fff',padding:8,borderRadius:7}}>نمونه دکمه</span></aside><button disabled={busy}>ذخیره ظاهر سازمان</button></form><p>لوگوی محصول Tekarai جدا می‌ماند. برای مشاهده در دستگاه‌های باز، صفحه را تازه کنید.</p></section>}
      </>}
      {tab === 'roles' && <section className="sa-card"><h2>نقش‌های سازمانی و اختیارات</h2><label>ویرایش نقش<select value={roleForm.id} onChange={e => { const r = panel.roles.find(x => x.id === e.target.value); setRoleForm(r ? {...r} : {id:'',code:'',name:'',actions:[]}); }}><option value="">نقش جدید</option>{panel.roles.filter(r => r.scopeType === 'TENANT').map(r => <option value={r.id} key={r.id}>{r.name}</option>)}</select></label><form onSubmit={e => { e.preventDefault(); void send({kind:'role',operation:roleForm.id ? 'update' : 'create',roleId:roleForm.id,...roleForm}); }}><label>کد انگلیسی<input dir="ltr" disabled={!!roleForm.id} required value={roleForm.code} onChange={e => setRoleForm({...roleForm,code:e.target.value})} /></label><label>نام نقش<input required value={roleForm.name} onChange={e => setRoleForm({...roleForm,name:e.target.value})} /></label><div className="sa-permissions">{Array.from(new Set([...Object.keys(PERMISSION_LABELS_FA),...(workspace?.catalog.flatMap(m=>m.permissions)||[]),...roleForm.actions])).filter(c => !['tenant.create','tenant.list','tenant.suspend','tenant.activate','tenant.close'].includes(c)).map(action => <label key={action}><input type="checkbox" checked={roleForm.actions.includes(action)} onChange={e => setRoleForm({...roleForm,actions:e.target.checked ? [...roleForm.actions,action] : roleForm.actions.filter(a => a !== action)})} />{permissionLabelFa(action)}</label>)}</div><button disabled={busy}>ذخیره نقش و اختیارات</button>{roleForm.id && <button type="button" disabled={busy} onClick={() => { if (window.confirm('فقط نقش بدون انتساب حذف می‌شود؛ تأیید می‌کنید؟')) void send({kind:'role',operation:'delete',roleId:roleForm.id}); }}>حذف نقش بدون انتساب</button>}</form></section>}
      {tab === 'administrators' && <section className="sa-card"><h2>ورودهای مستقل مدیریت کل</h2><p>شخص جدید برای مدیریت نسازید؛ مالک را از افراد موجود انتخاب کنید. تغییر ورود مدیریتِ خودتان از این مسیر ممنوع است. بازنشانی ورود مدیریتی دیگران، رمز موقت و تأیید دومرحله‌ای تازه لازم دارد.</p><form onSubmit={e => { e.preventDefault(); void send({kind:'identity',operation:adminOperation,userId:selected,username:adminName,temporaryPassword:temporary}); }}><label>مالک موجود<select required value={selected} onChange={e => setSelected(e.target.value)}><option value="">انتخاب کنید</option>{panel.users.filter(u => u.id !== panel.ownerUserId && (u.status === 'active' || (adminOperation === 'disable' && !!u.administration))).map(u => <option key={u.id} value={u.id}>{u.displayName || u.username} {u.administration ? `— ${u.administration.username} (${statusFa(u.administration.status)})` : ''}</option>)}</select></label><label>عملیات<select value={adminOperation} onChange={e => setAdminOperation(e.target.value)}><option value="create">ایجاد ورود مستقل</option><option value="reset">رمز موقت جایگزین و راه‌اندازی دوباره MFA</option><option value="disable">غیرفعال‌سازی ورود کل</option><option value="activate">فعال‌سازی ورود کل</option></select></label>{adminOperation === 'create' && <label>نام کاربری مستقل<input dir="ltr" required value={adminName} onChange={e => setAdminName(e.target.value)} /></label>}{['create','reset'].includes(adminOperation) && <label>رمز موقت برای تحویل دستی<input type="password" autoComplete="new-password" minLength={12} required value={temporary} onChange={e => setTemporary(e.target.value)} /></label>}<button disabled={busy}>ثبت عملیات مدیریتی</button></form></section>}
      {tab === 'database' && <SuperadminDatabaseTools tenants={panel.tenants} onChanged={()=>void load()}/>}
      {tab === 'audit' && <AuditReports people={panel.users} tenants={panel.tenants}/>}
    </>}
  </main>;
}
