"""Fresh-MFA diagnostics, signed read-only previews and reviewed audit records. No schema changes."""
import json, uuid
from contextlib import nullcontext
from datetime import datetime,time,timedelta
from django.core import signing
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.dateparse import parse_date
from django.contrib.auth.hashers import is_password_usable
from apps.identity.infrastructure.models import UserModel,TenantMembershipModel,UserRoleModel,UserPermissionModel,RoleModel,RolePermissionModel,MobileAccountModel,SessionModel,AdministrativeIdentityModel,AdministrativeGovernanceModel
from apps.tenancy.infrastructure.models import TenantModel
from apps.sharedKernel.infrastructure.models import AuditEventModel
from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.domain.errors import ValidationFailedError,PermissionDeniedError,EntityNotFoundError,ConflictError
from apps.identity.infrastructure.services.administrationLock import lockedAdministrationState
from apps.identity.infrastructure.services import administrativePanel as panel

OPERATIONS={
 'user':{'suspend':'user.suspend','activate':'user.update','archive':'user.disable','restoreArchive':'user.update','reset':'user.update','mobile':'user.update','assignRole':'user.assignRole','removeRole':'user.assignRole'},
 'erase':{'erase':'user.disable'},'tenant':{'suspend':'tenant.suspend','activate':'tenant.activate','close':'tenant.close','assignManager':'user.assignRole','removeManager':'user.assignRole'},
 'identity':{'create':'user.assignRole','reset':'user.assignRole','disable':'user.assignRole','activate':'user.assignRole'},
 'role':{'update':'role.update','delete':'role.delete'},
}
LABELS={'suspend':'غیرفعال‌سازی موقت','activate':'فعال‌سازی','archive':'بایگانی حساب','restoreArchive':'بازگردانی از بایگانی','reset':'صدور رمز موقت جایگزین','mobile':'اصلاح موبایل','assignRole':'افزودن نقش','removeRole':'برداشتن نقش','erase':'حذف دائمی اطلاعات حساب','close':'بستن سازمان','assignManager':'تعیین مدیر سازمان','removeManager':'برداشتن مدیر سازمان','create':'ایجاد ورود مستقل','disable':'غیرفعال‌سازی ورود مستقل','update':'ویرایش نقش','delete':'حذف نقش'}
SALT='tekarai.superadmin.review.v1'

def supported(data):return isinstance(data,dict) and isinstance(data.get('kind'),str) and isinstance(data.get('operation'),str) and data['operation'] in OPERATIONS.get(data['kind'],{})
def _mac(value):return salted_hmac(SALT,json.dumps(value,sort_keys=True,default=str,separators=(',',':')),algorithm='sha256').hexdigest()
def _rows(model,**filters):return list(model.objects.filter(**filters).order_by(model._meta.pk.name).values())
def _access(action,target=None):
 panel.requireFreshAdministrator();panel._requireAction(action,target)

def _user(identifier):
 user=UserModel.objects.filter(id=panel._uuid(identifier),deletedAt__isnull=True).first()
 if user is None:raise EntityNotFoundError('User',str(identifier))
 return user

def _safe(user):
 tenant=TenantModel.objects.filter(id=user.tenantId).first()
 roles=list(RoleModel.objects.filter(id__in=UserRoleModel.objects.filter(userId=user.id,tenantId=user.tenantId).values('roleId')).order_by('code').values_list('name',flat=True))
 memberships=TenantMembershipModel.objects.filter(userId=user.id,tenantId=user.tenantId)
 mobile=MobileAccountModel.objects.filter(userId=user.id).first()
 alias=AdministrativeIdentityModel.objects.filter(ownerUserId=user.id).first()
 return {'administrativeUsername':alias.username if alias else '—','administrativeStatus':alias.status if alias else 'none','administrativeMustChangePassword':bool(alias and alias.mustChangePassword),'username':user.username,'displayName':user.displayName,'phone':user.phone,'status':user.status,'tenantName':tenant.name if tenant else 'سازمان یافت نشد','tenantStatus':tenant.status if tenant else 'missing','roles':roles,'activeMemberships':memberships.filter(status='active',leftAt__isnull=True).count(),'activeSessions':SessionModel.objects.filter(userId=user.id,revokedAt__isnull=True,expiresAt__gt=timezone.now()).count(),'mustChangePassword':bool(mobile and mobile.mustChangePassword)}

