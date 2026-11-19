"""
import_production_44.py — ورود ۴۴ نفر فنی و مهندسی مستقیم روی SQL Server اصلی (Tekarai)
- با Windows Authentication وصل می‌شود (نیاز به Run as Administrator ندارد ولی بهتر است)
- رمز همه: Tekarai@1234 (هش شده با Django PBKDF2)

اجرا:
  cd C:/Users/Mitra/Desktop/Tekarai/backend
  .venv/Scripts/python.exe import_production_44.py            -> پیش‌نمایش
  .venv/Scripts/python.exe import_production_44.py --execute   -> اجرای واقعی
"""
import os, sys, uuid
from datetime import datetime, timezone

# برای هش پسورد از Django استفاده می‌کنیم (بدون نیاز به DB)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
import django
from django.conf import settings
if not settings.configured:
    settings.configure(
        SECRET_KEY='temp-for-hash-only',
        INSTALLED_APPS=['django.contrib.auth','django.contrib.contenttypes'],
        PASSWORD_HASHERS=['django.contrib.auth.hashers.PBKDF2PasswordHasher'],
    )
    django.setup()

from django.contrib.auth.hashers import make_password

import pyodbc

# ---------- تنظیم اتصال ----------
CONN_STR = (
    r"DRIVER={ODBC Driver 17 for SQL Server};"
    r"SERVER=localhost\SQLEXPRESS;"
    r"DATABASE=TekaraiLive;"
    r"Trusted_Connection=yes;"
    r"TrustServerCertificate=yes;"
)

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
PASSWORD_HASH = make_password(DEFAULT_PASSWORD)

def map_department(dept_str):
    d=dept_str
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

DRY_RUN = "--execute" not in sys.argv

print("="*60)
print(f"IMPORT 44 - Tekarai SQL Server - {'DRY-RUN' if DRY_RUN else 'EXECUTE'}")
print("="*60)

try:
    conn = pyodbc.connect(CONN_STR, autocommit=False)
except Exception as e:
    print(f"[ERROR] اتصال به SQL Server 실패: {e}")
    print("آیا سرویس SQLEXPRESS روشن است؟")
    sys.exit(1)

cur = conn.cursor()

# Tenant
cur.execute("SELECT TOP 1 id, code, name FROM [Tenant] WHERE deletedAt IS NULL ORDER BY createdAt")
row = cur.fetchone()
if not row:
    print("[ERROR] هیچ Tenant پیدا نشد")
    sys.exit(1)
tenant_id, tenant_code, tenant_name = row
print(f"Tenant: {tenant_code} ({tenant_name}) - {tenant_id}")

# Helper to check table exists
def table_exists(name):
    cur.execute("SELECT COUNT(*) FROM sys.tables WHERE name=?", (name,))
    return cur.fetchone()[0] > 0

has_dept = table_exists("OrganizationDepartment")
has_pos = table_exists("OrganizationPosition")
has_assign = table_exists("OrganizationAssignment")
has_membership = table_exists("TenantMembership")
print(f"Tables: Dept={has_dept} Pos={has_pos} Assign={has_assign} Membership={has_membership}")

