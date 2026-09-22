"""Project use cases (Phase 18b) — the §8 eight-step template."""

from __future__ import annotations

import uuid
from datetime import date

from apps.projects.application.commands.projectCommands import (
    ChangeProjectStatusCommand,
    CreateProjectCommand,
    UpdateProjectCommand,
)
from apps.projects.application.dto.projectDtos import (
    ProjectDto,
    ProjectListDto,
    projectDtoFromDomain,
)
from apps.projects.application.queries.projectQueries import (
    GetProjectQuery,
    ListProjectsQuery,
)
from apps.projects.domain.entities.project import Project
from apps.projects.domain.repositories.projectRepository import (
    ProjectFilters,
    ProjectRepository,
)
from apps.projects.domain.valueObjects.projectState import ProjectCode
from apps.sharedKernel.application.ports import (
    AuditRecorder,
    Clock,
    EventDispatcher,
    PermissionGate,
    UnitOfWork,
)
from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.application.useCase import AUDIT_CREATE, AUDIT_UPDATE, UseCase
from apps.sharedKernel.domain.errors import (
    DuplicateBusinessCodeError,
    EntityNotFoundError,
    TenantAccessDeniedError,
)


def parseDateOrNone(value: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def resolveTenantId(requestedTenantId: str) -> uuid.UUID:
    if requestedTenantId:
        return uuid.UUID(requestedTenantId)
    context = currentContext()
    if context.actorTenantId:
        return uuid.UUID(context.actorTenantId)
    if context.tenantId:
        return uuid.UUID(context.tenantId)
    raise TenantAccessDeniedError("Tenant scope could not be resolved.")


class CreateProjectUseCase(UseCase[CreateProjectCommand, ProjectDto]):
    requiredAction = "project.create"

    def __init__(
        self,
        repository: ProjectRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.repository = repository

    def validateCommand(self, command: CreateProjectCommand) -> None:
        ProjectCode(command.code)

    def businessRules(self, command: CreateProjectCommand) -> None:
        tenantId = resolveTenantId(command.tenantId)
        if self.repository.existsByCode(tenantId, str(ProjectCode(command.code))):
            raise DuplicateBusinessCodeError(
                "Project code already exists in this tenant.",
                details={"ruleId": "BR-PRJ-001"},
            )

    def perform(self, command: CreateProjectCommand) -> ProjectDto:
        tenantId = resolveTenantId(command.tenantId)
        project = Project.create(
            tenantId=tenantId,
            code=ProjectCode(command.code),
            name=command.name,
            description=command.description,
            ownerName=command.ownerName,
            dueDate=parseDateOrNone(command.dueDate),
            now=self.clock.nowUtc(),
        )
        self.repository.create(project)
        self.collectEventsFrom(project)
        self.audit(
            AUDIT_CREATE,
            resourceType="Project",
            resourceId=str(project.id),
            tenantId=tenantId,
            after=project.snapshot(),
        )
        return projectDtoFromDomain(project)


class UpdateProjectUseCase(UseCase[UpdateProjectCommand, ProjectDto]):
    requiredAction = "project.update"

    def __init__(
        self,
        repository: ProjectRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.repository = repository

    def perform(self, command: UpdateProjectCommand) -> ProjectDto:
        tenantId = resolveTenantId("")
        project = self.repository.getById(tenantId, uuid.UUID(command.projectId))
        if project is None:
            raise EntityNotFoundError("Project not found.")
        project.updateDetails(
            name=command.name,
            description=command.description,
            ownerName=command.ownerName,
            dueDate=parseDateOrNone(command.dueDate),
            progress=command.progress,
            health=command.health,
            now=self.clock.nowUtc(),
        )
        self.repository.update(project)
        self.collectEventsFrom(project)
        self.audit(
            AUDIT_UPDATE,
            resourceType="Project",
            resourceId=str(project.id),
            tenantId=tenantId,
            after=project.snapshot(),
        )
        return projectDtoFromDomain(project)


class ChangeProjectStatusUseCase(UseCase[ChangeProjectStatusCommand, ProjectDto]):
    requiredAction = "project.update"

    def __init__(
        self,
        repository: ProjectRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.repository = repository

    def perform(self, command: ChangeProjectStatusCommand) -> ProjectDto:
        tenantId = resolveTenantId("")
        project = self.repository.getById(tenantId, uuid.UUID(command.projectId))
        if project is None:
            raise EntityNotFoundError("Project not found.")
        project.changeStatus(command.target, self.clock.nowUtc())
        self.repository.update(project)
        self.collectEventsFrom(project)
        self.audit(
            AUDIT_UPDATE,
            resourceType="Project",
            resourceId=str(project.id),
            tenantId=tenantId,
            after=project.snapshot(),
        )
        return projectDtoFromDomain(project)


class ListProjectsUseCase(UseCase[ListProjectsQuery, ProjectListDto]):
    requiredAction = "project.list"

    def __init__(
        self,
        repository: ProjectRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.repository = repository

    def perform(self, query: ListProjectsQuery) -> ProjectListDto:
        tenantId = resolveTenantId("")
        page = self.repository.list(
            ProjectFilters(
                tenantId=tenantId,
                status=query.status,
                search=query.search,
                ordering=query.ordering,
                page=query.page,
                pageSize=query.pageSize,
            )
        )
        return ProjectListDto(
            items=[projectDtoFromDomain(item) for item in page.items],
            totalCount=page.totalCount,
        )


class GetProjectUseCase(UseCase[GetProjectQuery, ProjectDto]):
    requiredAction = "project.view"

    def __init__(
        self,
        repository: ProjectRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.repository = repository

    def perform(self, query: GetProjectQuery) -> ProjectDto:
        tenantId = resolveTenantId("")
        project = self.repository.getById(tenantId, uuid.UUID(query.projectId))
        if project is None:
            raise EntityNotFoundError("Project not found.")
        return projectDtoFromDomain(project)
