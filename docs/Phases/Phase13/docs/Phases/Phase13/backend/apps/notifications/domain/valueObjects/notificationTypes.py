"""Notification vocabularies (Phase 09 §3–§6, §9, §12, §21–§26, §29).

Single source of truth for every enumeration the Notification context
uses. Framework-free; the domain never imports Django/Channels/Redis (§37
house rule mirrored from the platform architecture).
"""

from __future__ import annotations

import hashlib
import uuid

# ---------------------------------------------------------------------------
# §3 notification statuses
# ---------------------------------------------------------------------------

NOTIFICATION_PENDING = "PENDING"
NOTIFICATION_PROCESSING = "PROCESSING"
NOTIFICATION_DELIVERED = "DELIVERED"
NOTIFICATION_PARTIALLY_DELIVERED = "PARTIALLY_DELIVERED"
NOTIFICATION_FAILED = "FAILED"
NOTIFICATION_EXPIRED = "EXPIRED"
NOTIFICATION_CANCELLED = "CANCELLED"

NOTIFICATION_STATUSES = (
    NOTIFICATION_PENDING,
    NOTIFICATION_PROCESSING,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_PARTIALLY_DELIVERED,
    NOTIFICATION_FAILED,
    NOTIFICATION_EXPIRED,
    NOTIFICATION_CANCELLED,
)

#: terminal states — no further delivery work happens
NOTIFICATION_TERMINAL = (
    NOTIFICATION_DELIVERED,
    NOTIFICATION_FAILED,
    NOTIFICATION_EXPIRED,
    NOTIFICATION_CANCELLED,
)

#: statuses that still have deliverable work
NOTIFICATION_DISPATCHABLE = (NOTIFICATION_PENDING, NOTIFICATION_PROCESSING)

# ---------------------------------------------------------------------------
# §4 categories (tenant-configurable behaviour, §4 closing note)
# ---------------------------------------------------------------------------

CATEGORY_SYSTEM = "SYSTEM"
CATEGORY_SECURITY = "SECURITY"
CATEGORY_TASK = "TASK"
CATEGORY_PROJECT = "PROJECT"
CATEGORY_HR = "HR"
CATEGORY_DOCUMENT = "DOCUMENT"
CATEGORY_WORKFLOW = "WORKFLOW"
CATEGORY_COMMUNICATION = "COMMUNICATION"
CATEGORY_MEETING = "MEETING"
CATEGORY_DEVICE = "DEVICE"
CATEGORY_MAINTENANCE = "MAINTENANCE"
CATEGORY_AI = "AI"
CATEGORY_REPORT = "REPORT"
CATEGORY_ADMINISTRATION = "ADMINISTRATION"

NOTIFICATION_CATEGORIES = (
    CATEGORY_SYSTEM,
    CATEGORY_SECURITY,
    CATEGORY_TASK,
    CATEGORY_PROJECT,
    CATEGORY_HR,
    CATEGORY_DOCUMENT,
    CATEGORY_WORKFLOW,
    CATEGORY_COMMUNICATION,
    CATEGORY_MEETING,
    CATEGORY_DEVICE,
    CATEGORY_MAINTENANCE,
    CATEGORY_AI,
    CATEGORY_REPORT,
    CATEGORY_ADMINISTRATION,
)

# ---------------------------------------------------------------------------
# §5 priorities
# ---------------------------------------------------------------------------

PRIORITY_LOW = "LOW"
PRIORITY_NORMAL = "NORMAL"
PRIORITY_HIGH = "HIGH"
PRIORITY_URGENT = "URGENT"
PRIORITY_CRITICAL = "CRITICAL"

NOTIFICATION_PRIORITIES = (
    PRIORITY_LOW,
    PRIORITY_NORMAL,
    PRIORITY_HIGH,
    PRIORITY_URGENT,
    PRIORITY_CRITICAL,
)

