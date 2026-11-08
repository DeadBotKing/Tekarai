"""Fail-closed tenant capability composition, independent of role authorization."""
import re
import uuid
from django.utils import timezone
from apps.tenancy.infrastructure.models import TenantModel, TenantWorkspaceModel
from apps.sharedKernel.domain.errors import PermissionDeniedError, ValidationFailedError, ConflictError, EntityNotFoundError
from .workspaceExtensions import EXTENSIONS

BUILTINS = (
 dict(code='maintenance', label='تجهیزات و تعمیرات', route='/app/maintenance/equipment', actionPrefixes=['maintenance.','analytics.','asset.'], apiPrefixes=['maintenance','analytics'], permissions=['maintenance.device.list','maintenance.workorder.list'], requires=[]),
 dict(code='projects', label='پروژه‌ها', route='/app/projects', actionPrefixes=['project.'], apiPrefixes=['projects'], permissions=['project.view','project.list'], requires=[]),
 dict(code='tasks', label='کارها', route='/app/tasks', actionPrefixes=['task.'], apiPrefixes=['tasks'], permissions=['task.view','task.list'], requires=['projects']),
 dict(code='documents', label='اسناد', route='/app/documents', actionPrefixes=['document.','maintenance.document.'], apiPrefixes=['documents','maintenance/documents'], permissions=['maintenance.document.view','document.view'], requires=[]),
 dict(code='procurement', label='تدارکات', route='/app/maintenance/procurement', actionPrefixes=['procurement.'], apiPrefixes=['procurement'], permissions=['procurement.supplier.view'], requires=['maintenance']),
 dict(code='safety', label='ایمنی', route='/app/maintenance/permits', actionPrefixes=['safety.'], apiPrefixes=['safety'], permissions=['safety.permit.view'], requires=['maintenance']),
 dict(code='communication', label='گفتگو', route='/app/chat', actionPrefixes=['communication.'], apiPrefixes=['communication'], permissions=['communication.chat.use'], requires=[]),
 dict(code='intelligence', label='هوشمندی', route='/app/intelligence', actionPrefixes=['projectIntelligence.','ai.','learning.'], apiPrefixes=['ai','learning','project-intelligence','intelligence'], permissions=['projectIntelligence.view','intelligence.view'], requires=['projects']),
)


def catalog():
    items = [dict(x) for x in BUILTINS] + [dict(x) for x in EXTENSIONS]
    seen = set()
    for item in items:
        code = item['code']
        if not re.fullmatch(r'[a-z][a-z0-9-]{1,39}', code) or code in seen:
            raise RuntimeError('Invalid/duplicate installed workspace module.')
        seen.add(code)
        if item not in BUILTINS and item['route'] != '/app/extensions/'+code:
            raise RuntimeError('Extensions require their dedicated internal route.')
        if item not in BUILTINS and (item['apiPrefixes'] != ['extensions/'+code] or item['actionPrefixes'] != ['extension.'+code+'.'] or not all(p.startswith('extension.'+code+'.') for p in item['permissions'])):
            raise RuntimeError('Extensions cannot shadow core APIs or actions.')
        for prefix in item['apiPrefixes']:
            if not re.fullmatch(r'[a-zA-Z0-9/-]+', prefix) or prefix.startswith('/') or '..' in prefix:
                raise RuntimeError('Invalid installed API prefix.')
        if not item['actionPrefixes'] or not item['apiPrefixes']:
            raise RuntimeError('A module must register server guards.')
    for item in items:
        if not set(item['requires']).issubset(seen):raise RuntimeError('Unknown dependency.')
    return items


def _tenant(tenantId):
    try: identity = uuid.UUID(str(tenantId))
    except (TypeError, ValueError):raise PermissionDeniedError('سازمان معتبر نیست.')
    tenant = TenantModel.objects.filter(id=identity, status='active', deletedAt__isnull=True).first()
    if tenant is None:raise PermissionDeniedError('سازمان فعال نیست.')
    return tenant


def profile(tenantId):
    tenant = _tenant(tenantId)
    row = TenantWorkspaceModel.objects.filter(tenantId=tenant.id).first()
    if row:
        result = {k:getattr(row,k) for k in ['title','introduction','homeMode','homeModule','enabledModules','menuOrder','revision']}
    else:
        # Exact existing Ronak identity only. No blanket legacy fallback for new tenants.
        legacy = str(tenant.id)=='0df1a1da-a7f9-4610-ae0d-96455183fb8e' and tenant.code=='platform'
        result = dict(title=tenant.name, introduction='', homeModule='', homeMode='legacy' if legacy else 'cards', enabledModules=[m['code'] for m in BUILTINS] if legacy else [], menuOrder=[], revision=0)
    # Retired/uninstalled modules can never remain enabled by stale configuration.
    result['enabledModules'] = [m for m in result['enabledModules'] if m in {x['code'] for x in catalog()}]
    return dict(result, tenantId=str(tenant.id), tenantCode=tenant.code, catalog=catalog())


