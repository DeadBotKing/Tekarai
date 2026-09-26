"""doctorLogin — عیب‌یاب ورود به سامانه.

چرا این اسکریپت؟
    وقتی صفحهٔ ورود پیام «Unexpected server error» می‌دهد، جنگو کد ۵۰۰ برگردانده
    و متن واقعی خطا فقط در لاگ سرور است. این اسکریپت همان درخواست ورود را
    از داخل خود جنگو اجرا می‌کند، استثنای واقعی را می‌گیرد و چاپ می‌کند.

اجرا (از پوشهٔ backend، با پایتون همان venv):
    python scripts/doctorLogin.py                 # فقط تشخیص
    python scripts/doctorLogin.py --fix           # تشخیص + migrate + ساخت ادمین
    python scripts/doctorLogin.py --fix --sqlite  # همان، ولی روی SQLite محلی

خروجی با کد ۰ یعنی ورود سالم است؛ کد غیرصفر یعنی مشکلی باقی است.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import sys
import traceback
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

TENANT_CODE = os.environ.get("PLATFORM_TENANT_CODE", "platform")
ADMIN_USERNAME = os.environ.get("PLATFORM_ADMIN_USERNAME", "platform-admin")
ADMIN_PASSWORD = os.environ.get("PLATFORM_ADMIN_PASSWORD", "Tekarai-Demo-2026!")
ADMIN_EMAIL = os.environ.get("PLATFORM_ADMIN_EMAIL", "platform-admin@tekarai.local")

OK = "[ سالم ]"
BAD = "[ خطا  ]"
WARN = "[ هشدار]"


class ExceptionCollector(logging.Handler):
    """هر استثنای لاگ‌شده را نگه می‌دارد تا علت واقعی ۵۰۰ را نشان دهیم."""

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self.tracebacks: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        if record.exc_info:
            self.tracebacks.append("".join(traceback.format_exception(*record.exc_info)))


def heading(text: str) -> None:
    print("\n" + "=" * 72)
    print(text)
    print("=" * 72)


def main() -> int:
    parser = argparse.ArgumentParser(description="عیب‌یابی ورود به سامانه Tekarai")
    parser.add_argument("--fix", action="store_true", help="اجرای migrate و ساخت کاربر مدیر")
    parser.add_argument("--sqlite", action="store_true", help="استفاده از SQLite محلی")
    args = parser.parse_args()

    if args.sqlite:
        os.environ["dbEngine"] = "sqlite"
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
    os.chdir(BACKEND_ROOT)

    heading("۱) بارگذاری تنظیمات جنگو")
    try:
        import django

        django.setup()
    except Exception:  # noqa: BLE001
        print(f"{BAD} تنظیمات جنگو بارگذاری نشد. متن خطا:")
        traceback.print_exc()
        print("\nراهنما: پکیج‌ها نصب نیستند؟  pip install -r requirements\\development.txt")
        return 2

    from django.conf import settings
    from django.db import connection

    engine = settings.DATABASES["default"]["ENGINE"]
    name = settings.DATABASES["default"]["NAME"]
    host = settings.DATABASES["default"].get("HOST", "")
    print(f"{OK} تنظیمات بارگذاری شد.")
    print(f"      موتور پایگاه داده : {engine}")
    print(f"      نام/مسیر پایگاه   : {name}")
    print(f"      میزبان            : {host or '(محلی)'}")

    heading("۲) اتصال به پایگاه داده")
    try:
        connection.ensure_connection()
        print(f"{OK} اتصال برقرار شد.")
    except Exception:  # noqa: BLE001
        print(f"{BAD} اتصال به پایگاه داده برقرار نشد. متن خطا:")
        traceback.print_exc()
        print("\nراهنما:")
        print("  • اگر SQL Server ندارید یا بالا نیست، با SQLite کار کنید:")
        print("      python scripts/doctorLogin.py --fix --sqlite")
        print("      یا در ریشهٔ پروژه:  .\\run_dev.ps1 -UseSqlite")
        return 3

    heading("۳) وجود جدول‌های موردنیاز (migrate)")
    from apps.identity.infrastructure.models import UserModel
    from apps.tenancy.infrastructure.models import TenantModel

    required = [UserModel._meta.db_table, TenantModel._meta.db_table]
    tables = set(connection.introspection.table_names())
    missing = [table for table in required if table not in tables]
    if missing:
        print(f"{BAD} این جدول‌ها وجود ندارند: {', '.join(missing)}")
        print(f"      تعداد کل جدول‌های موجود: {len(tables)}")
        if args.fix:
            print("\n>> اجرای migrate ...")
            from django.core.management import call_command

            call_command("migrate", "--noinput", verbosity=1)
            tables = set(connection.introspection.table_names())
            missing = [table for table in required if table not in tables]
            print(f"{OK if not missing else BAD} پس از migrate، جدول‌های ناموجود: {missing or 'ندارد'}")
        else:
            print("\nراهنما: این علت اصلی «Unexpected server error» است.")
            print("  python scripts/doctorLogin.py --fix        (یا --fix --sqlite)")
            return 4
    else:
        print(f"{OK} جدول‌های اصلی موجودند ({len(tables)} جدول).")

    heading("۴) وجود Tenant و کاربر مدیر")
    tenant = TenantModel.objects.filter(code=TENANT_CODE).first()
    user = UserModel.objects.filter(username=ADMIN_USERNAME).first()
    print(f"      Tenant «{TENANT_CODE}» : {'موجود' if tenant else 'موجود نیست'}")
    print(f"      کاربر «{ADMIN_USERNAME}» : {'موجود' if user else 'موجود نیست'}")
    if (not tenant or not user) and args.fix:
        print("\n>> اجرای bootstrapPlatform ...")
        from django.core.management import call_command

        os.environ["PLATFORM_TENANT_CODE"] = TENANT_CODE
        os.environ["PLATFORM_ADMIN_USERNAME"] = ADMIN_USERNAME
        os.environ["PLATFORM_ADMIN_PASSWORD"] = ADMIN_PASSWORD
        os.environ["PLATFORM_ADMIN_EMAIL"] = ADMIN_EMAIL
        buffer = io.StringIO()
        call_command("bootstrapPlatform", stdout=buffer, stderr=buffer)
        print(buffer.getvalue().strip() or "(بدون خروجی)")
        tenant = TenantModel.objects.filter(code=TENANT_CODE).first()
        user = UserModel.objects.filter(username=ADMIN_USERNAME).first()
    elif not tenant or not user:
        print(f"\n{WARN} برای ساخت آن‌ها: python scripts/doctorLogin.py --fix")

    heading("۵) آزمایش واقعی درخواست ورود")
    collector = ExceptionCollector()
    logging.getLogger().addHandler(collector)
    from django.test import Client

    if "testserver" not in settings.ALLOWED_HOSTS and "*" not in settings.ALLOWED_HOSTS:
        settings.ALLOWED_HOSTS = [*settings.ALLOWED_HOSTS, "testserver"]
    client = Client()
    response = client.post(
        "/api/v1/auth/login",
        data=json.dumps(
            {
                "tenantCode": TENANT_CODE,
                "identifier": ADMIN_USERNAME,
                "password": ADMIN_PASSWORD,
            }
        ),
        content_type="application/json",
    )
    logging.getLogger().removeHandler(collector)

    print(f"      کد وضعیت: HTTP {response.status_code}")
    try:
        payload = response.json()
    except Exception:  # noqa: BLE001
        payload = {}

    if response.status_code == 200:
        data = payload.get("data") or {}
        print(f"{OK} ورود موفق بود. کلیدهای پاسخ: {', '.join(sorted(data.keys())) or '(خالی)'}")
        print("\nاطلاعات ورود از طریق مرورگر:")
        print(f"      Tenant code : {TENANT_CODE}")
        print(f"      Username    : {ADMIN_USERNAME}")
        print(f"      Password    : {ADMIN_PASSWORD}")
        return 0

    errors = payload.get("errors") or []
    code = errors[0].get("code") if errors else "?"
    message = errors[0].get("message") if errors else response.content[:200]
    print(f"{BAD} ورود ناموفق بود. کد خطا: {code} — {message}")

    if collector.tracebacks:
        heading("علت واقعی خطای ۵۰۰ (این متن را برای پشتیبانی بفرستید)")
        print(collector.tracebacks[-1])

    if response.status_code == 401:
        print("\nراهنما: گذرواژه یا نام کاربری اشتباه است (نه مشکل سرور).")
        print("  گذرواژهٔ موردانتظار این اسکریپت:", ADMIN_PASSWORD)
        print("  برای ساخت دوبارهٔ کاربر با گذرواژهٔ دلخواه:")
        print('      $env:PLATFORM_ADMIN_PASSWORD="گذرواژهٔ‌شما"; python manage.py bootstrapPlatform')
    else:
        print("\nراهنما: اگر بالا خطای پایگاه داده دیدید، اول آن را رفع کنید:")
        print("      python scripts/doctorLogin.py --fix --sqlite")
    return 5


if __name__ == "__main__":
    raise SystemExit(main())
