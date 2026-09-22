"""Project commands (Phase 18b) — input carriers only."""

from __future__ import annotations

from dataclasses import dataclass

from apps.sharedKernel.application.messaging import Command


@dataclass(frozen=True)
class CreateProjectCommand(Command):
    tenantId: str
    code: str
    name: str
    description: str = ""
    ownerName: str = ""
    dueDate: str = ""


@dataclass(frozen=True)
class UpdateProjectCommand(Command):
    projectId: str
    name: str
    description: str = ""
    ownerName: str = ""
    dueDate: str = ""
    progress: int = 0
    health: int = 100


@dataclass(frozen=True)
class ChangeProjectStatusCommand(Command):
    projectId: str
    target: str
