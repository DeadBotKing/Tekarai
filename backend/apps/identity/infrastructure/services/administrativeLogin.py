"""Independent administrative password -> mandatory MFA -> bound session.

No primary password writes, no implicit role grants and no automatic retirement.
Every mutation uses the same database-owned global governance lock. TOTP replay
receipts live in the database (not a process-local cache).
"""
import dataclasses
import hashlib
import secrets
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.core import signing
from django.utils import timezone

from apps.identity.domain.services.totpService import generateSecret, currentCode, otpauthUrl
from apps.identity.domain.valueObjects.userState import validatePasswordStrength
from apps.identity.infrastructure.models import (
    AdministrativeIdentityModel as Identity, AdministrativeSessionModel as Binding,
    AdministrativeRecoveryCodeModel as Recovery, AdministrativePasswordHistoryModel as History,
    UserModel, SessionModel, TenantMembershipModel, MobileAccountModel,
)
from apps.identity.infrastructure.services.administrationLock import lockedAdministrationState
from apps.identity.infrastructure.services.administrativeAuthentication import (
    ADMINISTRATIVE_DEVICE, EncryptedAdministrativeSecretVault, credentialBinding,
)
from apps.sharedKernel.domain.errors import AuthenticationRequiredError, InvalidCredentialsError, ValidationFailedError

SALT = 'tekarai.independent.administration.login.v1'
VAULT = EncryptedAdministrativeSecretVault()


def _owner(identity, now):
    from apps.tenancy.infrastructure.models import TenantModel
    owner = UserModel.objects.filter(id=identity.ownerUserId, status='active', deletedAt__isnull=True).first()
    if (owner is None or identity.status != 'active'
            or (identity.lockedUntil is not None and identity.lockedUntil > now)
            or (owner.expiresAt is not None and owner.expiresAt <= now)
            or (owner.lockedUntil is not None and owner.lockedUntil > now)):
        raise InvalidCredentialsError('اطلاعات ورود مدیریت معتبر نیست.')
    if not TenantModel.objects.filter(id=owner.tenantId, status='active', deletedAt__isnull=True).exists():
        raise AuthenticationRequiredError('سازمان مالک فعال نیست.')
    if not TenantMembershipModel.objects.filter(userId=owner.id, tenantId=owner.tenantId,
                                               status='active', leftAt__isnull=True).exists():
        raise AuthenticationRequiredError('عضویت مالک فعال نیست.')
    if MobileAccountModel.objects.filter(userId=owner.id, mustChangePassword=True).exists():
        raise AuthenticationRequiredError('ابتدا رمز شخصی حساب اصلی را تعیین کنید.')
    if identity.mustChangePassword and (identity.temporaryExpiresAt is None or identity.temporaryExpiresAt <= now):
        raise AuthenticationRequiredError('رمز موقت مدیریت منقضی شده است.')
    return owner


def _proofBinding(identity, owner):
    return hashlib.sha256((identity.passwordHash + '\x00' + owner.passwordHash).encode()).hexdigest()


def _challenge(identity, owner, step):
    payload = {'identity': str(identity.id), 'binding': _proofBinding(identity, owner),
               'step': step, 'nonce': secrets.token_urlsafe(24)}
    if step in ('enroll', 'mfa'):
        payload['factor'] = hashlib.sha256(identity.mfaSecretRef.encode()).hexdigest()
    result = {'step': step, 'challenge': signing.dumps(payload, salt=SALT)}
    if step == 'enroll':
        secret = VAULT.reveal(identity.mfaSecretRef)
        result.update(secret=secret, otpauthUrl=otpauthUrl(secret, identity.username, issuer='Tekarai Superadmin'))
    return result


def _next(identity, owner):
    if identity.mustChangePassword:
        return _challenge(identity, owner, 'password')
    if identity.mfaConfirmedAt is None:
        identity.mfaSecretRef = VAULT.protect(generateSecret())
        identity.save(update_fields=['mfaSecretRef', 'updatedAt'])
        return _challenge(identity, owner, 'enroll')
    return _challenge(identity, owner, 'mfa')