# Departments
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
dept_ids = {}
if has_dept:
    for code, (name, parent_code) in DEPTS_DEF.items():
        cur.execute("SELECT id FROM [OrganizationDepartment] WHERE tenantId=? AND code=?", (tenant_id, code))
        r = cur.fetchone()
        if r:
            dept_ids[code] = r[0]
            print(f"[DEPT] موجود: {code}")
        else:
            if DRY_RUN:
                print(f"[DEPT] ایجاد می‌شود: {code} - {name}")
                dept_ids[code] = None
            else:
                new_id = str(uuid.uuid4()).replace('-','')
                parent_id = dept_ids.get(parent_code) if parent_code else None
                now = datetime.now(timezone.utc)
                cur.execute("""
                    INSERT INTO [OrganizationDepartment] (id, tenantId, createdAt, updatedAt, code, name, description, status, parentId, managerUserId, managerName, isSystem)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (new_id, tenant_id, now, now, code, name, "", "active", parent_id, None, "", 0))
                dept_ids[code] = new_id
                print(f"[DEPT] ساخته شد: {code}")
else:
    print("[WARN] جدول OrganizationDepartment وجود ندارد - واحدها ساخته نمی‌شوند (فقط کاربران)")

# Positions
unique_positions = sorted(set(d for _,_,d in PERSONS))
pos_ids = {}
if has_pos:
    for idx, pos_name in enumerate(unique_positions, 1):
        code = f"POS_{idx:02d}"
        cur.execute("SELECT id FROM [OrganizationPosition] WHERE tenantId=? AND name=?", (tenant_id, pos_name))
        r = cur.fetchone()
        if r:
            pos_ids[pos_name] = r[0]
            print(f"[POS] موجود: {pos_name}")
        else:
            if DRY_RUN:
                print(f"[POS] ایجاد می‌شود: {pos_name} -> {code}")
                pos_ids[pos_name] = None
            else:
                new_id = str(uuid.uuid4()).replace('-','')
                now = datetime.now(timezone.utc)
                cur.execute("""
                    INSERT INTO [OrganizationPosition] (id, tenantId, createdAt, updatedAt, code, name, description, level, isActive, isSystem)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (new_id, tenant_id, now, now, code, pos_name, "", position_level(pos_name), 1, 0))
                pos_ids[pos_name] = new_id
                print(f"[POS] ساخته شد: {pos_name} -> {code}")
else:
    print("[WARN] جدول Position وجود ندارد")

# Users
print("\n--- Users ---")
created=0
skipped=0
for name, phone, dept in PERSONS:
    username = phone
    email = f"{phone}@tekarai.local"
    cur.execute("SELECT id FROM [User] WHERE tenantId=? AND username=?", (tenant_id, username))
    r = cur.fetchone()
    if r:
        print(f"[SKIP] موجود: {name} ({username})")
        skipped+=1
        continue
    if DRY_RUN:
        dept_code, dept_name = map_department(dept)
        print(f"[NEW] {name} | {username} | {dept_name} / {dept}")
        created+=1
        continue
    # Real insert
    new_id = str(uuid.uuid4()).replace('-','')
    now = datetime.now(timezone.utc)
    # UserModel columns: id, tenantId, username, email, phone, passwordHash, displayName, status, kind, createdAt, etc.
    cur.execute("""
        INSERT INTO [User] (id, tenantId, username, email, phone, passwordHash, displayName, status, kind, createdAt, failedLoginCount)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (new_id, tenant_id, username, email, phone, PASSWORD_HASH, name, "active", "human", now, 0))
    # Membership
    if has_membership:
        mem_id = str(uuid.uuid4()).replace('-','')
        cur.execute("""
            INSERT INTO [TenantMembership] (id, userId, tenantId, status, isPrimary, defaultRole, joinedAt)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (mem_id, new_id, tenant_id, "active", 1, "member", now))
    # Assignment
    if has_assign and has_dept and has_pos:
        dept_code,_ = map_department(dept)
        dept_id = dept_ids.get(dept_code)
        pos_id = pos_ids.get(dept)
        if dept_id and pos_id:
            assign_id = str(uuid.uuid4()).replace('-','')
            cur.execute("""
                INSERT INTO [OrganizationAssignment] (id, tenantId, createdAt, updatedAt, userId, userDisplayName, departmentId, positionId, isPrimary, isActive)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (assign_id, tenant_id, now, now, new_id, name, dept_id, pos_id, 1, 1))
    print(f"[OK] {name} ({username})")
    created+=1

if DRY_RUN:
    conn.rollback()
    print("\n" + "="*60)
    print(f"پیش‌نمایش: {created} نفر جدید، {skipped} تکراری")
    print("برای اجرا: .venv\\Scripts\\python.exe import_production_44.py --execute")
else:
    conn.commit()
    print("\n" + "="*60)
    print(f"انجام شد: {created} ساخته شد، {skipped} تکراری")
    print(f"رمز همه: {DEFAULT_PASSWORD}")
    cur.execute("SELECT COUNT(*) FROM [User]")
    print(f"کل کاربران الان: {cur.fetchone()[0]}")
print("="*60)
cur.close()
conn.close()
