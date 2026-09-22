"""Task use cases (Phase 18b)."""

from __future__ import annotations

import uuid
from datetime import date

from apps.sharedKernel.application.ports import (
    AuditRecorder,
    Clock,
    EventDispatcher,
    PermissionGate,
    UnitOfWork,
)
from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.application.useCase import AUDIT_CREATE, AUDIT_UPDATE, UseCase
from apps.sharedKernel.domain.errors import EntityNotFoundError, TenantAccessDeniedError
from apps.tasks.application.commands.taskCommands import (
    ChangeTaskStatusCommand,
    CreateTaskCommand,
    UpdateTaskCommand,
)
from apps.tasks.application.dto.taskDtos import TaskDto, TaskListDto, taskDtoFromDomain
from apps.tasks.application.queries.taskQueries import GetTaskQuery, ListTasksQuery
from apps.tasks.domain.entities.task import Task
from apps.tasks.domain.repositories.taskRepository import TaskFilters, TaskRepository
from apps.tasks.domain.valueObjects.taskState import TaskPriority


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


def resolveProjectId(value: str) -> uuid.UUID | None:
    return uuid.UUID(value) if value else None


class CreateTaskUseCase(UseCase[CreateTaskCommand, TaskDto]):
    requiredAction = "task.create"

    def __init__(
        self,
        repository: TaskRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.repository = repository

    def validateCommand(self, command: CreateTaskCommand) -> None:
        TaskPriority(command.priority)

    def perform(self, command: CreateTaskCommand) -> TaskDto:
        tenantId = resolveTenantId(command.tenantId)
        task = Task.create(
            tenantId=tenantId,
            projectId=resolveProjectId(command.projectId),
            title=command.title,
            priority=TaskPriority(command.priority),
            assigneeName=command.assigneeName,
            dueDate=parseDateOrNone(command.dueDate),
            estimate=command.estimate,
            now=self.clock.nowUtc(),
        )
        self.repository.create(task)
        self.collectEventsFrom(task)
        self.audit(
            AUDIT_CREATE,
            resourceType="Task",
            resourceId=str(task.id),
            tenantId=tenantId,
            after=task.snapshot(),
        )
        return taskDtoFromDomain(task)


class UpdateTaskUseCase(UseCase[UpdateTaskCommand, TaskDto]):
    requiredAction = "task.update"

    def __init__(
        self,
        repository: TaskRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.repository = repository

    def validateCommand(self, command: UpdateTaskCommand) -> None:
        TaskPriority(command.priority)

    def perform(self, command: UpdateTaskCommand) -> TaskDto:
        tenantId = resolveTenantId("")
        task = self.repository.getById(tenantId, uuid.UUID(command.taskId))
        if task is None:
            raise EntityNotFoundError("Task not found.")
        task.updateDetails(
            title=command.title,
            priority=TaskPriority(command.priority),
            assigneeName=command.assigneeName,
            dueDate=parseDateOrNone(command.dueDate),
            estimate=command.estimate,
            now=self.clock.nowUtc(),
        )
        self.repository.update(task)
        self.collectEventsFrom(task)
        self.audit(
            AUDIT_UPDATE,
            resourceType="Task",
            resourceId=str(task.id),
            tenantId=tenantId,
            after=task.snapshot(),
        )
        return taskDtoFromDomain(task)


class ChangeTaskStatusUseCase(UseCase[ChangeTaskStatusCommand, TaskDto]):
    requiredAction = "task.update"

    def __init__(
        self,
        repository: TaskRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.repository = repository

    def perform(self, command: ChangeTaskStatusCommand) -> TaskDto:
        tenantId = resolveTenantId("")
        task = self.repository.getById(tenantId, uuid.UUID(command.taskId))
        if task is None:
            raise EntityNotFoundError("Task not found.")
        task.changeStatus(command.target, self.clock.nowUtc())
        self.repository.update(task)
        self.collectEventsFrom(task)
        self.audit(
            AUDIT_UPDATE,
            resourceType="Task",
            resourceId=str(task.id),
            tenantId=tenantId,
            after=task.snapshot(),
        )
        return taskDtoFromDomain(task)


class ListTasksUseCase(UseCase[ListTasksQuery, TaskListDto]):
    requiredAction = "task.list"

    def __init__(
        self,
        repository: TaskRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.repository = repository

    def perform(self, query: ListTasksQuery) -> TaskListDto:
        tenantId = resolveTenantId("")
        page = self.repository.list(
            TaskFilters(
                tenantId=tenantId,
                projectId=query.projectId,
                status=query.status,
                search=query.search,
                ordering=query.ordering,
                page=query.page,
                pageSize=query.pageSize,
            )
        )
        return TaskListDto(
            items=[taskDtoFromDomain(item) for item in page.items], totalCount=page.totalCount
        )


class GetTaskUseCase(UseCase[GetTaskQuery, TaskDto]):
    requiredAction = "task.view"

    def __init__(
        self,
        repository: TaskRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.repository = repository

    def perform(self, query: GetTaskQuery) -> TaskDto:
        tenantId = resolveTenantId("")
        task = self.repository.getById(tenantId, uuid.UUID(query.taskId))
        if task is None:
            raise EntityNotFoundError("Task not found.")
        return taskDtoFromDomain(task)
