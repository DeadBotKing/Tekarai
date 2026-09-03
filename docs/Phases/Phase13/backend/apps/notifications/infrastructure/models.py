"""Notification ORM models (Phase 09 §36/§37).

The twelve conceptual tables exactly as the spec lists them. Global
standards: UUID PKs, tenant scoping, createdAt/updatedAt, soft delete
where appropriate, plus the §37 index set (unread query, delivery
nextAttemptAt, idempotencyKey uniqueness).
"""

from __future__ import annotations

import uuid

from django.db import models


def uuidPk() -> models.UUIDField:
    return models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)


class NotificationRecordModel(models.Model):
    """§3 — single-recipient aggregate row (table `notifications`)."""

    id = uuidPk()
    tenantId = models.UUIDField(db_index=True)
    recipientId = models.UUIDField(db_index=True)
    notificationType = models.CharField(max_length=120, db_index=True)
    category = models.CharField(max_length=32, db_index=True)
    priority = models.CharField(max_length=16, db_index=True)
    title = models.CharField(max_length=300)
    body = models.TextField(blank=True, default="")
    status = models.CharField(max_length=24, db_index=True)
    sourceType = models.CharField(max_length=64, blank=True, default="", db_index=True)
    sourceId = models.CharField(max_length=120, blank=True, default="")
    idempotencyKey = models.CharField(max_length=64, db_index=True)
    requiresAcknowledgement = models.BooleanField(default=False)
    language = models.CharField(max_length=16, blank=True, default="")
    correlationId = models.CharField(max_length=64, blank=True, default="", db_index=True)
    causationId = models.CharField(max_length=120, blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)
    createdAt = models.DateTimeField(auto_now_add=True, db_index=True)
    updatedAt = models.DateTimeField(auto_now=True)
    scheduledAt = models.DateTimeField(null=True, blank=True)
    expiresAt = models.DateTimeField(null=True, blank=True)
    readAt = models.DateTimeField(null=True, blank=True)
    acknowledgedAt = models.DateTimeField(null=True, blank=True)
    deletedAt = models.DateTimeField(null=True, blank=True)  # §40 archive

    class Meta:
        db_table = "notificationsNotifications"
        indexes = [
            # §37 unread query — recipientId + readAt + createdAt
            models.Index(
                fields=["tenantId", "recipientId", "readAt", "createdAt"],
                name="IX_Ntf_unread",
            ),
            models.Index(fields=["tenantId", "status"], name="IX_Ntf_t_status"),
            models.Index(
                fields=["tenantId", "category", "priority"], name="IX_Ntf_t_cat_pri"
            ),
        ]
        constraints = [
            # §29/§37 — one notification per logical (event, recipient, type)
            models.UniqueConstraint(
                fields=["tenantId", "idempotencyKey"], name="UQ_Notification_idem"
            ),
        ]


class NotificationDeliveryModel(models.Model):
    """§25/§47 — one row per (notification, channel) with its own status."""

    id = uuidPk()
    tenantId = models.UUIDField(db_index=True)
    notificationId = models.UUIDField(db_index=True)
    channel = models.CharField(max_length=16, db_index=True)
    provider = models.CharField(max_length=48, blank=True, default="")
    status = models.CharField(max_length=24, db_index=True)
    attemptCount = models.IntegerField(default=0)
    maxAttempts = models.IntegerField(default=3)
    errorCode = models.CharField(max_length=48, blank=True, default="")
    errorMessage = models.CharField(max_length=500, blank=True, default="")
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)
    lastAttemptAt = models.DateTimeField(null=True, blank=True)
    nextAttemptAt = models.DateTimeField(null=True, blank=True, db_index=True)
    deliveredAt = models.DateTimeField(null=True, blank=True)
    failedAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notificationsDeliveries"
        indexes = [
            # §37 — retry worker scan: status + nextAttemptAt
            models.Index(
                fields=["status", "nextAttemptAt"], name="IX_Ndl_retry_scan"
            ),
            models.Index(
                fields=["notificationId", "channel"], name="IX_Ndl_ntf_channel"
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["notificationId", "channel"], name="UQ_Delivery_channel"
            ),
        ]


