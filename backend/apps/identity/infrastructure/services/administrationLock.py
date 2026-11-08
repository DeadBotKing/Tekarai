"""Single transaction-owned governance lock for last-admin/bootstrap invariants.

Every administrative identity/role/owner mutation and survivor calculation must use
this same resource. A per-target user lock cannot protect a last-admin invariant.
Unsupported backends fail closed. No rows or governance owner are created here.
"""
from contextlib import contextmanager
from django.db import connection, transaction
from django.db.models import F
from apps.sharedKernel.domain.errors import ConcurrencyConflictError

RESOURCE = 'tekarai.identity.administration.governance.v1'

@contextmanager
def lockedAdministrationState():
    with transaction.atomic():
        vendor = connection.vendor
        if vendor in ('microsoft', 'mssql'):
            with connection.cursor() as cursor:
                cursor.execute(
                    "DECLARE @result int; EXEC @result = sp_getapplock "
                    "@Resource=%s, @LockMode='Exclusive', @LockOwner='Transaction', "
                    "@LockTimeout=15000; SELECT @result;", [RESOURCE])
                row = cursor.fetchone()
            if row is None or row[0] is None or row[0] < 0:
                raise ConcurrencyConflictError('مدیریت سامانه در حال تغییر است؛ کمی بعد دوباره تلاش کنید.')
        elif vendor == 'postgresql':
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_advisory_xact_lock(%s)', [603271849100417])
        elif vendor == 'sqlite':
            from apps.identity.infrastructure.administrationModels import AdministrativeGovernanceModel
            # Even an empty UPDATE acquires the SQLite writer lock. No bootstrap row is inserted.
            AdministrativeGovernanceModel.objects.filter(key='platform').update(updatedAt=F('updatedAt'))
        else:
            raise ConcurrencyConflictError('قفل امن مدیریت برای این پایگاه داده تعریف نشده است.')
        yield
