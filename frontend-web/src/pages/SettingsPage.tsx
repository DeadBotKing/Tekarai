import { useEffect, useMemo, useState } from "react";
import { useLocalization } from "../core/localization/localizationContext";
import { useTheme } from "../core/theme/themeContext";
import { useTenant } from "../core/tenant/tenantContext";
import { useApiClient } from "../core/api/apiContext";
import { useAuth } from "../core/auth/authContext";
import type { UserSession } from "../core/auth/sessionStore";
import { createSecurityService, type ApiKeyRecord, type MfaSetup, type SessionRecord } from "../features/security/securityService";
import { Card, CardHeader, Button, SelectInput, TextInput, Badge, SectionHeader } from "../shared/components/primitives";
import { Icon } from "../shared/components/Icon";
import { Toast } from "../shared/components/overlays";

export function SettingsPage(): JSX.Element {
  const { t, locale, setLocale } = useLocalization();
  const { theme, setTheme } = useTheme();
  const { selectedTenant } = useTenant();
  const { session } = useAuth();
  const api = useApiClient();
  const security = useMemo(() => createSecurityService(api), [api]);
  const identity = session?.user as (UserSession & { tenantId?: string }) | undefined;
  const tenantId = identity?.tenantId ?? "";
  const [saved, setSaved] = useState(false);
  const [keys, setKeys] = useState<ApiKeyRecord[]>([]);
  const [sessions, setSessions] = useState<SessionRecord[]>([]);
  const [keyName, setKeyName] = useState("Tekarai integration");
  const [newRawKey, setNewRawKey] = useState("");
  const [mfaSetup, setMfaSetup] = useState<MfaSetup | null>(null);
  const [mfaCode, setMfaCode] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!session || !tenantId) { setLoading(false); return; }
    void Promise.all([security.listApiKeys(tenantId, session.user.id), security.listSessions()])
      .then(([nextKeys, nextSessions]) => { setKeys(nextKeys); setSessions(nextSessions); })
      .catch(() => setMessage("Security data could not be loaded."))
      .finally(() => setLoading(false));
  }, [security, session, tenantId]);

  const createKey = async (): Promise<void> => {
    if (!session || !tenantId || !keyName.trim()) return;
    try {
      const created = await security.createApiKey(tenantId, keyName.trim(), session.user.id);
      setKeys((current) => [created.apiKey, ...current]);
      setNewRawKey(created.rawKey);
      setMessage("API key created. Copy it now; it will not be shown again.");
    } catch { setMessage("API key could not be created."); }
  };

  const revokeKey = async (id: string): Promise<void> => {
    try { await security.revokeApiKey(id); setKeys((current) => current.map((key) => key.id === id ? { ...key, revokedAt: new Date().toISOString() } : key)); setMessage("API key revoked."); }
    catch { setMessage("API key could not be revoked."); }
  };

  const beginMfa = async (): Promise<void> => {
    try { setMfaSetup(await security.setupMfa()); setMessage("Scan the TOTP URL or enter the secret in your authenticator app."); }
    catch { setMessage("MFA setup could not be started. It may already be enabled."); }
  };

  const confirmMfa = async (): Promise<void> => {
    if (!mfaSetup || !mfaCode.trim()) return;
    try { const result = await security.confirmMfa(mfaSetup.factorId, mfaCode.trim()); setMfaSetup(null); setMfaCode(""); setMessage(`MFA enabled. Save these recovery codes: ${result.recoveryCodes.join(", ")}`); }
    catch { setMessage("The MFA code was rejected."); }
  };

  const revokeAll = async (): Promise<void> => {
    if (!session) return;
    try { await security.revokeAllSessions(session.user.id); setMessage("All other sessions were revoked."); }
    catch { setMessage("Sessions could not be revoked."); }
  };

  return <div className="page">
    <SectionHeader eyebrow={t("nav.account")} title={t("nav.settings")} subtitle="Manage your real account, authentication factors, credentials and browser preferences." actions={<Button variant="primary" icon="check" onClick={() => setSaved(true)}>{t("common.save")}</Button>} />
    <div className="settings-grid">
      <Card padding="md"><CardHeader title="Profile" subtitle="Identity is read from the authenticated backend session." /><div className="workspace-context"><span className="workspace-context__icon"><Icon name="users" size={22} /></span><div><strong>{session?.user.displayName ?? "—"}</strong><p>{session?.user.email ?? "—"}</p><p>{session?.user.role ?? "—"}</p></div><Badge tone="success" dot>Authenticated</Badge></div></Card>
      <Card padding="md"><CardHeader title="Appearance" subtitle="These preferences are local to this browser." /><div className="settings-form"><div className="setting-row"><div><strong>Theme</strong><span>Choose a light or dark workspace.</span></div><div className="theme-switcher"><button type="button" className={theme === "light" ? "is-active" : ""} onClick={() => setTheme("light")}><Icon name="sun" size={16} />Light</button><button type="button" className={theme === "dark" ? "is-active" : ""} onClick={() => setTheme("dark")}><Icon name="moon" size={16} />Dark</button></div></div><div className="setting-row"><div><strong>Language</strong><span>Layout direction follows the selected locale.</span></div><SelectInput aria-label={t("header.language")} value={locale} onChange={(event) => setLocale(event.target.value as "en" | "fa" | "de")} options={[{ value: "en", label: "English · LTR" }, { value: "fa", label: "فارسی · RTL" }, { value: "de", label: "Deutsch · LTR" }]} /></div></div></Card>
      <Card padding="md"><CardHeader title="Multi-factor authentication" subtitle="TOTP setup is confirmed by the real identity API." action={<Badge tone="success">TOTP</Badge>} />{mfaSetup ? <div className="settings-form"><p>Secret: <code>{mfaSetup.secret}</code></p><p>Authenticator URL: <code>{mfaSetup.otpauthUrl}</code></p><TextInput label="6-digit authenticator code" value={mfaCode} onChange={(event) => setMfaCode(event.target.value)} /><Button variant="primary" onClick={() => void confirmMfa()}>Confirm MFA</Button></div> : <Button variant="secondary" icon="shield" onClick={() => void beginMfa()}>Start MFA setup</Button>}</Card>
      <Card padding="md"><CardHeader title="API keys" subtitle="Raw secrets are returned once and are never stored in the browser." action={<Button variant="secondary" size="sm" onClick={() => void createKey()}>Create key</Button>} /><TextInput label="Key name" value={keyName} onChange={(event) => setKeyName(event.target.value)} /><div className="role-list">{newRawKey && <div className="context-security"><Icon name="lock" size={17} /><code>{newRawKey}</code></div>}{loading ? <p>Loading keys…</p> : keys.length === 0 ? <p>No API keys.</p> : keys.map((key) => <div className="role-row" key={key.id}><span className="role-row__icon"><Icon name="key" size={17} /></span><div><strong>{key.name}</strong><span>{key.prefix} · {key.revokedAt ? "revoked" : "active"}</span></div>{!key.revokedAt && <Button variant="ghost" size="sm" onClick={() => void revokeKey(key.id)}>Revoke</Button>}</div>)}</div></Card>
      <Card padding="md"><CardHeader title="Sessions" subtitle="Review and revoke active browser sessions." action={<Button variant="secondary" size="sm" onClick={() => void revokeAll()}>Revoke other sessions</Button>} />{sessions.length === 0 ? <p>No session data.</p> : sessions.map((item) => <div className="role-row" key={item.id}><span className="role-row__icon"><Icon name="lock" size={17} /></span><div><strong>{item.device || "Browser session"}</strong><span>{item.current ? "Current session" : item.status} · {item.lastActivityAt}</span></div></div>)}</Card>
      <Card padding="md"><CardHeader title="Workspace context" subtitle="Every request is scoped to this tenant." /><div className="workspace-context"><span className="workspace-context__icon"><Icon name="building" size={22} /></span><div><span className="eyebrow">{t("header.tenant")}</span><h2>{selectedTenant.name}</h2><p>{selectedTenant.industry} · {selectedTenant.plan}</p></div><Badge tone="success" dot>{t("common.status.active")}</Badge></div></Card>
    </div>{(saved || message) && <Toast message={message || t("common.save")} onClose={() => { setSaved(false); setMessage(""); }} />}</div>;
}
