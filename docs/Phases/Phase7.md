╔══════════════════════════════════════════════════════════════════════════════╗

║                              TEKARAI — PHASE 07                              ║

║                  IDENTITY, AUTHENTICATION \& AUTHORIZATION                   ║

╚══════════════════════════════════════════════════════════════════════════════╝



هدف فاز:



ساخت کامل زیرساخت هویت و دسترسی Tekarai به‌صورت Enterprise Grade،

Multi-Tenant، Secure و قابل توسعه برای 5 تا 10 سال آینده.



در پایان این فاز باید Tekarai بداند:



\- چه کسی وارد سیستم شده است.

\- این شخص متعلق به کدام Tenant است.

\- چه هویتی دارد.

\- چه Roleهایی دارد.

\- چه Permissionهایی دارد.

\- به چه Resourceهایی دسترسی دارد.

\- از چه Scopeهایی می‌تواند استفاده کند.

\- چه Sessionها و Tokenهایی فعال هستند.

\- چه عملیات امنیتی انجام داده است.

\- آیا حساب او فعال، مسدود، تعلیق یا منقضی شده است.

\- آیا دسترسی او در سطح Tenant، Organization، Department یا Resource محدود شده است.



──────────────────────────────────────────────────────────────────────────────

1\. جایگاه Identity در معماری

──────────────────────────────────────────────────────────────────────────────



Identity یکی از Core Bounded Contextهای Tekarai است.



Identity نباید صرفاً یک Django App ساده برای Login باشد.



Identity مسئول:



User Identity

Authentication

Authorization

Roles

Permissions

Sessions

Credentials

Security Policies

Access Control

Service Accounts

API Credentials

Identity Audit



است.





ساختار مفهومی:



&#x20;                   ┌─────────────────────┐

&#x20;                   │       Client        │

&#x20;                   └──────────┬──────────┘

&#x20;                              │

&#x20;                   ┌──────────▼──────────┐

&#x20;                   │ Authentication      │

&#x20;                   │ Login / Token       │

&#x20;                   └──────────┬──────────┘

&#x20;                              │

&#x20;                   ┌──────────▼──────────┐

&#x20;                   │ Identity            │

&#x20;                   │ User / Account      │

&#x20;                   └──────────┬──────────┘

&#x20;                              │

&#x20;                   ┌──────────▼──────────┐

&#x20;                   │ Authorization       │

&#x20;                   │ Role / Permission   │

&#x20;                   └──────────┬──────────┘

&#x20;                              │

&#x20;                   ┌──────────▼──────────┐

&#x20;                   │ Policy Evaluation   │

&#x20;                   └──────────┬──────────┘

&#x20;                              │

&#x20;                   ┌──────────▼──────────┐

&#x20;                   │ Resource Access     │

&#x20;                   └─────────────────────┘





──────────────────────────────────────────────────────────────────────────────

2\. Identity ≠ Employee

──────────────────────────────────────────────────────────────────────────────



یکی از مهم‌ترین تصمیم‌های معماری:



User با Employee یکی نیست.



User:



هویت دیجیتال شخص است.



Employee:



رابطه کاری شخص با Organization است.





بنابراین:



User

&#x20; │

&#x20; ├── Identity

&#x20; │

&#x20; └── Membership

&#x20;         │

&#x20;         └── Organization / Tenant





و Employee می‌تواند به User متصل باشد.



اما:



هر User الزاماً Employee نیست.





مثال:



Customer

Contractor

External Consultant

Supplier

System Operator

AI Agent

Service Account



ممکن است User داشته باشند بدون اینکه Employee باشند.





──────────────────────────────────────────────────────────────────────────────

3\. Account Lifecycle

──────────────────────────────────────────────────────────────────────────────



چرخه عمر Account باید از ابتدا مشخص باشد.



States:



INVITED

PENDING\_ACTIVATION

ACTIVE

SUSPENDED

LOCKED

DISABLED

EXPIRED

DELETED





نباید برای Stateهای امنیتی فقط از:



isActive



استفاده شود.





نمونه:



INVITED

&#x20;   ↓

PENDING\_ACTIVATION

&#x20;   ↓

ACTIVE

