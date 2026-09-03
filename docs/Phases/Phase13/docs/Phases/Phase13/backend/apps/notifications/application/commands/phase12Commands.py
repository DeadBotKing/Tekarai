"""Phase 12 notification commands/queries (docs/Phases/Phase12.md).

Frozen input messages for the multi-recipient broadcast model, recipient
read-state (§12.7/§12.8), delivery retry/dead-letter (§12.17/§12.18), rules
(§12.24) and the idempotent event intake (§12.38). Commands carry data only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from apps.sharedKernel.application.messaging import Command

# -- broadcast creation (§12.3/§12.7) -----------------------------------------


@dataclass(frozen=True)
class CreateBroadcastCommand(Command):
    notificationType: str
    title: str
    recipientIds: tuple = ()
    body: str = ""
    priority: str = "NORMAL"
    severity: str = "INFO"
    sourceType: str = ""
    sourceId: str = ""
    deepLink: str = ""
    language: str = ""
    metadata: dict = field(default_factory=dict)
    idempotencyKey: str = ""
    correlationId: str = ""


@dataclass(frozen=True)
class ListBroadcastsQuery(Command):
    unreadOnly: bool = False
    limit: int = 50


@dataclass(frozen=True)
class UnreadCountQuery(Command):
    pass


@dataclass(frozen=True)
class RecipientStateCommand(Command):
    notificationId: str
    action: str = "read"  # read | unread | archive | dismiss


# -- delivery (§12.14-§12.18) -------------------------------------------------


@dataclass(frozen=True)
class ListDeliveriesQuery(Command):
    notificationId: str = ""
    deadLetterOnly: bool = False
    limit: int = 100


@dataclass(frozen=True)
class RetryDeliveryCommand(Command):
    deliveryId: str


# -- rules (§12.24) -----------------------------------------------------------


@dataclass(frozen=True)
class DefineRuleCommand(Command):
    name: str
    eventType: str
    condition: dict = field(default_factory=dict)
    recipientStrategy: str = "TARGET"
    channels: tuple = ()
    priority: str = "NORMAL"
    templateKey: str = ""


# -- event intake (§12.23/§12.38) ---------------------------------------------


@dataclass(frozen=True)
class IngestEventCommand(Command):
    eventId: str
    eventType: str
    payload: dict = field(default_factory=dict)