class NotificationPreferenceModel(models.Model):
    """§10 — per (user, level, scope, channel); most specific wins."""

    id = uuidPk()
    tenantId = models.UUIDField(db_index=True)
    userId = models.UUIDField(db_index=True)
    level = models.CharField(max_length=12)
    category = models.CharField(max_length=32, blank=True, default="")
    notificationType = models.CharField(max_length=120, blank=True, default="")
    channel = models.CharField(max_length=16)
    enabled = models.BooleanField(default=True)
    quietHoursStart = models.CharField(max_length=8, blank=True, default="")
    quietHoursEnd = models.CharField(max_length=8, blank=True, default="")
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notificationsPreferences"
        indexes = [
            # §37 — tenantId + userId + category + notificationType
            models.Index(
                fields=["tenantId", "userId", "category", "notificationType"],
                name="IX_Pref_t_u_cat_type",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["userId", "level", "category", "notificationType", "channel"],
                name="UQ_Preference_scope",
            ),
        ]


class NotificationPreferenceRuleModel(models.Model):
    """§11 — tenant org rules: FORCED / DENIED channels."""

    id = uuidPk()
    tenantId = models.UUIDField(db_index=True)
    channel = models.CharField(max_length=16)
    action = models.CharField(max_length=8)  # FORCED | DENIED
    category = models.CharField(max_length=32, blank=True, default="")
    notificationType = models.CharField(max_length=120, blank=True, default="")
    description = models.CharField(max_length=300, blank=True, default="")
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notificationsPreferenceRules"
        indexes = [
            models.Index(fields=["tenantId", "action"], name="IX_Rule_t_action"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "channel", "action", "category", "notificationType"],
                name="UQ_Rule_scope",
            ),
        ]


class NotificationTemplateModel(models.Model):
    """§18/§19 — active template rows (history in the versions table)."""

    id = uuidPk()
    tenantId = models.UUIDField(db_index=True)
    templateKey = models.CharField(max_length=120, db_index=True)
    language = models.CharField(max_length=16)
    channel = models.CharField(max_length=16)
    version = models.IntegerField(default=1)
    title = models.CharField(max_length=300)
    subject = models.CharField(max_length=300, blank=True, default="")
    body = models.TextField(blank=True, default="")
    isActive = models.BooleanField(default=True, db_index=True)
    createdBy = models.UUIDField(null=True, blank=True)
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notificationsTemplates"
        indexes = [
            models.Index(
                fields=["tenantId", "templateKey", "language", "channel", "isActive"],
                name="IX_Tpl_lookup",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "templateKey", "language", "channel", "version"],
                name="UQ_Template_version",
            ),
        ]


class NotificationTemplateVersionModel(models.Model):
    """§19 — immutable version history for every template edit."""

    id = uuidPk()
    templateId = models.UUIDField(db_index=True)
    tenantId = models.UUIDField(db_index=True)
    templateKey = models.CharField(max_length=120, db_index=True)
    language = models.CharField(max_length=16)
    channel = models.CharField(max_length=16)
    version = models.IntegerField()
    title = models.CharField(max_length=300)
    subject = models.CharField(max_length=300, blank=True, default="")
    body = models.TextField(blank=True, default="")
    isActive = models.BooleanField(default=False)
    createdBy = models.UUIDField(null=True, blank=True)
    createdAt = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notificationsTemplateVersions"
        indexes = [
            models.Index(
                fields=["tenantId", "templateKey", "language", "channel", "version"],
                name="IX_TplV_history",
            ),
        ]


