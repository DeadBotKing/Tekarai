from rest_framework.views import APIView
from apps.sharedKernel.presentation.api.permissions import IsAuthenticated
from apps.sharedKernel.presentation.api.rateLimiting import enforceRateLimit
from apps.sharedKernel.application.requestContext import currentContext
from apps.identity.presentation.api.views.mobileViews import privateResponse
from apps.identity.infrastructure.services.administrativeGovernance import requireFreshAdministrator
from apps.identity.infrastructure.services.administrativePanel import _requireAction
from apps.tenancy.infrastructure.services.organizationWorkspace import profile, configure

class CurrentWorkspaceView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self,request):
        context=currentContext()
        from apps.identity.infrastructure.repositories.identityRepositoriesImpl import AccessRepositoryDjango
        from apps.identity.infrastructure.services.administrativeAuthentication import administrativeGrants
        from apps.identity.domain.services.permissionEvaluator import PermissionEvaluator
        import uuid
        actor,tenant=uuid.UUID(context.actorId),uuid.UUID(context.actorTenantId)
        grants=list(AccessRepositoryDjango().grantsOfUser(actor,tenant))+administrativeGrants(actor)
        result=profile(tenant)
        if not context.administrativeIdentityId:
            result['catalog']=[m for m in result['catalog'] if m['code'] in result['enabledModules']]
        result['permissions']=PermissionEvaluator().expandActionCodes(grants)
        return privateResponse(result)

class ManageWorkspaceView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self,request,tenantId):
        requireFreshAdministrator()
        _requireAction('tenant.list',tenantId)
        return privateResponse(profile(tenantId))
    @enforceRateLimit('auth:mfa')
    def post(self,request,tenantId):
        from apps.sharedKernel.domain.errors import ValidationFailedError
        if not isinstance(request.data,dict):raise ValidationFailedError('درخواست معتبر نیست.')
        data=dict(request.data);data['tenantId']=str(tenantId)
        return privateResponse(configure(data))

from apps.sharedKernel.presentation.api.openapi import EndpointSpec, registerEndpoint
for method,path in [('GET','organization-workspace/current'),('GET','superadmin/organizations/{tenantId}/workspace'),('POST','superadmin/organizations/{tenantId}/workspace')]:
    registerEndpoint(EndpointSpec(method=method,path='api/v1/'+path,summary='Organization composition; current principal tenant or independent superadmin with fresh MFA.',permission='authenticated',errorCodes=['PERM_PERMISSION_DENIED','VAL_VALIDATION_FAILED','SYS_CONCURRENCY_CONFLICT']))
