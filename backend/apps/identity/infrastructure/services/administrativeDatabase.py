"""Allowlisted superadmin data console. No raw SQL, introspection or arbitrary models."""
import json, uuid
from django.core import signing
from django.db.models import Q, F
from django.utils import timezone
from django.utils.crypto import salted_hmac
from apps.identity.infrastructure.services import administrativePanel as panel
from apps.identity.infrastructure.services.administrationLock import lockedAdministrationState
from apps.identity.infrastructure.models import UserModel, TenantMembershipModel, UserRoleModel
from apps.tenancy.infrastructure.models import TenantModel
from apps.organization.infrastructure.models import OrganizationDepartmentModel, OrganizationPositionModel, OrganizationAssignmentModel
from apps.maintenance.infrastructure.models import DeviceModel
from apps.documents.infrastructure.models import DocumentModel
from apps.sharedKernel.infrastructure.models import AuditEventModel
from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.domain.errors import ValidationFailedError, PermissionDeniedError, ConflictError, EntityNotFoundError

from apps.identity.domain.valueObjects.persianIdentity import validatePersianFullName

SALT='tekarai.superadmin.database.v1'
FIELD_LABELS={'id':'شناسه رکورد','tenantId':'شناسه سازمان','username':'نام کاربری','displayName':'نام نمایشی شخص','phone':'موبایل','status':'وضعیت','kind':'نوع حساب','code':'کد','name':'نام','description':'توضیحات','isActive':'فعال','level':'سطح','location':'محل استقرار','manufacturer':'سازنده','modelNumber':'مدل','serialNumber':'سریال','assetType':'نوع تجهیز','manufactureYear':'سال ساخت','capacity':'ظرفیت','powerRating':'توان','electricalSpec':'مشخصات برق','notes':'یادداشت','category':'دسته‌بندی','sizeBytes':'حجم فایل','uploadedAt':'زمان بارگذاری','userId':'شناسه شخص','isPrimary':'اصلی','joinedAt':'شروع عضویت','leftAt':'پایان عضویت','departmentId':'شناسه واحد','positionId':'شناسه سمت','userDisplayName':'نام ثبت‌شده در انتساب','roleId':'شناسه نقش','scopeType':'نوع دامنه','scopeRef':'دامنه','grantedAt':'زمان اعطا'}
# (model, label, read action, write action, visible columns, editable fields)
TABLES={
 'people':(UserModel,'افراد','user.list','user.update',('id','tenantId','username','displayName','phone','status','kind'),('displayName',)),
 'organizations':(TenantModel,'سازمان‌ها','tenant.list','tenant.create',('id','code','name','status'),('name',)),
 'departments':(OrganizationDepartmentModel,'واحدها','organization.department.view','organization.department.manage',('id','tenantId','code','name','description','status'),('name','description')),
 'positions':(OrganizationPositionModel,'سمت‌ها','organization.position.view','organization.position.manage',('id','tenantId','code','name','description','isActive','level'),('name','description')),
 'equipment':(DeviceModel,'تجهیزات','maintenance.device.list','maintenance.device.manage',('id','tenantId','code','name','status','location','manufacturer','modelNumber','serialNumber','assetType','manufactureYear','capacity','powerRating','electricalSpec','notes'),('name','location','manufacturer','modelNumber','serialNumber','assetType','manufactureYear','capacity','powerRating','electricalSpec','notes')),
 'documents':(DocumentModel,'مستندات','maintenance.document.view','maintenance.document.manage',('id','tenantId','name','category','description','sizeBytes','uploadedAt'),('name','category','description')),
 'memberships':(TenantMembershipModel,'عضویت‌ها — فقط مشاهده','user.list',None,('id','tenantId','userId','status','isPrimary','joinedAt','leftAt'),()),
 'assignments':(OrganizationAssignmentModel,'انتساب‌های سازمانی — فقط مشاهده','organization.assignment.view',None,('id','tenantId','userId','userDisplayName','departmentId','positionId','isActive','isPrimary'),()),
 'userRoles':(UserRoleModel,'نقش‌های اشخاص — فقط مشاهده','user.list',None,('id','tenantId','userId','roleId','scopeType','scopeRef','grantedAt'),()),
}

