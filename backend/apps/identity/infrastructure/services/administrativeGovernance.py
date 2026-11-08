"""Shared guards for NEW and LEGACY administration paths.

All state decisions below must execute under lockedAdministrationState. Survivor
sets count people with usable entry paths AFTER the proposed mutation, rather
than counting role rows. A person's disable removes all of their entry paths.
"""
import functools
import uuid
from contextlib import contextmanager

from django.utils import timezone
from django.db.models import Q

from apps.identity.infrastructure.models import (
    AdministrativeIdentityModel as Identity, AdministrativeGovernanceModel as Governance,
    RoleModel, RolePermissionModel, UserRoleModel, UserModel, TenantMembershipModel,
    MobileAccountModel, SessionModel,
)
from apps.identity.infrastructure.services.administrationLock import lockedAdministrationState
from apps.identity.infrastructure.services.administrativeAuthentication import verifiedAdministrativeSession
from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.domain.errors import PermissionDeniedError, EntityNotFoundError, ValidationFailedError

PLATFORM_ACTIONS = frozenset({'tenant.create', 'tenant.list', 'tenant.suspend', 'tenant.activate', 'tenant.close'})


def managedAdministration():
    return (Identity.objects.exists()
            or Governance.objects.filter(managedAdministrationEnabled=True).exists()
            or Governance.objects.filter(legacyAdminRetiredAt__isnull=False).exists())


def _legacyOwners():
    roles = RoleModel.objects.filter(code__iexact='platformAdmin', scopeType='GLOBAL', isActive=True)
    return set(UserRoleModel.objects.filter(roleId__in=roles.values('id'), scopeType__in=['GLOBAL', ''])
               .values_list('userId', flat=True))


def protectedOwner(userId):
    return (Identity.objects.filter(ownerUserId=userId).exists()
            or UserRoleModel.objects.filter(userId=userId,
                 roleId__in=RoleModel.objects.filter(scopeType__in=['GLOBAL', 'SYSTEM']).values('id')).exists())


def requireFreshAdministrator():
    context = currentContext()
    if not context.actorId or not context.sessionId:
        raise PermissionDeniedError('این عملیات به ورود مستقل مدیریت و تأیید دومرحله‌ای تازه نیاز دارد.')
    session = SessionModel.objects.filter(id=context.sessionId, userId=context.actorId).first()
    if session is None:
        raise PermissionDeniedError('نشست مدیریت معتبر نیست.')
    identity = verifiedAdministrativeSession(session, requireFresh=True)
    if identity is None:
        raise PermissionDeniedError('از صفحه ورود مستقل مدیریت کل وارد شوید.')
    return identity


def _rootOrUnmanagedLegacy():
    context = currentContext()
    if not managedAdministration() and context.actorId and uuid.UUID(context.actorId) in _legacyOwners():
        owner = UserModel.objects.filter(id=context.actorId, status='active', deletedAt__isnull=True).first()
        if owner:
            return None
    return requireFreshAdministrator()


def usableAdministratorOwners(*, excludingOwners=(), excludingLegacyOwners=()):
    """No client supplied counts. Caller holds the global lock through commit."""
    from apps.tenancy.infrastructure.models import TenantModel
    now = timezone.now()
    activeTenants = TenantModel.objects.filter(status='active', deletedAt__isnull=True).values('id')
    legacy = _legacyOwners() - set(excludingLegacyOwners)
    aliases = set()
    for identity in Identity.objects.filter(status='active', mustChangePassword=False,
            mfaConfirmedAt__isnull=False, firstVerifiedLoginAt__isnull=False).exclude(mfaSecretRef=''):
        if identity.lockedUntil is None or identity.lockedUntil <= now:
            aliases.add(identity.ownerUserId)
    result = set()
    for owner in UserModel.objects.filter(id__in=legacy | aliases, status='active', deletedAt__isnull=True,
                                          tenantId__in=activeTenants).exclude(id__in=excludingOwners):
        if owner.expiresAt is not None and owner.expiresAt <= now:
            continue
        if owner.lockedUntil is not None and owner.lockedUntil > now:
            continue
        if MobileAccountModel.objects.filter(userId=owner.id, mustChangePassword=True).exists():
            continue
        if TenantMembershipModel.objects.filter(userId=owner.id, tenantId=owner.tenantId,
                                                status='active', leftAt__isnull=True).exists():
            result.add(owner.id)
    return result


def _target(userId):
    user = UserModel.objects.filter(id=userId, deletedAt__isnull=True).first()
    if user is None:
        raise EntityNotFoundError('User', str(userId))
    context = currentContext()
    if str(user.tenantId) != str(context.actorTenantId or context.tenantId):
        requireFreshAdministrator()
    return user


