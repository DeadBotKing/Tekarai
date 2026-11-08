"""Framework-free superadmin invariants. Facts/evidence must be built by trusted server code.

This is a policy foundation, not an authorization endpoint. Repository integrations must
hold a stable global governance lock before calculating surviving-admin counts and keep
that lock through commit. Client flags, usernames and UI permission arrays are not facts.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from fnmatch import fnmatchcase
from uuid import UUID

from apps.sharedKernel.domain.errors import PermissionDeniedError, ValidationFailedError

PROTECTED_ROLE_CODE = 'platformadmin'
PLATFORM_ONLY_ACTIONS = frozenset({'tenant.create', 'tenant.list', 'tenant.suspend', 'tenant.activate', 'tenant.close'})
DESTRUCTIVE_ACCOUNT_OPERATIONS = frozenset({'suspend', 'archive', 'delete', 'demote'})

@dataclass(frozen=True)
class AdminActorFacts:
    userId: UUID
    tenantId: UUID
    active: bool
    builtInGlobalAdmin: bool
    sessionId: UUID | None = None
    activeMfaFactor: bool = False
    mfaVerifiedAt: datetime | None = None
    # Effective, deny-filtered codes, evaluated against the target tenant by the server.
    allowedActions: frozenset[str] = frozenset()

@dataclass(frozen=True)
class ManagedAccountFacts:
    userId: UUID
    tenantId: UUID
    status: str
    builtInGlobalAdmin: bool = False
    countsAsUsableAdmin: bool = False

@dataclass(frozen=True)
class ManagedRoleFacts:
    code: str
    scopeType: str
    # Expanded catalogue codes, not unchecked action patterns from the browser.
    actions: frozenset[str] = frozenset()

    @property
    def protected(self) -> bool:
        return self.code.strip().casefold() == PROTECTED_ROLE_CODE

    @property
    def platformScoped(self) -> bool:
        return self.protected or self.scopeType in {'GLOBAL', 'SYSTEM'}

@dataclass(frozen=True)
class DeletionEvidence:
    """Conservative server-side reference scan result; absent/incomplete proof means refusal."""
    referenceCheckComplete: bool = False
    businessReferences: int = 0
    everLoggedIn: bool = False
    confirmationMatchesTarget: bool = False

class SuperadminPolicy:
    MFA_FRESHNESS = timedelta(minutes=10)

    @staticmethod
    def requirePlatformAssurance(actor: AdminActorFacts, now: datetime) -> None:
        if not actor.active or not actor.builtInGlobalAdmin:
            raise PermissionDeniedError('این عملیات فقط برای سوپرادمین سامانه مجاز است.')
        verified = actor.mfaVerifiedAt
        if (not actor.sessionId or not actor.activeMfaFactor or verified is None
                or verified > now or now - verified > SuperadminPolicy.MFA_FRESHNESS):
            raise PermissionDeniedError('برای این عملیات، تأیید دومرحله‌ای تازه لازم است.')

    @staticmethod
    def _requireAction(actor: AdminActorFacts, action: str) -> None:
        if not actor.active or action not in actor.allowedActions:
            raise PermissionDeniedError(action=action)

    @staticmethod
    def _tenantBoundary(actor: AdminActorFacts, targetTenantId: UUID) -> None:
        if targetTenantId != actor.tenantId and not actor.builtInGlobalAdmin:
            raise PermissionDeniedError('دسترسی به سازمان دیگر مجاز نیست.')

    @staticmethod
    def expandedActions(patterns: tuple[str, ...], catalogue: frozenset[str]) -> frozenset[str]:
        expanded: set[str] = set()
        for pattern in patterns:
            matched = {code for code in catalogue if fnmatchcase(code, pattern)}
            if not matched:
                raise ValidationFailedError('کد اختیار ناشناخته یا بدون تطبیق است.')
            expanded.update(matched)
        return frozenset(expanded)

    @classmethod
    def requireRoleCreation(cls, actor: AdminActorFacts, role: ManagedRoleFacts, now: datetime) -> None:
        cls._requireAction(actor, 'role.create')
        if role.protected:
            raise ValidationFailedError('نقش اصلی سوپرادمین از قبل تعریف شده و قابل ساخت مجدد نیست.')
        cls._requireDelegation(actor, role, now)

    @classmethod
    def requireRoleEdit(cls, actor: AdminActorFacts, before: ManagedRoleFacts,
                        after: ManagedRoleFacts, now: datetime, *, delete: bool = False) -> None:
        cls._requireAction(actor, 'role.delete' if delete else 'role.update')
        if before.protected or after.protected:
            raise PermissionDeniedError('تعریف نقش اصلی سوپرادمین قابل حذف یا ویرایش نیست.')
        # Both old and new role scope/actions matter; do not downgrade a role to bypass its guard.
        cls._requireDelegation(actor, before, now)
        if not delete:
            cls._requireDelegation(actor, after, now)

    @classmethod
    def _requireDelegation(cls, actor: AdminActorFacts, role: ManagedRoleFacts, now: datetime) -> None:
        if actor.builtInGlobalAdmin:
            cls.requirePlatformAssurance(actor, now)
        elif role.platformScoped:
            raise PermissionDeniedError('مدیر سازمان نمی‌تواند نقش سراسری مدیریت کند.')
        if not actor.builtInGlobalAdmin and not role.actions.issubset(actor.allowedActions):
            raise PermissionDeniedError('اعطای اختیاری بیشتر از دسترسی خودتان مجاز نیست.')
        if not role.platformScoped and role.actions.intersection(PLATFORM_ONLY_ACTIONS):
            raise PermissionDeniedError('اختیارات مدیریت سامانه قابل واگذاری در نقش سازمانی نیست.')

    @classmethod
    def requireRoleAssignment(cls, actor: AdminActorFacts, target: ManagedAccountFacts,
                              role: ManagedRoleFacts, now: datetime, *, remove: bool = False,
                              usableAdminCountUnderLock: int | None = None) -> None:
        cls._requireAction(actor, 'user.assignRole')
        cls._tenantBoundary(actor, target.tenantId)
        cls._requireDelegation(actor, role, now)
        if target.builtInGlobalAdmin:
            cls.requirePlatformAssurance(actor, now)
        if remove and role.protected:
            cls._protectAdminSurvival(actor, target, 'demote', usableAdminCountUnderLock)

    @staticmethod
    def _protectAdminSurvival(actor: AdminActorFacts, target: ManagedAccountFacts,
                             operation: str, usableAdminCountUnderLock: int | None) -> None:
        if operation not in DESTRUCTIVE_ACCOUNT_OPERATIONS:
            return
        if actor.userId == target.userId:
            raise PermissionDeniedError('این عملیات روی حساب مدیریتی خودتان مجاز نیست.')
        if target.builtInGlobalAdmin:
            if usableAdminCountUnderLock is None or usableAdminCountUnderLock < 0:
                raise PermissionDeniedError('وضعیت مدیران فعال هنوز به‌صورت امن بررسی نشده است.')
            if target.countsAsUsableAdmin and usableAdminCountUnderLock <= 1:
                raise PermissionDeniedError('آخرین سوپرادمین فعال قابل حذف یا غیرفعال‌سازی نیست.')

    @classmethod
    def requireLifecycleChange(cls, actor: AdminActorFacts, target: ManagedAccountFacts,
                               operation: str, now: datetime,
                               *, usableAdminCountUnderLock: int | None = None) -> None:
        if operation not in {'activate', 'suspend', 'archive'}:
            raise ValidationFailedError('عملیات وضعیت حساب شناخته‌شده نیست.')
        cls._requireAction(actor, 'user.disable' if operation == 'archive' else 'user.suspend')
        cls._tenantBoundary(actor, target.tenantId)
        if actor.builtInGlobalAdmin or target.builtInGlobalAdmin:
            cls.requirePlatformAssurance(actor, now)
        cls._protectAdminSurvival(actor, target, operation, usableAdminCountUnderLock)

    @classmethod
    def requirePermanentDeletion(cls, actor: AdminActorFacts, target: ManagedAccountFacts,
                                 evidence: DeletionEvidence, now: datetime,
                                 *, usableAdminCountUnderLock: int | None = None) -> None:
        cls.requirePlatformAssurance(actor, now)
        cls._requireAction(actor, 'user.disable')
        cls._protectAdminSurvival(actor, target, 'delete', usableAdminCountUnderLock)
        if target.status != 'disabled':
            raise ValidationFailedError('حساب باید پیش از بررسی حذف دائمی بایگانی شده باشد.')
        if (not evidence.referenceCheckComplete or evidence.businessReferences != 0
                or evidence.everLoggedIn or not evidence.confirmationMatchesTarget):
            raise ValidationFailedError('حذف دائمی تأیید نشد؛ حساب و سوابق حفظ می‌شوند. از بایگانی استفاده کنید.')
