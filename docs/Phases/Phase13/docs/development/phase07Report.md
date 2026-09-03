# Phase 07 Report — Identity, Authentication & Authorization (هویت، احراز هویت و مجوزدهی)

> محدوده: `docs/Phases/Phase7.md` §1–§43 — معماری هویت در سطح سازمانی، چند-مستأجری (multi-tenant)، با افق ۵ تا ۱۰ سال.
> Baseline ورود: commit `21d3b42` (فاز ۶، ۲۳۵ تست سبز). خروجی فاز ۷: **۳۱۱ تست سبز** / ruff clean / mypy clean (۱۸۷ فایل) / بدون migration drift.

---

## 1. خلاصه

فاز ۷ لایه هویت Tekarai را از «کاربر + توکن مات» به یک **بدنه کامل Identity & Access** ارتقا داد:

- **User ≠ Employee** (§2): موجودیت User یک رکورد هویتی است (`kind: human | service`)، نه رکورد پرسنلی.
- **چرخه حیات ۸ حالته** (§3) با گذارهای صریح و LOCKED/EXPIRED به‌صورت overlay زمانی.
- **Credentials جدا از User** (§5) با ۸ نوع credential؛ توکن‌های verification/reset تک‌مصرف، زمان‌دار و شمارش تلاش.
- **JWT + Refresh** (§7/§8، ADR-022): access کوتاه‌عمر HS256 (stdlib، بدون وابستگی) + refresh مات چرخشی (hash روی ردیف session). JWT هرگز سازوکار یکتای session نیست — هر درخواست، ردیف Session را بازبینی می‌کند.
- **RBAC کامل** (§14–§17) + **مجوزدهی دومرحله‌ای** permission + resource policy (§18/§19) + **کش مجوزدهی با invalidation سخت** (§28).
- **Service Account و API Key** (§21/§22) برای agentها/integrationها/AI — کلید فقط hash شده ذخیره می‌شود، raw دقیقاً یک‌بار نمایش می‌یابد.
- **Password policy قابل تنظیم** (§23)، **MFA (TOTP + recovery codes)** (§24)، **recovery توکنی** (§25)، **verify ایمیل/تلفن** (§26)، **security events** (§27).

---

## 2. خروجی‌های الزامی (§40) — ۲۹ مورد، همه ✔