def _authorizeUnderLock(action, targetTenantId):
    from apps.identity.infrastructure.services.permissionGate import PermissionGateDjango
    context = currentContext()
    if not context.actorId or not UserModel.objects.filter(id=context.actorId, status='active', deletedAt__isnull=True, kind='human').exists():
        raise PermissionDeniedError('حساب شخص اقدام‌کننده فعال نیست.')
    if not PermissionGateDjango().hasPermission(
            uuid.UUID(context.actorId), action,
            tenantId=uuid.UUID(context.actorTenantId or context.tenantId), targetTenantId=targetTenantId):
        raise PermissionDeniedError(action=action)


def guardOrganizationManagerRemoval(user):
    from apps.tenancy.infrastructure.models import TenantModel
    role = RoleModel.objects.filter(code='tenantAdmin', scopeType='TENANT', isActive=True).first()
    if role is None or user.status != 'active' or not TenantModel.objects.filter(id=user.tenantId, status='active').exists():
        return
    if not UserRoleModel.objects.filter(userId=user.id, roleId=role.id, scopeType='TENANT').exists():
        return
    others = UserRoleModel.objects.filter(roleId=role.id, scopeType='TENANT', tenantId=user.tenantId).exclude(userId=user.id).values('userId')
    members = TenantMembershipModel.objects.filter(tenantId=user.tenantId, status='active', leftAt__isnull=True).values('userId')
    candidates = UserModel.objects.filter(id__in=others, tenantId=user.tenantId, status='active', deletedAt__isnull=True).filter(id__in=members)
    now = timezone.now()
    if not candidates.filter(Q(expiresAt__isnull=True) | Q(expiresAt__gt=now)).filter(Q(lockedUntil__isnull=True) | Q(lockedUntil__lte=now)).exists():
        raise PermissionDeniedError('ابتدا مدیر فعال جایگزین این سازمان را تعیین کنید.')


def guardAccountMutation(userId, operation):
    user = _target(userId)
    action = 'user.disable' if operation in {'disable', 'archive', 'delete'} else ('user.suspend' if operation in {'suspend', 'activate'} else 'user.update')
    _authorizeUnderLock(action, user.tenantId)
    if operation in {'suspend', 'disable', 'archive', 'delete'}:
        guardOrganizationManagerRemoval(user)
    if operation in {'suspend', 'disable', 'archive', 'delete', 'temporaryPassword'}:
        if str(user.id) == str(currentContext().actorId):
            raise PermissionDeniedError('غیرفعال‌سازی یا بازنشانی مدیریتی حساب خودتان مجاز نیست.')
    if protectedOwner(user.id):
        requireFreshAdministrator()
        if operation in {'suspend', 'disable', 'archive', 'delete', 'temporaryPassword'}:
            if not usableAdministratorOwners(excludingOwners={user.id}):
                raise PermissionDeniedError('این عملیات آخرین مسیر ورود قابل استفاده مدیریت را از بین می‌برد.')
    return user


@contextmanager
def guardedAccountMutation(userId, operation):
    with lockedAdministrationState():
        user = guardAccountMutation(userId, operation)
        yield user


def administrativeLifecycleMutation(function):
    @functools.wraps(function)
    def wrapped(self, command):
        operation = {'suspended': 'suspend', 'disabled': 'disable', 'active': 'activate'}.get(command.target)
        if operation is None:
            raise ValidationFailedError('وضعیت حساب معتبر نیست.')
        with guardedAccountMutation(command.userId, operation):
            result = function(self, command)
            if command.target != 'active':
                SessionModel.objects.filter(userId=command.userId, revokedAt__isnull=True).update(revokedAt=timezone.now())
            return result
    return wrapped


