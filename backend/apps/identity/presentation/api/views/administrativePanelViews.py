from django.urls import path
from rest_framework.views import APIView
from apps.identity.infrastructure.services import administrativePanel as panel
from apps.identity.infrastructure.services import administrativeReview as review
from apps.identity.presentation.api.views.mobileViews import privateResponse
from apps.sharedKernel.presentation.api.permissions import IsAuthenticated
from apps.sharedKernel.presentation.api.rateLimiting import enforceRateLimit
from apps.sharedKernel.domain.errors import ValidationFailedError
from apps.tenancy.infrastructure.models import TenantModel


class SetupView(APIView):
    permission_classes = [IsAuthenticated]

    @enforceRateLimit('auth:login')
    def post(self, request):
        return privateResponse(panel.setup(request.data))


class PanelView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return privateResponse(panel.overview())

    @enforceRateLimit('auth:mfa')
    def post(self, request):
        if not isinstance(request.data, dict):
            raise ValidationFailedError('درخواست معتبر نیست.')
        if review.supported(request.data):
            panel.requireFreshAdministrator()
            raise ValidationFailedError('ابتدا پیش‌نمایش تازه و تأیید نهایی همراه علت تغییر را ثبت کنید.')
        kind = request.data.get('kind')
        handlers = {'user': panel.userOperation, 'role': panel.roleOperation, 'tenant': panel.tenantOperation,
            'identity': panel.identityOperation, 'erase': panel.permanentDelete, 'handoff': panel.retireLegacy, 'stepup': panel.stepUp}
        if kind not in handlers:
            raise ValidationFailedError('نوع عملیات معتبر نیست.')
        return privateResponse(handlers[kind](request.data))


class DiagnosticsView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, userId):return privateResponse(review.diagnostics(userId))

class ReviewPreviewView(APIView):
    permission_classes = [IsAuthenticated]
    @enforceRateLimit('auth:mfa')
    def post(self, request):return privateResponse(review.preview(request.data))

class ReviewCommitView(APIView):
    permission_classes = [IsAuthenticated]
    @enforceRateLimit('auth:mfa')
    def post(self, request):return privateResponse(review.commit(request.data))

class ReviewReportView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):return privateResponse(review.reports(request.query_params))


class AppearanceView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request, code):
        tenant = TenantModel.objects.filter(code=code, status='active', deletedAt__isnull=True).first()
        if tenant is None:
            return privateResponse(None)
        return privateResponse(panel.tenantDto(tenant)['appearance'])


class CurrentAppearanceView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        from apps.sharedKernel.application.requestContext import currentContext
        tenant = TenantModel.objects.filter(id=currentContext().actorTenantId, status='active', deletedAt__isnull=True).first()
        return privateResponse(panel.tenantDto(tenant)['appearance'] if tenant else None)


class OrganizationEntryView(APIView):
    authentication_classes = []
    permission_classes = []
    def get(self, request):
        return privateResponse([{'code': t.code, 'name': panel.tenantDto(t)['appearance']['displayName']}
            for t in TenantModel.objects.filter(status='active', deletedAt__isnull=True).order_by('code')])


def registerAdministrativePanelEndpoints():
    from apps.sharedKernel.presentation.api.openapi import EndpointSpec, registerEndpoint
    for method, path, summary in [
        ('POST','superadmin/setup','Selected existing owner only; fresh primary password; pending independent credential, no automatic handoff.'),
        ('GET','superadmin/panel','Cross-organization management; verified independent administrative session and fresh MFA required.'),
        ('POST','superadmin/panel','Audited privileged mutations; server scope, delegation and survivor guards; no idempotency-stored secrets.'),
        ('GET','superadmin/panel/people/{userId}/diagnostics','Fresh-MFA account and membership diagnostics; no secrets.'),
        ('POST','superadmin/panel/preview','Read-only signed preview, valid 180 seconds.'),
        ('POST','superadmin/panel/commit','Bound one-use preview, reason and fresh-MFA required; atomic reviewed audit.'),
        ('GET','superadmin/panel/database','Allowlisted tenant-scoped data console; no credentials or raw SQL.'),
        ('POST','superadmin/panel/database/preview','Signed read-only preview of descriptive-field correction.'),
        ('POST','superadmin/panel/database/commit','One-use bound preview, fresh independent MFA, reason and atomic audit.'),
        ('GET','superadmin/panel/reports','Filtered, paginated, allowlisted administrative audit.'),
        ('GET','organization-appearance/current','Runtime appearance of the authenticated session organization.')]:
        registerEndpoint(EndpointSpec(method=method,path='api/v1/'+path,summary=summary,permission='authenticated',
            errorCodes=['AUTH_AUTHENTICATION_REQUIRED','PERM_PERMISSION_DENIED','VAL_VALIDATION_FAILED']))
    for path in ['organization-entry','organization-appearance/{code}']:
        registerEndpoint(EndpointSpec(method='GET',path='api/v1/'+path,summary='Public active-organization login branding only; no account or credential metadata.',authentication='none'))


class DatabaseConsoleView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        from apps.identity.infrastructure.services import administrativeDatabase as database
        return privateResponse(database.records(request.query_params) if request.query_params.get('table') else database.catalog())

class DatabasePreviewView(APIView):
    permission_classes = [IsAuthenticated]
    @enforceRateLimit('auth:mfa')
    def post(self, request):
        from apps.identity.infrastructure.services import administrativeDatabase as database
        return privateResponse(database.preview(request.data))

class DatabaseCommitView(APIView):
    permission_classes = [IsAuthenticated]
    @enforceRateLimit('auth:mfa')
    def post(self, request):
        from apps.identity.infrastructure.services import administrativeDatabase as database
        return privateResponse(database.commit(request.data))
