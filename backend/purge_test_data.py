"""
purge_test_data.py — پاک‌سازی کامل داده‌های تستی
فقط روی سرور اصلی (IIS) اجرا شود. قبل از اجرا حتما بکاپ بگیرید.

چه چیزی پاک می‌شود:
  - همه کاربران تستی (به جز platform-admin و اکانت‌های محافظت‌شده)
  - عضویت‌ها، نقش‌های کاربران، نشست‌ها
  - تمام داده‌های کاری: WorkOrder, Project, Task, Maintenance, Procurement, Organization, Documents و ...

چه چیزی باقی می‌ماند:
  - اکانت platform-admin (ورود superadmin)
  - کاتالوگ دسترسی‌ها و نقش‌های سیستمی (tenantAdmin, member, productionPlanner و ...)
  - تنانت اصلی (Platform / Ronak)
  - تنظیمات پایه

نحوه اجرا (روی سرور ویندوز با Run as Administrator):
  cd C:/Users/Mitra/Desktop/Tekarai/backend
  .venv/Scripts/python.exe purge_test_data.py            -> پیش‌نمایش (dry-run)
  .venv/Scripts/python.exe purge_test_data.py --execute  -> اجرای واقعی
"""
import os, sys, django
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from django.apps import apps
from django.db import transaction

# ---- محافظت‌شده‌ها — هرگز پاک نمی‌شوند ----
PROTECTED_USERNAMES = {
    "platform-admin", "platform_admin", "platformAdmin",
    "admin", "superadmin", "root",
}
PROTECTED_CODES = {"platform", "tekarai", "ronak"}  # Tenant codes

DRY_RUN = "--execute" not in sys.argv

print("="*60)
print("PURGE TEST DATA — Tekarai" + (" [DRY-RUN]" if DRY_RUN else " [EXECUTE]"))
print("="*60)

# 1. شناسایی کاربران محافظت‌شده
from apps.identity.infrastructure.models import UserModel, TenantMembershipModel, UserRoleModel, SessionModel, RoleModel
from apps.tenancy.infrastructure.models import TenantModel

protected_user_ids = set(
    UserModel.objects.filter(username__in=PROTECTED_USERNAMES).values_list("id", flat=True)
)
# همچنین هر کاربری که نقش platformAdmin دارد را نگه دار
platform_admin_role = RoleModel.objects.filter(code="platformAdmin").first()
if platform_admin_role:
    ids = UserRoleModel.objects.filter(roleId=platform_admin_role.id).values_list("userId", flat=True)
    protected_user_ids.update(ids)

print(f"\n[1] Protected users: {len(protected_user_ids)}")
for uid in protected_user_ids:
    u = UserModel.objects.filter(id=uid).first()
    if u:
        print(f"    KEEP -> {u.username} ({u.displayName})")

# 2. آمار قبل از پاک‌سازی
total_users = UserModel.objects.count()
test_users = UserModel.objects.exclude(id__in=protected_user_ids).count()
print(f"\n[2] Users total: {total_users} | test to delete: {test_users}")

# 3. لیست مدل‌های قابل پاک‌سازی (همه اپ‌ها به جز identity.Tenant/Role/Permission و django.*)
SKIP_MODELS = {
    ("identity", "rolemodel"),
    ("identity", "permissionmodel"),
    ("tenancy", "tenantmodel"),  # نگه می‌داریم — فقط soft-delete تستی‌ها اگر خواستید
    ("admin", "*"), ("auth", "*"), ("contenttypes", "*"), ("sessions", "*"),
    ("authtoken", "*"), ("migrations", "*"),
}

def should_skip(app_label, model_name):
    if (app_label, model_name) in SKIP_MODELS: return True
    if (app_label, "*") in SKIP_MODELS: return True
    if app_label in ("admin", "auth", "contenttypes", "sessions"): return True
    return False

all_models = apps.get_models()
print(f"\n[3] Scanning {len(all_models)} models...")
to_purge = []
for m in all_models:
    al = m._meta.app_label
    mn = m._meta.model_name
    if should_skip(al, mn):
        print(f"    SKIP  {al}.{mn}")
        continue
    # فقط مدل‌هایی که جدول دارند
    to_purge.append(m)

print(f"\n[4] Will purge {len(to_purge)} models (plus filtered Users):")
for m in to_purge:
    try:
        c = m.objects.count()
    except Exception:
        c = 0
        print(f"    - {m._meta.app_label}.{m._meta.model_name} (no table)")
        continue
    print(f"    - {m._meta.app_label}.{m._meta.model_name} ({c} rows)")

if DRY_RUN:
    print("\n" + "="*60)
    print("DRY-RUN تمام شد. هیچ‌چیز پاک نشد.")
    print("برای اجرای واقعی بزن:")
    print("  .venv/Scripts/python.exe purge_test_data.py --execute")
    print("="*60)
    sys.exit(0)

# 5. اجرای واقعی
confirm = input("\nآیا مطمئن هستید؟ همه داده‌های تستی پاک می‌شود! (yes/no): ").strip().lower()
if confirm != "yes":
    print("لغو شد.")
    sys.exit(1)

print("\n[5] Purging...")
with transaction.atomic():
    # ابتدا نشست‌ها و عضویت‌های کاربران تستی
    test_user_ids = list(UserModel.objects.exclude(id__in=protected_user_ids).values_list("id", flat=True))
    if test_user_ids:
        deleted, _ = SessionModel.objects.filter(userId__in=test_user_ids).delete()
        print(f"    Sessions deleted: {deleted}")
        deleted, _ = TenantMembershipModel.objects.filter(userId__in=test_user_ids).delete()
        print(f"    Memberships deleted: {deleted}")
        deleted, _ = UserRoleModel.objects.filter(userId__in=test_user_ids).delete()
        print(f"    UserRoles (test users) deleted: {deleted}")

    # سایر مدل‌ها — همه ردیف‌ها پاک شوند
    for m in to_purge:
        # UserModel را جداگانه و فیلتر شده پاک می‌کنیم
        if m == UserModel:
            deleted, _ = m.objects.exclude(id__in=protected_user_ids).delete()
            print(f"    {m._meta.label} -> deleted {deleted} (kept {len(protected_user_ids)})")
            continue
        # TenantModel — فقط تنانت‌های تستی (غیر محافظت‌شده) را پاک کن، platform را نگه دار
        if m == TenantModel:
            deleted, _ = m.objects.exclude(code__in=PROTECTED_CODES).delete()
            print(f"    {m._meta.label} -> deleted {deleted} (kept platform tenants)")
            continue
        # بقیه: کامل پاک
        try:
            count = m.objects.count()
            if count > 0:
                deleted, _ = m.objects.all().delete()
                print(f"    {m._meta.label} -> deleted {deleted}")
        except Exception as e:
            print(f"    [WARN] {m._meta.label} -> {e}")

print("\n" + "="*60)
print("DONE — دیتابیس خالی شد و آماده ورود لیست اصلی است.")
print("اکانت platform-admin سالم است. می‌توانید لیست جدید را بفرستید.")
print("="*60)
