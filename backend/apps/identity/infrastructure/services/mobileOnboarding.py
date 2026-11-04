"""Admin-only mobile onboarding; plaintext temporary credentials are returned once, never stored/logged."""
from __future__ import annotations
import dataclasses, hashlib, re, secrets, uuid
from datetime import timedelta
from contextlib import contextmanager
from django.core import signing
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone
from apps.identity.application.dto.identityDtos import userDtoFromDomain
from apps.identity.domain.entities.user import User
from apps.identity.domain.valueObjects.userState import validatePasswordStrength
from apps.identity.infrastructure.models import MobileAccountModel, UserModel, TenantMembershipModel, SessionModel, PasswordHistoryModel
from apps.identity.infrastructure.repositories.identityRepositoriesImpl import UserRepositoryDjango
from apps.identity.infrastructure.services.passwordHasherImpl import PasswordHasherDjango
from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.domain.errors import AuthenticationRequiredError, InvalidCredentialsError, DuplicateIdentifierError, EntityNotFoundError, PermissionDeniedError, ValidationFailedError
from apps.sharedKernel.infrastructure.wiring import sharedKernelProvider

SALT = 'tekarai.first-password.v1'
TEMP_TTL_HOURS = 24

def normalizeMobile(raw):
    value = str(raw).translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789'))
    value = re.sub(r'[\s()\-]', '', value)
    if value.startswith('+98'): value = '0' + value[3:]
    elif value.startswith('0098'): value = '0' + value[4:]
    elif value.startswith('98') and len(value) == 12: value = '0' + value[2:]
    if not re.fullmatch(r'09[0-9]{9}', value):
        raise ValidationFailedError('شمارهٔ موبایل معتبر وارد کنید؛ مانند 09123456789.', fieldErrors={'phone': 'invalid'})
    return value

def _authorize(action):
    context = currentContext()
    tenant = context.tenantId or context.actorTenantId
    if not context.actorId or not tenant:
        raise PermissionDeniedError(action=action)
    gate = sharedKernelProvider('permissionGate')()
    if not gate.hasPermission(uuid.UUID(context.actorId), action, tenantId=uuid.UUID(context.actorTenantId or tenant), targetTenantId=uuid.UUID(tenant)):
        raise PermissionDeniedError(action=action)
    return uuid.UUID(tenant)

def _audit(user, operation):
    sharedKernelProvider('auditRecorder')().record(action='UPDATE' if operation != 'created' else 'CREATE', resourceType='User', resourceId=str(user.id), tenantId=user.tenantId, before=None, after={'operation': 'mobileOnboarding.' + operation})

def _tenantCode(user):
    from apps.tenancy.infrastructure.repositories.tenantRepositoryImpl import TenantRepositoryDjango
    tenant = TenantRepositoryDjango().getById(user.tenantId)
    return str(tenant.code) if tenant else ''

def _secret():
    return secrets.token_urlsafe(20) + 'aA!7'

def _dto(user):
    return dataclasses.asdict(userDtoFromDomain(UserRepositoryDjango.toDomain(user)))

def _lockUser(userId):
    UserModel.objects.filter(id=userId).update(updatedAt=F('updatedAt'))

def lockAccountForLogin(tenantId, identifier):
    value = identifier.strip().lower()
    UserModel.objects.filter(tenantId=tenantId, deletedAt__isnull=True).filter(Q(username=value) | Q(email=value)).update(updatedAt=F('updatedAt'))

@contextmanager
def serializedAccount(tenantId, identifier):
    with transaction.atomic():
        lockAccountForLogin(tenantId, identifier)
        yield

def denyPendingAccess(userId):
    if MobileAccountModel.objects.filter(userId=userId, mustChangePassword=True).exists():
        raise AuthenticationRequiredError('برای ورود، ابتدا رمز موقت را تغییر دهید.')

def passwordChallenge(userId, passwordHash, now):
    state = MobileAccountModel.objects.filter(userId=userId, mustChangePassword=True).first()
    if state is None: return ''
    if not state.temporaryExpiresAt or state.temporaryExpiresAt <= now:
        raise InvalidCredentialsError('رمز موقت منقضی شده است؛ از مدیر رمز جدید بگیرید.')
    return signing.dumps({'u': str(userId), 'h': hashlib.sha256(passwordHash.encode()).hexdigest()}, salt=SALT)

def clearPending(userId):
    MobileAccountModel.objects.filter(userId=userId).update(mustChangePassword=False, temporaryExpiresAt=None)

def createMobileAccount(*, phone, displayName, email, username=''):
    tenant = _authorize('user.create')
    phone = normalizeMobile(phone)
    if not displayName.strip(): raise ValidationFailedError('نام و نام خانوادگی الزامی است.')
    username = (username.strip().lower() or 'u' + phone)
    if len(username) > 64: raise ValidationFailedError('نام کاربری طولانی است.')
    raw = _secret(); now = timezone.now(); expires = now + timedelta(hours=TEMP_TTL_HOURS)
    repo = UserRepositoryDjango()
    try:
        with transaction.atomic():
            if MobileAccountModel.objects.filter(phone=phone).exists():
                raise DuplicateIdentifierError('این شمارهٔ موبایل قبلاً ثبت شده است؛ حساب قبلی را ویرایش کنید.', details={'field': 'phone'})
            if repo.existsByUsername(tenant, username) or repo.existsByEmail(tenant, email.strip().lower()):
                raise DuplicateIdentifierError('نام کاربری یا ایمیل قبلاً ثبت شده است.')
            user = User.register(tenantId=tenant, username=username, email=email, passwordHash=PasswordHasherDjango().hash(raw), displayName=displayName, now=now, phone=phone)
            repo.create(user)
            MobileAccountModel.objects.create(userId=user.id, phone=phone, mustChangePassword=True, temporaryExpiresAt=expires)
            TenantMembershipModel.objects.create(userId=user.id, tenantId=tenant, isPrimary=True)
            model = UserModel.objects.get(id=user.id)
            _audit(model, 'created')
            events = user.pullEvents()
            transaction.on_commit(lambda: [sharedKernelProvider('eventDispatcher')().dispatch(event) for event in events])
            result = {'user': _dto(model), 'temporaryPassword': raw, 'temporaryExpiresAt': expires.isoformat(), 'tenantCode': _tenantCode(model)}
    except IntegrityError as error:
        raise DuplicateIdentifierError('شمارهٔ موبایل، نام کاربری یا ایمیل تکراری است.') from error
    return result