def _access():
 panel.requireFreshAdministrator()
 for action in ('tenant.list','user.list','audit.view'):panel._requireAction(action)

def _table(key):
 if not isinstance(key,str) or key not in TABLES:raise ValidationFailedError('جدول در فهرست مجاز نیست.')
 return TABLES[key]

def catalog():
 _access()
 return {'tables':[{'key':key,'label':v[1],'editable':bool(v[5]),'columns':[{'key':f,'label':FIELD_LABELS[f],'editable':f in v[5],'maxLength':min(v[0]._meta.get_field(f).max_length or 4000,4000),'required':not v[0]._meta.get_field(f).blank} for f in v[4]]} for key,v in TABLES.items()],'pageSize':50}

def _scope(key,tenantId,write=False):
 spec=_table(key);tenantId=panel._uuid(tenantId)
 tenant=TenantModel.objects.filter(id=tenantId,deletedAt__isnull=True).first()
 if not tenant:raise EntityNotFoundError('Tenant',str(tenantId))
 if write and tenant.status!='active':raise ConflictError('اصلاح اطلاعات سازمان غیرفعال از این مسیر مجاز نیست.')
 panel._requireAction(spec[2],tenantId)
 if write:
  if not spec[3]:raise PermissionDeniedError('این جدول فقط قابل مشاهده است.')
  panel._requireAction(spec[3],tenantId)
 query=spec[0].objects.filter(**({'id':tenantId} if key=='organizations' else {'tenantId':tenantId}))
 if any(f.name=='deletedAt' for f in spec[0]._meta.fields):query=query.filter(deletedAt__isnull=True)
 return spec,tenant,query

def _value(value):return value.isoformat() if hasattr(value,'isoformat') else str(value) if isinstance(value,uuid.UUID) else value

def _public(row,spec):
 result={f:_value(getattr(row,f)) for f in spec[4]};result['_truncatedFields']=[]
 for f,v in list(result.items()):
  if isinstance(v,str) and len(v)>4000:result[f]=v[:4000]+'…';result['_truncatedFields'].append(f)
 return result

def records(params):
 if params.get('purpose'):
  from apps.identity.infrastructure.services import legacyIdentityCorrections
  return legacyIdentityCorrections.records(params)
 _access();key=params.get('table');spec,tenant,query=_scope(key,params.get('tenantId'))
 try:offset=int(params.get('offset',0))
 except (ValueError,TypeError):raise ValidationFailedError('شماره صفحه معتبر نیست.')
 if offset<0 or offset>100000:raise ValidationFailedError('شماره صفحه خارج از محدوده است.')
 search=panel._text(params,'search',160,required=False)
 if search:
  textFields=[f for f in spec[4] if spec[0]._meta.get_field(f).get_internal_type() in ('CharField','TextField')]
  match=Q(pk__in=[])
  if _is_uuid(search):
   for f in spec[4]:
    if spec[0]._meta.get_field(f).get_internal_type()=='UUIDField':match|=Q(**{f:panel._uuid(search)})
  for f in textFields:match|=Q(**{f+'__icontains':search})
  query=query.filter(match)
 count=query.count()
 return {'items':[_public(row,spec) for row in query.order_by('id')[offset:offset+50]],'total':count,'offset':offset,'hasMore':offset+50<count,'tenantName':tenant.name}

def _is_uuid(value):
 try:uuid.UUID(str(value));return True
 except (ValueError,TypeError,AttributeError):return False

def _mac(value):return salted_hmac(SALT,json.dumps(value,sort_keys=True,default=str,separators=(',',':')),algorithm='sha256').hexdigest()

