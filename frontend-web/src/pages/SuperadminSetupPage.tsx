import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { useApiClient } from '../core/api/apiContext';
import './SuperadminPanelPage.css';

export function SuperadminSetupPage(): JSX.Element {
  const api = useApiClient();
  const [form, setForm] = useState({currentPassword:'',username:'',temporaryPassword:'',phone:'',ownerMfaCode:''});
  const [restartPending, setRestartPending] = useState(false);
  const [result, setResult] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent): Promise<void> {
    e.preventDefault();setBusy(true);setError('');
    try { await api.post('superadmin/setup',{...form,restartPending},{retry:0});setForm({currentPassword:'',username:'',temporaryPassword:'',phone:'',ownerMfaCode:''});setResult(true); }
    catch(caught) { setError(caught instanceof Error ? caught.message : 'راه‌اندازی انجام نشد.'); }
    finally {setBusy(false);}
  }
  return <main className="superadmin" dir="rtl"><h1>راه‌اندازی ورود مستقل مدیریت کل</h1><section className="sa-card"><p>این مرحله فقط برای مالک فعلی تأییدشده سامانه است. شخص جدید ایجاد نمی‌شود؛ موبایل همین مالک تکمیل می‌شود. رمز و ورود اصلی تغییر نمی‌کند. رمز یا کد تأیید را در گفتگو ارسال نکنید.</p>{error && <p role="alert" className="sa-error">{error}</p>}{result ? <><h2>ورود مستقل آماده راه‌اندازی است</h2><p>با نام کاربری و رمز موقت انتخاب‌شده وارد شوید؛ سپس رمز شخصی مستقل، برنامه تأییدکننده و کدهای بازیابی را تکمیل کنید. تحویل دسترسی قدیمی فقط پس از ورود موفق و بررسی یک کد بازیابی در پنل انجام می‌شود.</p><Link to="/superadmin/login">ورود مستقل مدیریت کل</Link></> : <form onSubmit={submit}>{(['currentPassword','phone','username','temporaryPassword'] as const).map((key,index) => <label key={key}>{['رمز فعلی حساب اصلی مالک','موبایل یکتای مالک','نام کاربری مستقل مدیریت (انگلیسی)','رمز موقت مستقل مدیریت (حداقل ۱۲ نویسه)'][index]}<input required dir="ltr" type={key.includes('Password') ? 'password' : 'text'} autoComplete={key === 'currentPassword' ? 'current-password' : key === 'temporaryPassword' ? 'new-password' : 'off'} minLength={key === 'temporaryPassword' ? 12 : undefined} value={form[key]} onChange={e => setForm({...form,[key]:e.target.value})} /></label>)}<label>کد تازه حساب اصلی (فقط اگر تأیید دومرحله‌ای آن فعال است)<input dir="ltr" autoComplete="one-time-code" value={form.ownerMfaCode} onChange={e => setForm({...form,ownerMfaCode:e.target.value})} /></label><label><input type="checkbox" checked={restartPending} onChange={e => setRestartPending(e.target.checked)} /> تجدید راه‌اندازی ناتمام (فقط ورود کلِ هرگز تکمیل‌نشده؛ رمز موقت قبلی نامعتبر می‌شود)</label><button disabled={busy}>{busy ? 'در حال بررسی…' : 'ایجاد ورود مستقل بدون تغییر رمز اصلی'}</button></form>}<p><Link to="/app/dashboard">بازگشت به محیط کاری</Link></p></section></main>;
}