| # | خروجی §40 | کجا پیاده شد | ✔ |
|---|---|---|---|
| 1 | User Identity Architecture | `domain/entities/user.py` (kind, identifier, 8-state) | ✔ |
| 2 | Account Lifecycle | `domain/valueObjects/userState.py` (state machine + overlays) | ✔ |
| 3 | Credential Architecture | `domain/entities/credential.py` (PasswordHistory/VerificationToken/PasswordResetToken) | ✔ |
| 4 | Authentication Architecture | `application/useCases/sessionUseCases.py` (§10: credential+status+tenant+ratelimit+lock+audit+session) | ✔ |
| 5 | JWT Architecture | `infrastructure/services/jwtService.py` + `ports.TokenIssuer` (ADR-022) | ✔ |
| 6 | Refresh Token Architecture | `Session.start/rotateRefreshToken` — rotation روی همان ردیف، hash-only | ✔ |
| 7 | Session Management | فیلدهای کامل §9 + list/revoke/logout-all (`/me/sessions`) | ✔ |
| 8 | Tenant Membership | `domain/entities/tenantMembership.py` (active/suspended/removed، isPrimary، defaultRole) | ✔ |
| 9 | RBAC | Role/Permission/RolePermission/UserRole + `roleUseCases.py` | ✔ |
| 10 | Permission System | `resource.<action>` مستقل از role؛ `UserPermission` (allow/deny) | ✔ |
| 11 | Role Scope | SYSTEM/GLOBAL/TENANT/ORGANIZATION/DEPARTMENT/PROJECT/RESOURCE | ✔ |
| 12 | Resource Authorization | `domain/policies/resourcePolicies.py` (Protocol + POLICIES registry) | ✔ |
| 13 | Policy Architecture | دو‌مرحله‌ای: permission gate → resource policy؛ هرگز در view (§19) | ✔ |
| 14 | Service Account Architecture | `domain/entities/serviceAccount.py` + use cases + endpoints | ✔ |
| 15 | API Key Architecture | prefix `tek_`، SHA-256، scopes، expiry، audit، X-API-Key authenticator | ✔ |
| 16 | Password Policy | `validatePasswordStrength` + `PASSWORD_POLICY` در settings (بدون الزام انقضا §23) | ✔ |
| 17 | MFA Architecture | `totpService.py` (RFC 6238 خالص) + MfaFactor/RecoveryCode + setup/confirm/disable | ✔ |
| 18 | Recovery Architecture | recovery codes هش‌شده تک‌مصرف (§24) + reset token (§25) | ✔ |
| 19 | Verification Architecture | کانال email/phone جدا از reset (§26)، attempt-cap | ✔ |
| 20 | Security Event Architecture | `SecurityEventModel` + `SecurityEventRecorderDjango` (واژگان §27) | ✔ |
| 21 | Authorization Cache Strategy | `authorizationCache.py` — TTL 60s + version bump (§28، §35.9) | ✔ |
| 22 | Identity Domain Events | userRegistered/userActivated/userSuspended/userDisabled/accountLocked/sessionCreated/sessionRevoked/apiKeyCreated/apiKeyRevoked/mfaEnabled/mfaDisabled/… | ✔ |
| 23 | Identity Use Cases | ۲۹ use case فاز ۷ در container (§31) — HTTP-free | ✔ |
| 24 | Identity API | ۲۵ مسیر جدید §32 در `identityRoutes.py` + OpenAPI specs | ✔ |
| 25 | Security Invariants | ۱۰ نامعادله §35 در domain/use case/verifier ها enforce شده | ✔ |
| 26 | Identity Tests | unit (25) + application (16) فاز ۷ | ✔ |
| 27 | Tenant Isolation Tests | S2/S9 ماتریس §37 + گاردهای معماری | ✔ |
| 28 | Security Tests | ماتریس ۱۰ سناریویی §37 (integration) + lifecycle توکن | ✔ |
| 29 | Identity Documentation | همین گزارش + ADR-022 + به‌روزرسانی runningAndTesting/api docs | ✔ |

---

## 3. Definition of Done (§41) — ۲۰ مورد، همه ✔

1. **User از Employee جدا** ✔ — `kind: human|service`؛ هیچ فیلد پرسنلی در User نیست (§2).
2. **عضویت چند-مستأجری** ✔ — `TenantMembership` جدا؛ کاربر فعال در A و suspended در B (تست S9).
3. **Tenant Membership مستقل** ✔ — aggregate با state machine خودش (removed ترمینال).
4. **AuthN جدا از AuthZ** ✔ — `AuthenticateUserUseCase.requiredAction == ""`؛ گارد معماری §20/§16.
5. **JWT + Refresh** ✔ — ADR-022؛ DoD فاز ۷ صریحاً فرمت ADR-019 را supersede می‌کند (مدل rotation/revocation حفظ شد).
6. **Session قابل مدیریت** ✔ — ۹ فیلد §9 + list/revoke per-session/logout-all + علامت session جاری.
7. **RBAC** ✔ — CRUD نقش + assign/remove با audit و event.
8. **Permission مستقل از Role** ✔ — جدول Permission با کد پایدار؛ grant مستقیم روی کاربر.
9. **Resource Authorization** ✔ — policy دومرحله‌ای در use case ها (نه view).
10. **Service Account** ✔ — create/disable/enable + کلید با ownerType=serviceAccount.
11. **API Key امن و قابل Revocation** ✔ — hash-only، revoke آنی (تست S10)، expiry (S8).
12. **MFA-ready** ✔ — TOTP فعال + challenge flow کامل + پیکربندی per system/tenant/user (`MFA_POLICY`).
13. **Password Recovery امن** ✔ — توکن hash، TTL 30m، تک‌مصرف، بدون account-enumeration، revoke همه sessionها.
14. **Security Eventها Audit** ✔ — هر عملیات امنیتی هم SecurityEvent می‌نویسد هم AuditEvent.
15. **Tenant Isolation چندلایه** ✔ — دامنه (scope در repo) + اپلیکیشن (GLOBAL gate) + infra (unique constraints) + تست.
16. **Permission Escalation تست** ✔ — member بدون `role.create` → 403؛ delete نقش تخصیص‌یافته → Conflict؛ never-disable-self policy.
17. **Token Revocation تست** ✔ — S6 (session)، replay refresh، S10 (API key)، logout-all.
18. **Use Caseها HTTP-free** ✔ — گارد معماری؛ فقط command/query می‌گیرند.
19. **Domain بدون Django** ✔ — گارد معماری `testDomainNeverImportsDjangoOrInfrastructure`.
20. **هیچ Secret خام در DB/Log** ✔ — keyHash/secretRef(Signer)/hash refresh و recovery؛ گاردهای `SecretHygieneTests`.