def diagnostics(userId):
 panel.requireFreshAdministrator();user=_user(userId);_access('user.view',user.tenantId);_access('tenant.list')
 now=timezone.now();state=_safe(user);tenant=TenantModel.objects.filter(id=user.tenantId,deletedAt__isnull=True).first()
 mobile=MobileAccountModel.objects.filter(userId=user.id).first();issues=[]
 def issue(code,message,action,blocking=True):issues.append({'code':code,'message':message,'action':action,'blocking':blocking})
 if user.kind!='human':issue('SERVICE_ACCOUNT','این حساب از نوع خدماتی است، نه حساب ورود عادی شخص.','حساب خدماتی را از مسیر حساب‌های خدماتی بررسی کنید.')
 if user.status!='active':issue('ACCOUNT_'+user.status.upper(),'حساب '+({'disabled':'بایگانی','suspended':'معلق'}.get(user.status,user.status))+' است.','برای حساب معلق فعال‌سازی، و برای حساب بایگانی بازگردانی از بایگانی را انتخاب کنید.')
 if tenant is None or tenant.status!='active':issue('TENANT_INACTIVE','سازمان حساب فعال یا موجود نیست.','ابتدا وضعیت سازمان را بررسی کنید؛ حساب را به سازمان دیگری منتقل نکنید.')
 if state['activeMemberships']==0:issue('MEMBERSHIP_INACTIVE','عضویت فعالِ پایان‌نیافته در همین سازمان پیدا نشد.','برای شخص بایگانی‌شده، پس از بررسی نقش‌ها تیک ترمیم عضویت را همراه بازگردانی تأیید کنید. برای شخص فعال، عضویت را جداگانه بررسی کنید.')
 if state['activeMemberships']>1:issue('MEMBERSHIP_AMBIGUOUS','بیش از یک عضویت فعال وجود دارد.','قبل از هر بازیابی، عضویت‌های تکراری را بررسی کنید.')
 if user.lockedUntil and user.lockedUntil>now:issue('ACCOUNT_LOCKED','حساب تا '+user.lockedUntil.isoformat()+' قفل است.','تا پایان قفل صبر کنید؛ بازیابی قفل را دور نمی‌زند.')
 if user.expiresAt and user.expiresAt<=now:issue('ACCOUNT_EXPIRED','اعتبار زمانی حساب منقضی شده است.','اعتبار زمانی را از مسیر مجاز مدیریت حساب بررسی کنید؛ بازگردانی آن را تمدید نمی‌کند.')
 if not is_password_usable(user.passwordHash):issue('PASSWORD_UNUSABLE','اعتبار رمز این حساب قابل استفاده نیست.','وضعیت حذف/اعتبار حساب را بررسی کنید؛ رمز شخصی قابل مشاهده نیست.')
 if mobile and mobile.mustChangePassword:
  expired=not mobile.temporaryExpiresAt or mobile.temporaryExpiresAt<=now
  issue('TEMPORARY_EXPIRED' if expired else 'FIRST_PASSWORD_REQUIRED','رمز موقت منقضی است.' if expired else 'تعیین اولین رمز شخصی لازم است.','پس از فعال شدن حساب رمز موقت جایگزین صادر کنید.' if expired else 'شخص باید مراحل تعیین رمز شخصی در ورود اول را کامل کند.',True)
 if not state['roles']:issue('NO_ROLE','نقش ثبت‌شده‌ای در سازمان اصلی دیده نشد.','نقش‌های شخص را بررسی کنید؛ ورود موفق به معنی دسترسی به ماژول‌ها نیست.',False)
 from apps.organization.infrastructure.models import OrganizationAssignmentModel,OrganizationDepartmentModel,OrganizationPositionModel
 postings=[]
 for item in OrganizationAssignmentModel.objects.filter(userId=user.id,tenantId=user.tenantId,isActive=True):
  postings.append({'unit':OrganizationDepartmentModel.objects.filter(id=item.departmentId,tenantId=user.tenantId).values_list('name',flat=True).first() or '—','position':OrganizationPositionModel.objects.filter(id=item.positionId,tenantId=user.tenantId).values_list('name',flat=True).first() or '—'})
 return {'userId':str(user.id),'state':state,'issues':issues,'ordinaryLoginBlocked':any(i['blocking'] for i in issues),'checkedAt':now.isoformat(),'expiresAt':user.expiresAt.isoformat() if user.expiresAt else None,'lockedUntil':user.lockedUntil.isoformat() if user.lockedUntil else None,'postings':postings,'memberships':[{'id':str(m.id),'status':m.status,'joinedAt':m.joinedAt.isoformat(),'leftAt':m.leftAt.isoformat() if m.leftAt else None} for m in TenantMembershipModel.objects.filter(userId=user.id,tenantId=user.tenantId).order_by('-joinedAt')],'note':'بررسی وضعیت ورود عادی در این لحظه است؛ صحت رمز، MFA شخص، نشست و دسترسی مؤثر به ماژول‌ها را تضمین نمی‌کند. هیچ رمزی نمایش داده نمی‌شود.'}