&#x20;   ↓

SUSPENDED

&#x20;   ↓

ACTIVE



یا:



ACTIVE

&#x20;   ↓

LOCKED

&#x20;   ↓

ACTIVE





──────────────────────────────────────────────────────────────────────────────

4\. User Identity

──────────────────────────────────────────────────────────────────────────────



User باید دارای Identity پایدار باشد.



حداقل:



id

username / login identifier

email

phone

status

createdAt

updatedAt

lastLoginAt

passwordChangedAt

failedLoginCount

lockedUntil





اما Login Identifier باید قابل توسعه باشد.



نباید معماری فقط بر Email متکی باشد.





──────────────────────────────────────────────────────────────────────────────

5\. Credential Architecture

──────────────────────────────────────────────────────────────────────────────



Credential از User جدا در نظر گرفته شود.



انواع Credential:



Password

Email Verification

Phone Verification

MFA Secret

Recovery Code

API Key

Service Credential

External Identity





Password نباید در User Entity به شکل Business Data مدیریت شود.



Password باید از طریق Security Infrastructure مدیریت شود.





──────────────────────────────────────────────────────────────────────────────

6\. Authentication Methods

──────────────────────────────────────────────────────────────────────────────



Architecture باید قابلیت:



Username/Password

Email/Password

Phone/OTP

Magic Link

MFA

SSO

OIDC

OAuth2

SAML

Service Account



را در آینده داشته باشد.





در V1 لازم نیست همه این روش‌ها پیاده‌سازی شوند.



اما Architecture نباید آنها را غیرممکن کند.





──────────────────────────────────────────────────────────────────────────────

7\. JWT Architecture

──────────────────────────────────────────────────────────────────────────────



برای API Authentication:



Access Token

Refresh Token



در نظر گرفته شود.



Access Token:



عمر کوتاه.



Refresh Token:



عمر طولانی‌تر.



Refresh Token باید قابل:



Rotation

Revocation

Tracking



باشد.





JWT نباید تنها مکانیزم Session Management باشد.





──────────────────────────────────────────────────────────────────────────────

8\. Token Claims

──────────────────────────────────────────────────────────────────────────────



Token باید حداقل اطلاعات مورد نیاز را داشته باشد.



مانند:



sub

jti

iat

exp

issuer

audience

tenantId

sessionId





نباید Permissionهای بسیار زیاد داخل Token ذخیره شوند.



چون تغییر Permission نباید مجبور به انتظار برای Expiration Token باشد.





──────────────────────────────────────────────────────────────────────────────

9\. Session Management

──────────────────────────────────────────────────────────────────────────────



هر Login باید Session قابل ردیابی ایجاد کند.



Session شامل:



id

user

tenant

createdAt

lastActivityAt

expiresAt

revokedAt

ipAddress

userAgent

device

status





باشد.





کاربر باید بتواند:



Active Sessions



را مشاهده کند و Sessionهای دیگر را Logout کند.





──────────────────────────────────────────────────────────────────────────────

10\. Login Security

──────────────────────────────────────────────────────────────────────────────



Login باید شامل:



Credential Validation

Account Status Check

Tenant Resolution

Rate Limiting

Brute Force Protection

Audit

Session Creation



باشد.





در صورت چند Login ناموفق:



Account می‌تواند موقتاً Lock شود.





──────────────────────────────────────────────────────────────────────────────

11\. Multi-Tenant Identity

──────────────────────────────────────────────────────────────────────────────



یک User می‌تواند عضو چند Tenant باشد.



مثال:



User

&#x20;├── Tenant A

&#x20;├── Tenant B

&#x20;└── Tenant C





بنابراین Tenant نباید الزاماً Property ثابت User باشد.





رابطه باید چیزی شبیه:



User

&#x20;  ↓

TenantMembership

&#x20;  ↓

Tenant





باشد.





──────────────────────────────────────────────────────────────────────────────

12\. Tenant Membership

──────────────────────────────────────────────────────────────────────────────



TenantMembership باید اطلاعاتی مانند:



user

tenant

status

joinedAt

leftAt

defaultRole

isPrimary

createdAt

updatedAt





داشته باشد.