def administrativeRoleMutation(operation):
    def decorate(function):
        @functools.wraps(function)
        def wrapped(self, command):
            from apps.identity.application.services.permissionCatalog import ACTIONS
            from apps.identity.domain.policies.superadminPolicy import SuperadminPolicy
            with lockedAdministrationState():
                context = currentContext()
                role = None
                if operation != 'create':
                    role = RoleModel.objects.filter(id=command.roleId).first()
                    if role is None:
                        raise EntityNotFoundError('Role', str(command.roleId))
                _authorizeUnderLock({'create': 'role.create', 'update': 'role.update', 'delete': 'role.delete'}.get(operation, 'user.assignRole'), uuid.UUID(context.actorTenantId or context.tenantId))
                protected = (command.code.strip().casefold() == 'platformadmin') if operation == 'create' else role.code.strip().casefold() == 'platformadmin'
                if operation in {'create', 'update', 'delete'}:
                    if protected:
                        raise PermissionDeniedError('تعریف نقش اصلی مدیریت کل قابل ساخت مجدد، حذف یا ویرایش نیست.')
                    _rootOrUnmanagedLegacy()  # Shared role definitions affect every organization.
                    scope = command.scopeType if operation == 'create' else role.scopeType
                    if scope != 'TENANT':
                        raise PermissionDeniedError('نقش‌های قابل مدیریت از این مسیر باید سازمانی باشند.')
                    if operation != 'delete':
                        patterns = tuple(command.actions)
                        expanded = SuperadminPolicy.expandedActions(patterns, frozenset(code for code, _ in ACTIONS))
                        if expanded.intersection(PLATFORM_ACTIONS):
                            raise PermissionDeniedError('اختیارات مدیریت کل قابل واگذاری در نقش سازمانی نیست.')
                else:
                    user = _target(command.userId)
                    if protectedOwner(user.id):
                        requireFreshAdministrator()
                    if operation == 'remove' and role.code == 'tenantAdmin' and role.scopeType == 'TENANT':
                        guardOrganizationManagerRemoval(user)
                    if operation == 'assign' and role.scopeType in {'GLOBAL', 'SYSTEM'}:
                        raise PermissionDeniedError('دسترسی مدیریت کل فقط از مسیر ورود مستقل مدیریت واگذار می‌شود.')
                    if operation == 'remove' and role.scopeType in {'GLOBAL', 'SYSTEM'}:
                        requireFreshAdministrator()
                        if str(user.id) == str(context.actorId):
                            raise PermissionDeniedError('برای انتقال دسترسی حساب خودتان از تحویل امن مدیریت استفاده کنید.')
                        if protected and not usableAdministratorOwners(excludingLegacyOwners={user.id}):
                            raise PermissionDeniedError('آخرین مسیر ورود مدیریت قابل حذف نیست.')
                    if operation == 'assign':
                        if command.tenantId and str(command.tenantId) != str(user.tenantId):
                            raise ValidationFailedError('سازمان نقش باید با سازمان حساب شخص مطابقت داشته باشد.')
                        patterns = tuple(RolePermissionModel.objects.filter(roleId=role.id).values_list('actionPattern', flat=True))
                        expanded = SuperadminPolicy.expandedActions(patterns, frozenset(code for code, _ in ACTIONS))
                        if role.scopeType != 'TENANT' or expanded.intersection(PLATFORM_ACTIONS):
                            raise PermissionDeniedError('این نقش برای واگذاری سازمانی مجاز نیست.')
                        # Even a compromised custom tenant role cannot delegate authority it lacks.
                        from apps.identity.infrastructure.services.permissionGate import PermissionGateDjango
                        gate = PermissionGateDjango()
                        for action in expanded:
                            if not gate.hasDelegationAuthority(uuid.UUID(context.actorId), action,
                                    tenantId=uuid.UUID(context.actorTenantId or context.tenantId), targetTenantId=user.tenantId):
                                raise PermissionDeniedError('اعطای اختیاری بیشتر از دسترسی خودتان مجاز نیست.')
                return function(self, command)
        return wrapped
    return decorate


def administrativeAccountMutation(operation):
    def decorate(function):
        @functools.wraps(function)
        def wrapped(userId, *args, **kwargs):
            with guardedAccountMutation(userId, operation):
                return function(userId, *args, **kwargs)
        return wrapped
    return decorate


def administrativeTenantMutation(function):
    @functools.wraps(function)
    def wrapped(self, command):
        with lockedAdministrationState():
            # First-run bootstrap explicitly clears requiredAction and has no actor.
            if currentContext().actorId:
                _rootOrUnmanagedLegacy()
            elif getattr(self, 'requiredAction', ''):
                raise PermissionDeniedError('ورود مدیریت کل لازم است.')
            target = getattr(command, 'target', '')
            tenantId = getattr(command, 'tenantId', None)
            if target in {'suspended', 'closed'}:
                owners = set(UserModel.objects.filter(tenantId=tenantId).values_list('id', flat=True))
                if not usableAdministratorOwners(excludingOwners=owners):
                    raise PermissionDeniedError('سازمان آخرین مدیر قابل استفاده را نمی‌توان متوقف کرد.')
                if UserModel.objects.filter(id=currentContext().actorId, tenantId=tenantId).exists():
                    raise PermissionDeniedError('سازمان حساب جاری را از نشست خودش متوقف نکنید.')
            result = function(self, command)
            if target in {'suspended', 'closed'}:
                SessionModel.objects.filter(tenantId=tenantId, revokedAt__isnull=True).update(revokedAt=timezone.now())
            return result
    return wrapped


def administrativeMembershipMutation(function):
    @functools.wraps(function)
    def wrapped(self, command):
        with lockedAdministrationState():
            user = _target(command.userId)
            _authorizeUnderLock('user.assignTenant', user.tenantId)
            if protectedOwner(user.id) or str(command.targetTenantId) != str(user.tenantId):
                requireFreshAdministrator()
            return function(self, command)
    return wrapped