---

## 4. ماتریس امنیتی §37 — ۱۰ سناریو (همه سبز)

| سناریو | تست | نتیجه |
|---|---|---|
| A→A مجاز | S1 | 200 |
| A→B ممنوع | S2 (کاربر tenant B، درخواست tenant A) | 403 `PERM_PERMISSION_DENIED` |
| بدون permission ممنوع | S3 | 403 |
| نقش revoked → آنی | S4 (bump §28) | 403 |
| کاربر disabled → لاگین ممنوع | S5 | 401 `AUTH_AUTHENTICATION_REQUIRED` |
| session revoked → آنی | S6 | 401 |
| توکن منقضی ممنوع | S7 | 401 `AUTH_TOKEN_EXPIRED` |
| API key منقضی ممنوع | S8 | 401 |
| عضویت suspended | S9 | 403 `TENANT_ACCESS_DENIED` |
| API key revoked ممنوع | S10 | 401 |

---

## 5. API جدید (§32) — ۲۵ مسیر، همه versioned زیر `/api/v1`

```
POST   auth/login                      → JWT + refresh (یا mfaRequired + challenge)
POST   auth/mfa/challenge              → تکمیل ورود دومرحله‌ای
POST   auth/refresh                    → چرخش refresh + JWT جدید
POST   auth/logout                     → revoke session
POST   auth/password/change            → تغییر رمز (policy+history، revoke sessions)
POST   auth/password/reset/request     → درخواست توکن (بدون enumeration)
POST   auth/password/reset/confirm     → مصرف تک‌مصرف توکن
POST   auth/verification/send          → صدور توکن email/phone
POST   auth/verify-email | verify-phone
GET    roles | POST roles
PATCH  roles/{roleId} | DELETE roles/{roleId}
POST   users/{userId}/roles | DELETE users/{userId}/roles
GET    api-keys | POST api-keys | DELETE api-keys/{apiKeyId}
GET    service-accounts | POST service-accounts
POST   service-accounts/{accountId}    → disable/enable
POST   me/mfa/setup | me/mfa/confirm | me/mfa/disable
GET    me/sessions | DELETE me/sessions/{sessionId}
POST   me/sessions/revoke-all
```

احراز هویت سر-به-سر: هدر **`X-API-Key`** (اول در زنجیره DRF) کنار `Authorization: Bearer <JWT>`.

---

## 6. مدل داده و Migration

- `infrastructure/models.py`: **۱۷ مدل** — جدید: PasswordHistory، VerificationToken، PasswordResetToken، MfaFactor، RecoveryCode، ApiKey، ServiceAccount، SecurityEvent؛ گسترش: User (kind/failedLoginCount/lockedUntil/expiresAt/phone)، Session (refreshTokenHash unique، ip/ua/device)، TenantMembership (status/isPrimary/defaultRole)، Role (isActive + UQ scopeType+code)، UserRole (scopeRef)، UserPermission.
- Migration `0002_phase7_identity`: ساخت ۸ جدول جدید، حذف `Session.tokenHash`، افزودن `refreshTokenHash` (با backfill امن برای ردیف‌های legacy و سپس unique §34)، قیدهای یکتای §34 و ایندکس‌های SecurityEvent.
- `bootstrapPlatform`: حالا عضویت ACTIVE برای platform-admin می‌سازد (لاگین §12 بدون آن 403 می‌شود).

## 7. پیکربندی (settings + env)

