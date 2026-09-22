"""Task value objects — closed status + priority sets (Phase 18b)."""

from __future__ import annotations

from dataclasses import dataclass

from apps.sharedKernel.domain.errors import ValidationFailedError
from apps.sharedKernel.domain.valueObjects import ValueObject

TASK_BACKLOG = "backlog"
TASK_TODO = "todo"
TASK_IN_PROGRESS = "inProgress"
TASK_REVIEW = "review"
TASK_DONE = "done"

TASK_STATUSES = (TASK_BACKLOG, TASK_TODO, TASK_IN_PROGRESS, TASK_REVIEW, TASK_DONE)

TASK_PRIORITY_LOW = "low"
TASK_PRIORITY_NORMAL = "normal"
TASK_PRIORITY_HIGH = "high"
TASK_PRIORITY_CRITICAL = "critical"

TASK_PRIORITIES = (
    TASK_PRIORITY_LOW,
    TASK_PRIORITY_NORMAL,
    TASK_PRIORITY_HIGH,
    TASK_PRIORITY_CRITICAL,
)


@dataclass(frozen=True)
class TaskStatus(ValueObject):
    value: str

    def __post_init__(self) -> None:
        if self.value not in TASK_STATUSES:
            raise ValidationFailedError("Invalid task status.", fieldErrors={"status": self.value})

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class TaskPriority(ValueObject):
    value: str

    def __post_init__(self) -> None:
        if self.value not in TASK_PRIORITIES:
            raise ValidationFailedError(
                "Invalid task priority.", fieldErrors={"priority": self.value}
            )

    def __str__(self) -> str:
        return self.value
