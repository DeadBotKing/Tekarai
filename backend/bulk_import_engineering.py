"""
bulk_import_engineering.py — ورود گروهی ۴۴ نفر فنی و مهندسی
- فقط روی سرور اصلی اجرا شود
- قبل از اجرا بکاپ دارید (Tekarai-2025-11-18.bak)
- همه کاربران با رمز موقت Tekarai@1234 ساخته می‌شوند — در اولین ورود باید عوض کنند

اجرا:
  cd C:/Users/Mitra/Desktop/Tekarai/backend
  .venv/Scripts/python.exe bulk_import_engineering.py            -> پیش‌نمایش
  .venv/Scripts/python.exe bulk_import_engineering.py --execute   -> اجرای واقعی
"""
import os, sys, django
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from django.db import transaction
from apps.identity.infrastructure.models import UserModel
from apps.tenancy.infrastructure.models import TenantModel
from apps.organization.infrastructure.models import (
    OrganizationDepartmentModel, OrganizationPositionModel, OrganizationAssignmentModel
)

DRY_RUN = "--execute" not in sys.argv

# ---------- داده‌های پاک‌شده از PDF ----------
PERSONS = [
    ("مهدی یارمحمدی", "09129432012", "مدیر فنی و مهندسی"),
    ("مصطفی صفا", "09120535494", "رییس مکانیک و طراحی مهندسی"),
    ("کرمی شهبازی آذرک", "09363822395", "واحد پروژه فنی و مهندسی"),
    ("پیمان یاری", "09193499439", "واحد پروژه فنی و مهندسی"),
    ("حسن عین پور", "09167453720", "واحد پروژه فنی و مهندسی"),
    ("یونس صالح", "09195231690", "واحد پروژه فنی و مهندسی"),
    ("هادی قاسمی", "09184939450", "سرپرست فنی جامدات"),
    ("آیهان حیدری", "09330146665", "کارشناس فنی جامدات"),
    ("میلاد محمدی", "09002550821", "کارشناس فنی جامدات"),
    ("مصطفی فرد", "09359959538", "کارشناس فنی جامدات"),
    ("احمد شهابی راد", "09190512839", "تراشکار"),
    ("علی نعمتی", "09358422007", "کارشناس فنی تزریقی"),
    ("مرتضی رضایی مقدم", "09127569668", "سرپرست فنی تزریقی خط1 و2"),
    ("سجاد کهنسال", "09128840364", "سرپرست فنی تزریقی خط3"),
    ("میلاد رایگان", "09186230775", "کارشناس فنی تزریقی1و2"),
    ("امیرحسین زلفی", "09183936442", "کارشناس فنی تزریقی1و2"),
    ("جواد منعمی", "09120262857", "کارشناس فنی تزریقی3"),
    ("فرزاد فرمانیان", "09190522042", "کارشناس فنی جامدات"),
    ("سامان صارمی", "09167563107", "کارشناس فنی تزریقی3"),
    ("احسان مروتی", "09198720900", "سرپرست فریزدرایر"),
    ("بهنام زهره", "09120682369", "کارشناس فریزدرایر"),
    ("مهدی نصیری", "09128855367", "کارشناس فریزدرایر"),
    ("محسن رمضانی ویشکی", "09372750444", "کارشناس فریزدرایر"),
    ("مهرشاد کهریزی", "09183689891", "رییس برق و اتوماسیون صنعتی"),
    ("آرش حیدری", "09185072143", "کارشناس برق و اتوماسیون صنعتی"),
    ("محمد جورکش", "09370398323", "سرپرست برق و اتوماسیون صنعتی"),
    ("جواد امیرشاهی", "09193560513", "کارشناس برق و اتوماسیون صنعتی"),
    ("دانیال امینی", "09933181900", "کارشناس برق و اتوماسیون صنعتی"),
    ("بهروز رسولی", "09100823904", "کارشناس برق و اتوماسیون صنعتی"),
    ("محمد جعفری", "09193561023", "کارشناس برق و اتوماسیون صنعتی"),
    ("امیرحسین حاجی لو", "09223540245", "کارشناس برق و اتوماسیون صنعتی"),
    ("عباس فرخ", "09196189256", "رییس تهویه مطبوع وHvac"),
    ("مجید نظری وفا", "09189169465", "پرسنل تاسیسات"),
    ("ناصر ساالری فر", "09184341321", "پرسنل تاسیسات"),
    ("علی زمانی", "09196562494", "پرسنل تاسیسات"),
    ("علی پور عوض", "09376557247", "پرسنل تاسیسات"),
    ("یونس فراهانی", "09128554542", "پرسنل تاسیسات"),
    ("حسین کرد", "09398308536", "پرسنل موتورخانه"),
    ("اسعد هاللی سامی", "09168535529", "پرسنل موتورخانه"),
    ("فرشاد رجبی", "09378985255", "پرسنل موتورخانه"),
    ("عماد رضائی پور", "09116498513", "سرپرستHvac"),
    ("ابراهیم محمدی", "09113282043", "رییس نگهداری و تعمیرات"),
    ("میترا یاری", "09183032356", "کارشناس تعمیرات و نگهداری"),
    ("میثم حاصلی", "09193551129", "کارشناس فنی تزریقی3"),
]

