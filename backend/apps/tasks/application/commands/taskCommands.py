"""Task commands (Phase 18b)."""

from __future__ import annotations

from dataclasses import dataclass

from apps.sharedKernel.application.messaging import Command


@dataclass(frozen=True)
class CreateTaskCommand(Command):
    tenantId: str
    projectId: str = ""
    title: str = ""
    priority: str = "normal"
    assigneeName: str = ""
    dueDate: str = ""
    estimate: str = ""


@dataclass(frozen=True)
class UpdateTaskCommand(Command):
    taskId: str
    title: str
    priority: str = "normal"
    assigneeName: str = ""
    dueDate: str = ""
    estimate: str = ""


@dataclass(frozen=True)
class ChangeTaskStatusCommand(Command):
    taskId: str
    target: str
