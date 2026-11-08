"""Audited privileged management. Views never trust client roles, counts or tenant scope."""
import base64
import hashlib
import re
import secrets
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import timedelta
from io import BytesIO

from django.apps import apps
from django.contrib.auth.hashers import check_password, make_password
from django.db import connection, models
from django.db.models import Q
from django.utils import timezone

from apps.identity.infrastructure.models import *
from apps.identity.infrastructure.services.administrationLock import lockedAdministrationState
from apps.identity.infrastructure.services.administrativeGovernance import (
    requireFreshAdministrator, usableAdministratorOwners, protectedOwner, guardAccountMutation, _legacyOwners,
)
from apps.sharedKernel.application.requestContext import currentContext, requestScope, RequestContext
from apps.sharedKernel.domain.errors import PermissionDeniedError, ValidationFailedError, EntityNotFoundError, ConflictError
from apps.sharedKernel.infrastructure.djangoPorts import AuditRecorderDjango
from apps.tenancy.infrastructure.models import TenantModel, TenantAppearanceModel


def audit(action, kind, resourceId, tenantId, after=None):
    AuditRecorderDjango().record(action='admin.' + action, resourceType=kind, resourceId=str(resourceId),
                                tenantId=tenantId, after=after or {})


def _uuid(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValidationFailedError('شناسه معتبر نیست.') from exc


def _text(data, key, maximum, required=True):
    value = data.get(key, '')
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
        raise ValidationFailedError('مقدار ' + key + ' معتبر نیست.')
    return value.strip()


def prepareSetup(ownerId):
    with lockedAdministrationState():
        ownerId = _uuid(ownerId)
        existing = AdministrativeGovernanceModel.objects.filter(key='platform').first()
        if existing and existing.bootstrapOwnerUserId == ownerId and existing.managedAdministrationEnabled:
            return {'prepared': True, 'alreadyManaged': True}
        if _legacyOwners() != {ownerId} or not usableAdministratorOwners() == {ownerId}:
            raise PermissionDeniedError('مالک فعال مدیریت با بررسی تأییدشده مطابقت ندارد.')
        state, created = AdministrativeGovernanceModel.objects.get_or_create(key='platform', defaults={'bootstrapOwnerUserId': ownerId})
        if state.bootstrapOwnerUserId != ownerId:
            raise PermissionDeniedError('مالک تنظیم‌شده متفاوت است.')
        return {'prepared': True, 'alreadyManaged': state.managedAdministrationEnabled}


def setup(data):
    """Narrow bootstrap exception: authenticated selected legacy owner + fresh password.
    Does not grant new authority until independent first-password + MFA completes.
    """
    from apps.identity.infrastructure.services.mobileOnboarding import normalizeMobile
    from apps.identity.domain.valueObjects.userState import validatePasswordStrength
    with lockedAdministrationState():
        context = currentContext()
        state = AdministrativeGovernanceModel.objects.filter(key='platform').first()
        if state is None or str(state.bootstrapOwnerUserId) != context.actorId or state.legacyAdminRetiredAt is not None:
            raise PermissionDeniedError('راه‌اندازی اولیه برای این حساب مجاز نیست یا تحویل مدیریت انجام شده است.')
        existing = AdministrativeIdentityModel.objects.filter(ownerUserId=state.bootstrapOwnerUserId).first()
        if AdministrativeIdentityModel.objects.exclude(ownerUserId=state.bootstrapOwnerUserId).exists() or (existing and (existing.firstVerifiedLoginAt is not None or data.get('restartPending') is not True)):
            raise PermissionDeniedError('ورود کل قبلاً ایجاد شده است؛ فقط راه‌اندازی ناتمام و هرگز واردنشده با تأیید بازراه‌اندازی قابل تجدید است.')
        owner = UserModel.objects.get(id=state.bootstrapOwnerUserId)
        session = SessionModel.objects.filter(id=context.sessionId, userId=owner.id, revokedAt__isnull=True,
                                             expiresAt__gt=timezone.now()).first()
        if session is None or owner.id not in _legacyOwners() or owner.id not in usableAdministratorOwners():
            raise PermissionDeniedError('ورود اصلی مالک معتبر نیست.')
        current = data.get('currentPassword', '')
        temporary = data.get('temporaryPassword', '')
        if not isinstance(current, str) or len(current) > 1024 or not check_password(current, owner.passwordHash):
            raise PermissionDeniedError('رمز فعلی مالک صحیح نیست.')
        factor = MfaFactorModel.objects.filter(userId=owner.id, status='active').first()
        if factor:
            from apps.identity.domain.services.totpService import verifyCode
            from apps.identity.infrastructure.services.secretVault import SigningSecretVault
            code = data.get('ownerMfaCode', '')
            if not isinstance(code, str) or not verifyCode(SigningSecretVault().reveal(factor.secretRef), code):
                raise PermissionDeniedError('کد تازه تأیید دومرحله‌ای حساب اصلی لازم است.')
        if not isinstance(temporary, str) or len(temporary) > 200:
            raise ValidationFailedError('رمز موقت معتبر نیست.')
        validatePasswordStrength(temporary)
        if check_password(temporary, owner.passwordHash):
            raise ValidationFailedError('رمز موقت مدیریت باید از رمز حساب اصلی متفاوت باشد.')
        username = _text(data, 'username', 64).lower()
        if not re.fullmatch(r'[a-z][a-z0-9._-]{2,63}', username):
            raise ValidationFailedError('نام کاربری مدیریت باید انگلیسی و حداقل سه نویسه باشد.')
        phone = normalizeMobile(_text(data, 'phone', 40))
        for other in UserModel.objects.exclude(id=owner.id).exclude(phone='').values_list('phone', flat=True):
            try:
                duplicate = normalizeMobile(other) == phone
            except ValidationFailedError:
                duplicate = False
            if duplicate:
                raise ConflictError('شماره موبایل برای شخص دیگری ثبت شده است.')
        if MobileAccountModel.objects.filter(phone=phone).exclude(userId=owner.id).exists():
            raise ConflictError('شماره موبایل برای شخص دیگری ثبت شده است.')
        MobileAccountModel.objects.update_or_create(userId=owner.id, defaults={'phone': phone})
        UserModel.objects.filter(id=owner.id).update(phone=phone, updatedAt=timezone.now())
        if AdministrativeIdentityModel.objects.filter(username=username).exclude(ownerUserId=owner.id).exists():
            raise ConflictError('نام کاربری مدیریت تکراری است.')
        if existing and check_password(temporary, existing.passwordHash):
            raise ValidationFailedError('برای تجدید راه‌اندازی، رمز موقت متفاوت انتخاب کنید.')
        if existing:
            AdministrativePasswordHistoryModel.objects.create(administrativeIdentityId=existing.id, passwordHash=existing.passwordHash)
            AdministrativeRecoveryCodeModel.objects.filter(administrativeIdentityId=existing.id).delete()
        identity, _ = AdministrativeIdentityModel.objects.update_or_create(ownerUserId=owner.id, defaults={
            'username':username, 'passwordHash':make_password(temporary), 'createdByUserId':owner.id,
            'temporaryExpiresAt':timezone.now()+timedelta(hours=24), 'mustChangePassword':True, 'status':'active',
            'mfaSecretRef':'', 'mfaConfirmedAt':None, 'failedLoginCount':0, 'lockedUntil':None})
        state.managedAdministrationEnabled = True
        state.save()
        audit('setup', 'AdministrativeIdentity', identity.id, owner.tenantId, {'ownerUserId': str(owner.id)})
        return {'username': username, 'loginUrl': '/superadmin/login', 'primaryLoginUnchanged': True}


def retireLegacy(data):
    from apps.identity.infrastructure.services.authorizationCache import bumpVersion
    from apps.identity.infrastructure.repositories.identityRepositoriesImpl import AccessRepositoryDjango
    with lockedAdministrationState():
        identity = requireFreshAdministrator()
        state = AdministrativeGovernanceModel.objects.get(key='platform')
        owner = UserModel.objects.get(id=identity.ownerUserId)
        if state.bootstrapOwnerUserId != owner.id or state.legacyAdminRetiredAt is not None:
            raise PermissionDeniedError('تحویل اولیه برای این حساب مجاز نیست یا قبلاً انجام شده است.')
        if data.get('confirmation') != owner.username or data.get('confirm') is not True:
            raise ValidationFailedError('نام کاربری مالک و تأیید دوم را دقیق وارد کنید.')
        code = _text(data, 'recoveryCode', 100)
        digest = hashlib.sha256(f'recovery.v1:{identity.id}:{code}'.encode()).hexdigest()
        if AdministrativeRecoveryCodeModel.objects.filter(administrativeIdentityId=identity.id, codeHash=digest,
                usedAt__isnull=True).update(usedAt=timezone.now()) != 1:
            raise PermissionDeniedError('یک کد بازیابی ذخیره‌شده و استفاده‌نشده لازم است.')
        tenantRole = RoleModel.objects.filter(code='tenantAdmin', scopeType='TENANT', isActive=True).first()
        if tenantRole is None:
            raise ValidationFailedError('نقش مدیر سازمان موجود نیست؛ تحویل انجام نشد.')
        # Keep the primary person's organization management, not GLOBAL authority.
        AccessRepositoryDjango().grantRoleToUser(owner.id, owner.tenantId, tenantRole.id)
        globalRoles = RoleModel.objects.filter(scopeType__in=['GLOBAL', 'SYSTEM']).values('id')
        UserRoleModel.objects.filter(userId=owner.id).filter(Q(roleId__in=globalRoles) | Q(scopeType__in=['GLOBAL', 'SYSTEM'])).delete()
        # Direct GLOBAL exceptions must not keep an alternative primary elevation.
        UserPermissionModel.objects.filter(userId=owner.id, effect='allow', scopeType__in=['GLOBAL', 'SYSTEM']).delete()
        state.legacyAdminRetiredAt = timezone.now()
        state.save()
        # Keep ONLY the CURRENT verified administrative session alive.
        SessionModel.objects.filter(userId=owner.id, revokedAt__isnull=True).exclude(id=currentContext().sessionId).update(revokedAt=timezone.now())
        bumpVersion(owner.id)
        if owner.id not in usableAdministratorOwners():
            raise PermissionDeniedError('مسیر جایگزین مدیریت قابل استفاده نیست؛ تحویل لغو شد.')
        audit('handoff', 'AdministrativeIdentity', identity.id, owner.tenantId, {'primaryLoginPreserved': True})
        return {'retired': True, 'primaryLoginPreserved': True}


def stepUp(data):
    from apps.identity.infrastructure.services.administrativeAuthentication import verifiedAdministrativeSession
    from apps.identity.infrastructure.services.administrativeLogin import _consumeCode
    failed = False
    with lockedAdministrationState():
        context = currentContext()
        session = SessionModel.objects.filter(id=context.sessionId, userId=context.actorId).first()
        if session is None:
            raise PermissionDeniedError()
        identity = verifiedAdministrativeSession(session)
        if identity is None:
            raise PermissionDeniedError('ورود مستقل مدیریت لازم است.')
        now = timezone.now()
        if not _consumeCode(identity, data.get('code'), now, allowRecovery=True):
            identity.failedLoginCount += 1
            if identity.failedLoginCount >= 5:
                identity.lockedUntil = now + timedelta(minutes=15)
            identity.save(update_fields=['failedLoginCount', 'lockedUntil', 'updatedAt'])
            failed = True
        else:
            identity.failedLoginCount = 0
            identity.lockedUntil = None
            identity.save(update_fields=['failedLoginCount', 'lockedUntil', 'updatedAt'])
            AdministrativeSessionModel.objects.filter(sessionId=session.id).update(mfaVerifiedAt=now)
            audit('stepup', 'AdministrativeIdentity', identity.id, session.tenantId)
    if failed:
        raise PermissionDeniedError('کد معتبر نیست یا قبلاً استفاده شده است.')
    return {'verified': True}


def _requireAction(action, targetTenantId=None):
    from apps.identity.infrastructure.services.permissionGate import PermissionGateDjango
    context = currentContext()
    actor = _uuid(context.actorId)
    if not PermissionGateDjango().hasPermission(actor, action, tenantId=_uuid(context.actorTenantId), targetTenantId=targetTenantId):
        raise PermissionDeniedError(action=action)


def overview():
    identity = requireFreshAdministrator()
    for action in ['user.list', 'tenant.list', 'role.list', 'audit.view']:
        _requireAction(action)
    from apps.organization.infrastructure.models import OrganizationAssignmentModel, OrganizationDepartmentModel, OrganizationPositionModel
    departments = {str(x.id): x.name for x in OrganizationDepartmentModel.objects.all()}
    positions = {str(x.id): x.name for x in OrganizationPositionModel.objects.all()}
    postings = {}
    for item in OrganizationAssignmentModel.objects.filter(isActive=True):
        postings[str(item.userId)] = {'unit': departments.get(str(item.departmentId), ''), 'position': positions.get(str(item.positionId), '')}
    roles = {str(r.id): {'id': str(r.id), 'name': r.name, 'code': r.code, 'scopeType': r.scopeType,
             'actions': list(RolePermissionModel.objects.filter(roleId=r.id).values_list('actionPattern', flat=True))} for r in RoleModel.objects.filter(isActive=True)}
    userRoles = {}
    for assignment in UserRoleModel.objects.all():
        if str(assignment.roleId) in roles:
            userRoles.setdefault(str(assignment.userId), []).append(str(assignment.roleId))
    aliases = {str(a.ownerUserId): {'id': str(a.id), 'username': a.username, 'status': a.status,
        'ready': bool(a.firstVerifiedLoginAt and a.mfaConfirmedAt and not a.mustChangePassword)} for a in AdministrativeIdentityModel.objects.all()}
    users = []
    for user in UserModel.objects.filter(deletedAt__isnull=True).order_by('username'):
        users.append({'id': str(user.id), 'tenantId': str(user.tenantId), 'username': user.username,
            'displayName': user.displayName, 'phone': user.phone, 'email': user.email, 'status': user.status,
            'roles': userRoles.get(str(user.id), []), 'administration': aliases.get(str(user.id)), **postings.get(str(user.id), {})})
    state = AdministrativeGovernanceModel.objects.filter(key='platform').first()
    return {'identityId': str(identity.id), 'ownerUserId': str(identity.ownerUserId), 'legacyRetired': bool(state and state.legacyAdminRetiredAt),
        'users': users, 'roles': list(roles.values()), 'tenants': [tenantDto(t) for t in TenantModel.objects.filter(deletedAt__isnull=True)],
        'audit': auditList()}


def auditList():
    from apps.sharedKernel.infrastructure.models import AuditEventModel
    return [{'id': str(a.id), 'time': a.occurredAt.isoformat(), 'action': a.action, 'resource': a.resourceType,
        'resourceId': a.resourceId, 'actorId': str(a.actorUserId or ''), 'tenantId': str(a.tenantId or ''),
        'administrativeIdentityId': (a.afterState or {}).get('_administrativeIdentityId', '') if isinstance(a.afterState, dict) else ''}
        for a in AuditEventModel.objects.order_by('-occurredAt')[:200]]


def tenantDto(tenant):
    appearance = TenantAppearanceModel.objects.filter(tenantId=tenant.id).first()
    return {'id': str(tenant.id), 'code': tenant.code, 'name': tenant.name, 'status': tenant.status,
        'appearance': {'displayName': appearance.displayName if appearance else ('داروسازی روناک' if tenant.code == 'platform' else tenant.name),
            'tenantCode': tenant.code,
            'logoData': appearance.logoData if appearance else '', 'primaryColor': appearance.primaryColor if appearance else '#214d3d',
            'theme': appearance.theme if appearance else 'warm', 'revision': appearance.revision if appearance else 0}}


@contextmanager
def targetScope(tenantId):
    from dataclasses import replace
    context = currentContext()
    with requestScope(replace(context, tenantId=str(tenantId))):
        yield


def userOperation(data):
    from apps.identity.infrastructure.services import mobileOnboarding
    from apps.identity.infrastructure import container
    from apps.identity.application.commands.identityCommands import AssignRoleCommand, RemoveRoleCommand, ChangeUserStatusCommand
    with lockedAdministrationState():
        requireFreshAdministrator()
        operation = _text(data, 'operation', 30)
        if operation == 'create':
            tenant = TenantModel.objects.filter(id=_uuid(data.get('tenantId')), status__in=['active','suspended'], deletedAt__isnull=True).first()
            if tenant is None:
                raise ValidationFailedError('سازمان فعال انتخاب کنید.')
            from django.core.validators import validate_email
            email = _text(data, 'email', 320)
            try:
                validate_email(email)
            except Exception as exc:
                raise ValidationFailedError('ایمیل معتبر وارد کنید.') from exc
            with targetScope(tenant.id):
                return mobileOnboarding.createMobileAccount(phone=_text(data, 'phone', 40), displayName=_text(data, 'displayName', 160),
                    email=email, username=_text(data, 'username', 64, False))
        userId = _uuid(data.get('userId'))
        user = UserModel.objects.filter(id=userId, deletedAt__isnull=True).first()
        if user is None:
            raise EntityNotFoundError('User', str(userId))
        with targetScope(user.tenantId):
            if operation == 'restoreArchive':
                return restoreArchivedAccount(user,data)
            if operation == 'activate' and user.status == 'disabled':
                raise ValidationFailedError('این حساب بایگانی شده؛ از گزینه بازگردانی از بایگانی استفاده کنید.')
            if operation == 'mobile':
                return mobileOnboarding.updateMobile(user.id, _text(data, 'phone', 40))
            if operation == 'reset':
                return mobileOnboarding.issueTemporaryPassword(user.id)
            if operation in {'suspend', 'activate', 'archive'}:
                target = {'suspend': 'suspended', 'activate': 'active', 'archive': 'disabled'}[operation]
                container.changeUserStatusUseCase().execute(ChangeUserStatusCommand(userId=str(user.id), target=target))
                return {'changed': True}
            if operation in {'assignRole', 'removeRole'}:
                roleId = str(_uuid(data.get('roleId')))
                if operation == 'assignRole':
                    return container.assignRoleUseCase().execute(AssignRoleCommand(userId=str(user.id), roleId=roleId, tenantId=str(user.tenantId)))
                return container.removeRoleUseCase().execute(RemoveRoleCommand(userId=str(user.id), roleId=roleId))
        raise ValidationFailedError('عملیات کاربر معتبر نیست.')


def restoreArchivedAccount(user, data):
    """Privileged explicit recovery only; ordinary disabled->active stays forbidden.
    Caller holds the shared administration lock. Never recreate a person or undo erasure.
    """
    from apps.identity.infrastructure.services.administrativeGovernance import _authorizeUnderLock
    requireFreshAdministrator()
    _authorizeUnderLock('user.update', user.tenantId)
    _authorizeUnderLock('user.suspend', user.tenantId)
    if data.get('confirm') is not True or data.get('confirmation') != user.username:
        raise ValidationFailedError('برای بازگردانی، نام کاربری دقیق و تأیید پیامد عملیات لازم است.')
    if user.deletedAt is not None or user.kind != 'human' or user.status != 'disabled':
        raise ValidationFailedError('فقط حساب شخص بایگانی‌شده و حذف‌نشده قابل بازگردانی است.')
    if not TenantModel.objects.filter(id=user.tenantId,status='active',deletedAt__isnull=True).exists():
        raise PermissionDeniedError('ابتدا وضعیت سازمان حساب را بررسی کنید؛ سازمان باید فعال باشد.')
    memberships = TenantMembershipModel.objects.filter(userId=user.id,tenantId=user.tenantId)
    openMemberships = list(memberships.filter(leftAt__isnull=True).exclude(status='removed'))
    if len(openMemberships)>1 or any(m.status not in {'active','suspended'} for m in openMemberships):
        raise ConflictError('وضعیت عضویت‌های این سازمان مبهم است؛ برای جلوگیری از دسترسی نادرست، بررسی مدیر لازم است.')
    needsRepair = not openMemberships or openMemberships[0].status != 'active'
    if needsRepair:
        if data.get('repairMembership') is not True:
            raise ValidationFailedError('عضویت فعال همین سازمان پیدا نشد؛ تیک «ترمیم عضویت همین سازمان در صورت نیاز» را با بررسی نقش‌ها تأیید کنید.')
        _authorizeUnderLock('user.assignTenant', user.tenantId)
    now=timezone.now()
    if user.expiresAt is not None and user.expiresAt <= now:
        raise PermissionDeniedError('اعتبار زمانی حساب منقضی است؛ بازگردانی آن را تمدید نمی‌کند.')
    if user.lockedUntil is not None and user.lockedUntil > now:
        raise PermissionDeniedError('حساب موقتاً قفل است؛ پس از پایان قفل دوباره اقدام کنید.')
    membershipAction = 'unchanged'
    if needsRepair:
        if openMemberships:
            # A suspended, not-ended membership is resumed in place.
            membership = openMemberships[0]
            if TenantMembershipModel.objects.filter(id=membership.id,status='suspended',leftAt__isnull=True).update(status='active') != 1:
                raise ConflictError('عضویت هم‌زمان تغییر کرده؛ صفحه را تازه کنید.')
            membershipAction = 'reactivated'
        else:
            # Ended/removed history stays immutable. No role or other-tenant grant is added.
            primaryExists = TenantMembershipModel.objects.filter(userId=user.id,isPrimary=True,status='active',leftAt__isnull=True).exists()
            membership = TenantMembershipModel.objects.create(userId=user.id,tenantId=user.tenantId,status='active',isPrimary=not primaryExists,defaultRole='member')
            membershipAction = 'rejoined' if memberships.exclude(id=membership.id).exists() else 'created'
    else:
        membership = openMemberships[0]
    changed=UserModel.objects.filter(id=user.id,status='disabled',deletedAt__isnull=True,kind='human').update(status='active',updatedAt=now)
    if changed!=1:
        raise ConflictError('وضعیت حساب تغییر کرده؛ صفحه را تازه‌سازی کنید.')
    SessionModel.objects.filter(userId=user.id,revokedAt__isnull=True).update(revokedAt=now)
    ApiKeyModel.objects.filter(ownerId=user.id,ownerType='user',revokedAt__isnull=True).update(revokedAt=now)
    from apps.identity.infrastructure.services.authorizationCache import bumpVersion
    bumpVersion(user.id)
    audit('user.restoreArchive','User',user.id,user.tenantId,{'from':'disabled','to':'active','samePersonRetained':True,'oldSessionsAndApiKeysRevoked':True,'membershipAction':membershipAction,'membershipId':str(membership.id)})
    return {'changed':True,'restored':True,'userId':str(user.id),'username':user.username,'membershipAction':membershipAction}


def roleOperation(data):
    from apps.identity.infrastructure import container
    from apps.identity.application.commands.identityCommands import CreateRoleCommand, UpdateRoleCommand, DeleteRoleCommand
    with lockedAdministrationState():
        requireFreshAdministrator()
        operation = data.get('operation')
        actions = data.get('actions', [])
        if not isinstance(actions, list) or len(actions) > 1000 or any(not isinstance(x, str) or len(x) > 64 for x in actions):
            raise ValidationFailedError('فهرست اختیارات معتبر نیست.')
        if operation == 'create':
            result = container.createRoleUseCase().execute(CreateRoleCommand(code=_text(data, 'code', 64), name=_text(data, 'name', 160), actions=actions))
        elif operation == 'update':
            result = container.updateRoleUseCase().execute(UpdateRoleCommand(roleId=str(_uuid(data.get('roleId'))), name=_text(data, 'name', 160), actions=actions))
        elif operation == 'delete':
            result = container.deleteRoleUseCase().execute(DeleteRoleCommand(roleId=str(_uuid(data.get('roleId')))))
        else:
            raise ValidationFailedError('عملیات نقش معتبر نیست.')
        return {'changed': True}


def validateAppearance(data):
    name = _text(data, 'displayName', 160)
    color = _text(data, 'primaryColor', 7)
    if not re.fullmatch(r'#[0-9A-Fa-f]{6}', color) or data.get('theme') not in {'warm', 'light', 'forest'}:
        raise ValidationFailedError('رنگ یا قالب معتبر نیست.')
    logo = data.get('logoData', '')
    if not isinstance(logo, str) or len(logo) > 750000:
        raise ValidationFailedError('لوگو باید تصویر PNG یا JPEG با حجم حداکثر ۵۰۰ کیلوبایت باشد.')
    if logo:
        match = re.fullmatch(r'data:image/(png|jpeg);base64,([A-Za-z0-9+/=]+)', logo)
        if not match:
            raise ValidationFailedError('فرمت لوگو PNG یا JPEG باشد؛ SVG یا آدرس خارجی مجاز نیست.')
        try:
            from PIL import Image
            raw = base64.b64decode(match[2], validate=True)
            if len(raw) > 512000:
                raise ValueError()
            with Image.open(BytesIO(raw)) as image:
                if image.format != {'png': 'PNG', 'jpeg': 'JPEG'}[match[1]] or max(image.size) > 4096 or min(image.size) < 1:
                    raise ValueError()
                image.verify()
        except Exception as exc:
            raise ValidationFailedError('فایل لوگو تصویر معتبر یا اندازه مجاز نیست.') from exc
    return {'displayName': name, 'primaryColor': color.lower(), 'theme': data['theme'], 'logoData': logo}


def tenantOperation(data):
    from apps.identity.infrastructure.services.authorizationCache import bumpVersion
    from apps.identity.infrastructure.repositories.identityRepositoriesImpl import AccessRepositoryDjango
    with lockedAdministrationState():
        requireFreshAdministrator()
        operation = data.get('operation')
        action = {'create':'tenant.create','suspend':'tenant.suspend','activate':'tenant.activate','close':'tenant.close','appearance':'tenant.view','assignManager':'user.assignRole','removeManager':'user.assignRole'}.get(operation)
        if action is None:
            raise ValidationFailedError('عملیات سازمان معتبر نیست.')
        _requireAction(action)
        if operation == 'create':
            code = _text(data, 'code', 64).lower()
            if not re.fullmatch(r'[a-z][a-z0-9-]{1,63}', code):
                raise ValidationFailedError('کد سازمان باید انگلیسی و یکتا باشد.')
            if TenantModel.objects.filter(code=code).exists():
                raise ConflictError('کد سازمان تکراری است.')
            tenant = TenantModel.objects.create(code=code, name=_text(data, 'name', 160))
        else:
            tenant = TenantModel.objects.filter(id=_uuid(data.get('tenantId')), deletedAt__isnull=True).first()
            if tenant is None:
                raise EntityNotFoundError('Tenant', str(data.get('tenantId')))
        if operation in {'suspend', 'close'}:
            # A tenant suspension removes every owner with that home tenant.
            owners = set(UserModel.objects.filter(tenantId=tenant.id).values_list('id', flat=True))
            if not usableAdministratorOwners(excludingOwners=owners):
                raise PermissionDeniedError('سازمان آخرین مدیر قابل استفاده را نمی‌توان بست یا متوقف کرد.')
            if UserModel.objects.filter(id=currentContext().actorId, tenantId=tenant.id).exists():
                raise PermissionDeniedError('سازمان حساب مدیریتی جاری را از نشست خودش متوقف نکنید.')
            tenant.status = 'suspended' if operation == 'suspend' else 'closed'
            SessionModel.objects.filter(tenantId=tenant.id, revokedAt__isnull=True).update(revokedAt=timezone.now())
        elif operation == 'activate':
            if tenant.status == 'closed':
                raise ValidationFailedError('سازمان بسته‌شده مطابق چرخه وضعیت قابل فعال‌سازی مجدد نیست.')
            tenant.status = 'active'
        elif operation == 'appearance':
            appearance = validateAppearance(data)
            previous = TenantAppearanceModel.objects.filter(tenantId=tenant.id).first()
            if data.get('revision') != (previous.revision if previous else 0):
                raise ConflictError('ظاهر سازمان تغییر کرده است؛ صفحه را تازه کنید.')
            appearance['revision'] = (previous.revision if previous else 0) + 1
            TenantAppearanceModel.objects.update_or_create(tenantId=tenant.id, defaults=appearance)
            tenant.name = appearance['displayName']
        elif operation in {'assignManager', 'removeManager'}:
            user = UserModel.objects.filter(id=_uuid(data.get('userId')), tenantId=tenant.id, status='active', deletedAt__isnull=True).first()
            if user is None:
                raise ValidationFailedError('مدیر باید یک کاربر فعال همین سازمان باشد؛ شخص دیگری نسازید.')
            role = RoleModel.objects.get(code='tenantAdmin', scopeType='TENANT', isActive=True)
            from apps.identity.infrastructure import container
            from apps.identity.application.commands.identityCommands import AssignRoleCommand, RemoveRoleCommand
            if operation == 'assignManager':
                container.assignRoleUseCase().execute(AssignRoleCommand(userId=str(user.id), roleId=str(role.id), tenantId=str(tenant.id)))
            else:
                from apps.identity.infrastructure.services.administrativeGovernance import guardAccountMutation
                # Keep at least one active scoped manager while the organization is active.
                managerIds = UserRoleModel.objects.filter(roleId=role.id, tenantId=tenant.id).exclude(userId=user.id).values('userId')
                if tenant.status == 'active' and not UserModel.objects.filter(id__in=managerIds, status='active', deletedAt__isnull=True).exists():
                    raise PermissionDeniedError('ابتدا مدیر جایگزین سازمان را تعیین کنید.')
                container.removeRoleUseCase().execute(RemoveRoleCommand(userId=str(user.id), roleId=str(role.id)))
            bumpVersion(user.id)
        elif operation != 'create':
            raise ValidationFailedError('عملیات سازمان معتبر نیست.')
        tenant.updatedAt = timezone.now()
        tenant.save()
        audit('tenant.' + operation, 'Tenant', tenant.id, tenant.id,
              {'userId': str(data.get('userId', ''))} if operation in {'assignManager', 'removeManager'} else {'revision': tenantDto(tenant)['appearance']['revision']})
        return tenantDto(tenant)


_referenceReviewActive = ContextVar('identity_serializable_reference_review', default=False)


@contextmanager
def serializableReferenceReview():
    if _referenceReviewActive.get():
        yield
        return
    # SQL Server range locks protect reference evidence until commit. Never lower
    # an unknown caller-owned transaction's isolation or restore before commit.
    if connection.vendor == 'sqlite':
        yield  # The governance UPDATE holds SQLite's single writer lock.
        return
    if connection.vendor not in {'microsoft', 'mssql'} or connection.in_atomic_block:
        raise PermissionDeniedError('تراکنش مستقل و بررسی سریالی برای حذف لازم است؛ بایگانی کنید.')
    levels = {1:'READ UNCOMMITTED',2:'READ COMMITTED',3:'REPEATABLE READ',4:'SERIALIZABLE',5:'SNAPSHOT'}
    with connection.cursor() as cursor:
        cursor.execute('SELECT transaction_isolation_level FROM sys.dm_exec_sessions WHERE session_id=@@SPID')
        row = cursor.fetchone()
        if not row or row[0] not in levels:
            raise PermissionDeniedError('سطح تراکنش قابل اثبات نیست؛ حذف مسدود است.')
        previous = levels[row[0]]
        cursor.execute('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE')
    token = _referenceReviewActive.set(True)
    try:
        yield
    finally:
        _referenceReviewActive.reset(token)
        try:
            with connection.cursor() as cursor:
                cursor.execute('SET TRANSACTION ISOLATION LEVEL ' + previous)
        except Exception:
            connection.close()
            raise


def permanentDelete(data):
    """Permanent credential/contact erasure, retaining ONLY a technical tombstone.
    No physical UUID removal: business contexts use non-FK UUID references. All
    ambiguous evidence fails closed; known history means archive, never erasure.
    """
    with serializableReferenceReview(), lockedAdministrationState():
        requireFreshAdministrator()
        user = guardAccountMutation(_uuid(data.get('userId')), 'delete')
        if protectedOwner(user.id) or user.status != 'disabled' or user.lastLoginAt is not None:
            raise PermissionDeniedError('فقط حساب بایگانی‌شده، هرگز واردنشده و غیرمدیریتی بدون سابقه قابل حذف اطلاعات است.')
        if data.get('confirmation') != user.username or data.get('confirm') is not True:
            raise ValidationFailedError('نام کاربری و تأیید دوم حذف را وارد کنید.')
        # Every non-identity registered model is scanned, including audit actors.
        # UUID, text, JSON and relation references are inspected. Missing tables,
        # unsupported lookups, unknown field storage or any match mean refusal.
        values = [str(user.id), user.id.hex]
        try:
            registered = list(apps.get_models(include_auto_created=True))
            knownTables = {m._meta.db_table for m in registered if m._meta.managed and not m._meta.proxy}
            if set(connection.introspection.table_names()) - knownTables - {'django_migrations'}:
                raise PermissionDeniedError('جدول خارج از مدل‌های بررسی‌شده وجود دارد؛ حذف مسدود است و بایگانی مجاز است.')
            for model in registered:
                if model._meta.app_label in {'identity', 'contenttypes', 'auth', 'sessions', 'admin'} or model._meta.proxy or not model._meta.managed:
                    continue
                query = Q()
                checked = False
                for field in model._meta.concrete_fields:
                    if field.name in {'tenantId', 'correlationId', 'requestId'}:
                        continue
                    if model._meta.db_table == 'AuditEvent' and field.name != 'actorUserId':
                        continue  # Account creation/reset audits are retained, not personal activity.
                    if isinstance(field, models.BinaryField) and model.objects.exists():
                        raise PermissionDeniedError('بررسی سابقه داده دودویی کامل نیست؛ فقط بایگانی مجاز است.')
                    if isinstance(field, models.ForeignKey) and isinstance(field.target_field, models.UUIDField):
                        query |= Q(**{field.name: user.id}); checked = True
                    elif isinstance(field, models.UUIDField):
                        query |= Q(**{field.name: user.id}); checked = True
                    elif isinstance(field, (models.CharField, models.TextField, models.JSONField)):
                        for value in values:
                            query |= Q(**{field.name + '__icontains': value})
                        checked = True
                if checked and model.objects.filter(query).exists():
                    raise PermissionDeniedError('این حساب سابقه یا ارجاع دارد؛ فقط بایگانی مجاز است.')
        except PermissionDeniedError:
            raise
        except Exception as exc:
            raise PermissionDeniedError('اثبات نبود سابقه کامل نشد؛ حذف مسدود است و بایگانی در دسترس می‌ماند.') from exc
        # Identity activity other than never-used memberships/grants also prevents deletion.
        if SessionModel.objects.filter(userId=user.id).exists() or ApiKeyModel.objects.filter(ownerId=user.id).exists():
            raise PermissionDeniedError('حساب سابقه ورود یا کلید دسترسی دارد؛ بایگانی کنید.')
        UserRoleModel.objects.filter(userId=user.id).delete()
        UserPermissionModel.objects.filter(userId=user.id).delete()
        MobileAccountModel.objects.filter(userId=user.id).delete()
        PasswordHistoryModel.objects.filter(userId=user.id).delete()
        TenantMembershipModel.objects.filter(userId=user.id).delete()
        marker = 'deleted-' + user.id.hex
        UserModel.objects.filter(id=user.id).update(username=marker, email=marker, phone='', displayName='حساب حذف‌شده',
            passwordHash='!', deletedAt=timezone.now(), updatedAt=timezone.now())
        audit('erase', 'User', user.id, user.tenantId, {'technicalTombstoneRetained': True})
        return {'deleted': True, 'technicalTombstoneRetained': True}


def identityOperation(data):
    from apps.identity.domain.valueObjects.userState import validatePasswordStrength
    with lockedAdministrationState():
        actor = requireFreshAdministrator()
        _requireAction('user.assignRole')
        operation = data.get('operation')
        owner = UserModel.objects.filter(id=_uuid(data.get('userId')), deletedAt__isnull=True).first()
        if owner is None:
            raise ValidationFailedError('مالک باید یک فرد فعال موجود باشد.')
        if operation != 'disable' and owner.status != 'active':
            raise ValidationFailedError('برای ایجاد، بازنشانی یا فعال‌سازی ورود، مالک باید فعال باشد.')
        if owner.id == actor.ownerUserId:
            raise PermissionDeniedError('تغییر مدیریتی ورود کل خودتان مجاز نیست؛ از مدیر مستقل دیگری کمک بگیرید.')
        identity = AdministrativeIdentityModel.objects.filter(ownerUserId=owner.id).first()
        if operation == 'create':
            if identity or not owner.phone or MobileAccountModel.objects.filter(userId=owner.id, mustChangePassword=True).exists():
                raise ValidationFailedError('مالک باید موبایل یکتا و رمز شخصی تکمیل‌شده داشته باشد و ورود کل دیگری نداشته باشد.')
            from apps.identity.infrastructure.services.mobileOnboarding import normalizeMobile
            phone = normalizeMobile(owner.phone)
            if not MobileAccountModel.objects.filter(userId=owner.id, phone=phone, mustChangePassword=False).exists():
                raise ValidationFailedError('ابتدا موبایل یکتای مالک را در حساب اصلی تکمیل کنید.')
            if not TenantModel.objects.filter(id=owner.tenantId, status='active', deletedAt__isnull=True).exists() or not TenantMembershipModel.objects.filter(userId=owner.id, tenantId=owner.tenantId, status='active', leftAt__isnull=True).exists():
                raise ValidationFailedError('سازمان و عضویت مالک باید فعال باشد.')
            username = _text(data, 'username', 64).lower()
            if not re.fullmatch(r'[a-z][a-z0-9._-]{2,63}', username) or AdministrativeIdentityModel.objects.filter(username=username).exists():
                raise ValidationFailedError('نام کاربری مدیریت باید انگلیسی و یکتا باشد.')
            identity = AdministrativeIdentityModel(ownerUserId=owner.id, username=username, createdByUserId=actor.ownerUserId)
        elif identity is None:
            raise EntityNotFoundError('AdministrativeIdentity', str(owner.id))
        if operation in {'create', 'reset'}:
            password = data.get('temporaryPassword', '')
            if not isinstance(password, str) or len(password) > 200:
                raise ValidationFailedError('رمز موقت معتبر نیست.')
            validatePasswordStrength(password)
            if check_password(password, owner.passwordHash) or (identity.passwordHash and check_password(password, identity.passwordHash)):
                raise ValidationFailedError('رمز موقت جدید باید از رمزهای موجود متفاوت باشد.')
            if identity.passwordHash:
                AdministrativePasswordHistoryModel.objects.create(administrativeIdentityId=identity.id, passwordHash=identity.passwordHash)
            identity.passwordHash = make_password(password)
            identity.mustChangePassword = True
            identity.temporaryExpiresAt = timezone.now() + timedelta(hours=24)
            identity.mfaSecretRef = ''
            identity.mfaConfirmedAt = None
            AdministrativeRecoveryCodeModel.objects.filter(administrativeIdentityId=identity.id).delete()
            identity.failedLoginCount = 0
            identity.lockedUntil = None
            identity.status = 'active'
        elif operation in {'disable', 'activate'}:
            identity.status = 'disabled' if operation == 'disable' else 'active'
        else:
            raise ValidationFailedError('عملیات ورود کل معتبر نیست.')
        if operation in {'reset', 'disable'} and not usableAdministratorOwners(excludingOwners={owner.id}):
            raise PermissionDeniedError('آخرین مسیر مدیریت قابل حذف یا بازنشانی نیست.')
        identity.save()
        if operation != 'create':
            ids = AdministrativeSessionModel.objects.filter(administrativeIdentityId=identity.id).values('sessionId')
            SessionModel.objects.filter(id__in=ids, revokedAt__isnull=True).update(revokedAt=timezone.now())
        audit('identity.' + operation, 'AdministrativeIdentity', identity.id, owner.tenantId, {'ownerUserId': str(owner.id)})
        return {'changed': True, 'username': identity.username}
