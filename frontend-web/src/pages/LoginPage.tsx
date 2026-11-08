import { useOrganizationAppearance, useOrganizationTheme } from "../core/tenant/organizationAppearance";
import { OrganizationBrand } from "../shared/components/OrganizationBrand";
import { organizationBranding } from "../app/configuration/organizationBranding";
import { BrandLogo } from "../shared/components/BrandLogo";
import { useState, useEffect } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { runtimeConfig } from "../app/configuration/runtimeConfig";
import { FirstPasswordRequiredError, MfaRequiredError, useAuth } from "../core/auth/authContext";
import { classifyError } from "../core/errors/appErrors";
import { useLocalization } from "../core/localization/localizationContext";
import { localeMeta } from "../core/localization/i18n";
import { Button, TextInput } from "../shared/components/primitives";
import { Icon } from "../shared/components/Icon";

import { useApiClient } from "../core/api/apiContext";

export function LoginPage(): JSX.Element {
  const {organizationCode}=useParams();
  const isDemo = runtimeConfig.demoMode;
  const api = useApiClient();
  const { t, cycleLocale, locale } = useLocalization();
  const { login, completeMfa, isAuthenticated, isLoading } = useAuth();
  const navigate = useNavigate();
  const [entries, setEntries] = useState<{code:string;name:string}[]>([]);
  useEffect(() => { if (!isDemo) api.get<unknown>("organization-entry", {retry:0}).then(value => { if(Array.isArray(value)) { const valid = value.filter(v => typeof v.code === "string" && typeof v.name === "string"); setEntries(valid); if(valid.length && !organizationBranding.singleOrganization && !organizationCode) setTenantCode(current => valid.some(v => v.code === current) ? current : valid[0].code); } }).catch(() => {}); }, [api,organizationCode]);
  const singleOrganization = organizationBranding.singleOrganization && !isDemo;
  const [tenantCode, setTenantCode] = useState(organizationCode || (singleOrganization ? organizationBranding.defaultTenantCode : isDemo ? "platform" : ""));
  useEffect(()=>{if(organizationCode)setTenantCode(organizationCode);},[organizationCode]);
  const appearance = useOrganizationAppearance(tenantCode, !isDemo);
  useOrganizationTheme(appearance, !isDemo);
  const [identifier, setIdentifier] = useState(isDemo ? "platform-admin" : "");
  const [password, setPassword] = useState(isDemo ? "demo-password" : "");
  const [error, setError] = useState("");
  const [challenge, setChallenge] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [changing, setChanging] = useState(false);
  const [notice, setNotice] = useState('');
  const [mfaChallenge, setMfaChallenge] = useState('');
  const [mfaCode, setMfaCode] = useState('');
  // Off by default: staying signed in is a choice, not something that
  // happens to someone on a shared machine without them noticing.
  const [remember, setRemember] = useState(false);

  if (isAuthenticated) return <Navigate to="/app/dashboard" replace />;
  const submit = async (event: React.FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    setError("");
    try {
      await login({ tenantCode, identifier, password, remember });
      navigate("/app/dashboard", { replace: true });
    } catch (reason) {
      if (reason instanceof FirstPasswordRequiredError) {
        setPassword(''); setChallenge(reason.challenge); setNotice(''); return;
      }
      if (reason instanceof MfaRequiredError) { setPassword(''); setMfaChallenge(reason.challenge); return; }
      const classified = classifyError(reason);
      setError(
        classified.category === "authentication"
          ? t("auth.invalid")
          : classified.category === "server"
            ? t("auth.serverError")
            : classified.category === "network" || classified.category === "timeout"
              ? t("auth.networkError")
              : classified.message,
      );
    }
  };

  if (mfaChallenge) return <main className="auth-page__form" dir="rtl"><div className="auth-card"><h2>تأیید دومرحله‌ای</h2><form onSubmit={(e) => { e.preventDefault(); setError(''); void completeMfa(mfaChallenge, mfaCode, remember).then(() => navigate('/app/dashboard', { replace: true })).catch((reason: unknown) => setError(classifyError(reason).message)); }}><TextInput label="کد برنامهٔ احراز هویت یا کد بازیابی" autoComplete="one-time-code" value={mfaCode} onChange={(e) => setMfaCode(e.target.value)} required />{error && <p role="alert">{error}</p>}<Button type="submit" variant="primary" loading={isLoading} disabled={isLoading || !mfaCode.trim()}>تأیید و ورود</Button><Button disabled={isLoading} onClick={() => { setMfaChallenge(''); setMfaCode(''); setError(''); }}>بازگشت به ورود</Button></form></div></main>;
  if (challenge) return <main className="auth-page__form" dir="rtl"><div className="auth-card"><h2>انتخاب رمز شخصی</h2><p>رمز موقت فقط برای این مرحله است. رمز شخصی را به مدیر تحویل ندهید.</p><p>حداقل ۱۲ کاراکتر، حروف بزرگ و کوچک انگلیسی و یک علامت؛ متفاوت با رمز موقت و رمزهای قبلی.</p><form onSubmit={(event) => {
    event.preventDefault(); setError('');
    if (newPassword !== confirmPassword) { setError('تکرار رمز با رمز جدید یکسان نیست.'); return; }
    setChanging(true);
    void api.post('auth/password/first', { challenge, newPassword }, { retry: 0 }).then(() => {
      setChallenge(''); setNewPassword(''); setConfirmPassword(''); setNotice('رمز شخصی ذخیره شد؛ اکنون با نام کاربری و رمز جدید وارد شوید.');
    }).catch((reason: unknown) => setError(classifyError(reason).message)).finally(() => setChanging(false));
  }}><TextInput label="رمز شخصی جدید" type="password" required autoComplete="new-password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} /><TextInput label="تکرار رمز شخصی" type="password" required autoComplete="new-password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} />{error && <p role="alert">{error}</p>}<Button type="submit" variant="primary" loading={changing} disabled={changing || newPassword.length < 12 || !confirmPassword}>ذخیره رمز شخصی</Button><Button disabled={changing} onClick={() => { setChallenge(''); setNewPassword(''); setConfirmPassword(''); setError(''); }}>بازگشت به ورود</Button></form></div></main>;
  return <div className="auth-page"><div className="auth-page__visual"><div className="auth-brand"><BrandLogo large /><strong>{runtimeConfig.appName}</strong></div><div className="auth-visual__content"><span className="eyebrow">{t("auth.hero.eyebrow")}</span><h1>{t("auth.hero.title")} <em>{t("auth.hero.accent")}</em></h1><p>{t("auth.hero.body")}</p><div className="auth-visual__metrics"><div><strong>{t("auth.hero.metric1Value")}</strong><span>{t("auth.hero.metric1Label")}</span></div><div><strong>{t("auth.hero.metric2Value")}</strong><span>{t("auth.hero.metric2Label")}</span></div><div><strong>{t("auth.hero.metric3Value")}</strong><span>{t("auth.hero.metric3Label")}</span></div></div></div><div className="auth-visual__footer"><span><Icon name="shield" size={15} /> {t("auth.hero.feature1")}</span><span><Icon name="sparkles" size={15} /> {t("auth.hero.feature2")}</span></div></div><main className="auth-page__form"><div className="auth-form__top"><button type="button" className="language-button language-button--auth" onClick={cycleLocale} aria-label={t("header.language")}>{localeMeta[locale].nativeLabel}</button></div><div className="auth-card"><div className="auth-card__heading"><OrganizationBrand appearance={appearance} /><span className="auth-card__icon"><Icon name="lock" size={20} /></span><span className="eyebrow">{runtimeConfig.appName.toUpperCase()}</span><h2>{t("auth.welcome")}</h2><p>{t("auth.subtitle")}</p></div>{notice && <p role="status">{notice}</p>}<form onSubmit={submit} noValidate>{!singleOrganization && entries.length > 1 && <label>سازمان<select value={tenantCode} onChange={e => setTenantCode(e.target.value)}>{entries.map(entry => <option key={entry.code} value={entry.code}>{entry.name}</option>)}</select></label>}{!singleOrganization && entries.length <= 1 && <TextInput label={t("auth.tenantCode")} name="tenantCode" value={tenantCode} onChange={(event) => setTenantCode(event.target.value)} autoComplete="organization" required />}<TextInput label={t("auth.identifier")} name="username" value={identifier} onChange={(event) => setIdentifier(event.target.value)} autoComplete="username" required /><TextInput label={t("auth.password")} name="password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required />{error && <div className="form-alert" role="alert"><Icon name="warning" size={17} /><span>{error}</span></div>}<div className="auth-form__options"><label className="checkbox-label"><input type="checkbox" name="remember" checked={remember} onChange={(event) => setRemember(event.target.checked)} /> <span>{t("auth.remember")}</span></label></div><Button type="submit" variant="primary" size="lg" className="auth-submit" loading={isLoading} iconAfter="arrowRight">{isLoading ? t("auth.signingIn") : t("auth.signIn")}</Button></form>{isDemo && <div className="demo-callout"><Icon name="sparkles" size={16} /><span>{t("auth.demoHint")}</span></div>}<p><Link to="/superadmin/login">ورود مستقل مدیریت کل</Link></p><div className="auth-card__security"><Icon name="shield" size={16} /><span>{t("auth.secure")}</span></div></div><p className="auth-copyright">© 2026 {runtimeConfig.appName}</p></main></div>;
}
