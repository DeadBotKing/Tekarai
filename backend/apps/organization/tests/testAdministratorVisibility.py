"""Regression: admin can create work orders but sees [] after org adoption."""
import uuid
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient
from apps.identity.application.services.principalDirectory import isTenantAdministratorForAction
from apps.identity.infrastructure.models import RoleModel, UserRoleModel, UserPermissionModel, PermissionModel, TenantMembershipModel
from apps.identity.infrastructure.services.authorizationCache import bumpVersion
from apps.organization.application.services import orgService
from apps.organization.application.services.accessContract import scopeFilterForUser, userCanActOnRecord
from apps.maintenance.application.useCases.workOrderUseCases import organizationScopeFilters
from apps.maintenance.infrastructure.models import DeviceModel
from tests.support.phase6Helpers import loginViaApi, platformTenantId, seedPlatform

ACTION = "maintenance.workorder.list"
class AdministratorVisibilityTests(TestCase):
    def setUp(self):
        cache.clear(); seedPlatform()
        self.tenant = platformTenantId()
        self.client = APIClient()
        tokens = loginViaApi(self.client)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {tokens['accessToken']}"}
        orgService.seedDefaults(self.tenant)
        profile = self.client.get("/api/v1/organization/my-access", **self.auth)
        self.user = uuid.UUID(profile.json()["data"]["userId"])
        self.device = DeviceModel.objects.create(tenantId=self.tenant,code="ADMIN-PUMP",name="پمپ آزمایشی")

    def test_admin_without_posting_has_tenant_wide_list_and_record_access(self):
        self.assertTrue(scopeFilterForUser(self.tenant,self.user,ACTION).unrestricted)
        self.assertEqual(organizationScopeFilters(self.tenant,str(self.user)),{})
        self.assertTrue(userCanActOnRecord(self.tenant,self.user,"maintenance.workorder.view",ownerUserId=str(uuid.uuid4())))

    def test_create_two_then_list_and_open_both_over_http(self):
        ids=[]
        for title in ("رفع نشتی پمپ", "بررسی صدای پمپ"):
            response=self.client.post("/api/v1/maintenance/work-orders", {"deviceId":str(self.device.id),"title":title,"description":"آزمون","orderType":"corrective","priority":"normal","department":"general","requestedByName":"مدیر"}, format="json", **self.auth)
            self.assertEqual(response.status_code,201,response.content)
            ids.append(response.json()["data"]["id"])
        response=self.client.get("/api/v1/maintenance/work-orders",**self.auth)
        self.assertEqual(response.status_code,200,response.content)
        self.assertTrue(set(ids).issubset({row["id"] for row in response.json()["data"]}))
        for item in ids:
            detail=self.client.get(f"/api/v1/maintenance/work-orders/{item}",**self.auth)
            self.assertEqual(detail.status_code,200,detail.content)

    def test_regular_operational_role_does_not_bypass_org_scope(self):
        UserRoleModel.objects.filter(userId=self.user,roleId__in=RoleModel.objects.filter(code__in=["platformAdmin","tenantAdmin"]).values("id")).delete()
        bumpVersion(self.user)
        self.assertFalse(isTenantAdministratorForAction(self.tenant,self.user,ACTION))
        self.assertTrue(scopeFilterForUser(self.tenant,self.user,ACTION).denied)
        self.assertFalse(userCanActOnRecord(self.tenant,self.user,"maintenance.workorder.view",ownerUserId=str(self.user)))

    def test_explicit_deny_still_wins(self):
        permission=PermissionModel.objects.get(code=ACTION)
        UserPermissionModel.objects.create(userId=self.user,permissionId=permission.id,actionPattern=ACTION,effect="deny",scopeType="TENANT")
        bumpVersion(self.user)
        self.assertFalse(isTenantAdministratorForAction(self.tenant,self.user,ACTION))
        self.assertFalse(scopeFilterForUser(self.tenant,self.user,ACTION).unrestricted)
        response=self.client.get("/api/v1/maintenance/work-orders",**self.auth)
        self.assertEqual(response.status_code,403,response.content)

    def test_missing_membership_never_grants_cross_tenant_access(self):
        self.assertFalse(isTenantAdministratorForAction(uuid.uuid4(),self.user,ACTION))

    def test_inactive_admin_role_is_not_a_bypass(self):
        RoleModel.objects.filter(code__in=["platformAdmin","tenantAdmin"]).update(isActive=False)
        bumpVersion(self.user)
        self.assertFalse(isTenantAdministratorForAction(self.tenant,self.user,ACTION))

    def test_inactive_membership_is_not_a_bypass(self):
        TenantMembershipModel.objects.filter(userId=self.user,tenantId=self.tenant).update(status="suspended")
        self.assertFalse(isTenantAdministratorForAction(self.tenant,self.user,ACTION))

    def test_admin_still_needs_the_specific_action(self):
        self.assertFalse(isTenantAdministratorForAction(self.tenant,self.user,"unknown.module.action"))