PRIORITY_RANK: dict[str, int] = {
    PRIORITY_LOW: 0,
    PRIORITY_NORMAL: 1,
    PRIORITY_HIGH: 2,
    PRIORITY_URGENT: 3,
    PRIORITY_CRITICAL: 4,
}

#: §5 — CRITICAL may bypass user preferences ONLY for these categories and
#: only when the tenant policy explicitly allows it (no arbitrary bypass).
BYPASS_ALLOWED_CATEGORIES = (CATEGORY_SECURITY, CATEGORY_SYSTEM)

# ---------------------------------------------------------------------------
# §12 delivery channels
# ---------------------------------------------------------------------------

CHANNEL_IN_APP = "IN_APP"
CHANNEL_PUSH = "PUSH"
CHANNEL_EMAIL = "EMAIL"
CHANNEL_SMS = "SMS"
CHANNEL_DESKTOP = "DESKTOP"
CHANNEL_BROWSER = "BROWSER"

DELIVERY_CHANNELS = (
    CHANNEL_IN_APP,
    CHANNEL_PUSH,
    CHANNEL_EMAIL,
    CHANNEL_SMS,
    CHANNEL_DESKTOP,
    CHANNEL_BROWSER,
)

#: channels carried by the push/web infrastructure on this platform
PUSH_LIKE_CHANNELS = (CHANNEL_PUSH, CHANNEL_DESKTOP, CHANNEL_BROWSER)

# ---------------------------------------------------------------------------
# §25 delivery statuses (per channel)
# ---------------------------------------------------------------------------

DELIVERY_PENDING = "PENDING"
DELIVERY_SENT = "SENT"
DELIVERY_DELIVERED = "DELIVERED"
DELIVERY_FAILED = "FAILED"
DELIVERY_SKIPPED = "SKIPPED"          # preference/policy disabled the channel
DELIVERY_RETRY_SCHEDULED = "RETRY_SCHEDULED"
DELIVERY_PERMANENTLY_FAILED = "PERMANENTLY_FAILED"

DELIVERY_STATUSES = (
    DELIVERY_PENDING,
    DELIVERY_SENT,
    DELIVERY_DELIVERED,
    DELIVERY_FAILED,
    DELIVERY_SKIPPED,
    DELIVERY_RETRY_SCHEDULED,
    DELIVERY_PERMANENTLY_FAILED,
)

#: §24 — error classes that must never be retried
PERMANENT_ERROR_CODES = (
    "INVALID_ADDRESS",
    "INVALID_TOKEN",
    "UNSUBSCRIBED",
    "CHANNEL_DISABLED",
    "TENANT_BLOCKED",
    "NO_ACTIVE_DEVICE",
)

# ---------------------------------------------------------------------------
# §9 recipient types
# ---------------------------------------------------------------------------

RECIPIENT_USER = "USER"
RECIPIENT_ROLE = "ROLE"
RECIPIENT_DEPARTMENT = "DEPARTMENT"
RECIPIENT_TEAM = "TEAM"
RECIPIENT_PROJECT = "PROJECT"
RECIPIENT_CHANNEL = "CHANNEL"
RECIPIENT_ORGANIZATION = "ORGANIZATION"
RECIPIENT_TENANT = "TENANT"
RECIPIENT_EXTERNAL = "EXTERNAL_RECIPIENT"

RECIPIENT_TYPES = (
    RECIPIENT_USER,
    RECIPIENT_ROLE,
    RECIPIENT_DEPARTMENT,
    RECIPIENT_TEAM,
    RECIPIENT_PROJECT,
    RECIPIENT_CHANNEL,
    RECIPIENT_ORGANIZATION,
    RECIPIENT_TENANT,
    RECIPIENT_EXTERNAL,
)

# ---------------------------------------------------------------------------
# §10 preference levels — the most specific applicable preference wins
# ---------------------------------------------------------------------------

