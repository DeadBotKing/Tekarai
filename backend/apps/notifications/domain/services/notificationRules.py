"""Notification domain rules (Phase 09 §5/§10/§11/§20/§24/§28/§29).

Pure functions — no framework imports (§37).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from apps.notifications.domain.valueObjects.notificationTypes import (
    BYPASS_ALLOWED_CATEGORIES,
    DELIVERY_CHANNELS,
    PRIORITY_CRITICAL,
    PRIORITY_RANK,
    PREF_LEVEL_CATEGORY,
    PREF_LEVEL_GLOBAL,
    PREF_LEVEL_TYPE,
    RATE_MAX_PER_WINDOW,
    RATE_WINDOW_SECONDS,
)
from apps.sharedKernel.domain.errors import ValidationFailedError


# ---------------------------------------------------------------------------
# §10/§11 channel selection: policy ∩ tenant rules − user preferences
# ---------------------------------------------------------------------------


def resolveChannels(
    *,
    policyChannels: tuple[str, ...],
    forcedChannels: tuple[str, ...],
    deniedChannels: tuple[str, ...],
    preferenceRows: list[tuple[str, str, str, str, bool]],  # (level, category, type, channel, enabled)
    notificationType: str,
    category: str,
    priority: str,
    allowPreferenceBypass: bool,
) -> tuple[tuple[str, ...], list[str]]:
    """Returns (selected channels, human-readable resolution trace).

    Order of authority (§10/§11/§5):
      1. tenant DENY removes a channel unconditionally;
      2. tenant FORCE adds a channel unconditionally (org policy wins);
      3. user preferences (most specific level wins) filter the rest;
      4. CRITICAL may bypass user preferences ONLY for SECURITY/SYSTEM and
         only when the policy explicitly allows it (no arbitrary bypass §5).
    """
    denied = set(deniedChannels)
    forced = [c for c in forcedChannels if c not in denied]

    base = [c for c in policyChannels if c in DELIVERY_CHANNELS and c not in denied]

    bypass = (
        priority == PRIORITY_CRITICAL
        and allowPreferenceBypass
        and category in BYPASS_ALLOWED_CATEGORIES
    )
    trace: list[str] = []
    if denied:
        trace.append(f"tenant-denied={','.join(sorted(denied))}")

    if bypass:
        # §5 — CRITICAL bypasses user preferences ONLY for SECURITY/SYSTEM and
        # only when the policy explicitly allows it. Tenant rules still apply.
        selected = list(dict.fromkeys([*base, *forced]))
        trace.append("critical-bypass(user prefs ignored)")
        if forced:
            trace.append(f"tenant-forced={','.join(forced)}")
        return tuple(selected), trace

    # §10/§11 — user preferences filter the policy channels; tenant FORCED
    # channels stay regardless of user wishes.
    chosen = [c for c in base if _userChannelEnabled(preferenceRows, notificationType, category, c)]
    selected = list(dict.fromkeys([*chosen, *forced]))
    for channel in base:
        if channel not in chosen:
            trace.append(f"user-disabled={channel}")
    if forced:
        trace.append(f"tenant-forced={','.join(forced)}")
    return tuple(selected), trace


def _userChannelEnabled(
    preferenceRows: list[tuple[str, str, str, str, bool]],
    notificationType: str,
    category: str,
    channel: str,
) -> bool:
    """§10 — most specific applicable preference wins (TYPE > CATEGORY > GLOBAL)."""
    rank = {PREF_LEVEL_TYPE: 2, PREF_LEVEL_CATEGORY: 1, PREF_LEVEL_GLOBAL: 0}
    applicable = []
    for level, prefCategory, prefType, prefChannel, enabled in preferenceRows:
        if prefChannel != channel:
            continue
        if level == PREF_LEVEL_TYPE and prefType == notificationType:
            applicable.append((rank[level], enabled))
        elif level == PREF_LEVEL_CATEGORY and prefCategory == category:
            applicable.append((rank[level], enabled))
        elif level == PREF_LEVEL_GLOBAL:
            applicable.append((rank[level], enabled))
    if not applicable:
        return True  # no preference = default ON
    return max(applicable, key=lambda item: item[0])[1]


# ---------------------------------------------------------------------------
# §20 language resolution: user → org policy → tenant → platform
# ---------------------------------------------------------------------------


def resolveLanguage(
    *,
    userLanguage: str,
    tenantDefault: str,
    platformDefault: str = "en-US",
) -> str:
    for candidate in (userLanguage, tenantDefault, platformDefault):
        if candidate:
            return candidate
    return platformDefault


# ---------------------------------------------------------------------------
# §24 retry classification
# ---------------------------------------------------------------------------


def isRetryable(errorCode: str) -> bool:
    from apps.notifications.domain.valueObjects.notificationTypes import (
        PERMANENT_ERROR_CODES,
    )

    return errorCode not in PERMANENT_ERROR_CODES


# ---------------------------------------------------------------------------
# §28 rate limiting — identical notification storm guard
# ---------------------------------------------------------------------------


def rateLimitKeyOf(tenantId: uuid.UUID, userId: uuid.UUID, notificationType: str) -> str:
    return f"{tenantId}:{userId}:{notificationType}"


def exceedsRateWindow(recentCount: int) -> bool:
    return recentCount >= RATE_MAX_PER_WINDOW


def withinCooldown(lastCreatedAt: datetime, now: datetime, cooldownSeconds: int) -> bool:
    if cooldownSeconds <= 0:
        return False
    return (now - lastCreatedAt).total_seconds() < cooldownSeconds


# ---------------------------------------------------------------------------
# §5 priority helpers
# ---------------------------------------------------------------------------


def outranks(a: str, b: str) -> bool:
    return PRIORITY_RANK.get(a, 0) > PRIORITY_RANK.get(b, 0)


def validateCategory(category: str, allowed: tuple[str, ...]) -> None:
    if category not in allowed:
        raise ValidationFailedError(
            "Unknown notification category.", fieldErrors={"category": category}
        )
