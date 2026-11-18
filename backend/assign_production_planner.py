"""assign_production_planner.py
Run from backend dir:  python assign_production_planner.py
Shows all users + roles and lets you grant productionPlanner to a user by username/phone.
"""
import os, sys, django
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.identity.infrastructure.models import RoleModel, UserModel, UserRoleModel

print("="*60)
print("Roles:")
print("="*60)
for r in RoleModel.objects.all().order_by('scopeType','code'):
    count = UserRoleModel.objects.filter(roleId=r.id).count()
    print(f"  [{r.scopeType:8s}] id={str(r.id)[:8]}...  code={r.code:25s}  name={r.name:35s}  assigned={count}")

prod_role = RoleModel.objects.filter(code='productionPlanner').first()
if not prod_role:
    print("\n[ERROR] productionPlanner role not found! Re-run syncPermissionCatalog.")
    sys.exit(1)
print(f"\n[OK] productionPlanner role found: {prod_role.name} ({prod_role.id})")

print("\n" + "="*60)
print("Active users (first 50):")
print("="*60)
users = list(UserModel.objects.filter(deletedAt__isnull=True).order_by('displayName','username')[:50])
for u in users:
    roles = list(UserRoleModel.objects.filter(userId=u.id).values_list('roleId', flat=True))
    role_names = [RoleModel.objects.filter(id=rid).values_list('name',flat=True).first() or str(rid)[:8] for rid in roles]
    has_prod = any(rid == prod_role.id for rid in roles)
    print(f"  {'[PP]' if has_prod else '    '} id={str(u.id)[:8]}...  user={u.username:20s}  name={str(u.displayName or '')[:25]:25s}  roles={role_names}")

if len(sys.argv) < 2:
    print("\n" + "="*60)
    print("To assign productionPlanner to a user, run:")
    print("   python assign_production_planner.py <username>")
    print("e.g.:")
    print("   python assign_production_planner.py علی.رضایی")
    print("="*60)
    sys.exit(0)

target_user = sys.argv[1]
user = UserModel.objects.filter(username=target_user, deletedAt__isnull=True).first()
if not user:
    user = UserModel.objects.filter(phone=target_user, deletedAt__isnull=True).first()
if not user:
    print(f"[ERROR] No active user with username/phone '{target_user}'.")
    sys.exit(1)

existing = UserRoleModel.objects.filter(userId=user.id, roleId=prod_role.id).first()
if existing:
    print(f"[OK] User {user.username} already has productionPlanner role.")
else:
    tenant_id = user.tenantId
    UserRoleModel.objects.create(userId=user.id, roleId=prod_role.id, tenantId=tenant_id, scopeType='TENANT')
    from apps.identity.infrastructure.services.authorizationCache import bumpVersion
    bumpVersion(user.id)
    print(f"[OK] Granted productionPlanner role to {user.username} ({user.displayName})")
    print(f"     Tenant: {tenant_id}")

print("\nDone! Recycle IIS app pool / iisreset, then the user should have access.")