def moduleForAction(action):
    matches = [(len(p), m['code']) for m in catalog() for p in m['actionPrefixes'] if action.startswith(p)]
    return max(matches)[1] if matches else None


def allowsAction(tenantId, action):
    module = moduleForAction(action)
    if module is None and action.startswith('extension.'):return False
    return module is None or module in profile(tenantId)['enabledModules']


def enforceRequest(tenantId, path):
    # Evaluated after authentication against principal tenant, never client header.
    marker = '/api/v1/'
    if not path.startswith(marker):return
    path = path[len(marker):].strip('/')
    if re.match(r'^projects/[^/]+/intelligence(?:/|$)', path):
        if 'intelligence' not in profile(tenantId)['enabledModules']:
            raise PermissionDeniedError('هوشمندی سازمان فعال نیست.')
    matches = [(len(p), m['code']) for m in catalog() for p in m['apiPrefixes'] if path==p or path.startswith(p+'/')]
    if matches:
        module = max(matches)[1]
        if module not in profile(tenantId)['enabledModules']:
            raise PermissionDeniedError('این امکان برای سازمان شما فعال نشده است.')
    elif path.startswith('extensions/'):
        raise PermissionDeniedError('قابلیت اختصاصی نصب و ثبت نشده است.')


def configure(data):
    from apps.identity.infrastructure.services.administrationLock import lockedAdministrationState
    from apps.identity.infrastructure.services.administrativeGovernance import requireFreshAdministrator
    from apps.identity.infrastructure.services.administrativePanel import _requireAction, audit
    with lockedAdministrationState():
        requireFreshAdministrator()
        current = profile(data.get('tenantId'))
        _requireAction('tenant.activate', uuid.UUID(current['tenantId']))
        if type(data.get('revision')) is not int or data['revision'] != current['revision']:
            raise ConflictError('تنظیمات تغییر کرده؛ صفحه را تازه‌سازی کنید.')
        if current['tenantId']=='0df1a1da-a7f9-4610-ae0d-96455183fb8e' and data.get('confirmRonak') is not True:
            raise ValidationFailedError('تغییر محیط فعلی روناک نیاز به تأیید صریح دارد.')
        modules, order = data.get('enabledModules'), data.get('menuOrder', [])
        known = {m['code']:m for m in catalog()}
        for values in [modules,order]:
            if not isinstance(values,list) or not all(isinstance(x,str) for x in values) or len(set(values))!=len(values):
                raise ValidationFailedError('فهرست امکانات/ترتیب منو معتبر نیست.')
        if not set(modules).issubset(known) or not set(order).issubset(modules):
            raise ValidationFailedError('فقط امکانات نصب‌شده و فعال قابل انتخاب هستند.')
        for code in modules:
            if not set(known[code]['requires']).issubset(modules):
                raise ValidationFailedError('وابستگی لازم فعال نیست: '+known[code]['label'])
        title, introduction, mode = data.get('title'),data.get('introduction',''),data.get('homeMode')
        if not isinstance(title,str) or not 1<=len(title.strip())<=160 or not isinstance(introduction,str) or len(introduction)>1200:
            raise ValidationFailedError('عنوان یا متن صفحه معتبر نیست.')
        if mode not in {'cards','list','legacy'} or (mode=='legacy' and current['tenantId']!='0df1a1da-a7f9-4610-ae0d-96455183fb8e'):
            raise ValidationFailedError('قالب صفحه اصلی معتبر نیست.')
        if mode=='legacy' and not {m['code'] for m in BUILTINS}.issubset(modules):
            raise ValidationFailedError('صفحه قدیمی روناک همه امکانات فعلی را لازم دارد؛ برای انتخاب امکانات از قالب ساده استفاده کنید.')
        homeModule=data.get('homeModule','')
        if not isinstance(homeModule,str) or (homeModule and homeModule not in modules):
            raise ValidationFailedError('صفحه شروع باید از امکانات فعال همین سازمان باشد.')
        fields=dict(homeModule=homeModule,title=title.strip(),introduction=introduction,homeMode=mode,enabledModules=modules,menuOrder=order,revision=current['revision']+1)
        row,_=TenantWorkspaceModel.objects.update_or_create(tenantId=current['tenantId'],defaults=fields)
        audit('workspace.configure','TenantWorkspace',row.tenantId,row.tenantId,{'revision':row.revision,'enabledModules':modules})
        return profile(row.tenantId)
