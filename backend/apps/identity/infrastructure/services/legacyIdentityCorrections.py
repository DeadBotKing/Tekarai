"""Opt-in, per-person Persian correction. No translation, bulk update, new alias or password change."""
import uuid
from django.core import signing
from django.db import IntegrityError
from django.db.models import F
from django.utils import timezone
from apps.identity.domain.valueObjects.persianIdentity import FULL_NAME, USERNAME, validatePersianFullName, validatePersianUsername
from apps.identity.infrastructure.models import UserModel, SessionModel, AdministrativeSessionModel
from apps.identity.infrastructure.services import administrativeDatabase as db
from apps.identity.infrastructure.services.administrationLock import lockedAdministrationState
from apps.organization.infrastructure.models import OrganizationAssignmentModel
from apps.sharedKernel.infrastructure.models import AuditEventModel
from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.domain.errors import ValidationFailedError, PermissionDeniedError, ConflictError, EntityNotFoundError

PURPOSE = 'persianIdentityCorrection'
SALT = 'tekarai.superadmin.persian-identity-correction.v1'
FIELDS = ('displayName', 'username')

def needed(row):
    return [key for key, valid in [('displayName',3 <= len(row.displayName) <= 160 and FULL_NAME.fullmatch(row.displayName)), ('username',3 <= len(row.username) <= 64 and USERNAME.fullmatch(row.username))] if not valid]

def records(params):
    db._access()
    if params.get('table') != 'people' or params.get('purpose') != PURPOSE:
        raise ValidationFailedError('فهرست اصلاح مشخصات معتبر نیست.')
    spec, tenant, query = db._scope('people', params.get('tenantId'))
    try: offset = int(params.get('offset', 0))
    except (ValueError, TypeError): raise ValidationFailedError('شماره صفحه معتبر نیست.')
    if not 0 <= offset <= 100000: raise ValidationFailedError('شماره صفحه خارج از محدوده است.')
    search = db.panel._text(params, 'search', 160, required=False).casefold()
    items = []; count = 0
    # Portable across SQL Server and SQLite; no DB-specific regex or guessed transliteration.
    for row in query.filter(kind='human').only(*spec[4]).order_by('id').iterator(chunk_size=500):
        missing = needed(row)
        if not missing or (search and search not in (' '.join([str(row.id), row.displayName, row.username, row.phone])).casefold()): continue
        if offset <= count < offset + 50:
            item = db._public(row, spec); item['needsCorrection'] = missing; items.append(item)
        count += 1
    return {'items':items,'total':count,'offset':offset,'hasMore':offset+50<count,'tenantName':tenant.name}

def prepare(data, lock=False):
    keys = {'table','tenantId','recordId','changes','purpose','confirmation','acknowledgeUsernameChange'}
    if not isinstance(data,dict) or set(data)!=keys or data.get('table')!='people' or data.get('purpose')!=PURPOSE:
        raise ValidationFailedError('ساختار درخواست اصلاح مشخصات معتبر نیست.')
    spec, tenant, query = db._scope('people',data['tenantId'],write=True)
    query = query.filter(id=db.panel._uuid(data['recordId']),kind='human')
    if lock: query.update(displayName=F('displayName'))
    row = query.first()
    if row is None: raise EntityNotFoundError('User',str(data['recordId']))
    if not needed(row): raise ConflictError('این حساب دیگر نیازمند فارسی‌سازی نیست؛ فهرست را تازه کنید.')
    changes=data['changes']
    if not isinstance(changes,dict) or not changes or any(key not in FIELDS for key in changes):
        raise ValidationFailedError('فقط نام کامل و نام کاربری همین شخص قابل اصلاح است.')
    normalized={}
    for key,value in changes.items():
        if not isinstance(value,str): raise ValidationFailedError('مشخصات فارسی معتبر وارد کنید.')
        value=value.strip()
        if value==getattr(row,key): continue
        (validatePersianFullName if key=='displayName' else validatePersianUsername)(value)
        normalized[key]=value
    if not normalized: raise ValidationFailedError('تغییری برای ثبت وجود ندارد.')
    if 'username' in normalized:
        if data['confirmation']!=row.username or data['acknowledgeUsernameChange'] is not True:
            raise ValidationFailedError('نام کاربری فعلی را دقیق بنویسید و تحویل شناسهٔ جدید و خروج نشست‌های عادی را تأیید کنید.')
        if UserModel.objects.filter(tenantId=tenant.id,username__iexact=normalized['username']).exclude(id=row.id).exists():
            raise ConflictError('این نام کاربری در همین سازمان قبلاً استفاده شده است؛ نام دیگری انتخاب کنید.')
    return spec,tenant,row,normalized