یک User می‌تواند:



ACTIVE



در Tenant A باشد و:



SUSPENDED



در Tenant B.





──────────────────────────────────────────────────────────────────────────────

13\. Tenant Context

──────────────────────────────────────────────────────────────────────────────



هر Request باید Tenant Context داشته باشد.



مثال:



Request

&#x20;↓

Authenticated User

&#x20;↓

Tenant Context

&#x20;↓

Authorization

&#x20;↓

Use Case





Application نباید Tenant Context را از HTTP Request به‌صورت مستقیم دریافت کند.



باید یک Context abstraction وجود داشته باشد.





──────────────────────────────────────────────────────────────────────────────

14\. RBAC

──────────────────────────────────────────────────────────────────────────────



Tekarai باید RBAC داشته باشد.



Role:



مثلاً:



System Administrator

Tenant Administrator

HR Manager

Project Manager

Employee

Auditor

Viewer





Permission:



مثلاً:



user.read

user.create

user.update

user.delete



project.read

project.create

project.update



document.read

document.download





Role مجموعه‌ای از Permissionها است.





──────────────────────────────────────────────────────────────────────────────

15\. Permission Model

──────────────────────────────────────────────────────────────────────────────



Permission باید مستقل از Role باشد.



ساختار:



Role

&#x20; ↓

RolePermission

&#x20; ↓

Permission





یک Permission می‌تواند به چند Role تعلق داشته باشد.





──────────────────────────────────────────────────────────────────────────────

16\. Permission Naming

──────────────────────────────────────────────────────────────────────────────



Permissionها باید استاندارد باشند.



فرمت پیشنهادی:



<resource>.<action>





مثال:



users.read

users.create

users.update

users.delete



projects.read

projects.create

projects.update

projects.delete



documents.read

documents.download

documents.approve





Permission Name نباید به View یا URL وابسته باشد.





──────────────────────────────────────────────────────────────────────────────

17\. Role Scope

──────────────────────────────────────────────────────────────────────────────



Role باید Scope داشته باشد.



Scopeها می‌توانند:



SYSTEM

TENANT

ORGANIZATION

DEPARTMENT

PROJECT

RESOURCE





باشند.





مثال:



Project Manager



ممکن است فقط:



PROJECT



Scope داشته باشد.





──────────────────────────────────────────────────────────────────────────────

18\. Resource Authorization

──────────────────────────────────────────────────────────────────────────────



داشتن Permission:



project.read



به‌تنهایی کافی نیست.





ممکن است User اجازه خواندن Project داشته باشد اما فقط Projectهای خودش را ببیند.





بنابراین Authorization باید دو مرحله داشته باشد:



1\. Permission Check

2\. Resource Policy Check





مثال:



Can user read project X?





──────────────────────────────────────────────────────────────────────────────

19\. Policy Architecture

──────────────────────────────────────────────────────────────────────────────



Policy باید قابل توسعه باشد.



مثال:



ProjectPolicy

DocumentPolicy

EmployeePolicy

TaskPolicy





Policy مسئول تعیین دسترسی به Resource است.





مثلاً:



canView()

canCreate()

canUpdate()

canDelete()

canApprove()





Policy نباید داخل View نوشته شود.





──────────────────────────────────────────────────────────────────────────────

20\. Separation of Authentication and Authorization

──────────────────────────────────────────────────────────────────────────────



Authentication:



WHO ARE YOU?





Authorization:



WHAT CAN YOU DO?





این دو سیستم نباید با یکدیگر مخلوط شوند.





──────────────────────────────────────────────────────────────────────────────

21\. Service Accounts

──────────────────────────────────────────────────────────────────────────────



Tekarai باید Service Account داشته باشد.



برای:



Agents

Integrations

Automation

Background Workers

External Systems

AI Services





Service Account نباید User انسانی تلقی شود.





اما می‌تواند:



Credential

Permission

Role

Scope

Audit Identity



داشته باشد.





──────────────────────────────────────────────────────────────────────────────

22\. API Keys

──────────────────────────────────────────────────────────────────────────────



برای Integrationهای Server-to-Server:



API Key Architecture



در نظر گرفته شود.





