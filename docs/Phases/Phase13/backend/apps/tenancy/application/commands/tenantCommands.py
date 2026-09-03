"""Tenant commands (Phase 06 §5) — input carriers only, no HTTP."""

from __future__ import annotations

from dataclasses import dataclass

from apps.sharedKernel.application.messaging import Command


@dataclass(frozen=True)
class CreateTenantCommand(Command):
    code: str
    name: str


@dataclass(frozen=True)
class ChangeTenantStatusCommand(Command):
    tenantId: str
    target: str
    reason: str = ""


@dataclass(frozen=True)
class SuspendTenantCommand(Command):
    tenantId: str
    reason: str = ""