def _prepare(data,lock=False):
 if not isinstance(data,dict) or set(data)!={'table','tenantId','recordId','changes'}:raise ValidationFailedError('ساختار درخواست اصلاح معتبر نیست.')
 key=data['table'];spec,tenant,query=_scope(key,data['tenantId'],write=True)
 query=query.filter(id=panel._uuid(data['recordId']))
 # A no-op UPDATE obtains an actual row write lock even where SELECT FOR UPDATE is unsupported.
 # Commit only, never the read-only preview; it is rolled back on every refusal.
 if lock and spec[5]:query.update(**{spec[5][0]:F(spec[5][0])})
 row=query.first()
 if row is None:raise EntityNotFoundError('Record',str(data['recordId']))
 changes=data['changes']
 if not isinstance(changes,dict) or not changes or any(f not in spec[5] for f in changes):raise ValidationFailedError('فقط فیلدهای قابل اصلاح این جدول مجازند.')
 normalized={}
 for f,v in changes.items():
  field=spec[0]._meta.get_field(f);maximum=min(field.max_length or 4000,4000)
  if not isinstance(v,str) or len(v)>maximum or any(ord(c)<32 and not (f in {'description','notes'} and c in '\r\n\t') for c in v):raise ValidationFailedError('مقدار '+FIELD_LABELS[f]+' معتبر نیست.')
  if len(str(getattr(row,f)))>4000:raise ValidationFailedError('متن بسیار بلند را از صفحهٔ اصلی همان ماژول اصلاح کنید.')
  v=v.strip()
  if not field.blank and not v:raise ValidationFailedError(FIELD_LABELS[f]+' نباید خالی باشد.')
  if v!=getattr(row,f):
   if key=='people' and f=='displayName':validatePersianFullName(v)
   normalized[f]=v
 if not normalized:raise ValidationFailedError('تغییری برای ثبت وجود ندارد.')
 return spec,tenant,row,normalized

def _fingerprint(row,tenant):return _mac({'row':{f.attname:getattr(row,f.attname) for f in row._meta.concrete_fields},'tenant':{f.attname:getattr(tenant,f.attname) for f in tenant._meta.concrete_fields}})
def _audit(key,row,values):return {'databaseTable':key,'databaseRecord':str(row.id),'databaseValues':values}

def preview(envelope):
 _access()
 if isinstance(envelope,dict) and isinstance(envelope.get('request'),dict) and envelope['request'].get('purpose')=='persianIdentityCorrection':
  from apps.identity.infrastructure.services import legacyIdentityCorrections
  return legacyIdentityCorrections.preview(envelope)
 if not isinstance(envelope,dict):raise ValidationFailedError('درخواست معتبر نیست.')
 data=envelope.get('request');context=currentContext()
 with lockedAdministrationState():
  _access()
  spec,tenant,row,changes=_prepare(data)
  claims={'actor':context.actorId,'session':context.sessionId,'identity':getattr(context,'administrativeIdentityId',''),'request':_mac(data),'state':_fingerprint(row,tenant),'nonce':str(uuid.uuid4())}
  return {'token':signing.dumps(claims,salt=SALT,compress=True),'expiresIn':180,'operation':'اصلاح کنترل‌شدهٔ اطلاعات','kind':'database','targetId':str(row.id),'tenantId':str(tenant.id),'before':{'جدول':spec[1],'سازمان':tenant.name,'شناسه رکورد':str(row.id),**{FIELD_LABELS[f]:getattr(row,f) for f in changes}},'changes':{FIELD_LABELS[f]:v for f,v in changes.items()},'notes':['فقط فیلدهای نمایش‌داده‌شده اصلاح می‌شوند؛ شناسه، سازمان مالک، وضعیت، نقش و اعتبارنامه تغییر نمی‌کنند.','علت و قبل/بعد ثبت می‌شوند؛ رمز یا کد محرمانه در داده و علت ننویسید.']+(['نام نمایشی ذخیره‌شده در انتساب‌های همین شخص نیز همگام می‌شود.'] if data['table']=='people' else [])}