def preview(envelope):
    db._access()
    if not isinstance(envelope,dict): raise ValidationFailedError('درخواست معتبر نیست.')
    data=envelope.get('request'); context=currentContext()
    with lockedAdministrationState():
        db._access(); spec,tenant,row,changes=prepare(data)
        claims={'actor':context.actorId,'session':context.sessionId,'identity':getattr(context,'administrativeIdentityId',''),'request':db._mac(data),'state':db._fingerprint(row,tenant),'nonce':str(uuid.uuid4())}
        notes=['هیچ ترجمه یا اصلاحی خودکار نیست؛ فقط مقادیر تأییدشدهٔ همین شخص ثبت می‌شوند.','شناسهٔ شخص، شماره، ایمیل، رمز، وضعیت، نقش‌ها، عضویت‌ها و سوابق حفظ می‌شوند.','نام کاربری و عوامل ورود مستقل مدیریت تغییر نمی‌کنند.']
        if 'username' in changes: notes+=['نام کاربری حساب به مقدار جدید تغییر می‌کند؛ شناسهٔ جدید را جداگانه به شخص تحویل دهید. ایمیل قبلی به‌عنوان مسیر ورود حفظ می‌شود.','همهٔ نشست‌های عادی این شخص بسته می‌شوند؛ او با نام کاربری جدید و همان رمز قبلی دوباره وارد می‌شود. ورود با ایمیل قبلی برقرار است؛ شمارهٔ ثبت‌شده تغییر نمی‌کند.']
        if 'displayName' in changes: notes+=['نام ذخیره‌شده در انتساب‌های همین شخص و همین سازمان همگام می‌شود.']
        return {'token':signing.dumps(claims,salt=SALT,compress=True),'expiresIn':180,'operation':'فارسی‌سازی مشخصات حساب موجود','kind':'database','targetId':str(row.id),'tenantId':str(tenant.id),'before':{'سازمان':tenant.name,'شناسه شخص':str(row.id),'نام شخص':row.displayName,'نام کاربری فعلی':row.username},'changes':{db.FIELD_LABELS[k]:v for k,v in changes.items()},'notes':notes}

def audit(row,values):
    return {'databaseTable':'people','databaseRecord':str(row.id),'databaseValues':values,'identityCorrection':True}

def commit(envelope):
    db._access()
    if not isinstance(envelope,dict) or envelope.get('confirm') is not True: raise ValidationFailedError('تأیید نهایی لازم است.')
    reason=db.panel._text(envelope,'reason',500)
    if len(reason)<3: raise ValidationFailedError('علت تغییر باید حداقل سه نویسه باشد.')
    data=envelope.get('request'); context=currentContext()
    try: claims=signing.loads(envelope.get('token',''),salt=SALT,max_age=180)
    except (signing.BadSignature,TypeError,ValueError): raise ConflictError('پیش‌نمایش منقضی یا نامعتبر است.')
    binding={'actor':context.actorId,'session':context.sessionId,'identity':getattr(context,'administrativeIdentityId',''),'request':db._mac(data)}
    if not isinstance(claims,dict) or any(claims.get(k)!=v for k,v in binding.items()): raise ConflictError('درخواست یا نشست با پیش‌نمایش یکسان نیست.')
    with lockedAdministrationState():
        db._access(); nonce=db.panel._uuid(claims.get('nonce'))
        if AuditEventModel.objects.filter(id=nonce).exists(): raise ConflictError('این تأیید قبلاً استفاده شده است.')
        spec,tenant,row,changes=prepare(data,lock=True)
        db._access(); db.panel._requireAction('user.update',tenant.id)
        if claims.get('state')!=db._fingerprint(row,tenant): raise ConflictError('مشخصات شخص پس از پیش‌نمایش تغییر کرده است؛ دوباره بررسی کنید.')
        before=audit(row,{key:getattr(row,key) for key in changes}); now=timezone.now()
        try: UserModel.objects.filter(id=row.id,tenantId=tenant.id).update(**changes,updatedAt=now)
        except IntegrityError as exc: raise ConflictError('نام کاربری هم‌زمان ثبت شده است؛ دوباره بررسی و نام دیگری انتخاب کنید.') from exc
        if 'displayName' in changes: OrganizationAssignmentModel.objects.filter(userId=row.id,tenantId=tenant.id).update(userDisplayName=changes['displayName'])
        revoked=SessionModel.objects.filter(userId=row.id,revokedAt__isnull=True).exclude(id__in=AdministrativeSessionModel.objects.values('sessionId')).update(revokedAt=now) if 'username' in changes else 0
        AuditEventModel.objects.create(id=nonce,actorUserId=db.panel._uuid(context.actorId),tenantId=tenant.id,action='admin.reviewed.database.update',resourceType=spec[0]._meta.db_table,resourceId=str(row.id),beforeState=before,afterState={'state':audit(row,changes),'reason':reason,'operation':'update','ordinarySessionsRevoked':revoked,'_administrativeIdentityId':getattr(context,'administrativeIdentityId',''),'_administrativeSessionId':context.sessionId},ipAddress=getattr(context,'ipAddress','')[:64],userAgent=getattr(context,'userAgent','')[:300],correlationId=getattr(context,'correlationId',''),requestId=getattr(context,'requestId',''))
        row.refresh_from_db()
        return {'record':db._public(row,spec),'ordinarySessionsRevoked':revoked,'usernameChanged':'username' in changes,'independentManagementLoginUnchanged':True}
