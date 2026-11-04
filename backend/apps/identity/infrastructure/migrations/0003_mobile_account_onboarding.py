from django.db import migrations, models
import re

def canonical(raw):
    value = str(raw).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    value = re.sub(r"[\s()\-]", "", value)
    if value.startswith("+98"): value = "0" + value[3:]
    elif value.startswith("0098"): value = "0" + value[4:]
    elif value.startswith("98") and len(value) == 12: value = "0" + value[2:]
    return value if re.fullmatch(r"09[0-9]{9}", value) else None

def reserveExisting(apps, schema_editor):
    User = apps.get_model("identity", "UserModel")
    Mobile = apps.get_model("identity", "MobileAccountModel")
    seen = {}; rows = []
    for user in User.objects.using(schema_editor.connection.alias).filter(kind="human", deletedAt__isnull=True).exclude(phone="").iterator():
        phone = canonical(user.phone)
        if not phone: continue  # preserve old input; manager can correct it later
        if phone in seen:
            raise RuntimeError("Existing users share a normalized mobile. Review before migration; no accounts were merged.")
        seen[phone] = user.id
        rows.append(Mobile(userId=user.id, phone=phone, mustChangePassword=False))
    Mobile.objects.using(schema_editor.connection.alias).bulk_create(rows)

class Migration(migrations.Migration):
    dependencies = [("identity", "0002_phase7_identity")]
    operations = [
        migrations.CreateModel(name="MobileAccountModel", fields=[
            ("userId", models.UUIDField(primary_key=True, serialize=False)),
            ("phone", models.CharField(max_length=11, unique=True)),
            ("mustChangePassword", models.BooleanField(default=False)),
            ("temporaryExpiresAt", models.DateTimeField(blank=True, null=True)),
            ("updatedAt", models.DateTimeField(auto_now=True)),
        ], options={"db_table": "IdentityMobileAccount"}),
        migrations.RunPython(reserveExisting, migrations.RunPython.noop),
    ]