class NotificationPolicyModel(models.Model):
    """§8 — config-driven behaviour per type/category."""

    id = uuidPk()
    tenantId = models.UUIDField(db_index=True)
    policyKey = models.CharField(max_length=120, db_index=True)
    notificationType = models.CharField(max_length=120, blank=True, default="")
    category = models.CharField(max_length=32, blank=True, default="")
    enabled = models.BooleanField(default=True)
    priority = models.CharField(max_length=16, default="NORMAL")
    templateKey = models.CharField(max_length=120, blank=True, default="")
    maxAttempts = models.IntegerField(default=3)
    cooldownSeconds = models.IntegerField(default=60)
    digestible = models.BooleanField(default=False)
    escalation = models.JSONField(default=list, blank=True)
    allowPreferenceBypass = models.BooleanField(default=False)
    description = models.CharField(max_length=300, blank=True, default="")
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notificationsPolicies"
        indexes = [
            models.Index(
                fields=["tenantId", "notificationType", "category", "enabled"],
                name="IX_Pol_match",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "policyKey"], name="UQ_Policy_key"
            ),
        ]


class NotificationPolicyChannelModel(models.Model):
    """§8/§36 — per-policy channel rows (provider overrides)."""

    id = uuidPk()
    policyId = models.UUIDField(db_index=True)
    tenantId = models.UUIDField(db_index=True)
    channel = models.CharField(max_length=16)
    enabled = models.BooleanField(default=True)
    providerOverride = models.CharField(max_length=48, blank=True, default="")

    class Meta:
        db_table = "notificationsPolicyChannels"
        indexes = [
            models.Index(fields=["policyId", "channel"], name="IX_PolC_pol_channel"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["policyId", "channel"], name="UQ_PolicyChannel"
            ),
        ]


class NotificationDeviceModel(models.Model):
    """§15 — many devices per user; token stored, never exposed (§33)."""

    id = uuidPk()
    tenantId = models.UUIDField(db_index=True)
    userId = models.UUIDField(db_index=True)
    platform = models.CharField(max_length=12)
    deviceIdentifier = models.CharField(max_length=190)
    pushToken = models.CharField(max_length=512)  # §33 — server-side only
    provider = models.CharField(max_length=48, default="FCM")
    isActive = models.BooleanField(default=True, db_index=True)
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)
    lastSeenAt = models.DateTimeField(null=True, blank=True)
    revokedAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notificationsDevices"
        indexes = [
            # §37 — userId + isActive + platform
            models.Index(
                fields=["tenantId", "userId", "isActive", "platform"],
                name="IX_Dev_u_active_platform",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "userId", "deviceIdentifier"],
                name="UQ_Device_identifier",
            ),
        ]


class NotificationDigestModel(models.Model):
    """§21 — grouped notifications waiting for their digest window."""

    id = uuidPk()
    tenantId = models.UUIDField(db_index=True)
    userId = models.UUIDField(db_index=True)
    kind = models.CharField(max_length=12)
    status = models.CharField(max_length=8, default="OPEN")
    itemCount = models.IntegerField(default=0)
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)
    periodStart = models.DateTimeField()
    periodEnd = models.DateTimeField(db_index=True)
    sentAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notificationsDigests"
        indexes = [
            models.Index(
                fields=["tenantId", "userId", "kind", "status"],
                name="IX_Dgst_open",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "userId", "kind", "status"],
                condition=models.Q(status="OPEN"),
                name="UQ_Digest_open_once",
            ),
        ]


class NotificationDigestItemModel(models.Model):
    id = uuidPk()
    digestId = models.UUIDField(db_index=True)
    tenantId = models.UUIDField(db_index=True)
    notificationId = models.UUIDField(db_index=True)
    addedAt = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notificationsDigestItems"
        indexes = [
            models.Index(fields=["digestId", "notificationId"], name="IX_DgstI_pair"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["digestId", "notificationId"], name="UQ_DigestItem_once"
            ),
        ]