def updateMobile(userId, phone):
    tenant = _authorize('user.update'); phone = normalizeMobile(phone)
    try:
        with transaction.atomic():
            _lockUser(userId)
            user = UserModel.objects.filter(id=userId, tenantId=tenant, deletedAt__isnull=True, kind='human').first()
            if user is None: raise EntityNotFoundError('User', str(userId))
            state = MobileAccountModel.objects.filter(userId=user.id).first()
            if state: state.phone = phone; state.save(update_fields=['phone', 'updatedAt'])
            else: MobileAccountModel.objects.create(userId=user.id, phone=phone)
            UserModel.objects.filter(id=user.id).update(phone=phone, updatedAt=timezone.now())
            user.phone = phone; _audit(user, 'phoneChanged')
            return _dto(user)
    except IntegrityError as error:
        raise DuplicateIdentifierError('این شمارهٔ موبایل برای حساب دیگری ثبت شده است.', details={'field': 'phone'}) from error

def issueTemporaryPassword(userId):
    tenant = _authorize('user.update')
    if str(userId) == str(currentContext().actorId):
        raise ValidationFailedError('برای حساب خودتان از تغییر رمز عبور استفاده کنید.')
    with transaction.atomic():
        _lockUser(userId)
        user = UserModel.objects.filter(id=userId, tenantId=tenant, status='active', kind='human', deletedAt__isnull=True).first()
        if user is None: raise EntityNotFoundError('User', str(userId))
        state = MobileAccountModel.objects.filter(userId=user.id).first()
        if not state: raise ValidationFailedError('ابتدا شمارهٔ موبایل این فرد را ثبت کنید.')
        raw = _secret(); now = timezone.now(); expires = now + timedelta(hours=TEMP_TTL_HOURS)
        PasswordHistoryModel.objects.create(userId=user.id, passwordHash=user.passwordHash)
        UserModel.objects.filter(id=user.id).update(passwordHash=PasswordHasherDjango().hash(raw), passwordChangedAt=now, failedLoginCount=0, lockedUntil=None, updatedAt=now)
        state.mustChangePassword = True; state.temporaryExpiresAt = expires; state.save()
        SessionModel.objects.filter(userId=user.id, revokedAt__isnull=True).update(revokedAt=now)
        _audit(user, 'temporaryPasswordIssued')
        return {'user': _dto(user), 'temporaryPassword': raw, 'temporaryExpiresAt': expires.isoformat(), 'tenantCode': _tenantCode(user)}

def completeFirstPassword(challenge, newPassword):
    try: payload = signing.loads(challenge, salt=SALT, max_age=600); userId = uuid.UUID(payload['u'])
    except (signing.BadSignature, ValueError, KeyError, TypeError): raise InvalidCredentialsError('درخواست نامعتبر یا منقضی شده است؛ دوباره وارد شوید.')
    validatePasswordStrength(newPassword)
    with transaction.atomic():
        _lockUser(userId)
        user = UserModel.objects.filter(id=userId, status='active', deletedAt__isnull=True).first()
        state = MobileAccountModel.objects.filter(userId=userId, mustChangePassword=True).first()
        now = timezone.now()
        if not user or not state or not state.temporaryExpiresAt or state.temporaryExpiresAt <= now or not secrets.compare_digest(payload.get('h', ''), hashlib.sha256(user.passwordHash.encode()).hexdigest()):
            raise InvalidCredentialsError('درخواست نامعتبر یا منقضی شده است؛ دوباره وارد شوید.')
        if user.expiresAt and user.expiresAt <= now: raise AuthenticationRequiredError('حساب منقضی شده است.')
        if user.lockedUntil and user.lockedUntil > now: raise AuthenticationRequiredError('حساب موقتاً قفل است.')
        if not TenantMembershipModel.objects.filter(userId=user.id, tenantId=user.tenantId, status='active').exists(): raise AuthenticationRequiredError()
        hasher = PasswordHasherDjango()
        history = list(PasswordHistoryModel.objects.filter(userId=user.id).order_by('-createdAt').values_list('passwordHash', flat=True)[:5])
        if any(hasher.verify(newPassword, value) for value in [user.passwordHash, *history]):
            raise ValidationFailedError('رمز جدید باید با رمز موقت و رمزهای قبلی متفاوت باشد.')
        PasswordHistoryModel.objects.create(userId=user.id, passwordHash=user.passwordHash)
        UserModel.objects.filter(id=user.id).update(passwordHash=hasher.hash(newPassword), passwordChangedAt=now, failedLoginCount=0, lockedUntil=None, updatedAt=now)
        clearPending(user.id)
        SessionModel.objects.filter(userId=user.id, revokedAt__isnull=True).update(revokedAt=now)
        _audit(user, 'firstPasswordChanged')
    return {'changed': True}
