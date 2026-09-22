"""Projects composition root (Phase 18b)."""

from __future__ import annotations

from apps.projects.application.useCases.projectUseCases import (
    ChangeProjectStatusUseCase,
    CreateProjectUseCase,
    GetProjectUseCase,
    ListProjectsUseCase,
    UpdateProjectUseCase,
)
from apps.projects.infrastructure.repositories.projectRepositoryImpl import (
    ProjectRepositoryDjango,
)
from apps.sharedKernel.infrastructure.wiring import sharedKernelProvider


def projectRepository() -> ProjectRepositoryDjango:
    return ProjectRepositoryDjango()


def _deps() -> dict:
    return {
        "repository": projectRepository(),
        "unitOfWork": sharedKernelProvider("unitOfWork")(),
        "auditRecorder": sharedKernelProvider("auditRecorder")(),
        "eventDispatcher": sharedKernelProvider("eventDispatcher")(),
        "permissionGate": sharedKernelProvider("permissionGate")(),
        "clock": sharedKernelProvider("clock")(),
    }


def createProjectUseCase() -> CreateProjectUseCase:
    return CreateProjectUseCase(**_deps())


def updateProjectUseCase() -> UpdateProjectUseCase:
    return UpdateProjectUseCase(**_deps())


def changeProjectStatusUseCase() -> ChangeProjectStatusUseCase:
    return ChangeProjectStatusUseCase(**_deps())


def listProjectsUseCase() -> ListProjectsUseCase:
    return ListProjectsUseCase(**_deps())


def getProjectUseCase() -> GetProjectUseCase:
    return GetProjectUseCase(**_deps())