def commit(envelope):
 _access()
 if isinstance(envelope,dict) and isinstance(envelope.get('request'),dict) and envelope['request'].get('purpose')=='persianIdentityCorrection':
  from apps.identity.infrastructure.services import legacyIdentityCorrections
  return legacyIdentityCorrections.commit(envelope)
 if not isinstance(envelope,dict) or envelope.get('confirm') is not True:raise ValidationFailedError('تأیید نهایی لازم است.')
 reason=panel._text(envelope,'reason',500)
 if len(reason)<3:raise ValidationFailedError('علت تغییر باید حداقل سه نویسه باشد.')
 data=envelope.get('request');context=currentContext()
 try:claims=signing.loads(envelope.get('token',''),salt=SALT,max_age=180)
 except (signing.BadSignature,TypeError,ValueError):raise ConflictError('پیش‌نمایش منقضی یا نامعتبر است.')
 if not isinstance(claims,dict) or any(claims.get(k)!=v for k,v in {'actor':context.actorId,'session':context.sessionId,'identity':getattr(context,'administrativeIdentityId',''),'request':_mac(data)}.items()):raise ConflictError('درخواست یا نشست با پیش‌نمایش یکسان نیست.')
 with lockedAdministrationState():
  _access()
  nonce=panel._uuid(claims.get('nonce'))
  if AuditEventModel.objects.filter(id=nonce).exists():raise ConflictError('این تأیید قبلاً استفاده شده است.')
  spec,tenant,row,changes=_prepare(data,lock=True)
  _access()
  panel._requireAction(spec[3],tenant.id)
  if claims.get('state')!=_fingerprint(row,tenant):raise ConflictError('رکورد پس از پیش‌نمایش تغییر کرده است؛ دوباره بررسی کنید.')
  before=_audit(data['table'],row,{f:getattr(row,f) for f in changes})
  update=dict(changes)
  if any(f.name=='updatedAt' for f in row._meta.fields):update['updatedAt']=timezone.now()
  spec[0].objects.filter(id=row.id).update(**update)
  if data['table']=='people':OrganizationAssignmentModel.objects.filter(userId=row.id,tenantId=tenant.id).update(userDisplayName=changes['displayName'])
  after=_audit(data['table'],row,changes)
  AuditEventModel.objects.create(id=nonce,actorUserId=panel._uuid(context.actorId),tenantId=tenant.id,action='admin.reviewed.database.update',resourceType=spec[0]._meta.db_table,resourceId=str(row.id),beforeState=before,afterState={'state':after,'reason':reason,'operation':'update','_administrativeIdentityId':getattr(context,'administrativeIdentityId',''),'_administrativeSessionId':context.sessionId},ipAddress=getattr(context,'ipAddress','')[:64],userAgent=getattr(context,'userAgent','')[:300],correlationId=getattr(context,'correlationId',''),requestId=getattr(context,'requestId',''))
  row.refresh_from_db()
  return {'record':_public(row,spec)}

def auditState(value):
 """Only server-registered descriptive fields may enter the existing audit viewer."""
 if not isinstance(value,dict) or not isinstance(value.get('databaseTable'),str) or value['databaseTable'] not in TABLES:return {}
 spec=TABLES[value['databaseTable']];values=value.get('databaseValues')
 if not isinstance(values,dict) or not _is_uuid(value.get('databaseRecord')):return {}
 editable=spec[5]+(('username',) if value['databaseTable']=='people' and value.get('identityCorrection') is True else ())
 return {'جدول':spec[1],'شناسه رکورد':value['databaseRecord'],**{FIELD_LABELS[k]:v for k,v in values.items() if k in editable and isinstance(v,str) and len(v)<=4000}}
