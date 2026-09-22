"""Tasks composition root (Phase 18b)."""

from __future__ import annotations

from apps.sharedKernel.infrastructure.wiring import sharedKernelProvider
from apps.tasks.application.useCases.taskUseCases import (
    ChangeTaskStatusUseCase,
    CreateTaskUseCase,
    GetTaskUseCase,
    ListTasksUseCase,
    UpdateTaskUseCase,
)
from apps.tasks.infrastructure.repositories.taskRepositoryImpl import TaskRepositoryDjango


def taskRepository() -> TaskRepositoryDjango:
    return TaskRepositoryDjango()


def _deps() -> dict:
    return {
        "repository": taskRepository(),
        "unitOfWork": sharedKernelProvider("unitOfWork")(),
        "auditRecorder": sharedKernelProvider("auditRecorder")(),
        "eventDispatcher": sharedKernelProvider("eventDispatcher")(),
        "permissionGate": sharedKernelProvider("permissionGate")(),
        "clock": sharedKernelProvider("clock")(),
    }


def createTaskUseCase() -> CreateTaskUseCase:
    return CreateTaskUseCase(**_deps())


def updateTaskUseCase() -> UpdateTaskUseCase:
    return UpdateTaskUseCase(**_deps())


def changeTaskStatusUseCase() -> ChangeTaskStatusUseCase:
    return ChangeTaskStatusUseCase(**_deps())


def listTasksUseCase() -> ListTasksUseCase:
    return ListTasksUseCase(**_deps())


def getTaskUseCase() -> GetTaskUseCase:
    return GetTaskUseCase(**_deps())
