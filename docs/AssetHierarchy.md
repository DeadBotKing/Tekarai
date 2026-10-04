# سلسله‌مراتب دارایی — Asset Hierarchy

> Phase 27. Makes the plant's asset chain explicit end to end:
>
> ```
> سایت └── ساختمان └── سالن └── خط تولید └── سیستم └── تجهیز اصلی └── زیرتجهیز └── قطعه
> ```

## Why this exists

Equipment, locations and BOM already existed, and a determined user could *imply*
most of a hierarchy from them. What was missing was the ability to state it: an
asset's level was never recorded, a transfer left no trace, and "where was this
installed before?" had no answer at all. This slice turns those implications into
recorded facts.

## The two trees

The hierarchy is deliberately **two trees joined at the device**, not one:

| Tree | Model | Ordering rule |
| --- | --- | --- |
| Locations | `MaintenanceLocationModel.parentId` + materialised `path` | `childRank >= parentRank` |
| Assets | `DeviceModel.parentDeviceId` | `childRank > parentRank` |

Locations may repeat a rank (a `hall` inside a `hall` is a legitimate bay), so the
comparison is `>=`. Assets may not: a `subEquipment` cannot own a `subEquipment`,
because that is exactly the ambiguity this slice removes. Hence `>`.

**A device with a parent device nests under the parent, never under its location.**
Otherwise a bearing would appear twice — once under the motor and once under the
production line — and the count of "equipment on line 1" would be wrong.

### Ranked vocabularies

`LOCATION_KIND_RANK` and `ASSET_LEVELS` are **open vocabularies**: a tenant may
invent a kind the catalogue has never seen (`«دستگاه»`, `«اسکید»`). Ordering is
therefore validated *only when both ends are ranked*. An unranked kind is carried
without complaint rather than rejected — a tenant's own taxonomy is not an error.

## Asset level: derived, never silently rewritten

`DeviceModel.assetLevel` defaults to `mainEquipment`, so **every legacy row already
claims to be main equipment**. A default is not an assertion, and the rules engine
is careful about the difference:

`resolveChildLevel(parentLevel, parentName, childLevel, *, stated)`

1. Nesting already valid → return the child's level untouched.
2. Invalid, **not** stated, and still the bare default → derive one rung down
   (`mainEquipment` → `subEquipment` → `component`).
3. Invalid and **stated** → raise `AssetHierarchyError` (HTTP 422).

`stated` is true only when the client actually sent `assetLevel`. A move never
states a level; a nameplate PATCH states one only if the field is in the payload.
The effect: hanging a legacy device off a machine quietly files it as a
sub-assembly, while a user who *insists* a component owns a main equipment gets a
clear error instead of having their data rewritten behind their back.

## Guards on a move

`MoveAssetCommand` refuses to: move a retired device, record a no-op move, create
a cycle, nest deeper than 12, or accept a stated level that contradicts the parent.

Cycle detection walks the parent chain rather than trusting the materialised path,
because the path is a cache and a cache can lag. Note that a cycle between two
*catalogued* levels is arithmetically impossible — `childRank > parentRank` fails
first — so the cycle guard only earns its keep on open-vocabulary levels. It is
tested there.

## What a move writes

One move produces three records, in one transaction:

- a row in `AssetMovementModel` (from/to location **and** from/to parent, date,
  reason, performer, note);
- a `relocated` entry on the device timeline;
- an `AUDIT_CREATE` audit record.

`previousLocation` on the ancestry endpoint is read from the ledger's latest row,
not from a "previous" column — a column holds one hop, the ledger holds the life
of the asset.

> The ledger copies the device's cached `locationPath` as the move's origin. If
> that cache is blank the transfer reads as "came from nowhere", which is why
> `seedDemo` now populates `locationPath` and backfills it for older rows.

## Retirement

`RetireAssetCommand` records `retiredOn` **and** `retireReason`. It refuses to
retire a device that still has live children unless `retireChildren` is passed, in
which case the whole subtree goes and `retiredIds[]` comes back — a motor cannot
leave the plant while its bearing is still officially turning.

It also refuses `retiredOn < installedOn`.

`ReinstateAssetCommand` clears the retirement facts and puts the device back into
one of `LIVE_STATUSES`, which is derived as `DEVICE_STATUSES` minus `retired` so
the two lists cannot drift apart.

## Cost centre

`costCenterCode` / `costCenterName` live on the device and are editable from the
nameplate section of the profile's location tab. They are plain strings on
purpose: a finance-owned cost-centre *entity* would need an owner, a lifecycle and
a sync, none of which this product has, and a free-text code already answers "what
does this asset cost against?".

## API

All routes under `/api/v1/maintenance`:

| Method | Route | Notes |
| --- | --- | --- |
| `GET` | `assets/tree?rootId=&includeRetired=` | whole tree + unplaced devices + counts |
| `GET` | `devices/<uuid>/ancestry` | both chains root-first, children, previous location |
| `GET` `POST` | `devices/<uuid>/movements` | POST ⇒ 201 |
| `POST` | `devices/<uuid>/retirement` | ⇒ `{retiredCount, retiredIds[]}` |
| `DELETE` | `devices/<uuid>/retirement?status=` | reinstate; defaults to `operational` |

Reinstate takes its status as a **query parameter** because `ApiClient.delete`
cannot carry a body.

## UI

- **`/app/maintenance/asset-tree`** — the read-only tree: expand/collapse, search,
  an "include retired" toggle, per-node level/status/cost-centre badges, a device
  count on every location, and an **unplaced devices** panel so equipment attached
  to no location is visible rather than silently missing from the tree.
- **Device profile → محل استقرار** — upstream chain, current/previous location,
  installation date, cost centre, editable level, the children table, the movement
  ledger, and the move / retire / reinstate actions (all behind
  `maintenanceDeviceManage`).

The location summary reads each level from the real location chain and labels it
with that level's own kind. It used to slice the path string positionally and call
segment 2 "room" — which was fine for a three-deep tree and wrong the moment a
plant modelled سایت ← ساختمان ← سالن ← خط.

### Search semantics

A node that matches the search term is returned **whole, with its subtree intact**;
only non-matching nodes recurse and survive on the strength of their descendants.
Pruning a match's children makes the hit render as a leaf and hides the
sub-assemblies that are usually the reason someone searched for it.

## Tests

- `apps/maintenance/tests/testAssetHierarchyRules.py` — 28 unit tests
- `backend/tests/integration/testAssetHierarchyApi.py` — 41 API tests
- `frontend-web/src/tests/assetHierarchy.test.ts` — 14 tests (tree helpers + mappers)

Backend suite: 2741 tests, 5 pre-existing `tests.architecture.*` failures.
Frontend: 171/171.

## Demo data

`seedDemo` builds the full chain: `SITE-01 → BLD-A → HALL-1 → LINE-1 →
{SYS-HYD1, SYS-COOL1}` plus `LINE-2` and `BLD-B → BOILER`, with
`PRS-101 → PRS-101-MTR → PRS-101-BRG` three levels deep and cost centres on every
machine. Parent links are wired in a **second pass** after the create loop, since a
child defined before its parent has no id to point at, and the pass is guarded by
`parentDeviceId__isnull=True` so re-seeding never re-parents a device a user has
since moved.