def _target(data):
 if not supported(data):raise ValidationFailedError('این عملیات پیش‌نمایش پشتیبانی‌شده ندارد.')
 kind=data['kind'];user=None;tenant=None;role=None
 if kind in {'user','identity','erase'}:
  user=_user(data.get('userId'));tenant=TenantModel.objects.filter(id=user.tenantId).first()
 elif kind=='tenant':
  tenant=TenantModel.objects.filter(id=panel._uuid(data.get('tenantId')),deletedAt__isnull=True).first()
  if tenant is None:raise EntityNotFoundError('Tenant',str(data.get('tenantId')))
  if data['operation'] in {'assignManager','removeManager'}:user=_user(data.get('userId'))
 else:
  role=RoleModel.objects.filter(id=panel._uuid(data.get('roleId'))).first()
  if role is None:raise EntityNotFoundError('Role',str(data.get('roleId')))
 if user and tenant and user.tenantId!=tenant.id:raise ValidationFailedError('شخص باید متعلق به همین سازمان باشد.')
 panel._requireAction(OPERATIONS[kind][data['operation']],tenant.id if tenant else None)
 return user,tenant,role

def _snapshot(data):
 user,tenant,role=_target(data);state={}
 if user:
  uid=user.id
  state.update(user=_rows(UserModel,id=uid),membership=_rows(TenantMembershipModel,userId=uid),roles=_rows(UserRoleModel,userId=uid),permissions=_rows(UserPermissionModel,userId=uid),mobile=_rows(MobileAccountModel,userId=uid),aliases=_rows(AdministrativeIdentityModel,ownerUserId=uid))
  state['sessions']=list(SessionModel.objects.filter(userId=uid).order_by('id').values('id','expiresAt','revokedAt'))
  if data.get('roleId'):state['requestedRole']=_rows(RoleModel,id=panel._uuid(data['roleId']))
 if tenant:state['tenant']=_rows(TenantModel,id=tenant.id)
 if data['kind']=='tenant':state.update(users=_rows(UserModel,tenantId=tenant.id),memberships=_rows(TenantMembershipModel,tenantId=tenant.id),roles=_rows(UserRoleModel,tenantId=tenant.id))
 if role:state.update(role=_rows(RoleModel,id=role.id),permissions=_rows(RolePermissionModel,roleId=role.id),assigned=_rows(UserRoleModel,roleId=role.id))
 state['governance']=_rows(AdministrativeGovernanceModel)
 return state

def _view(data):
 user,tenant,role=_target(data)
 before=_safe(user) if user else {'tenantName':tenant.name,'tenantStatus':tenant.status,'users':UserModel.objects.filter(tenantId=tenant.id,deletedAt__isnull=True).count()} if tenant else {'roleName':role.name,'assignments':UserRoleModel.objects.filter(roleId=role.id).count(),'actions':list(RolePermissionModel.objects.filter(roleId=role.id).order_by('actionPattern').values_list('actionPattern',flat=True))}
 notes=['کنترل نهایی مجوز، وضعیت و حفظ مدیر جایگزین هنگام اجرا دوباره انجام می‌شود.','حساب یا سازمان انتخاب‌شده را پیش از تأیید بررسی کنید.']
 op=data['operation']
 if op in {'suspend','archive','reset','disable','close','restoreArchive'}:notes.append('نشست‌های قبلی طبق نوع عملیات بسته یا نامعتبر می‌شوند؛ ورود دوباره ممکن است لازم شود.')
 if op=='restoreArchive':notes.append('همان شناسه، موبایل، رمز، نقش‌ها و سوابق حفظ می‌شود. ترمیم عضویت فقط در صورت تیک جداگانه و نیاز انجام می‌شود؛ سابقهٔ پایان عضویت پاک نمی‌شود.')
 if op=='erase':notes.append('فقط اطلاعات حساب بدون ورود و سابقه قابل پاک‌سازی است؛ شناسهٔ فنی باقی می‌ماند. در وجود وابستگی، سرور حذف را رد می‌کند.')
 if op in {'close','archive'}:notes.append('این عملیات، حذف داده‌های سازمان یا سوابق شخص نیست.')
 if op=='reset':notes.append('رمز موقت فقط پس از موفقیت، برای تحویل خصوصی نشان داده می‌شود؛ در گزارش ذخیره نمی‌شود.')
 changes={}
 if op=='mobile':changes['phone']=data.get('phone','')
 if op=='restoreArchive':changes['repairMembership']=data.get('repairMembership') is True
 if op in {'assignRole','removeRole'} and data.get('roleId'):
  changes['roleId']=data['roleId']
  chosen=RoleModel.objects.filter(id=panel._uuid(data['roleId'])).first()
  if chosen:changes['requestedRole']=chosen.name
 if data['kind']=='identity' and op=='create':changes['requestedAdminUsername']=data.get('username','')
 if role and 'actions' in data:changes['actions']=data['actions']
 return {'operation':LABELS.get(op,op),'kind':data['kind'],'targetId':str(user.id if user else tenant.id if tenant else role.id),'tenantId':str(tenant.id) if tenant else None,'before':before,'changes':changes,'notes':notes}

