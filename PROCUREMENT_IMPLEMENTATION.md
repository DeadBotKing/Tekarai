# Procurement and Purchasing — Phase 32

## Delivered

The procurement bounded context adds the complete first purchasing cycle for CMMS spare parts:

- Supplier/vendor master data with contact, tax, payment terms, currency and default lead time.
- Supplier-part catalog with supplier SKU, price, MOQ, lead time and preferred supplier.
- Purchase requisitions with multiple lines, estimated cost, priority, needed-by date and justification.
- Requisition lifecycle: draft → submitted → approved/rejected/cancelled → ordered.
- Approval/audit records for requisitions and purchase orders.
- Purchase orders with multiple lines, taxes, totals, expected date, payment terms and currency.
- Purchase order lifecycle: draft → submitted → approved → partially received/received/cancelled.
- Goods receipts with accepted/rejected quantities. Posting a receipt atomically increases `SparePart.quantityOnHand`, updates its latest unit cost and writes an immutable `PartTransaction` receipt ledger entry.
- Supplier returns. Posting a return validates stock, decrements inventory and writes a negative return ledger entry atomically.
- Supplier invoices linked to supplier and optional purchase order with status, dates and financial totals.
- Procurement dashboard counters.
- Permission-aware API endpoints and UI guards.
- Persian UI with tabbed procurement workspace and modal forms for adding suppliers and requisitions.
- Select/drop-down fields for currency, priority and workflow status; the existing platform quick-create/dropdown conventions remain available for future catalogs.

## API

Mounted under `/api/v1/procurement/`:

- `GET/POST suppliers`
- `PATCH/DELETE suppliers/{supplierId}`
- `GET/POST suppliers/{supplierId}/parts`
- `GET/POST requisitions`
- `POST requisitions/{id}/submit|approve|reject|cancel`
- `GET/POST purchase-orders`
- `GET purchase-orders/{id}`
- `POST purchase-orders/{id}/submit|approve|cancel`
- `GET/POST receipts`
- `GET/POST returns`
- `GET/POST invoices`
- `GET dashboard`

## Data integrity rules

- Every row is tenant scoped.
- Supplier code, requisition number, purchase order number, receipt number, return number and supplier invoice number are unique within a tenant as appropriate.
- Receipt posting is transactional and cannot over-receive a stock balance silently.
- Return posting rejects insufficient inventory.
- Receipt and return operations produce inventory ledger entries.
- Decimal quantities and monetary values are validated server-side.
- Server-side action permissions are applied independently of UI visibility.

## Verification performed

- `python manage.py check --settings=config.settings.testing` — passed.
- `python manage.py makemigrations procurement --check --settings=config.settings.testing` — passed.
- `python manage.py test apps.procurement --settings=config.settings.testing` — 4 tests passed.
- `python -m compileall -q apps config` — passed.
- `npm run typecheck` — passed.
- `npm run test -- --run` — 101 tests passed.
- `npm run build` — passed.

The repository's pre-existing global `makemigrations --check` still reports an unrelated existing drift in `apps/documents` (`0002_alter_documentmodel_file.py`); procurement itself has no migration drift.