`JWT_AUTH` (jwtSigningKey/jwtIssuer/jwtAudience/jwtAccessTtlMinutes/jwtChallengeTtlMinutes)، `PASSWORD_POLICY` (minLength=12, complexity, history=5, lock 5×15m، انقضا الزامی نیست)، `MFA_POLICY`، `VERIFICATION_POLICY` — همه با پیش‌فرض امن و قابل override از `.env` (نمونه‌ها در `.env.example`).

## 8. تست‌ها — ۳۱۱ (۲۳۵ فاز ۶ + ۷۶ فاز ۷)

- **unit/testPhase7Domain.py (25):** state machineها (user/membership/serviceAccount/session/mfa/apiKey)، overlay های LOCKED/EXPIRED، password policy، TOTP (drift/tamper/otpauth)، resource policies (self/GLOBAL/never-self/own-session)، JWT (round-trip، امضای دستکاری‌شده، انقضا، audience، نوع توکن).
- **application/testPhase7UseCases.py (16):** لاگین با username/email، قفل brute-force با ثبت ACCOUNT_LOCKED **بیرون از تراکنش** (rollback-safe)، MFA challenge + recovery code، list/revoke session، تغییر رمز (reuse/wrong-current/revoke-all)، reset تک‌مصرف + بدون enumeration، CRUD نقش + grant/revoke آنی (§28)، delete نقش تخصیص‌یافته، API key create/verify/revoke (hash-only)، service account disable/enable + کلید غیرفعال، bump کش.
- **integration/testPhase7ApiContract.py (25):** ماتریس §37 (۱۰)، چرخه توکن (rotation/replay/tamper)، API key auth، نمایش تک‌باری raw key، تغییر رمز، reset endpoints، نقش‌ها با permission، sessions خودخدمتی، MFA end-to-end، service accounts، verification، لاگین با email و رد فیلد legacy.
- **architecture/testPhase7Architecture.py (12):** application بدون Django/DRF، domain خالص، JWT نه سازوکار یکتا (بازبینی ردیف session در سورس)، بهداشت secretها، versioning مسیرها، inventory کامل ۲۹ use case.

## 9. تصمیم‌ها

- **ADR-022**: JWT درون‌سازمانی HS256 با stdlib به‌جای PyJWT/SimpleJWT — سطح امنیتی کوچک و قابل ممیزی، بدون وابستگی؛ الگوریتم در پورت `TokenIssuer` کپسوله شده و ارتقا به RS256 بعداً یک‌تغییر زیرساختی است.
- **شمارنده brute-force بیرون از تراکنش**: شکست لاگین تراکنش را rollback می‌کند؛ شمارش/قفل/رویدادهای امنیتی بعد از rollback ثبت می‌شوند تا §10 با §9 (تمامیت تراکنش) تعارض نداشته باشد.
- **کش مجوزدهی**: TTL کوتاه (60s) + version stamp per user — revoke نقش با bump نسخه آنی می‌شود؛ backend کش قابل تعویض (LocMem → Redis) بدون تغییر فراخوان‌ها.

## 10. اجرا روی ویندوز (خلاصه runbook)

```powershell
Set-Location C:\Users\Mitra\Desktop\Tekarai\backend
.\venv\Scripts\Activate.ps1
python manage.py migrate                      # 0002_phase7_identity اعمال می‌شود
$env:PLATFORM_ADMIN_PASSWORD="Tekarai-Admin-2026!"
python manage.py bootstrapPlatform
python manage.py runserver
# تست:
python manage.py test --settings=config.settings.testing
```

> **توجه فاز ۷:** پاسخ login حالا `accessToken` + `refreshToken` دارد (فیلد `token` قبلی حذف شد)؛ refresh/logout بدنه‌ی `{"refreshToken": "…"}` می‌گیرند. توصیه: `jwtSigningKey` اختصاصی در `.env`.

## 11. مانده برای فازهای بعد (خارج از scope فاز ۷)

- ارسال واقعی ایمیل/پیامک (ادغام out-of-band provider) — اکنون توکن خام فقط در پاسخ dev/test برمی‌گردد.
- WebAuthn به‌عنوان factor جدید کنار TOTP (معماری §24 آماده است).
- SSO/OIDC به‌عنوان credential type خارجی (`externalIdentity` از قبل در ثابت‌های credential هست).