API Key باید:



hashed

revocable

scoped

expirable

auditable



باشد.





Raw API Key نباید در Database ذخیره شود.





──────────────────────────────────────────────────────────────────────────────

23\. Password Policy

──────────────────────────────────────────────────────────────────────────────



Password Policy باید configurable باشد.



موارد:



minimum length

complexity

password history

expiration policy

failed attempts

lock duration





اما Password Expiration نباید بدون Business Requirement اجباری شود.





──────────────────────────────────────────────────────────────────────────────

24\. MFA Architecture

──────────────────────────────────────────────────────────────────────────────



Architecture باید MFA-ready باشد.



روش‌ها:



TOTP

Email OTP

SMS OTP

WebAuthn / Passkeys





MFA باید قابل فعال/غیرفعال شدن بر اساس:



System

Tenant

User



باشد.





──────────────────────────────────────────────────────────────────────────────

25\. Recovery

──────────────────────────────────────────────────────────────────────────────



Password Recovery باید:



Tokenized

Time Limited

Single Use

Audited



باشد.





Recovery Token نباید قابل استفاده مجدد باشد.





──────────────────────────────────────────────────────────────────────────────

26\. Verification

──────────────────────────────────────────────────────────────────────────────



Email و Phone Verification باید مستقل باشند.



مثلاً:



EmailVerification



PhoneVerification





هر Verification:



token

expiresAt

verifiedAt

attemptCount





داشته باشد.





──────────────────────────────────────────────────────────────────────────────

27\. Security Events

──────────────────────────────────────────────────────────────────────────────



Security Event باید ثبت شود.



مثال:



LOGIN\_SUCCESS

LOGIN\_FAILED

ACCOUNT\_LOCKED

PASSWORD\_CHANGED

PASSWORD\_RESET

MFA\_ENABLED

MFA\_DISABLED

SESSION\_CREATED

SESSION\_REVOKED

API\_KEY\_CREATED

API\_KEY\_REVOKED

ROLE\_ASSIGNED

ROLE\_REMOVED

PERMISSION\_CHANGED





این Eventها باید با Audit Architecture هماهنگ باشند.





──────────────────────────────────────────────────────────────────────────────

28\. Authorization Cache

──────────────────────────────────────────────────────────────────────────────



برای Performance باید امکان Cache کردن Authorization Data وجود داشته باشد.



اما:



Permission Change



باید بتواند Cache را Invalidate کند.





Cache نباید باعث شود Permission قدیمی برای مدت نامعلوم معتبر باقی بماند.





──────────────────────────────────────────────────────────────────────────────

29\. Identity Domain Model

──────────────────────────────────────────────────────────────────────────────



مدل مفهومی:



User

Credential

UserIdentifier

TenantMembership

Role

Permission

RolePermission

UserRole

Session

APIKey

ServiceAccount

SecurityEvent

VerificationToken

PasswordResetToken





مدل‌های بیشتر در ERD نهایی اضافه می‌شوند.





──────────────────────────────────────────────────────────────────────────────

30\. Domain Events

──────────────────────────────────────────────────────────────────────────────



Identity باید Event تولید کند.



مثال:



UserRegistered

UserActivated

UserSuspended

UserDisabled

UserLoggedIn

UserLoggedOut

PasswordChanged

RoleAssigned

RoleRevoked

PermissionChanged

SessionRevoked





Eventها نباید به Django Signal محدود شوند.





──────────────────────────────────────────────────────────────────────────────

31\. Application Use Cases

──────────────────────────────────────────────────────────────────────────────



حداقل Use Caseهای زیر باید طراحی شوند:



RegisterUser

ActivateUser

SuspendUser

DisableUser

EnableUser



AuthenticateUser

RefreshToken

LogoutUser

LogoutAllSessions



ChangePassword

ResetPassword



VerifyEmail

VerifyPhone



CreateTenantMembership

SuspendTenantMembership

RemoveTenantMembership



CreateRole

UpdateRole

DeleteRole



AssignRole

RemoveRole



CreateAPIKey

RevokeAPIKey



CreateServiceAccount

DisableServiceAccount





──────────────────────────────────────────────────────────────────────────────