def login(username, password):
    if not isinstance(username, str) or not isinstance(password, str) or len(username) > 64 or len(password) > 1024:
        raise InvalidCredentialsError('اطلاعات ورود مدیریت معتبر نیست.')
    failed = False
    with lockedAdministrationState():
        now = timezone.now()
        identity = Identity.objects.filter(username=username.strip()).first()
        if identity is None:
            check_password(password, make_password(secrets.token_urlsafe(32)))
            failed = True
        else:
            owner = _owner(identity, now)
            if not check_password(password, identity.passwordHash):
                identity.failedLoginCount += 1
                if identity.failedLoginCount >= 5:
                    identity.lockedUntil = now + timedelta(minutes=15)
                identity.save(update_fields=['failedLoginCount', 'lockedUntil', 'updatedAt'])
                failed = True
            else:
                # Password knowledge alone must NOT reset MFA failure counters.
                result = _next(identity, owner)
    # Deliberately outside atomic(): failure counters must survive the exception.
    if failed:
        raise InvalidCredentialsError('اطلاعات ورود مدیریت معتبر نیست.')
    return result


def _load(token, expected):
    try:
        data = signing.loads(token, salt=SALT, max_age=600)
        if not isinstance(data, dict) or data.get('step') not in expected:
            raise ValueError()
        identity = Identity.objects.get(id=data['identity'])
        owner = _owner(identity, timezone.now())
        if not secrets.compare_digest(data['binding'], _proofBinding(identity, owner)):
            raise ValueError()
        if data['step'] in ('enroll', 'mfa'):
            if not secrets.compare_digest(data['factor'], hashlib.sha256(identity.mfaSecretRef.encode()).hexdigest()):
                raise ValueError()
        receipt = hashlib.sha256(('login-proof.v1:' + token).encode()).hexdigest()
        if Recovery.objects.filter(codeHash=receipt).exists():
            raise ValueError()
        return identity, owner, data['step']
    except (signing.BadSignature, ValueError, KeyError, TypeError, Identity.DoesNotExist) as exc:
        raise AuthenticationRequiredError('درخواست ورود مدیریت منقضی یا نامعتبر است.') from exc


def changeFirstPassword(token, personalPassword):
    if not isinstance(personalPassword, str) or len(personalPassword) > 1024:
        raise ValidationFailedError('رمز شخصی معتبر نیست.')
    validatePasswordStrength(personalPassword)
    with lockedAdministrationState():
        identity, owner, _ = _load(token, {'password'})
        if not identity.mustChangePassword:
            raise AuthenticationRequiredError('درخواست تغییر رمز قبلاً استفاده شده است.')
        prior = [identity.passwordHash, owner.passwordHash]
        prior.extend(History.objects.filter(administrativeIdentityId=identity.id).values_list('passwordHash', flat=True)[:6])
        if any(check_password(personalPassword, value) for value in prior):
            raise ValidationFailedError('رمز مدیریت باید از رمز موقت، رمز حساب اصلی و رمزهای قبلی متفاوت باشد.')
        History.objects.create(administrativeIdentityId=identity.id, passwordHash=identity.passwordHash)
        identity.passwordHash = make_password(personalPassword)
        identity.mustChangePassword = False
        identity.temporaryExpiresAt = None
        identity.passwordChangedAt = timezone.now()
        identity.save()
        return _next(identity, owner)


def _consumeCode(identity, raw, now, *, allowRecovery):
    if not isinstance(raw, str) or len(raw) > 100:
        return False
    raw = raw.strip().replace(' ', '')
    if len(raw) == 6 and raw.isascii() and raw.isdigit():
        secret = VAULT.reveal(identity.mfaSecretRef)
        counter = int(now.timestamp()) // 30
        for drift in (-1, 0, 1):
            step = counter + drift
            if secrets.compare_digest(currentCode(secret, at=step * 30), raw):
                receipt = hashlib.sha256(f'totp-step.v1:{identity.id}:{step}'.encode()).hexdigest()
                if Recovery.objects.filter(codeHash=receipt).exists():
                    return False
                Recovery.objects.create(administrativeIdentityId=identity.id, codeHash=receipt, usedAt=now)
                return True
    if allowRecovery:
        digest = hashlib.sha256(f'recovery.v1:{identity.id}:{raw}'.encode()).hexdigest()
        return Recovery.objects.filter(administrativeIdentityId=identity.id, codeHash=digest,
                                       usedAt__isnull=True).update(usedAt=now) == 1
    return False


