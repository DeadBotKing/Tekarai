import { useEffect, useMemo, useState } from "react";
import { runtimeConfig } from "../app/configuration/runtimeConfig";
import { useApiClient } from "../core/api/apiContext";
import { useLocalization } from "../core/localization/localizationContext";
import { DataTable, type DataTableColumn } from "../shared/components/DataTable";
import { createSecurityService, type SessionRecord, type UserAccount, type MfaSetupResult } from "../features/security/securityService";
import { Toast } from "../shared/components/overlays";
import { Badge, Button, Card, CardHeader, SectionHeader, TextInput } from "../shared/components/primitives";

export function AccountPage(): JSX.Element {
  const { t } = useLocalization();
  const api = useApiClient();
  const service = useMemo(() => createSecurityService(api), [api]);

  const [me, setMe] = useState<UserAccount | null>(null);
  const [sessions, setSessions] = useState<SessionRecord[]>([]);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [repeatPassword, setRepeatPassword] = useState("");
  const [mfaSetup, setMfaSetup] = useState<MfaSetupResult | null>(null);
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [mfaCode, setMfaCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState("");
  const fail = (key: Parameters<typeof t>[0]) => setToast(t(key));

  const refreshSessions = (): void => {
    if (runtimeConfig.demoMode) return;
    service.listSessions().then(setSessions).catch(() => fail("admin.loadFailed"));
  };
  useEffect(() => {
    if (runtimeConfig.demoMode) {
      setMe({ id: "demo", tenantId: "demo", username: "demo.admin", email: "demo@tekarai.local", displayName: "راهبر نمایشی", status: "active", createdAt: "" });
      return;
    }
    service.me().then((account) => setMe(account.user)).catch(() => fail("admin.loadFailed"));
    refreshSessions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const changePassword = (): void => {
    if (newPassword !== repeatPassword) { fail("account.passwordMismatch"); return; }
    if (newPassword.length < 12) { fail("account.passwordShort"); return; }
    setBusy(true);
    service.changePassword(currentPassword, newPassword)
      .then(() => { setToast(t("account.passwordChanged")); setCurrentPassword(""); setNewPassword(""); setRepeatPassword(""); })
      .catch(() => fail("account.passwordFailed"))
      .finally(() => setBusy(false));
  };

  const startMfa = (): void => {
    setBusy(true);
    service.setupMfa()
      .then(setMfaSetup)
      .catch(() => fail("account.mfaFailed"))
      .finally(() => setBusy(false));
  };

  const confirmMfa = (): void => {
    if (!mfaSetup) return;
    setBusy(true);
    service.confirmMfa(mfaSetup.factorId, mfaCode.trim())
      .then((result) => { setRecoveryCodes(result.recoveryCodes); setMfaSetup(null); setMfaCode(""); setToast(t("account.mfaEnabled")); })
      .catch(() => fail("account.mfaFailed"))
      .finally(() => setBusy(false));
  };

  const revokeAll = (): void => {
    setBusy(true);
    service.revokeAllSessions()
      .then(() => { setToast(t("account.revoked")); refreshSessions(); })
      .catch(() => fail("admin.loadFailed"))
      .finally(() => setBusy(false));
  };

  const sessionColumns = useMemo<DataTableColumn<SessionRecord>[]>(() => [
    { key: "device", label: t("account.sessionDevice"), accessor: (row) => `${row.device || "—"} ${row.userAgent || ""}`.trim(), sortable: true, render: (row) => <span>{row.device || row.userAgent || "—"} {row.current && <Badge tone="success" dot>{t("account.currentSession")}</Badge>}</span> },
    { key: "ip", label: t("account.sessionIp"), accessor: (row) => row.ipAddress, sortable: true },
    { key: "last", label: t("account.sessionLastActive"), accessor: (row) => row.lastActivityAt, sortable: true, render: (row) => <span>{new Date(row.lastActivityAt).toLocaleString()}</span> },
    { key: "action", label: "", hideable: false, render: (row) => row.current ? null : <Button variant="ghost" size="sm" icon="close" onClick={() => { service.revokeSession(row.id).then(() => { setToast(t("account.revoked")); refreshSessions(); }).catch(() => fail("admin.loadFailed")); }}>{t("account.revoke")}</Button> },
  // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [t]);

  return <div className="page">
    <SectionHeader eyebrow={t("nav.account")} title={t("account.title")} subtitle={t("account.subtitle")} />
    <div className="admin-content">
      <Card padding="md"><CardHeader title={t("account.profile")} />
        <div className="form-grid">
          <TextInput label={t("account.username")} value={me?.username ?? ""} readOnly />
          <TextInput label={t("account.displayName")} value={me?.displayName ?? ""} readOnly />
          <TextInput label={t("account.email")} value={me?.email ?? ""} readOnly />
          <TextInput label={t("account.status")} value={me?.status ?? ""} readOnly />
        </div>
      </Card>
      <Card padding="md"><CardHeader title={t("account.password")} />
        <div className="form-grid">
          <TextInput label={t("account.currentPassword")} type="password" required value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} />
          <TextInput label={t("account.newPassword")} type="password" required value={newPassword} onChange={(event) => setNewPassword(event.target.value)} />
          <TextInput label={t("account.repeatPassword")} type="password" required value={repeatPassword} onChange={(event) => setRepeatPassword(event.target.value)} />
        </div>
        <Button variant="primary" disabled={busy || !currentPassword || !newPassword} onClick={changePassword}>{t("common.save")}</Button>
      </Card>
      <Card padding="md"><CardHeader title={t("account.sessions")} action={<Button variant="secondary" size="sm" icon="close" onClick={revokeAll}>{t("account.revokeAll")}</Button>} />
        <DataTable columns={sessionColumns} data={sessions} rowKey={(row) => row.id} search="" empty={{ title: t("common.loading") }} />
      </Card>
      <Card padding="md"><CardHeader title={t("account.mfa")} />
        {!mfaSetup && recoveryCodes.length === 0 && <>
          <Button variant="primary" disabled={busy} onClick={startMfa}>{t("account.mfaStart")}</Button>
          <Button variant="ghost" onClick={() => service.disableMfa().then(() => setToast(t("account.revoked"))).catch(() => fail("account.mfaFailed"))}>{t("account.mfaDisable")}</Button>
        </>}
        {mfaSetup && <div className="form-grid">
          <p>{t("account.mfaSecretHint")}</p>
          <code dir="ltr">{mfaSetup.secret}</code>
          <p className="muted-cell" dir="ltr">{mfaSetup.otpauthUrl}</p>
          <TextInput label={t("account.mfaCode")} required inputMode="numeric" value={mfaCode} onChange={(event) => setMfaCode(event.target.value)} />
          <Button variant="primary" disabled={busy || mfaCode.trim().length < 6} onClick={confirmMfa}>{t("account.mfaConfirm")}</Button>
        </div>}
        {recoveryCodes.length > 0 && <div className="form-grid">
          <p>{t("account.mfaEnabled")}</p>
          {recoveryCodes.map((code) => <code key={code} dir="ltr">{code}</code>)}
          <Button variant="secondary" onClick={() => setRecoveryCodes([])}>{t("common.close")}</Button>
        </div>}
      </Card>
    </div>
    {toast && <Toast message={toast} onClose={() => setToast("")} />}
  </div>;
}