DEFAULT_PASSWORD = "Tekarai@1234"

def map_department(dept_str):
    d = dept_str
    if "مکانیک" in d: return ("ENG_MECH", "مکانیک و طراحی مهندسی")
    if "پروژه" in d: return ("ENG_PROJ", "واحد پروژه")
    if "جامدات" in d: return ("ENG_JAM", "فنی جامدات")
    if "تزریقی" in d: return ("ENG_TAZ", "فنی تزریقی")
    if "فریز" in d: return ("ENG_FREEZE", "فریزدرایر")
    if "برق" in d: return ("ENG_ELEC", "برق و اتوماسیون صنعتی")
    if "تهویه" in d or "Hvac" in d or "تاسیسات" in d or "موتورخانه" in d: return ("ENG_HVAC", "تاسیسات و تهویه مطبوع")
    if "نگهداری" in d or "تعمیرات" in d: return ("ENG_MAINT", "نگهداری و تعمیرات")
    if "مدیر فنی" in d: return ("ENG_ROOT", "فنی و مهندسی")
    if "تراشکار" in d: return ("ENG_MECH", "مکانیک و طراحی مهندسی")
    return ("ENG_ROOT", "فنی و مهندسی")

def position_level(name):
    if "مدیر" in name: return 100
    if "رییس" in name: return 80
    if "سرپرست" in name: return 60
    if "کارشناس" in name: return 40
    if "تراشکار" in name: return 35
    if "پرسنل" in name: return 20
    return 30

# ---------- Tenant ----------
tenant = TenantModel.objects.filter(deletedAt__isnull=True).order_by("createdAt").first()
if not tenant:
    print("[ERROR] هیچ تنانتی پیدا نشد!")
    sys.exit(1)
print(f"Tenant: {tenant.code} ({tenant.name}) - {tenant.id}")
print(f"Mode: {'DRY-RUN' if DRY_RUN else 'EXECUTE'} — {len(PERSONS)} نفر")
print("="*60)

# ---------- Departments ----------
DEPTS_DEF = {
    "ENG_ROOT": ("فنی و مهندسی", None),
    "ENG_MECH": ("مکانیک و طراحی مهندسی", "ENG_ROOT"),
    "ENG_PROJ": ("واحد پروژه", "ENG_ROOT"),
    "ENG_JAM": ("فنی جامدات", "ENG_ROOT"),
    "ENG_TAZ": ("فنی تزریقی", "ENG_ROOT"),
    "ENG_FREEZE": ("فریزدرایر", "ENG_ROOT"),
    "ENG_ELEC": ("برق و اتوماسیون صنعتی", "ENG_ROOT"),
    "ENG_HVAC": ("تاسیسات و تهویه مطبوع", "ENG_ROOT"),
    "ENG_MAINT": ("نگهداری و تعمیرات", "ENG_ROOT"),
}

departments = {}
for code, (name, parent_code) in DEPTS_DEF.items():
    existing = OrganizationDepartmentModel.objects.filter(tenantId=tenant.id, code=code).first()
    if existing:
        departments[code] = existing
        print(f"[DEPT] موجود: {code} - {name}")
    else:
        if DRY_RUN:
            print(f"[DEPT] ایجاد می‌شود: {code} - {name}")
            # fake object for dry-run
            departments[code] = type("obj", (), {"id": None, "code": code, "name": name})()
        else:
            parent_id = departments.get(parent_code).id if parent_code and parent_code in departments else None
            # اگر parent هنوز ساخته نشده، دوباره بگیر
            if parent_code and parent_code not in departments:
                p = OrganizationDepartmentModel.objects.filter(tenantId=tenant.id, code=parent_code).first()
                parent_id = p.id if p else None
            obj = OrganizationDepartmentModel.objects.create(
                tenantId=tenant.id, code=code, name=name,
                status="active", parentId=parent_id, isSystem=False
            )
            departments[code] = obj
            print(f"[DEPT] ساخته شد: {code} - {name}")

