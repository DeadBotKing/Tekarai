"""Separate privileged credentials linked to one existing person, never duplicate User records.

No account/role/bootstrap records are created by importing this module. Authentication
and management services must verify owner state, membership and session binding before
using any credential. These tables are not an authorization shortcut.
"""
import uuid
from django.db import models


class AdministrativeIdentityModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ownerUserId = models.UUIDField(unique=True)
    username = models.CharField(max_length=64, unique=True)
    passwordHash = models.CharField(max_length=255)
    status = models.CharField(max_length=16, default='active')
    mustChangePassword = models.BooleanField(default=True)
    temporaryExpiresAt = models.DateTimeField(null=True, blank=True)
    passwordChangedAt = models.DateTimeField(null=True, blank=True)
    failedLoginCount = models.IntegerField(default=0)
    lockedUntil = models.DateTimeField(null=True, blank=True)
    mfaSecretRef = models.CharField(max_length=512, blank=True, default='')
    mfaConfirmedAt = models.DateTimeField(null=True, blank=True)
    firstVerifiedLoginAt = models.DateTimeField(null=True, blank=True)
    createdByUserId = models.UUIDField()
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'AdministrativeIdentity'


class AdministrativeSessionModel(models.Model):
    sessionId = models.UUIDField(primary_key=True)
    administrativeIdentityId = models.UUIDField(db_index=True)
    ownerUserId = models.UUIDField(db_index=True)
    credentialBindingHash = models.CharField(max_length=64)
    mfaVerifiedAt = models.DateTimeField()
    createdAt = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'AdministrativeSession'


class AdministrativeRecoveryCodeModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    administrativeIdentityId = models.UUIDField(db_index=True)
    codeHash = models.CharField(max_length=64, unique=True)
    usedAt = models.DateTimeField(null=True, blank=True)
    createdAt = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'AdministrativeRecoveryCode'


class AdministrativePasswordHistoryModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    administrativeIdentityId = models.UUIDField(db_index=True)
    passwordHash = models.CharField(max_length=255)
    createdAt = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'AdministrativePasswordHistory'
        ordering = ['-createdAt']


class AdministrativeGovernanceModel(models.Model):
    key = models.CharField(max_length=32, primary_key=True, default='platform')
    bootstrapOwnerUserId = models.UUIDField()
    managedAdministrationEnabled = models.BooleanField(default=False)
    legacyAdminRetiredAt = models.DateTimeField(null=True, blank=True)
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'AdministrativeGovernance'
