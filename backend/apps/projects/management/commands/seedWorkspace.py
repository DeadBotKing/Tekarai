"""seedWorkspace — idempotent demo data for the workspace-delivery contexts.

What it provisions (safe to re-run — existing rows are left untouched):

1. The platform tenant + administrator (via ``bootstrapPlatform``).
2. A demo customer tenant with a tenant admin and a member.
3. A fixed set of projects (BR-PRJ-001 unique codes) and tasks in both tenants.

Runs against whatever database is configured (SQL Server Express on the
user's machine, SQLite in CI). It uses the same use-case layer as the live
API so every row is audited and event-driven, exactly like a real request.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

from django.core.management import call_command
from django.core.management.base import BaseCommand

from apps.identity.application.commands.identityCommands import CreateUserCommand
from apps.identity.domain.entities.tenantMembership import TenantMembership
from apps.identity.domain.valueObjects.userState import validatePasswordStrength
from apps.identity.infrastructure.container import createUserUseCase
from apps.identity.infrastructure.models import RoleModel
from apps.identity.infrastructure.repositories.identityRepositoriesImpl import (
    AccessRepositoryDjango,
    TenantMembershipRepositoryDjango,
    UserRepositoryDjango,
)
from apps.maintenance.application.commands.maintenanceCommands import (
    RecordDevicePmCommand,
    RegisterDeviceCommand,
    SubmitWorkOrderCommand,
)
from apps.maintenance.infrastructure.container import (
    recordDevicePmUseCase,
    registerDeviceUseCase,
    submitWorkOrderUseCase,
)
from apps.maintenance.infrastructure.models import DeviceModel, WorkOrderModel
from apps.projects.application.commands.projectCommands import CreateProjectCommand
from apps.projects.infrastructure.container import createProjectUseCase
from apps.projects.infrastructure.models import ProjectModel
from apps.projects.infrastructure.repositories.projectRepositoryImpl import (
    ProjectRepositoryDjango,
)
from apps.sharedKernel.application.requestContext import RequestContext, requestScope
from apps.sharedKernel.domain.errors import ValidationFailedError
from apps.tasks.application.commands.taskCommands import CreateTaskCommand
from apps.tasks.infrastructure.container import createTaskUseCase
from apps.tasks.infrastructure.models import TaskModel
from apps.tenancy.application.commands.tenantCommands import CreateTenantCommand
from apps.tenancy.infrastructure.container import createTenantUseCase
from apps.tenancy.infrastructure.repositories.tenantRepositoryImpl import (
    TenantRepositoryDjango,
)

DEFAULT_PASSWORD = "Tekarai-Demo-2026!"

#: (code, name, description, owner, dueDate) — codes follow BR-PRJ-001.
SEED_PROJECTS: list[tuple[str, str, str, str, str]] = [
    (
        "NOVA-24",
        "Nova Plant Modernization",
        "Modernize production planning and asset visibility across three sites.",
        "Maya Chen",
        "2026-10-18",
    ),
    (
        "ATLAS-11",
        "Atlas Quality System",
        "A governed quality workflow for engineering and validation teams.",
        "Jon Bell",
        "2026-11-02",
    ),
    (
        "ORBIT-07",
        "Orbit Energy Reporting",
        "Unify operational energy data and compliance reporting.",
        "Sara Novak",
        "2026-09-29",
    ),
    (
        "BRIDGE-18",
        "Bridge Supplier Portal",
        "Create a secure supplier collaboration experience.",
        "Owen Wright",
        "2026-12-15",
    ),
]

#: (project code, title, priority, assignee, dueDate, estimate)
SEED_TASKS: list[tuple[str, str, str, str, str, str]] = [
    ("NOVA-24", "Validate equipment data contract", "high", "Maya Chen", "2026-09-10", "2d"),
    ("NOVA-24", "Run workspace access review", "critical", "Maya Chen", "2026-09-03", "1h"),
    ("ATLAS-11", "Publish quality workflow v2", "normal", "Jon Bell", "2026-09-14", "1d"),
    ("ORBIT-07", "Review supplier risk report", "critical", "Sara Novak", "2026-09-08", "4h"),
    ("ORBIT-07", "Reconcile monthly energy readings", "high", "Jon Bell", "2026-09-11", "2d"),
    ("BRIDGE-18", "Close acceptance evidence", "normal", "Owen Wright", "2026-09-22", "3h"),
]

#: (code, name, location, pmIntervalDays, lastPmDate) — Persian CMMS demo devices.
SEED_DEVICES: list[tuple[str, str, str, int, str]] = [
    ("PUMP-01", "پمپ خنک‌کننده اصلی", "سالن تولید A", 30, "2026-08-20"),
    ("CNC-14", "دستگاه تراش CNC", "کارگاه ماشین‌کاری", 45, "2026-09-10"),
    ("COMP-07", "کمپرسور هوا", "اتاق تأسیسات", 60, "2026-09-01"),
    ("GEN-02", "ژنراتور اضطراری", "محوطه بیرونی", 90, "2026-04-01"),
]

#: (device code, title, orderType, priority, requestedBy) — Persian demo work orders.
SEED_WORK_ORDERS: list[tuple[str, str, str, str, str]] = [
    ("PUMP-01", "صدای غیرعادی از یاتاقان پمپ", "corrective", "high", "علی رضایی"),
    ("CNC-14", "کالیبراسیون دوره‌ای محور Z", "preventive", "normal", "سیستم PM"),
    ("GEN-02", "تعویض باتری ژنراتور", "corrective", "critical", "حسین محمدی"),
    ("COMP-07", "بازرسی فشار مخزن هوا", "inspection", "low", "سیستم PM"),
]


class Command(BaseCommand):
    help = "Seed demo tenants, users, projects and tasks (idempotent)."

    def add_arguments(self, parser) -> None:  # noqa: ANN001
        parser.add_argument(
            "--password",
            default="",
            help="Password for the seeded demo users (default: env WORKSPACE_SEED_PASSWORD).",
        )
        parser.add_argument(
            "--demo-tenant",
            default="acme",
            help="Code of the demo customer tenant (lowercase slug).",
        )

    def handle(self, *args, **options) -> None:  # noqa: ANN002, ANN003
        password = options["password"] or os.environ.get(
            "WORKSPACE_SEED_PASSWORD", DEFAULT_PASSWORD
        )
        demoCode = str(options["demo_tenant"])

        # 1) Platform tenant + admin + catalogue + roles (idempotent).
        os.environ.setdefault("PLATFORM_ADMIN_PASSWORD", DEFAULT_PASSWORD)
        call_command("bootstrapPlatform", verbosity=0)
        platform = TenantRepositoryDjango().getByCode("platform")
        if platform is None:  # pragma: no cover — bootstrapPlatform guarantees it
            raise RuntimeError("bootstrapPlatform did not create the platform tenant.")
        self.stdout.write("seeding workspace for tenant: platform")
        self._seedProjects(platform.id)
        self._seedTasks(platform.id)
        self._seedDevices(platform.id)
        self._seedWorkOrders(platform.id)

        # 2) Demo customer tenant + users + workspace.
        demo = self._ensureTenant(demoCode, "Acme Industries")
        self._ensureUser(
            demo.id,
            f"{demoCode}-admin",
            f"{demoCode}-admin@tekarai.local",
            "Acme Administrator",
            password,
            "tenantAdmin",
        )
        self._ensureUser(
            demo.id,
            f"{demoCode}-member",
            f"{demoCode}-member@tekarai.local",
            "Acme Member",
            password,
            "member",
        )
        self.stdout.write(f"seeding workspace for tenant: {demoCode}")
        self._seedProjects(demo.id)
        self._seedTasks(demo.id)
        self._seedDevices(demo.id)
        self._seedWorkOrders(demo.id)

        self.stdout.write(self.style.SUCCESS("seedWorkspace complete."))

    # -- tenants ------------------------------------------------------------

    def _ensureTenant(self, code: str, name: str):
        repository = TenantRepositoryDjango()
        existing = repository.getByCode(code)
        if existing is not None:
            self.stdout.write(f"  tenant exists: {code}")
            return existing
        useCase = createTenantUseCase()
        useCase.requiredAction = ""  # first-run seed has no actor yet
        with requestScope(RequestContext(actorId="", tenantId="")):
            useCase.execute(CreateTenantCommand(code=code, name=name))
        self.stdout.write(f"  tenant created: {code}")
        created = repository.getByCode(code)
        assert created is not None
        return created

    # -- users --------------------------------------------------------------

    def _ensureUser(
        self,
        tenantId: uuid.UUID,
        username: str,
        email: str,
        displayName: str,
        password: str,
        roleCode: str,
    ) -> None:
        repository = UserRepositoryDjango()
        access = AccessRepositoryDjango()
        roleId = RoleModel.objects.get(code=roleCode).id
        existing = repository.getByUsername(tenantId, username)
        if existing is None:
            try:
                validatePasswordStrength(password)
            except ValidationFailedError as exc:
                self.stderr.write(f"  password policy failure for {username}: {exc.fieldErrors}")
                return
            useCase = createUserUseCase()
            useCase.requiredAction = ""  # first-run seed has no actor yet
            with requestScope(RequestContext(actorId="", tenantId=str(tenantId))):
                userDto = useCase.execute(
                    CreateUserCommand(
                        tenantId=str(tenantId),
                        username=username,
                        email=email,
                        password=password,
                        displayName=displayName,
                    )
                )
            userId = uuid.UUID(userDto.id)
            access.grantRoleToUser(userId, tenantId, roleId)
            self._ensureMembership(userId, tenantId)
            self.stdout.write(f"  user created: {username}")
        else:
            access.grantRoleToUser(existing.id, tenantId, roleId)
            self._ensureMembership(existing.id, tenantId)
            self.stdout.write(f"  user ready: {username}")

    def _ensureMembership(self, userId: uuid.UUID, tenantId: uuid.UUID) -> None:
        membershipRepository = TenantMembershipRepositoryDjango()
        if membershipRepository.get(userId, tenantId) is None:
            membership = TenantMembership.establish(
                userId=userId, tenantId=tenantId, now=self._now()
            )
            membershipRepository.create(membership)

    # -- workspace ----------------------------------------------------------

    def _seedProjects(self, tenantId: uuid.UUID) -> None:
        for code, name, description, owner, dueDate in SEED_PROJECTS:
            if ProjectRepositoryDjango().existsByCode(tenantId, code):
                self.stdout.write(f"  project exists: {code}")
                continue
            useCase = createProjectUseCase()
            useCase.requiredAction = ""  # first-run seed has no actor yet
            with requestScope(RequestContext(actorId="", tenantId=str(tenantId))):
                useCase.execute(
                    CreateProjectCommand(
                        tenantId=str(tenantId),
                        code=code,
                        name=name,
                        description=description,
                        ownerName=owner,
                        dueDate=dueDate,
                    )
                )
            self.stdout.write(f"  project created: {code}")

    def _seedTasks(self, tenantId: uuid.UUID) -> None:
        projectIds: dict[str, uuid.UUID] = {
            model.code: model.id
            for model in ProjectModel.objects.filter(tenantId=tenantId, deletedAt__isnull=True)
        }
        for projectCode, title, priority, assignee, dueDate, estimate in SEED_TASKS:
            projectId = projectIds.get(projectCode)
            if projectId is None:
                self.stderr.write(f"  skipping task (no project {projectCode}): {title}")
                continue
            if TaskModel.objects.filter(
                tenantId=tenantId, projectId=projectId, title=title, deletedAt__isnull=True
            ).exists():
                continue
            useCase = createTaskUseCase()
            useCase.requiredAction = ""  # first-run seed has no actor yet
            with requestScope(RequestContext(actorId="", tenantId=str(tenantId))):
                useCase.execute(
                    CreateTaskCommand(
                        tenantId=str(tenantId),
                        projectId=str(projectId),
                        title=title,
                        priority=priority,
                        assigneeName=assignee,
                        dueDate=dueDate,
                        estimate=estimate,
                    )
                )
            self.stdout.write(f"  task created: {title}")

    # -- maintenance (CMMS) -------------------------------------------------

    def _seedDevices(self, tenantId: uuid.UUID) -> None:
        for code, name, location, interval, lastPm in SEED_DEVICES:
            if DeviceModel.objects.filter(
                tenantId=tenantId, code=code, deletedAt__isnull=True
            ).exists():
                self.stdout.write(f"  device exists: {code}")
                continue
            registerUseCase = registerDeviceUseCase()
            registerUseCase.requiredAction = ""  # first-run seed has no actor yet
            with requestScope(RequestContext(actorId="", tenantId=str(tenantId))):
                dto = registerUseCase.execute(
                    RegisterDeviceCommand(
                        tenantId=str(tenantId),
                        code=code,
                        name=name,
                        location=location,
                        pmIntervalDays=interval,
                    )
                )
                if lastPm:
                    pmUseCase = recordDevicePmUseCase()
                    pmUseCase.requiredAction = ""
                    pmUseCase.execute(RecordDevicePmCommand(deviceId=dto.id, performedOn=lastPm))
            self.stdout.write(f"  device created: {code}")

    def _seedWorkOrders(self, tenantId: uuid.UUID) -> None:
        deviceIds: dict[str, uuid.UUID] = {
            model.code: model.id
            for model in DeviceModel.objects.filter(tenantId=tenantId, deletedAt__isnull=True)
        }
        for deviceCode, title, orderType, priority, requestedBy in SEED_WORK_ORDERS:
            deviceId = deviceIds.get(deviceCode)
            if deviceId is None:
                self.stderr.write(f"  skipping work order (no device {deviceCode}): {title}")
                continue
            if WorkOrderModel.objects.filter(
                tenantId=tenantId, deviceId=deviceId, title=title, deletedAt__isnull=True
            ).exists():
                continue
            useCase = submitWorkOrderUseCase()
            useCase.requiredAction = ""  # first-run seed has no actor yet
            with requestScope(RequestContext(actorId="", tenantId=str(tenantId))):
                useCase.execute(
                    SubmitWorkOrderCommand(
                        tenantId=str(tenantId),
                        deviceId=str(deviceId),
                        title=title,
                        orderType=orderType,
                        priority=priority,
                        requestedByName=requestedBy,
                    )
                )
            self.stdout.write(f"  work order created: {title}")

    @staticmethod
    def _now() -> datetime:
        return datetime.now(tz=UTC)