class NotificationScheduleModel(models.Model):
    """§22 — IMMEDIATE/SCHEDULED/RECURRING/DELAYED/DIGEST rows."""

    id = uuidPk()
    tenantId = models.UUIDField(db_index=True)
    kind = models.CharField(max_length=12)
    status = models.CharField(max_length=12, default="PENDING", db_index=True)
    recipientSpec = models.JSONField(default=dict)
    notificationType = models.CharField(max_length=120)
    category = models.CharField(max_length=32)
    priority = models.CharField(max_length=16)
    title = models.CharField(max_length=300)
    body = models.TextField(blank=True, default="")
    sourceType = models.CharField(max_length=64, blank=True, default="")
    sourceId = models.CharField(max_length=120, blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)
    correlationId = models.CharField(max_length=64, blank=True, default="")
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)
    scheduledAt = models.DateTimeField(null=True, blank=True)
    nextRunAt = models.DateTimeField(null=True, blank=True, db_index=True)
    lastRunAt = models.DateTimeField(null=True, blank=True)
    recurEverySeconds = models.IntegerField(default=0)
    expiresAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notificationsSchedules"
        indexes = [
            # §22 — worker poll: due pending schedules
            models.Index(fields=["status", "nextRunAt"], name="IX_Sched_due"),
        ]


# ---------------------------------------------------------------------------
# Phase 12 — canonical multi-recipient notification model (docs/Phases/Phase12.md).
# The Phase 09 single-recipient tables above stay untouched; these tables add
# the broadcast/recipient split (§12.8), delivery attempts (§12.16), dead-letter
# (§12.18), rules (§12.24) and the idempotent event log (§12.38).
# ---------------------------------------------------------------------------