PREF_LEVEL_GLOBAL = "GLOBAL"        # per user, all notifications
PREF_LEVEL_CATEGORY = "CATEGORY"    # per user + category
PREF_LEVEL_TYPE = "TYPE"            # per user + notificationType

PREFERENCE_LEVELS = (PREF_LEVEL_GLOBAL, PREF_LEVEL_CATEGORY, PREF_LEVEL_TYPE)

# ---------------------------------------------------------------------------
# §21 digests / §22 scheduling
# ---------------------------------------------------------------------------

DIGEST_HOURLY = "HOURLY"
DIGEST_DAILY = "DAILY"
DIGEST_WEEKLY = "WEEKLY"
DIGEST_KINDS = (DIGEST_HOURLY, DIGEST_DAILY, DIGEST_WEEKLY)

SCHEDULE_IMMEDIATE = "IMMEDIATE"
SCHEDULE_SCHEDULED = "SCHEDULED"
SCHEDULE_RECURRING = "RECURRING"
SCHEDULE_DELAYED = "DELAYED"
SCHEDULE_DIGEST = "DIGEST"
SCHEDULE_KINDS = (
    SCHEDULE_IMMEDIATE,
    SCHEDULE_SCHEDULED,
    SCHEDULE_RECURRING,
    SCHEDULE_DELAYED,
    SCHEDULE_DIGEST,
)

SCHEDULE_PENDING = "PENDING"
SCHEDULE_DONE = "DONE"
SCHEDULE_CANCELLED = "CANCELLED"
SCHEDULE_STATUSES = (SCHEDULE_PENDING, SCHEDULE_DONE, SCHEDULE_CANCELLED)

DIGEST_STATUS_OPEN = "OPEN"
DIGEST_STATUS_SENT = "SENT"
DIGEST_STATUSES = (DIGEST_STATUS_OPEN, DIGEST_STATUS_SENT)

# ---------------------------------------------------------------------------
# §20 localization — language resolution order
# ---------------------------------------------------------------------------

LANGUAGE_USER = "USER"
LANGUAGE_ORG_POLICY = "ORG_POLICY"
LANGUAGE_TENANT_DEFAULT = "TENANT_DEFAULT"
LANGUAGE_PLATFORM_DEFAULT = "PLATFORM_DEFAULT"

PLATFORM_DEFAULT_LANGUAGE = "en-US"
SUPPORTED_LANGUAGES = ("fa-IR", "en-US", "de-DE")

# ---------------------------------------------------------------------------
# §24 retry / backoff defaults
# ---------------------------------------------------------------------------

DEFAULT_MAX_ATTEMPTS = 3
RETRY_BASE_DELAY_SECONDS = 30        # attempt 1 → 30s
RETRY_BACKOFF_MULTIPLIER = 4         # 30s → 2m → 10m (spec example)
RETRY_MAX_DELAY_SECONDS = 600

#: §28 rate limiting — identical-notification cooldown per user+type
DEFAULT_COOLDOWN_SECONDS = 60
RATE_WINDOW_SECONDS = 60
RATE_MAX_PER_WINDOW = 20

#: §23 expiration default for time-boxed notifications (e.g. security codes)
DEFAULT_EXPIRY_SECONDS = 0           # 0 = no expiry

# ---------------------------------------------------------------------------
# §29 deduplication key
# ---------------------------------------------------------------------------


def idempotencyKeyOf(
    *,
    tenantId: uuid.UUID | str,
    eventType: str,
    eventId: str,
    recipientId: str,
    notificationType: str,
) -> str:
    """Stable, hashed dedup key (§29): the same logical event + recipient +
    type can never create a second notification row."""
    raw = "|".join(
        [str(tenantId), eventType, eventId, recipientId, notificationType]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def notificationKeyDisplay(
    *, tenantId: str, eventType: str, eventId: str, recipientId: str, notificationType: str
) -> str:
    """Human-readable form used in audits (§35) — never stored raw."""
    return f"{tenantId}/{eventType}/{eventId}/{recipientId}/{notificationType}"