def preview(envelope):
 panel.requireFreshAdministrator()
 if not isinstance(envelope,dict) or not isinstance(envelope.get('request'),dict):raise ValidationFailedError('درخواست پیش‌نمایش معتبر نیست.')
 data=envelope['request'];context=currentContext()
 with lockedAdministrationState():
  view=_view(data);state=_snapshot(data)
  claims={'actor':context.actorId,'session':context.sessionId,'request':_mac(data),'state':_mac(state),'nonce':str(uuid.uuid4())}
  return {'token':signing.dumps(claims,salt=SALT,compress=True),'expiresIn':180,**view}

def commit(envelope):
 panel.requireFreshAdministrator()
 if not isinstance(envelope,dict) or not isinstance(envelope.get('request'),dict) or envelope.get('confirm') is not True:raise ValidationFailedError('تأیید نهایی عملیات لازم است.')
 data=envelope['request'];reason=panel._text(envelope,'reason',500)
 if len(reason)<3:raise ValidationFailedError('علت تغییر را حداقل سه نویسه بنویسید؛ رمز یا کد محرمانه ننویسید.')
 try:claims=signing.loads(envelope.get('token',''),salt=SALT,max_age=180)
 except (signing.BadSignature,TypeError,ValueError):raise ConflictError('پیش‌نمایش نامعتبر یا منقضی است؛ پیش‌نمایش تازه بگیرید.')
 context=currentContext()
 if not isinstance(claims,dict):raise ConflictError('پیش‌نمایش معتبر نیست.')
 if claims.get('actor')!=context.actorId or claims.get('session')!=context.sessionId or claims.get('request')!=_mac(data):raise ConflictError('درخواست یا نشست با پیش‌نمایش یکسان نیست؛ دوباره بررسی کنید.')
 with (panel.serializableReferenceReview() if data.get('kind')=='erase' else nullcontext()), lockedAdministrationState():
  if AuditEventModel.objects.filter(id=panel._uuid(claims.get('nonce'))).exists():raise ConflictError('این تأیید قبلاً استفاده شده است.')
  if claims.get('state')!=_mac(_snapshot(data)):raise ConflictError('وضعیت از زمان پیش‌نمایش تغییر کرده؛ پیش‌نمایش تازه بگیرید.')
  view=_view(data);before=view['before'];user,tenant,role=_target(data)
  handlers={'user':panel.userOperation,'erase':panel.permanentDelete,'tenant':panel.tenantOperation,'identity':panel.identityOperation,'role':panel.roleOperation}
  if user and data['kind']=='user' and data['operation'] in {'suspend','archive','reset','removeRole','restoreArchive'} and (data.get('confirm') is not True or data.get('confirmation')!=user.username):
   raise ValidationFailedError('نام کاربری دقیق شخص و تأیید اولیهٔ عملیات لازم است.')
  result=handlers[data['kind']](data)
  if user:
   user.refresh_from_db();after=_safe(user)
  elif tenant:
   tenant.refresh_from_db();after={'tenantName':tenant.name,'tenantStatus':tenant.status}
  else:
   updated=RoleModel.objects.filter(id=role.id).first();after={'roleName':updated.name if updated else 'حذف شد','actions':list(RolePermissionModel.objects.filter(roleId=role.id).order_by('actionPattern').values_list('actionPattern',flat=True))}
  if data['kind']=='erase':
   allowed={'status','tenantStatus','activeMemberships','activeSessions'};before={k:v for k,v in before.items() if k in allowed};after={k:v for k,v in after.items() if k in allowed}
  AuditEventModel.objects.create(id=panel._uuid(claims['nonce']),actorUserId=panel._uuid(context.actorId),tenantId=tenant.id if tenant else panel._uuid(context.actorTenantId),action='admin.reviewed.'+data['kind']+'.'+data['operation'],resourceType='User' if user else 'Tenant' if tenant else 'Role',resourceId=view['targetId'],beforeState=before,afterState={'state':after,'reason':reason,'operation':data['operation'],'_administrativeIdentityId':getattr(context,'administrativeIdentityId',''),'_administrativeSessionId':context.sessionId},ipAddress=getattr(context,'ipAddress','')[:64],userAgent=getattr(context,'userAgent','')[:300],correlationId=getattr(context,'correlationId',''),requestId=getattr(context,'requestId',''))
  return result