class NotificationModel(models.Model):
    """§12.3 — ONE notification addressed to MANY recipients (broadcast).

    Read state is NOT stored here (§12.8 forbids Notification.isRead); it lives
    on NotificationRecipientModel.
    """

    id = uuidPk()
    tenantId = models.UUIDField(db_index=True)
    notificationType = models.CharField(max_length=120, db_index=True)
    severity = models.CharField(max_length=16, default="INFO")
    priority = models.CharField(max_length=16, db_index=True, default="NORMAL")
    title = models.CharField(max_length=300)
    body = models.TextField(blank=True, default="")
    sourceType = models.CharField(max_length=64, blank=True, default="", db_index=True)
    sourceId = models.CharField(max_length=120, blank=True, default="")
    deepLink = models.CharField(max_length=300, blank=True, default="")
    language = models.CharField(max_length=16, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    idempotencyKey = models.CharField(max_length=80, blank=True, default="", db_index=True)
    correlationId = models.CharField(max_length=64, blank=True, default="", db_index=True)
    createdAt = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "notifications"
        indexes = [
            models.Index(fields=["tenantId", "notificationType"], name="IX_Ntf12_type"),
            models.Index(fields=["tenantId", "priority"], name="IX_Ntf12_pri"),
        ]
        constraints = [
            # §12.38 — a redelivered event must not duplicate a notification
            models.UniqueConstraint(
                fields=["tenantId", "idempotencyKey"],
                condition=models.Q(idempotencyKey__gt=""),
                name="UQ_Notifications12_idem",
            ),
        ]


class NotificationRecipientModel(models.Model):
    """§12.7/§12.8 — per-recipient read/archive/dismiss state."""

    id = uuidPk()
    tenantId = models.UUIDField(db_index=True)
    notificationId = models.UUIDField(db_index=True)
    userId = models.UUIDField(db_index=True)
    recipientState = models.CharField(max_length=12, default="UNREAD", db_index=True)
    readAt = models.DateTimeField(null=True, blank=True)
    archivedAt = models.DateTimeField(null=True, blank=True)
    dismissedAt = models.DateTimeField(null=True, blank=True)
    createdAt = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notificationRecipients"
        indexes = [
            # §12.48 — unread inbox query: (tenant, recipient, state, created)
            models.Index(
                fields=["tenantId", "userId", "recipientState", "createdAt"],
                name="IX_Recp_inbox",
            ),
            models.Index(fields=["notificationId", "userId"], name="IX_Recp_n_u"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["notificationId", "userId"], name="UQ_Recp_notif_user"
            ),
        ]


class NotificationRecipientDeliveryModel(models.Model):
    """§12.14 — one channel delivery to one recipient of a broadcast.

    Distinct from the Phase 09 ``NotificationDeliveryModel`` (single-recipient
    rows in ``notificationsDeliveries``); this is the broadcast delivery table.
    """

    id = uuidPk()
    tenantId = models.UUIDField(db_index=True)
    notificationId = models.UUIDField(db_index=True)
    recipientId = models.UUIDField(db_index=True)
    channel = models.CharField(max_length=16, db_index=True)
    provider = models.CharField(max_length=48, blank=True, default="")
    deliveryStatus = models.CharField(max_length=16, default="PENDING", db_index=True)
    attemptCount = models.IntegerField(default=0)
    maxAttempts = models.IntegerField(default=5)
    errorCode = models.CharField(max_length=48, blank=True, default="")
    errorMessage = models.CharField(max_length=500, blank=True, default="")
    lastAttemptAt = models.DateTimeField(null=True, blank=True)
    nextAttemptAt = models.DateTimeField(null=True, blank=True, db_index=True)
    deliveredAt = models.DateTimeField(null=True, blank=True)
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notificationDeliveries"
        indexes = [
            # §12.48 — retry worker scan
            models.Index(fields=["deliveryStatus", "nextAttemptAt"], name="IX_Dlv12_retry"),
            models.Index(
                fields=["notificationId", "recipientId", "channel"],
                name="IX_Dlv12_nrc",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["notificationId", "recipientId", "channel"],
                name="UQ_Dlv12_triple",
            ),
        ]


class NotificationAttemptModel(models.Model):
    """§12.16 — every provider send attempt is audited."""

    id = uuidPk()
    tenantId = models.UUIDField(db_index=True)
    deliveryId = models.UUIDField(db_index=True)
    attemptNumber = models.IntegerField()
    outcome = models.CharField(max_length=12)
    provider = models.CharField(max_length=48, blank=True, default="")
    providerMessageId = models.CharField(max_length=120, blank=True, default="")
    errorCode = models.CharField(max_length=48, blank=True, default="")
    errorMessage = models.CharField(max_length=500, blank=True, default="")
    responseMetadata = models.JSONField(default=dict, blank=True)
    startedAt = models.DateTimeField(null=True, blank=True)
    completedAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notificationAttempts"
        indexes = [
            models.Index(fields=["deliveryId", "attemptNumber"], name="IX_Att_dlv_num"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["deliveryId", "attemptNumber"], name="UQ_Att_dlv_num"
            ),
        ]


class NotificationRuleModel(models.Model):
    """§12.24 — WHEN event / IF condition / THEN notify rule."""

    id = uuidPk()
    tenantId = models.UUIDField(db_index=True)
    name = models.CharField(max_length=160)
    eventType = models.CharField(max_length=120, db_index=True)
    condition = models.JSONField(default=dict, blank=True)
    recipientStrategy = models.CharField(max_length=24, default="TARGET")
    channels = models.JSONField(default=list)
    priority = models.CharField(max_length=16, default="NORMAL")
    templateKey = models.CharField(max_length=120, blank=True, default="")
    isActive = models.BooleanField(default=True, db_index=True)
    createdAt = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notificationRules"
        indexes = [
            models.Index(fields=["tenantId", "eventType", "isActive"], name="IX_Rule_evt"),
        ]


class NotificationEventModel(models.Model):
    """§12.38 — idempotent inbound event log (dedupe redelivered events)."""

    id = uuidPk()
    tenantId = models.UUIDField(db_index=True)
    eventId = models.CharField(max_length=80, db_index=True)
    eventType = models.CharField(max_length=120, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    processed = models.BooleanField(default=False, db_index=True)
    createdAt = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notificationEvents"
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "eventId"], name="UQ_Event_tenant_evt"
            ),
        ]
