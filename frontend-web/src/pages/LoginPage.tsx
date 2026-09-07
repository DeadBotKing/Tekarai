import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { runtimeConfig } from "../app/configuration/runtimeConfig";
import { useAuth } from "../core/auth/authContext";
import { classifyError } from "../core/errors/appErrors";
import { useLocalization } from "../core/localization/localizationContext";
import { Button, TextInput } from "../shared/components/primitives";
import { Icon } from "../shared/components/Icon";

export function LoginPage(): JSX.Element {
  const { t, cycleLocale, locale } = useLocalization();
  const { login, isAuthenticated, isLoading } = useAuth();
  const navigate = useNavigate();
  const [tenantCode, setTenantCode] = useState(runtimeConfig.demoMode ? "platform" : "");
  const [identifier, setIdentifier] = useState(runtimeConfig.demoMode ? "platform-admin" : "");
  const [password, setPassword] = useState(runtimeConfig.demoMode ? "demo-password" : "");
  const [error, setError] = useState("");

  if (isAuthenticated) return <Navigate to="/app/dashboard" replace />;
  const submit = async (event: React.FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    setError("");
    try {
      await login({ tenantCode, identifier, password });
      navigate("/app/dashboard", { replace: true });
    } catch (reason) {
      const classified = classifyError(reason);
      setError(classified.category === "authentication" ? t("auth.invalid") : classified.message);
    }
  };

  return <div className="auth-page"><div className="auth-page__visual"><div className="auth-brand"><span className="brand-mark brand-mark--large">T</span><strong>{runtimeConfig.appName}</strong></div><div className="auth-visual__content"><span className="eyebrow">APPLICATION INTERFACE PLATFORM</span><h1>Make the complex feel <em>clear.</em></h1><p>One secure, configurable workspace for projects, people, documents and intelligence.</p><div className="auth-visual__metrics"><div><strong>12</strong><span>connected domains</span></div><div><strong>24/7</strong><span>operational visibility</span></div><div><strong>1</strong><span>trusted context</span></div></div></div><div className="auth-visual__footer"><span><Icon name="shield" size={15} /> Tenant-isolated by design</span><span><Icon name="sparkles" size={15} /> Intelligence-ready</span></div></div><main className="auth-page__form"><div className="auth-form__top"><button type="button" className="language-button language-button--auth" onClick={cycleLocale} aria-label={t("header.language")}>{locale.toUpperCase()}</button></div><div className="auth-card"><div className="auth-card__heading"><span className="auth-card__icon"><Icon name="lock" size={20} /></span><span className="eyebrow">{runtimeConfig.appName.toUpperCase()}</span><h2>{t("auth.welcome")}</h2><p>{t("auth.subtitle")}</p></div><form onSubmit={submit} noValidate><TextInput label={t("auth.tenantCode")} value={tenantCode} onChange={(event) => setTenantCode(event.target.value)} autoComplete="organization" required /><TextInput label={t("auth.identifier")} value={identifier} onChange={(event) => setIdentifier(event.target.value)} autoComplete="username" required /><TextInput label={t("auth.password")} type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required />{error && <div className="form-alert" role="alert"><Icon name="warning" size={17} /><span>{error}</span></div>}<div className="auth-form__options"><label className="checkbox-label"><input type="checkbox" defaultChecked /> <span>{t("auth.remember")}</span></label><a href="#forgot">{t("auth.forgot")}</a></div><Button type="submit" variant="primary" size="lg" className="auth-submit" loading={isLoading} iconAfter="arrowRight">{isLoading ? t("auth.signingIn") : t("auth.signIn")}</Button></form>{runtimeConfig.demoMode && <div className="demo-callout"><Icon name="sparkles" size={16} /><span>{t("auth.demoHint")}</span></div>}<div className="auth-card__security"><Icon name="shield" size={16} /><span>{t("auth.secure")}</span></div></div><p className="auth-copyright">© 2026 {runtimeConfig.appName} · <a href="#privacy">{t("footer.privacy")}</a></p></main></div>;
}