32\. API Endpoints

──────────────────────────────────────────────────────────────────────────────



Endpointها باید Versioned باشند.



مثال:



/api/v1/auth/login/

/api/v1/auth/refresh/

/api/v1/auth/logout/



/api/v1/auth/password/change/

/api/v1/auth/password/reset/



/api/v1/auth/verify-email/



/api/v1/users/

/api/v1/users/{id}/



/api/v1/roles/

/api/v1/permissions/



/api/v1/sessions/

/api/v1/api-keys/





URL نباید محل Business Logic باشد.





──────────────────────────────────────────────────────────────────────────────

33\. Admin Access

──────────────────────────────────────────────────────────────────────────────



Django Admin نباید مسیر اصلی Business Application باشد.



Admin فقط برای:



System Administration

Debugging

Operations

Controlled Management



استفاده شود.





تمام Authorizationهای حساس باید در Domain/Application نیز enforce شوند.





──────────────────────────────────────────────────────────────────────────────

34\. Database Constraints

──────────────────────────────────────────────────────────────────────────────



برای Identity باید از Database Constraint نیز استفاده شود.



مثال:



Unique User Identifier

Unique Tenant Membership

Unique Role Name per Scope

Unique Permission Code

Unique API Key Identifier





Business Rule نباید فقط به Application Validation وابسته باشد.





──────────────────────────────────────────────────────────────────────────────

35\. Security Invariants

──────────────────────────────────────────────────────────────────────────────



قوانین غیرقابل نقض:



1\. User بدون Authentication نمی‌تواند Resource محافظت‌شده را بخواند.



2\. User بدون Permission نمی‌تواند Operation را انجام دهد.



3\. User از Tenant A نمی‌تواند داده Tenant B را بخواند.



4\. Revoked Session نباید معتبر باشد.



5\. Expired Token نباید معتبر باشد.



6\. Revoked API Key نباید معتبر باشد.



7\. Disabled User نباید بتواند Login کند.



8\. Suspended Membership نباید بتواند در Tenant فعالیت کند.



9\. Permission قدیمی نباید بعد از Revocation برای مدت نامعلوم معتبر بماند.



10\. Security-sensitive operation باید Audit شود.





──────────────────────────────────────────────────────────────────────────────

36\. Testing

──────────────────────────────────────────────────────────────────────────────



Identity باید تست‌های جدی داشته باشد.



Unit:



Password Policy

Role Policy

Permission Policy

Account State Transition





Integration:



Authentication

JWT

Session

Repository

Database





Security:



Brute Force

Token Expiration

Token Revocation

Permission Escalation

Tenant Isolation

Role Escalation

API Key Revocation





API:



Login

Refresh

Logout

Password Reset

Role Assignment

Permission Enforcement





──────────────────────────────────────────────────────────────────────────────

37\. Security Testing Matrix

──────────────────────────────────────────────────────────────────────────────



حداقل این سناریوها:



User A → Tenant A → allowed



User A → Tenant B → denied



User without permission → denied



User with revoked role → denied



Disabled user → login denied



Expired token → denied



Revoked token → denied



Expired API key → denied



Revoked API key → denied



Suspended membership → denied





──────────────────────────────────────────────────────────────────────────────

38\. Logging

──────────────────────────────────────────────────────────────────────────────



Identity Log باید شامل:



timestamp

event

userId

tenantId

sessionId

ip

userAgent

correlationId

result

reason





باشد.





Password، Token و Secret نباید Log شوند.





──────────────────────────────────────────────────────────────────────────────

39\. Folder Structure

──────────────────────────────────────────────────────────────────────────────



ساختار پیشنهادی:



apps/

└── identity/

&#x20;   ├── domain/

&#x20;   │   ├── entities/

&#x20;   │   ├── valueObjects/

&#x20;   │   ├── repositories/

&#x20;   │   ├── services/

&#x20;   │   ├── events/

&#x20;   │   └── exceptions/

&#x20;   │

&#x20;   ├── application/

&#x20;   │   ├── commands/

&#x20;   │   ├── queries/

&#x20;   │   ├── dto/

&#x20;   │   ├── useCases/