def verifyMfa(token, code):
    failed = False
    with lockedAdministrationState():
        identity, owner, step = _load(token, {'enroll', 'mfa'})
        now = timezone.now()
        if identity.mustChangePassword:
            raise AuthenticationRequiredError('ابتدا رمز شخصی مدیریت را تعیین کنید.')
        if (step == 'enroll') != (identity.mfaConfirmedAt is None):
            raise AuthenticationRequiredError('درخواست تأیید معتبر نیست.')
        if not _consumeCode(identity, code, now, allowRecovery=step == 'mfa'):
            identity.failedLoginCount += 1
            if identity.failedLoginCount >= 5:
                identity.lockedUntil = now + timedelta(minutes=15)
            identity.save(update_fields=['failedLoginCount', 'lockedUntil', 'updatedAt'])
            failed = True
        else:
            recoveryCodes = []
            if step == 'enroll':
                identity.mfaConfirmedAt = now
                for _ in range(10):
                    value = secrets.token_hex(10)
                    Recovery.objects.create(administrativeIdentityId=identity.id,
                        codeHash=hashlib.sha256(f'recovery.v1:{identity.id}:{value}'.encode()).hexdigest())
                    recoveryCodes.append(value)
            identity.firstVerifiedLoginAt = identity.firstVerifiedLoginAt or now
            identity.failedLoginCount = 0
            identity.lockedUntil = None
            identity.save()
            Recovery.objects.create(administrativeIdentityId=identity.id,
                codeHash=hashlib.sha256(('login-proof.v1:' + token).encode()).hexdigest(), usedAt=now)
            result = _openSession(identity, owner, now)
            if recoveryCodes:
                result['recoveryCodes'] = recoveryCodes
    if failed:
        raise InvalidCredentialsError('کد تأیید معتبر نیست یا قبلاً استفاده شده است.')
    return result


def _openSession(identity, owner, now):
    from apps.identity.infrastructure.services.jwtService import defaultJwtService
    from apps.identity.application.dto.identityDtos import userDtoFromDomain
    from apps.sharedKernel.infrastructure.models import AuditEventModel
    raw = secrets.token_urlsafe(48)
    session = SessionModel.objects.create(userId=owner.id, tenantId=owner.tenantId,
        refreshTokenHash=hashlib.sha256(raw.encode()).hexdigest(), expiresAt=now + timedelta(hours=8),
        device=ADMINISTRATIVE_DEVICE)
    Binding.objects.create(sessionId=session.id, administrativeIdentityId=identity.id,
        ownerUserId=owner.id, credentialBindingHash=credentialBinding(identity, owner), mfaVerifiedAt=now)
    access, ttl = defaultJwtService().issueAccessToken(userId=owner.id, tenantId=owner.tenantId, sessionId=session.id)
    from apps.sharedKernel.application.requestContext import currentContext
    context = currentContext()
    AuditEventModel.objects.create(actorUserId=owner.id, tenantId=owner.tenantId,
        action='admin.login', resourceType='AdministrativeIdentity', resourceId=str(identity.id),
        ipAddress=context.ipAddress[:64], userAgent=context.userAgent[:300],
        correlationId=context.correlationId[:64], requestId=context.requestId[:64],
        afterState={'administrativeIdentityId': str(identity.id), 'sessionId': str(session.id)})
    from apps.identity.application.services.permissionCatalog import ACTIONS
    return {'step': 'authenticated', 'accessToken': access, 'refreshToken': raw,
            'expiresIn': ttl, 'expiresAt': session.expiresAt.isoformat(),
            'user': dataclasses.asdict(userDtoFromDomain(owner)), 'permissions': [code for code, _ in ACTIONS],
            'administrativeIdentityId': str(identity.id)}