SAFE_FIELDS={'administrativeUsername','administrativeStatus','administrativeMustChangePassword','username','displayName','phone','status','tenantName','tenantStatus','roles','activeMemberships','activeSessions','mustChangePassword','users','roleName','assignments','actions'}
def _redacted(value):
 if isinstance(value,dict) and 'databaseTable' in value:
  from apps.identity.infrastructure.services.administrativeDatabase import auditState
  return auditState(value)
 return {k:v for k,v in value.items() if k in SAFE_FIELDS} if isinstance(value,dict) else {}
def reports(params):
 panel.requireFreshAdministrator();panel._requireAction('audit.view');panel._requireAction('tenant.list')
 query=AuditEventModel.objects.all().order_by('-occurredAt','-id')
 for key,field in [('tenantId','tenantId'),('actorId','actorUserId'),('userId','resourceId')]:
  if params.get(key):query=query.filter(**{field:panel._uuid(params[key]) if field!='resourceId' else str(panel._uuid(params[key]))})
 for key,field in [('action','action__icontains'),('search','afterState__reason__icontains')]:
  if params.get(key):
   if key=='search':query=query.filter(action__startswith='admin.reviewed.')
   query=query.filter(**{field:panel._text(params,key,160)})
 for key,end in [('from',False),('to',True)]:
  if params.get(key):
   try:day=parse_date(params[key])
   except (ValueError,TypeError):raise ValidationFailedError('تاریخ معتبر نیست.')
   if day is None:raise ValidationFailedError('تاریخ باید به شکل YYYY-MM-DD میلادی باشد.')
   bound=timezone.make_aware(datetime.combine(day+timedelta(days=1) if end else day,time.min))
   query=query.filter(**{'occurredAt__lt' if end else 'occurredAt__gte':bound})
 try:offset=int(params.get('offset',0))
 except (ValueError,TypeError):raise ValidationFailedError('شماره صفحه معتبر نیست.')
 if not 0<=offset<=1000000:raise ValidationFailedError('شماره صفحه معتبر نیست.')
 count=query.count();rows=list(query[offset:offset+50]);users={str(u.id):u.displayName or u.username for u in UserModel.objects.filter(id__in={r.actorUserId for r in rows if r.actorUserId})};tenants={str(t.id):t.name for t in TenantModel.objects.filter(id__in={r.tenantId for r in rows if r.tenantId})}
 items=[]
 for r in rows:
  after=r.afterState if isinstance(r.afterState,dict) else {};reviewed=r.action.startswith('admin.reviewed.')
  items.append({'id':str(r.id),'time':r.occurredAt.isoformat(),'action':r.action,'resource':r.resourceType,'resourceId':r.resourceId,'actorId':str(r.actorUserId or ''),'actorName':users.get(str(r.actorUserId),'حساب حذف‌شده/نامشخص'),'tenantId':str(r.tenantId or ''),'tenantName':tenants.get(str(r.tenantId),'سازمان حذف‌شده/نامشخص'),'reason':after.get('reason','') if reviewed else '', 'before':_redacted(r.beforeState) if reviewed else {},'after':_redacted(after.get('state')) if reviewed else {},'reviewed':reviewed,'legacyNote':'' if reviewed else 'رویداد قدیمی/مسیر دیگر؛ علت و قبل/بعد کامل در این قالب ثبت نشده است.'})
 return {'items':items,'total':count,'offset':offset,'pageSize':50,'hasMore':offset+50<count}
