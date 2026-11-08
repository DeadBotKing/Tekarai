import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useApiClient } from '../core/api/apiContext';
import { useAuth } from '../core/auth/authContext';
import type { TokenPair } from '../core/api/apiTypes';
import type { UserSession } from '../core/auth/sessionStore';

type LoginResult = Partial<TokenPair> & {
  step: 'password' | 'enroll' | 'mfa' | 'authenticated';
  challenge?: string; secret?: string; otpauthUrl?: string; recoveryCodes?: string[];
  user?: UserSession; permissions?: string[];
};

export function SuperadminLoginPage(): JSX.Element {
  const api = useApiClient();
  const { adoptAdministrativeSession } = useAuth();
  const navigate = useNavigate();
  const [stage, setStage] = useState<LoginResult | null>(null);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [qr, setQr] = useState('');
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let active = true;
    setQr('');
    if (stage?.otpauthUrl) {
      import('qrcode').then(qrcode => qrcode.toDataURL(stage.otpauthUrl!, { width: 220, margin: 2 }))
        .then(data => { if (active) setQr(data); }).catch(() => {});
    }
    return () => { active = false; };
  }, [stage?.otpauthUrl]);

  function enter(result: LoginResult): void {
    if (!result.accessToken || !result.refreshToken || !result.user) throw new Error('ورود مدیریت تکمیل نشده است.');
    adoptAdministrativeSession({ accessToken: result.accessToken, refreshToken: result.refreshToken,
      expiresIn: result.expiresIn, user: result.user, permissions: result.permissions });
    setStage(null); setPassword(''); setCode(''); setConfirmation('');
    navigate('/superadmin', { replace: true });
  }

  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault(); setError(''); setBusy(true);
    try {
      let result: LoginResult;
      if (!stage) {
        result = await api.post<LoginResult>('superadmin/auth/login', { username, password }, { retry: 0 });
      } else if (stage.step === 'password') {
        if (password !== confirmation) throw new Error('رمز جدید و تکرار آن یکسان نیست.');
        result = await api.post<LoginResult>('superadmin/auth/password', { challenge: stage.challenge, newPassword: password }, { retry: 0 });
      } else {
        result = await api.post<LoginResult>('superadmin/auth/mfa', { challenge: stage.challenge, code }, { retry: 0 });
      }
      setPassword(''); setConfirmation(''); setCode('');
      if (result.step === 'authenticated' && !result.recoveryCodes?.length) enter(result);
      else setStage(result);
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'ورود انجام نشد.'); }
    finally { setBusy(false); }
  }

  const inputStyle = { display: 'block', width: '100%', padding: '11px', margin: '8px 0 18px', border: '1px solid #d7d2c7', borderRadius: 8, boxSizing: 'border-box' as const };
  return <main dir="rtl" style={{ minHeight: '100vh', background: '#f6f4ee', display: 'grid', placeItems: 'center', padding: 24 }}>
    <section style={{ width: '100%', maxWidth: 440, padding: 30, borderRadius: 18, background: '#fffefa', boxShadow: '0 10px 35px #29382d12' }}>
      <h1 style={{ color: '#183b30' }}>ورود مدیریت کل</h1>
      <p style={{ color: '#68665f', lineHeight: 1.9 }}>این ورود از حساب روزمره جداست و همیشه به تأیید دومرحله‌ای نیاز دارد.</p>
      {error && <p role="alert" style={{ color: '#a02f21' }}>{error}</p>}
      {stage?.step === 'authenticated' ? <>
        <h2>کدهای بازیابی یک‌بارمصرف</h2>
        <p>این کدها فقط همین‌بار نمایش داده می‌شوند. آن‌ها را در جای امن و خارج از این رایانه نگه دارید؛ برای کسی ارسال نکنید.</p>
        <pre dir="ltr" style={{ padding: 14, background: '#f4f1e8', whiteSpace: 'pre-wrap' }}>{stage.recoveryCodes?.join('\n')}</pre>
        <label><input type="checkbox" checked={saved} onChange={e => setSaved(e.target.checked)} /> کدها را در جای امن ذخیره کردم.</label>
        <button style={{ ...inputStyle, marginTop: 18 }} disabled={!saved} onClick={() => enter(stage)}>ورود به سامانه</button>
      </> : <form onSubmit={submit}>
        {!stage && <>
          <label>نام کاربری مدیریت<input style={inputStyle} dir="ltr" autoComplete="username" required value={username} onChange={e => setUsername(e.target.value)} /></label>
          <label>رمز مدیریت<input style={inputStyle} dir="ltr" type="password" autoComplete="current-password" maxLength={1024} required value={password} onChange={e => setPassword(e.target.value)} /></label>
        </>}
        {stage?.step === 'password' && <>
          <p>رمز موقت را با رمز شخصی مدیریت جایگزین کنید؛ این رمز باید با رمز حساب روزمره متفاوت باشد.</p>
          <label>رمز شخصی جدید<input style={inputStyle} type="password" autoComplete="new-password" minLength={12} maxLength={1024} required value={password} onChange={e => setPassword(e.target.value)} /></label>
          <label>تکرار رمز جدید<input style={inputStyle} type="password" autoComplete="new-password" required value={confirmation} onChange={e => setConfirmation(e.target.value)} /></label>
        </>}
        {stage?.step === 'enroll' && <>
          <p>در برنامه تأییدکننده، کد زیر را اسکن کنید یا کلید را دستی وارد کنید. سپس کد شش‌رقمی را بنویسید. ساعت تلفن و سرور باید صحیح باشد.</p>
          {qr && <img src={qr} alt="کد راه‌اندازی تأیید دومرحله‌ای مدیریت" style={{ display: 'block', margin: 'auto' }} />}
          <code dir="ltr" style={{ display: 'block', overflowWrap: 'anywhere', userSelect: 'all', padding: 12 }}>{stage.secret}</code>
        </>}
        {(stage?.step === 'enroll' || stage?.step === 'mfa') && <label>کد تأیید{stage.step === 'mfa' ? ' یا کد بازیابی' : ''}<input style={inputStyle} dir="ltr" autoComplete="one-time-code" maxLength={100} required value={code} onChange={e => setCode(e.target.value)} /></label>}
        <button type="submit" disabled={busy} style={{ ...inputStyle, background: '#214d3d', color: '#fff', cursor: 'pointer' }}>{busy ? 'در حال بررسی…' : 'ادامه'}</button>
        {stage && <button type="button" disabled={busy} onClick={() => { setStage(null); setPassword(''); setConfirmation(''); setCode(''); setError(''); }}>شروع دوباره ورود</button>}
      </form>}
      <p style={{ marginTop: 20 }}><Link to="/login">بازگشت به ورود معمولی</Link></p>
    </section>
  </main>;
}