&#x20;   │   └── services/

&#x20;   │

&#x20;   ├── infrastructure/

&#x20;   │   ├── models/

&#x20;   │   ├── repositories/

&#x20;   │   ├── authentication/

&#x20;   │   ├── authorization/

&#x20;   │   ├── security/

&#x20;   │   └── migrations/

&#x20;   │

&#x20;   └── presentation/

&#x20;       └── api/

&#x20;           ├── serializers/

&#x20;           ├── views/

&#x20;           ├── permissions/

&#x20;           ├── urls/

&#x20;           └── schemas/





──────────────────────────────────────────────────────────────────────────────

40\. خروجی‌های الزامی Phase 07

──────────────────────────────────────────────────────────────────────────────



\[ ] User Identity Architecture



\[ ] Account Lifecycle



\[ ] Credential Architecture



\[ ] Authentication Architecture



\[ ] JWT Architecture



\[ ] Refresh Token Architecture



\[ ] Session Management



\[ ] Tenant Membership



\[ ] RBAC



\[ ] Permission System



\[ ] Role Scope



\[ ] Resource Authorization



\[ ] Policy Architecture



\[ ] Service Account Architecture



\[ ] API Key Architecture



\[ ] Password Policy



\[ ] MFA Architecture



\[ ] Recovery Architecture



\[ ] Verification Architecture



\[ ] Security Event Architecture



\[ ] Authorization Cache Strategy



\[ ] Identity Domain Events



\[ ] Identity Use Cases



\[ ] Identity API



\[ ] Security Invariants



\[ ] Identity Tests



\[ ] Tenant Isolation Tests



\[ ] Security Tests



\[ ] Identity Documentation





──────────────────────────────────────────────────────────────────────────────

41\. Definition of Done

──────────────────────────────────────────────────────────────────────────────



Phase 07 زمانی تمام شده است که:



1\. User از Employee جدا باشد.



2\. User بتواند عضو چند Tenant باشد.



3\. Tenant Membership مستقل باشد.



4\. Authentication از Authorization جدا باشد.



5\. JWT + Refresh Token Architecture وجود داشته باشد.



6\. Session قابل مدیریت باشد.



7\. RBAC وجود داشته باشد.



8\. Permission مستقل از Role باشد.



9\. Resource Authorization وجود داشته باشد.



10\. Service Account پشتیبانی شود.



11\. API Key امن و قابل Revocation باشد.



12\. MFA-ready باشد.



13\. Password Recovery امن باشد.



14\. Security Eventها Audit شوند.



15\. Tenant Isolation در چند Layer enforce شود.



16\. Permission Escalation تست شده باشد.



17\. Token Revocation تست شده باشد.



18\. تمام Identity Use Caseها مستقل از HTTP باشند.



19\. Domain به Django وابسته نباشد.



20\. هیچ Secret یا Token خام در Database یا Log ذخیره نشود.





──────────────────────────────────────────────────────────────────────────────

42\. قانون پیاده‌سازی

──────────────────────────────────────────────────────────────────────────────



قبل از ایجاد Model:



Domain Model

&#x20;   ↓

Business Rules

&#x20;   ↓

Aggregate / Entity

&#x20;   ↓

Repository Contract

&#x20;   ↓

Application Use Case

&#x20;   ↓

Infrastructure Model

&#x20;   ↓

API Contract

&#x20;   ↓

Implementation

&#x20;   ↓

Tests





نباید از:



Django Model



مستقیماً به:



API



برسیم.





مسیر صحیح:



API

&#x20;↓

Application

&#x20;↓

Domain

&#x20;↓

Repository

&#x20;↓

Infrastructure

&#x20;↓

Database





──────────────────────────────────────────────────────────────────────────────

43\. نکته حیاتی برای Tekarai

──────────────────────────────────────────────────────────────────────────────



Identity باید به‌گونه‌ای ساخته شود که در آینده بتواند:



Web

Mobile

Desktop

Windows Agent

AI Agent

External Integration

API Consumer

Service Worker



را بدون بازطراحی Core Authentication پشتیبانی کند.





Identity باید Foundation امنیتی کل Tekarai باشد.





END OF PHASE 07

