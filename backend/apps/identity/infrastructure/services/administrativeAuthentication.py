"""Privileged session assurance. Never infer administrative authority from a user ID.

This module deliberately does not grant roles, modify primary passwords or bootstrap
accounts. An administrative login must create a marked Session and its binding in
one transaction, only AFTER changing the temporary password and verifying MFA.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.sharedKernel.domain.errors import AuthenticationRequiredError

ADMINISTRATIVE_DEVICE = 'tekarai.superadmin.v1'
FRESH_MFA_SECONDS = 600


class EncryptedAdministrativeSecretVault:
    """Authenticated encryption, not Django's reversible plaintext HMAC signing.

    Rotating SECRET_KEY invalidates these secrets and requires controlled MFA
    recovery. No fallback to plaintext/signed-secret storage is permitted.
    """
    prefix = 'fernet.v1.'

    def _cipher(self):
        from cryptography.fernet import Fernet
        key = hashlib.sha256(b'tekarai.administrative.mfa.v1\x00' + settings.SECRET_KEY.encode()).digest()
        return Fernet(base64.urlsafe_b64encode(key))

    def protect(self, raw: str) -> str:
        if not raw or len(raw) > 128:
            raise ValueError('Invalid administrative secret.')
        return self.prefix + self._cipher().encrypt(raw.encode()).decode('ascii')

    def reveal(self, protected: str) -> str:
        from cryptography.fernet import InvalidToken
        if not isinstance(protected, str) or not protected.startswith(self.prefix):
            raise AuthenticationRequiredError('Invalid administrative secret reference.')
        try:
            return self._cipher().decrypt(protected[len(self.prefix):].encode('ascii')).decode('utf-8')
        except (InvalidToken, ValueError, UnicodeError) as exc:
            raise AuthenticationRequiredError('Invalid administrative secret reference.') from exc


def credentialBinding(identity, owner) -> str:
    """Length-delimited canonical encoding binds independent AND primary credentials."""
    values = [str(identity.id), str(identity.ownerUserId), identity.passwordHash,
              identity.mfaSecretRef, str(identity.mfaConfirmedAt),
              str(owner.id), owner.passwordHash]
    return hashlib.sha256(json.dumps(values, separators=(',', ':')).encode()).hexdigest()


def verifiedAdministrativeSession(session, owner=None, *, requireFresh=False, now=None):
    """Return verified identity, None for ordinary sessions, otherwise fail closed.

    Re-read mutable data on EVERY call; never cache this result in owner grants.
    Losing a binding cannot silently downgrade a privileged session to an ordinary
    owner login. API keys never enter this path.
    """
    from apps.identity.infrastructure.models import (
        AdministrativeSessionModel, AdministrativeIdentityModel, UserModel,
        TenantMembershipModel, MobileAccountModel,
    )
    from apps.tenancy.infrastructure.models import TenantModel
    now = now or timezone.now()
    record = AdministrativeSessionModel.objects.filter(sessionId=session.id).first()
    marked = session.device == ADMINISTRATIVE_DEVICE
    if record is None and not marked:
        return None

    def deny():
        raise AuthenticationRequiredError('نشست مدیریت معتبر نیست؛ دوباره وارد شوید.')

    if record is None or not marked or session.revokedAt is not None or session.expiresAt <= now:
        deny()
    if record.ownerUserId != session.userId:
        deny()
    identity = AdministrativeIdentityModel.objects.filter(id=record.administrativeIdentityId).first()
    owner = UserModel.objects.filter(id=session.userId).first()
    if identity is None or owner is None or identity.ownerUserId != owner.id:
        deny()
    if (identity.status != 'active' or identity.mustChangePassword or not identity.mfaSecretRef
            or identity.mfaConfirmedAt is None or identity.firstVerifiedLoginAt is None):
        deny()
    if (owner.status != 'active' or owner.deletedAt is not None or owner.tenantId != session.tenantId
            or (owner.expiresAt is not None and owner.expiresAt <= now)
            or (owner.lockedUntil is not None and owner.lockedUntil > now)):
        deny()
    if identity.lockedUntil is not None and identity.lockedUntil > now:
        deny()
    if MobileAccountModel.objects.filter(userId=owner.id, mustChangePassword=True).exists():
        deny()
    if not TenantModel.objects.filter(id=session.tenantId, status='active', deletedAt__isnull=True).exists():
        deny()
    if not TenantMembershipModel.objects.filter(userId=owner.id, tenantId=session.tenantId,
                                               status='active', leftAt__isnull=True).exists():
        deny()
    if not hmac.compare_digest(record.credentialBindingHash, credentialBinding(identity, owner)):
        deny()
    # No future-dated assurance, even when a client-supplied timestamp is malicious.
    if record.mfaVerifiedAt > now or record.mfaVerifiedAt < identity.mfaConfirmedAt:
        deny()
    if requireFresh and now - record.mfaVerifiedAt > timedelta(seconds=FRESH_MFA_SECONDS):
        raise AuthenticationRequiredError('برای این عملیات کد تأیید دومرحله‌ای تازه لازم است.')
    return identity


def administrativeGrants(actorId, *, requireFresh=False):
    """Request/session-scoped additions; MUST NOT be written to owner grant cache."""
    from apps.sharedKernel.application.requestContext import currentContext
    from apps.identity.infrastructure.models import SessionModel
    from apps.identity.domain.valueObjects.accessGrant import AccessGrant, SCOPE_GLOBAL
    from apps.identity.application.services.permissionCatalog import ACTIONS
    context = currentContext()
    if not context.sessionId or str(context.actorId) != str(actorId):
        return []
    session = SessionModel.objects.filter(id=context.sessionId, userId=actorId).first()
    if session is None or session.revokedAt is not None or session.expiresAt <= timezone.now():
        raise AuthenticationRequiredError('Session revoked or expired.')
    identity = verifiedAdministrativeSession(session, requireFresh=requireFresh)
    if identity is None:
        return []
    return [AccessGrant(actionPattern=code, scopeType=SCOPE_GLOBAL) for code, _ in ACTIONS]