# ---------- Positions ----------
unique_positions = sorted(set(d for _,_,d in PERSONS))
positions = {}
for idx, pos_name in enumerate(unique_positions, 1):
    code = f"POS_{idx:02d}"
    # try find by name
    existing = OrganizationPositionModel.objects.filter(tenantId=tenant.id, name=pos_name).first()
    if existing:
        positions[pos_name] = existing
        print(f"[POS] موجود: {pos_name} ({existing.code})")
    else:
        if DRY_RUN:
            print(f"[POS] ایجاد می‌شود: {pos_name} -> {code}")
            positions[pos_name] = type("obj", (), {"id": None, "code": code, "name": pos_name})()
        else:
            obj = OrganizationPositionModel.objects.create(
                tenantId=tenant.id, code=code, name=pos_name,
                level=position_level(pos_name), isActive=True, isSystem=False
            )
            positions[pos_name] = obj
            print(f"[POS] ساخته شد: {pos_name} -> {code} (level {obj.level})")

# ---------- Users + Assignments ----------
from apps.identity.application.commands.identityCommands import CreateUserCommand
from apps.identity.infrastructure.container import createUserUseCase
from apps.sharedKernel.application.requestContext import RequestContext, requestScope

print("\n--- Users ---")
created = 0
skipped = 0
for name, phone, dept in PERSONS:
    username = phone  # 0912...
    email = f"{phone}@tekarai.local"
    existing = UserModel.objects.filter(tenantId=tenant.id, username=username).first()
    if existing:
        print(f"[SKIP] موجود: {name} ({username})")
        skipped += 1
        # ensure assignment exists
        dept_code, _ = map_department(dept)
        dept_obj = departments.get(dept_code)
        pos_obj = positions.get(dept)
        if not DRY_RUN and dept_obj and pos_obj and dept_obj.id and pos_obj.id:
            exists = OrganizationAssignmentModel.objects.filter(tenantId=tenant.id, userId=existing.id, departmentId=dept_obj.id, positionId=pos_obj.id).first()
            if not exists:
                OrganizationAssignmentModel.objects.create(
                    tenantId=tenant.id, userId=existing.id, userDisplayName=name,
                    departmentId=dept_obj.id, positionId=pos_obj.id, isPrimary=True, isActive=True
                )
                print(f"      ↳ انتصاب اضافه شد: {dept_obj.name} / {pos_obj.name}")
        continue

    if DRY_RUN:
        dept_code, dept_name = map_department(dept)
        print(f"[NEW] {name} | {username} | {dept_name} / {dept}")
        created += 1
        continue

    # real create
    try:
        useCase = createUserUseCase()
        useCase.requiredAction = ""
        with requestScope(RequestContext(actorId="", tenantId=str(tenant.id))):
            dto = useCase.execute(CreateUserCommand(
                tenantId=str(tenant.id), username=username, email=email,
                password=DEFAULT_PASSWORD, displayName=name
            ))
        user_id = dto.id
        # also set phone field
        UserModel.objects.filter(id=user_id).update(phone=phone)
        # assignment
        dept_code, _ = map_department(dept)
        dept_obj = departments[dept_code]
        pos_obj = positions[dept]
        OrganizationAssignmentModel.objects.create(
            tenantId=tenant.id, userId=user_id, userDisplayName=name,
            departmentId=dept_obj.id, positionId=pos_obj.id, isPrimary=True, isActive=True
        )
        print(f"[OK] ساخته شد: {name} ({username}) -> {dept_obj.name} / {pos_obj.name}")
        created += 1
    except Exception as e:
        print(f"[ERR] {name} ({username}): {e}")

print("\n" + "="*60)
if DRY_RUN:
    print(f"پیش‌نمایش تمام شد: {created} نفر جدید، {skipped} تکراری")
    print("برای اجرای واقعی: .venv/Scripts/python.exe bulk_import_engineering.py --execute")
else:
    print(f"انجام شد: {created} نفر ساخته شد، {skipped} نفر از قبل موجود بود")
    print(f"رمز همه: {DEFAULT_PASSWORD} — در اولین ورود عوض شود")
    print("واحد سازمانی و سمت همه ست شد. دسترسی‌ها را بعدا با هم تنظیم می‌کنیم.")
print("="*60)
