"""نقش «مدیر منابع انسانی» — a read-only people view (v0.14.0).

The role is seeded by ``bootstrapPlatform`` (which ``run_dev`` executes on
every start, idempotently), so it materialises on fresh *and* existing
databases. These tests pin the contract the admin UI relies on: the role
exists with its Persian name, carries exactly the read-only preset, never
gains a manage verb, and actually resolves for a granted user.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from django.core.management import call_command
from django.test import TestCase

from apps.identity.application.commands.identityCommands import (
    AssignRoleCommand,
    CreateUserCommand,
)
from apps.identity.application.queries.identityQueries import ListRolesQuery
from apps.identity.application.services.permissionCatalog import (
    ACTIONS,
    HR_MANAGER_ROLE,
    ROLE_PRESETS,
)
from apps.identity.infrastructure import container as identityContainer
from apps.identity.infrastructure.container import listRolesUseCase
from apps.identity.infrastructure.models import RoleModel, UserRoleModel
from apps.sharedKernel.application.requestContext import RequestContext, requestScope
from apps.sharedKernel.infrastructure.wiring import sharedKernelProvider
from tests.support.phase6Helpers import platformTenantId, seedPlatform

HR_ROLE_ACTIONS = ROLE_PRESETS[HR_MANAGER_ROLE]


def asAdmin(tenantId: str) -> RequestContext:
    from apps.identity.infrastructure.repositories.identityRepositoriesImpl import (
        UserRepositoryDjango,
    )
    from tests.support.phase6Helpers import PLATFORM_ADMIN_USERNAME

    admin = UserRepositoryDjango().getByUsername(platformTenantId(), PLATFORM_ADMIN_USERNAME)
    return RequestContext(
        actorId=str(admin.id) if admin else "",
        tenantId=tenantId,
        actorTenantId=tenantId,
    )


def nowUtcHelper() -> datetime:
    return datetime.now(tz=UTC)


def asUser(userId: str, tenantId: str) -> RequestContext:
    return RequestContext(actorId=userId, tenantId=tenantId, actorTenantId=tenantId)


class HrManagerPresetTests(TestCase):
    """The preset itself — codes are real and the role stays read-only."""

    def testPresetExistsAndUsesRealCatalogueCodes(self) -> None:
        catalogue = {code for code, _ in ACTIONS}
        self.assertTrue(
            HR_ROLE_ACTIONS,
            "the HR manager preset must not be empty",
        )
        unknown = [action for action in HR_ROLE_ACTIONS if action not in catalogue]
        self.assertEqual(
            unknown,
            [],
            "every HR preset action must exist in the permission catalogue",
        )

    def testPresetCoversThePeopleView(self) -> None:
        for action in (
            # personnel + performance-review pages (frontend nav and the
            # backend view use cases both ride the device registry).
            "maintenance.device.list",
            "maintenance.device.view",
            # the organisation chart, read-only.
            "organization.department.view",
            "organization.position.view",
            "organization.assignment.view",
            "organization.accessRule.view",
            # the user directory.
            "user.view",
            "user.list",
            # semi-managerial: running the appraisal process itself.
            "maintenance.review.manage",
        ):
            self.assertIn(action, HR_ROLE_ACTIONS)

    def testPresetHasNoManageVerbs(self) -> None:
        # An HR manager sees people and scores and can run the appraisal
        # round; they must not be able to rewrite the machines, the org,
        # the users or a single work order. maintenance.review.manage is
        # the one manage verb they hold — on purpose (v0.14.1).
        manageVerbs = [action for action in HR_ROLE_ACTIONS if action.endswith(".manage")]
        self.assertEqual(
            manageVerbs,
            ["maintenance.review.manage"],
            "the only manage verb must be the appraisal one",
        )
        for action in (
            "user.create",
            "user.assignRole",
            "organization.department.manage",
            "organization.accessRule.manage",
            "maintenance.device.manage",
            "maintenance.inventory.manage",
            "maintenance.workorder.route",
            "maintenance.workorder.assign",
            "role.update",
        ):
            self.assertNotIn(action, HR_ROLE_ACTIONS)


class HrManagerSeedTests(TestCase):
    """bootstrapPlatform materialises the role — idempotently."""

    def setUp(self) -> None:
        seedPlatform()

    def testRoleSeededWithPersianNameAndTenantScope(self) -> None:
        role = RoleModel.objects.get(code=HR_MANAGER_ROLE)
        self.assertEqual(role.name, "مدیر منابع انسانی")
        self.assertEqual(role.scopeType, "TENANT")
        self.assertTrue(role.isActive)

    def testSeedIsIdempotent(self) -> None:
        call_command("bootstrapPlatform", verbosity=0)
        self.assertEqual(
            RoleModel.objects.filter(code=HR_MANAGER_ROLE).count(),
            1,
            "re-running the seed must not duplicate the role",
        )

    def testRoleListedWithItsActions(self) -> None:
        # This is the query the administration → roles page calls; it needs
        # an actor holding role.list, hence the admin scope.
        with requestScope(asAdmin(str(platformTenantId()))):
            roles = listRolesUseCase().execute(ListRolesQuery())
        hr = next((role for role in roles if role.code == HR_MANAGER_ROLE), None)
        self.assertIsNotNone(hr, "hrManager must appear in the role list")
        assert hr is not None  # for the type checker
        self.assertEqual(hr.name, "مدیر منابع انسانی")
        self.assertEqual(set(hr.actions), set(HR_ROLE_ACTIONS))

    def testGrantedUserResolvesThePreset(self) -> None:
        tenantId = platformTenantId()
        gate = sharedKernelProvider("permissionGate")()
        with requestScope(asAdmin(str(tenantId))):
            member = identityContainer.createUserUseCase().execute(
                CreateUserCommand(
                    tenantId=str(tenantId),
                    username="hr.manager",
                    email="hr.manager@member.test",
                    password="Strong-Pass-2026!",
                    displayName="مدیر منابع انسانی",
                )
            )
            from apps.identity.domain.entities.tenantMembership import TenantMembership
            from apps.identity.infrastructure.repositories.identityRepositoriesImpl import (
                TenantMembershipRepositoryDjango,
            )

            TenantMembershipRepositoryDjango().create(
                TenantMembership.establish(uuid.UUID(member.id), tenantId, nowUtcHelper())
            )
            role = RoleModel.objects.get(code=HR_MANAGER_ROLE)
            identityContainer.assignRoleUseCase().execute(
                AssignRoleCommand(userId=member.id, roleId=role.id)
            )

        userId = uuid.UUID(member.id)
        # The people view: allowed to look, refused to touch.
        for action in (
            "maintenance.device.list",
            "maintenance.device.view",
            "organization.department.view",
            "organization.accessRule.view",
            "user.list",
            # the semi-managerial upgrade: the appraisal process itself.
            "maintenance.review.manage",
        ):
            self.assertTrue(
                gate.hasPermission(userId, action, tenantId=tenantId),
                f"hrManager must be allowed {action}",
            )
        for action in (
            "organization.department.manage",
            "user.create",
            "maintenance.device.manage",
            "maintenance.workorder.route",
            "role.update",
        ):
            self.assertFalse(
                gate.hasPermission(userId, action, tenantId=tenantId),
                f"hrManager must be refused {action}",
            )
        # And the grant is recorded as a plain tenant role.
        self.assertTrue(UserRoleModel.objects.filter(userId=userId, roleId=role.id).exists())

    def testHrManagerRunsTheAppraisalRound(self) -> None:
        """دوره بسازد، امتیاز ثبت کند، محاسبه کند — و ماشین‌آلات را نتواند.

        The HR user drives the real use cases (not just the gate) through a
        whole round: open a cycle, record a mark, compute the results. The
        same actor must still be refused machine management.
        """
        from apps.maintenance.application.useCases.performanceReviewUseCases import (
            ComputeCycleCommand,
            SaveCycleCommand,
            SaveRaterScoreCommand,
        )
        from apps.maintenance.infrastructure import container as maintenanceContainer
        from apps.maintenance.infrastructure.models import MaintenancePersonnelModel

        tenantId = platformTenantId()
        with requestScope(asAdmin(str(tenantId))):
            member = identityContainer.createUserUseCase().execute(
                CreateUserCommand(
                    tenantId=str(tenantId),
                    username="hr.runner",
                    email="hr.runner@member.test",
                    password="Strong-Pass-2026!",
                    displayName="مدیر منابع انسانی",
                )
            )
            from apps.identity.domain.entities.tenantMembership import TenantMembership
            from apps.identity.infrastructure.repositories.identityRepositoriesImpl import (
                TenantMembershipRepositoryDjango,
            )

            TenantMembershipRepositoryDjango().create(
                TenantMembership.establish(uuid.UUID(member.id), tenantId, nowUtcHelper())
            )
            hrRole = RoleModel.objects.get(code=HR_MANAGER_ROLE)
            identityContainer.assignRoleUseCase().execute(
                AssignRoleCommand(userId=member.id, roleId=hrRole.id)
            )
            personnel = MaintenancePersonnelModel.objects.create(
                tenantId=tenantId,
                personnelCode="HR-EMP-01",
                fullName="کارمند نمونه",
                createdAt=nowUtcHelper(),
            )

        # Everything below runs AS the HR manager, not as the admin.
        with requestScope(asUser(member.id, str(tenantId))):
            cycle = maintenanceContainer.saveReviewCycleUseCase().execute(
                SaveCycleCommand(
                    code="HR-1405",
                    name="ارزیابی نیم‌سال اول ۱۴۰۵",
                    fromDate="2026-03-21",
                    toDate="2026-09-21",
                    systemWeightPercent=30,
                )
            )
            self.assertTrue(cycle["id"])

            score = maintenanceContainer.saveRaterScoreUseCase().execute(
                SaveRaterScoreCommand(
                    cycleId=cycle["id"],
                    personnelId=str(personnel.id),
                    raterRole="hrManager",
                    score=18.5,
                    raterName="مدیر منابع انسانی",
                )
            )
            self.assertTrue(score["id"])

            computed = maintenanceContainer.computeReviewCycleUseCase().execute(
                ComputeCycleCommand(cycleId=cycle["id"])
            )
            self.assertGreaterEqual(len(computed.get("results", [])), 1)

            # …but the machine register stays closed to them.
            from apps.maintenance.application.commands.maintenanceCommands import (
                RegisterDeviceCommand,
            )
            from apps.sharedKernel.domain.errors import PermissionDeniedError

            with self.assertRaises(PermissionDeniedError):
                maintenanceContainer.registerDeviceUseCase().execute(
                    RegisterDeviceCommand(code="SHOULD-NOT-WORK", name="نباید ساخته شود")
                )
