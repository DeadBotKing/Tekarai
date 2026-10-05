"""Asset hierarchy use cases (Phase 27).

The plant is one chain:

    سایت ← ساختمان ← خط تولید ← سیستم ← تجهیز اصلی ← زیرتجهیز ← قطعه

Phase 26 built both halves but left them implicit: locations knew their
parent, devices knew theirs, and nothing joined the two or guarded either.
This module makes the chain explicit and answerable —

* read it as a tree, from any root;
* read one asset's upstream chain, devices and locations together;
* move an asset and keep where it came from;
* take an asset out of service with a date and a reason.

Every write goes through the same two guards: no cycles, and no child filed
above its parent.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from apps.maintenance.application.services.tenantResolver import (
    parseDateOrNone,
    resolveTenantId,
)
from apps.maintenance.domain.entities.deviceHistory import DeviceHistoryEntry
from apps.maintenance.domain.services.assetHierarchyRules import (
    AssetHierarchyError,
    ancestorChain,
    assertDepthWithinLimit,
    assertNoCycle,
    descendantIds,
    resolveChildLevel,
)
from apps.maintenance.domain.valueObjects.maintenanceState import (
    ASSET_LEVELS,
    ASSET_MAIN_EQUIPMENT,
    DEVICE_RETIRED,
    DEVICE_STATUSES,
)
from apps.sharedKernel.application.useCase import AUDIT_CREATE, AUDIT_UPDATE, UseCase
from apps.sharedKernel.domain.errors import EntityNotFoundError

PERMISSION_REGISTRY_VIEW = "maintenance.device.view"
PERMISSION_REGISTRY_MANAGE = "maintenance.device.manage"

#: Statuses that still mean "this asset is in the plant" — the canonical
#: DEVICE_STATUSES minus `retired`. Reinstating is only allowed into one of
#: these, so a caller cannot "un-retire" a device straight back to retired.
LIVE_STATUSES = tuple(status for status in DEVICE_STATUSES if status != DEVICE_RETIRED)


# =====================================================================================
# Commands / queries
# =====================================================================================
@dataclass(frozen=True)
class AssetTreeQuery:
    rootLocationId: str = ""
    includeRetired: bool = False


@dataclass(frozen=True)
class AssetAncestryQuery:
    deviceId: str


@dataclass(frozen=True)
class MoveAssetCommand:
    deviceId: str
    toLocationId: str = ""
    toParentDeviceId: str = ""
    movedOn: str = ""
    reason: str = ""
    performedBy: str = ""
    note: str = ""
    updateInstalledOn: bool = False
    clearLocation: bool = False
    clearParent: bool = False


@dataclass(frozen=True)
class AssetMovementsQuery:
    deviceId: str


@dataclass(frozen=True)
class RetireAssetCommand:
    deviceId: str
    retiredOn: str = ""
    reason: str = ""
    retireChildren: bool = False


@dataclass(frozen=True)
class ReinstateAssetCommand:
    deviceId: str
    status: str = "operational"


@dataclass
class AssetTreeNode:
    """One node of the rendered tree — a location or a device."""

    id: str
    nodeType: str
    code: str
    name: str
    kind: str = ""
    assetLevel: str = ""
    status: str = ""
    criticality: str = ""
    path: str = ""
    costCenterCode: str = ""
    costCenterName: str = ""
    installedOn: str = ""
    retiredOn: str = ""
    deviceCount: int = 0
    children: list = field(default_factory=list)


# =====================================================================================
# Base
# =====================================================================================
class AssetHierarchyUseCaseBase(UseCase):
    """Shared wiring: devices, locations, the movement ledger and the timeline."""

    def __init__(
        self,
        *,
        deviceRepository,  # noqa: ANN001 — protocol, injected by the container
        locationRepository,  # noqa: ANN001
        movementRepository,  # noqa: ANN001
        historyRepository,  # noqa: ANN001
        unitOfWork,  # noqa: ANN001
        auditRecorder,  # noqa: ANN001
        eventDispatcher,  # noqa: ANN001
        permissionGate,  # noqa: ANN001
        clock,  # noqa: ANN001
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.deviceRepository = deviceRepository
        self.locationRepository = locationRepository
        self.movementRepository = movementRepository
        self.historyRepository = historyRepository

    def requireDevice(self, tenantId: uuid.UUID, deviceId: str):  # noqa: ANN201
        device = self.deviceRepository.getById(tenantId, uuid.UUID(deviceId))
        if device is None:
            raise EntityNotFoundError("Device not found.")
        return device

    def deviceIndex(self, tenantId: uuid.UUID) -> dict[str, dict]:
        """Every live device keyed by id — one query, reused by each guard."""
        return {row["id"]: row for row in self.deviceRepository.hierarchyRows(tenantId)}

    @staticmethod
    def parentsFrom(index: dict[str, dict]) -> dict[str, str | None]:
        return {key: (row["parentDeviceId"] or None) for key, row in index.items()}

    def recordHistory(
        self,
        tenantId: uuid.UUID,
        deviceId: uuid.UUID,
        action: str,
        note: str,
        now,  # noqa: ANN001
        *,
        fromStatus: str = "",
        toStatus: str = "",
    ) -> None:
        self.historyRepository.append(
            DeviceHistoryEntry.create(
                tenantId=tenantId,
                deviceId=deviceId,
                action=action,
                now=now,
                fromStatus=fromStatus,
                toStatus=toStatus,
                note=note,
            )
        )


# =====================================================================================
# Read: the tree
# =====================================================================================
class GetAssetTreeUseCase(AssetHierarchyUseCaseBase):
    """The whole plant as one nested structure.

    Locations nest by `parentId`, devices nest under their location, and a
    sub-assembly nests under its parent device rather than its location — the
    parent link is the stronger statement of where a part belongs.
    """

    requiredAction = PERMISSION_REGISTRY_VIEW

    def perform(self, query: AssetTreeQuery) -> dict:
        tenantId = resolveTenantId("")
        locations = self.locationRepository.treeRows(tenantId)
        devices = self.deviceRepository.hierarchyRows(tenantId)
        if not query.includeRetired:
            devices = [row for row in devices if row["status"] != "retired"]

        deviceNodes = {row["id"]: self._deviceNode(row) for row in devices}
        childrenOf: dict[str, list[str]] = {}
        for row in devices:
            parent = row["parentDeviceId"]
            if parent and parent in deviceNodes:
                childrenOf.setdefault(parent, []).append(row["id"])

        # Attach sub-assemblies to their parent device, skipping any link that
        # loops — a corrupted row must not hang the render.
        parents = {row["id"]: (row["parentDeviceId"] or None) for row in devices}
        attached: set[str] = set()
        for parentId, childIds in childrenOf.items():
            for childId in childIds:
                if childId == parentId or childId in ancestorChain(parentId, parents):
                    continue
                deviceNodes[parentId].children.append(deviceNodes[childId])
                attached.add(childId)

        locationNodes = {row["id"]: self._locationNode(row) for row in locations}
        for row in devices:
            if row["id"] in attached:
                continue
            holder = locationNodes.get(row["locationId"])
            if holder is not None:
                holder.children.append(deviceNodes[row["id"]])

        roots: list[AssetTreeNode] = []
        for row in locations:
            node = locationNodes[row["id"]]
            parent = locationNodes.get(row["parentId"])
            if parent is not None and parent is not node:
                parent.children.append(node)
            else:
                roots.append(node)

        if query.rootLocationId:
            root = locationNodes.get(query.rootLocationId)
            if root is None:
                raise EntityNotFoundError("Location not found.")
            roots = [root]

        for node in locationNodes.values():
            node.deviceCount = self._countDevices(node)

        unplaced = [
            deviceNodes[row["id"]]
            for row in devices
            if row["id"] not in attached and not locationNodes.get(row["locationId"])
        ]

        return {
            "roots": [self._asDict(node) for node in roots],
            "unplacedDevices": [self._asDict(node) for node in unplaced],
            "counts": {
                "locations": len(locations),
                "devices": len(devices),
                "unplacedDevices": len(unplaced),
            },
        }

    def _countDevices(self, node: AssetTreeNode) -> int:
        total = 0
        for child in node.children:
            if child.nodeType == "device":
                total += 1 + self._countDevices(child)
            else:
                total += self._countDevices(child)
        return total

    @staticmethod
    def _locationNode(row: dict) -> AssetTreeNode:
        return AssetTreeNode(
            id=row["id"],
            nodeType="location",
            code=row["code"],
            name=row["name"],
            kind=row["kind"],
            path=row["path"],
        )

    @staticmethod
    def _deviceNode(row: dict) -> AssetTreeNode:
        return AssetTreeNode(
            id=row["id"],
            nodeType="device",
            code=row["code"],
            name=row["name"],
            assetLevel=row["assetLevel"],
            status=row["status"],
            criticality=row["criticality"],
            path=row["locationPath"],
            costCenterCode=row["costCenterCode"],
            costCenterName=row["costCenterName"],
            installedOn=row["installedOn"],
            retiredOn=row["retiredOn"],
        )

    def _asDict(self, node: AssetTreeNode) -> dict:
        return {
            "id": node.id,
            "nodeType": node.nodeType,
            "code": node.code,
            "name": node.name,
            "kind": node.kind,
            "assetLevel": node.assetLevel,
            "status": node.status,
            "criticality": node.criticality,
            "path": node.path,
            "costCenterCode": node.costCenterCode,
            "costCenterName": node.costCenterName,
            "installedOn": node.installedOn,
            "retiredOn": node.retiredOn,
            "deviceCount": node.deviceCount,
            "children": [self._asDict(child) for child in node.children],
        }


# =====================================================================================
# Read: one asset's upstream chain
# =====================================================================================
class GetAssetAncestryUseCase(AssetHierarchyUseCaseBase):
    """Everything above one device: parent assets, then the location chain.

    This is the «دارایی بالادستی» answer — when a line goes down, what else
    is implicated, and which budget carries it.
    """

    requiredAction = PERMISSION_REGISTRY_VIEW

    def perform(self, query: AssetAncestryQuery) -> dict:
        tenantId = resolveTenantId("")
        index = self.deviceIndex(tenantId)
        row = index.get(str(query.deviceId))
        if row is None:
            raise EntityNotFoundError("Device not found.")

        parents = self.parentsFrom(index)
        deviceChain = [
            {
                "id": index[key]["id"],
                "code": index[key]["code"],
                "name": index[key]["name"],
                "assetLevel": index[key]["assetLevel"],
                "nodeType": "device",
            }
            for key in ancestorChain(str(query.deviceId), parents)
            if key in index
        ]

        # The location chain starts at whichever asset in the chain is placed:
        # a component inherits the line its machine stands on.
        locationId = row["locationId"]
        for key in ancestorChain(str(query.deviceId), parents):
            if locationId:
                break
            locationId = index.get(key, {}).get("locationId", "")

        locationRows = {item["id"]: item for item in self.locationRepository.treeRows(tenantId)}
        locationParents = {key: (item["parentId"] or None) for key, item in locationRows.items()}
        locationChain: list[dict] = []
        if locationId and locationId in locationRows:
            keys = [locationId, *ancestorChain(locationId, locationParents)]
            locationChain = [
                {
                    "id": locationRows[key]["id"],
                    "code": locationRows[key]["code"],
                    "name": locationRows[key]["name"],
                    "kind": locationRows[key]["kind"],
                    "nodeType": "location",
                }
                for key in keys
                if key in locationRows
            ]

        childrenOf: dict[str, list[str]] = {}
        for key, item in index.items():
            if item["parentDeviceId"]:
                childrenOf.setdefault(item["parentDeviceId"], []).append(key)

        return {
            "device": {
                "id": row["id"],
                "code": row["code"],
                "name": row["name"],
                "assetLevel": row["assetLevel"],
                "status": row["status"],
                "locationPath": row["locationPath"],
                "costCenterCode": row["costCenterCode"],
                "costCenterName": row["costCenterName"],
                "installedOn": row["installedOn"],
                "retiredOn": row["retiredOn"],
            },
            # Root first, so the UI can print it as a breadcrumb.
            "deviceChain": list(reversed(deviceChain)),
            "locationChain": list(reversed(locationChain)),
            "children": [
                {
                    "id": index[key]["id"],
                    "code": index[key]["code"],
                    "name": index[key]["name"],
                    "assetLevel": index[key]["assetLevel"],
                    "status": index[key]["status"],
                }
                for key in sorted(
                    childrenOf.get(str(query.deviceId), []),
                    key=lambda item: index[item]["code"],
                )
            ],
            "descendantCount": len(descendantIds(str(query.deviceId), childrenOf)),
            "previousLocation": self.movementRepository.previousLocation(
                tenantId, uuid.UUID(str(query.deviceId))
            ),
        }


class ListAssetMovementsUseCase(AssetHierarchyUseCaseBase):
    """The transfer history of one asset, newest first."""

    requiredAction = PERMISSION_REGISTRY_VIEW

    def perform(self, query: AssetMovementsQuery) -> list[dict]:
        tenantId = resolveTenantId("")
        self.requireDevice(tenantId, str(query.deviceId))
        return self.movementRepository.listForDevice(tenantId, uuid.UUID(str(query.deviceId)))


# =====================================================================================
# Write: move, retire, reinstate
# =====================================================================================
class MoveAssetUseCase(AssetHierarchyUseCaseBase):
    """Relocate an asset and keep the place it came from.

    The ledger row is written from the values read in the same call that
    overwrites them, so a transfer can never land without its origin.
    """

    requiredAction = PERMISSION_REGISTRY_MANAGE

    def perform(self, command: MoveAssetCommand) -> dict:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        deviceId = str(command.deviceId)
        index = self.deviceIndex(tenantId)
        row = index.get(deviceId)
        if row is None:
            raise EntityNotFoundError("Device not found.")
        if row["status"] == "retired":
            raise AssetHierarchyError(
                "این تجهیز از رده خارج شده است؛ برای جابه‌جایی ابتدا آن را به چرخهٔ کار بازگردانید."
            )

        movedOn = parseDateOrNone(str(command.movedOn or "")) or now.date()

        toLocationId: uuid.UUID | None = None
        toLocationPath = ""
        if command.toLocationId:
            location = self.locationRepository.getById(
                tenantId, uuid.UUID(str(command.toLocationId))
            )
            if location is None:
                raise EntityNotFoundError("Location not found.")
            toLocationId = location.id
            toLocationPath = location.displayPath()
        elif not command.clearLocation and row["locationId"]:
            toLocationId = uuid.UUID(row["locationId"])
            toLocationPath = row["locationPath"]

        toParentId: uuid.UUID | None = None
        resolvedLevel = ""
        if command.toParentDeviceId:
            parentRow = index.get(str(command.toParentDeviceId))
            if parentRow is None:
                raise EntityNotFoundError("Parent device not found.")
            parents = self.parentsFrom(index)
            assertNoCycle(deviceId, str(command.toParentDeviceId), parents)
            assertDepthWithinLimit(str(command.toParentDeviceId), parents)
            resolvedLevel = resolveChildLevel(
                parentRow["assetLevel"], parentRow["name"], row["assetLevel"]
            )
            toParentId = uuid.UUID(str(command.toParentDeviceId))
        elif not command.clearParent and row["parentDeviceId"]:
            toParentId = uuid.UUID(row["parentDeviceId"])

        unchanged = (
            str(toLocationId or "") == row["locationId"]
            and str(toParentId or "") == row["parentDeviceId"]
        )
        if unchanged:
            raise AssetHierarchyError(
                "محل نصب و والد این تجهیز تغییری نکرده است؛ جابه‌جایی ثبت نشد."
            )

        previous = self.deviceRepository.moveDevice(
            tenantId,
            uuid.UUID(deviceId),
            toLocationId=toLocationId,
            toLocationPath=toLocationPath,
            toParentDeviceId=toParentId,
            installedOn=movedOn if command.updateInstalledOn else None,
            assetLevel=resolvedLevel if resolvedLevel != row["assetLevel"] else "",
            now=now,
        )

        movement = self.movementRepository.record(
            tenantId=tenantId,
            deviceId=uuid.UUID(deviceId),
            fromLocationId=previous.get("fromLocationId"),
            fromLocationPath=previous.get("fromLocationPath", ""),
            toLocationId=toLocationId,
            toLocationPath=toLocationPath,
            fromParentDeviceId=previous.get("fromParentDeviceId"),
            toParentDeviceId=toParentId,
            movedOn=movedOn,
            reason=str(command.reason or ""),
            performedBy=str(command.performedBy or ""),
            note=str(command.note or ""),
            now=now,
        )

        origin = previous.get("fromLocationPath") or "—"
        self.recordHistory(
            tenantId,
            uuid.UUID(deviceId),
            "relocated",
            f"جابه‌جایی از «{origin}» به «{toLocationPath or '—'}»"
            + (f" — {command.reason}" if command.reason else ""),
            now,
        )
        self.audit(
            AUDIT_CREATE,
            resourceType="AssetMovement",
            resourceId=movement["id"],
            tenantId=tenantId,
            before={
                "locationId": str(previous.get("fromLocationId") or ""),
                "parentDeviceId": str(previous.get("fromParentDeviceId") or ""),
            },
            after={
                "locationId": str(toLocationId or ""),
                "parentDeviceId": str(toParentId or ""),
            },
        )
        return movement


class RetireAssetUseCase(AssetHierarchyUseCaseBase):
    """Take an asset out of service with a date and a reason.

    Refuses while live sub-assemblies still hang off it, unless the caller
    asks for the whole subtree: a retired machine whose motor is still listed
    as operational is a reporting lie.
    """

    requiredAction = PERMISSION_REGISTRY_MANAGE

    def perform(self, command: RetireAssetCommand) -> dict:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        deviceId = str(command.deviceId)
        index = self.deviceIndex(tenantId)
        row = index.get(deviceId)
        if row is None:
            raise EntityNotFoundError("Device not found.")
        if row["status"] == "retired":
            raise AssetHierarchyError("این تجهیز پیش‌تر از رده خارج شده است.")

        retiredOn = parseDateOrNone(str(command.retiredOn or "")) or now.date()
        installed = row["installedOn"]
        if installed and retiredOn.isoformat() < installed:
            raise AssetHierarchyError("تاریخ خروج از رده نمی‌تواند پیش از تاریخ نصب باشد.")

        childrenOf: dict[str, list[str]] = {}
        for key, item in index.items():
            if item["parentDeviceId"]:
                childrenOf.setdefault(item["parentDeviceId"], []).append(key)
        descendants = [
            key
            for key in descendantIds(deviceId, childrenOf)
            if index.get(key, {}).get("status") != "retired"
        ]
        if descendants and not command.retireChildren:
            names = "، ".join(index[key]["code"] for key in descendants[:5])
            raise AssetHierarchyError(
                f"{len(descendants)} زیرتجهیز هنوز فعال است ({names})؛ "
                "ابتدا آن‌ها را از رده خارج کنید یا گزینهٔ خروج گروهی را انتخاب کنید."
            )

        targets = [deviceId, *descendants] if command.retireChildren else [deviceId]
        retired: list[str] = []
        for key in targets:
            previousStatus = self.deviceRepository.retireDevice(
                tenantId,
                uuid.UUID(key),
                retiredOn=retiredOn,
                reason=str(command.reason or ""),
                now=now,
            )
            if not previousStatus:
                continue
            retired.append(key)
            self.recordHistory(
                tenantId,
                uuid.UUID(key),
                "retired",
                f"خروج از رده در {retiredOn.isoformat()}"
                + (f" — {command.reason}" if command.reason else ""),
                now,
                fromStatus=previousStatus,
                toStatus="retired",
            )
        self.audit(
            AUDIT_UPDATE,
            resourceType="DeviceRetirement",
            resourceId=deviceId,
            tenantId=tenantId,
            after={"retiredOn": retiredOn.isoformat(), "count": len(retired)},
        )
        return {
            "deviceId": deviceId,
            "retiredOn": retiredOn.isoformat(),
            "reason": str(command.reason or ""),
            "retiredCount": len(retired),
            "retiredIds": retired,
        }


class ReinstateAssetUseCase(AssetHierarchyUseCaseBase):
    """Put a retired asset back in service — the date and reason go with it."""

    requiredAction = PERMISSION_REGISTRY_MANAGE

    def perform(self, command: ReinstateAssetCommand) -> dict:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        deviceId = str(command.deviceId)
        index = self.deviceIndex(tenantId)
        row = index.get(deviceId)
        if row is None:
            raise EntityNotFoundError("Device not found.")
        if row["status"] != "retired":
            raise AssetHierarchyError("این تجهیز از رده خارج نشده است.")

        status = str(command.status or "operational")
        if status not in LIVE_STATUSES:
            raise AssetHierarchyError("وضعیت بازگشت به کار معتبر نیست.")
        self.deviceRepository.reinstateDevice(tenantId, uuid.UUID(deviceId), status=status, now=now)
        self.recordHistory(
            tenantId,
            uuid.UUID(deviceId),
            "reinstated",
            "بازگشت به چرخهٔ کار",
            now,
            fromStatus="retired",
            toStatus=status,
        )
        self.audit(
            AUDIT_UPDATE,
            resourceType="DeviceRetirement",
            resourceId=deviceId,
            tenantId=tenantId,
            after={"status": status},
        )
        return {"deviceId": deviceId, "status": status}


__all__ = [
    "ASSET_LEVELS",
    "ASSET_MAIN_EQUIPMENT",
    "AssetAncestryQuery",
    "AssetMovementsQuery",
    "AssetTreeQuery",
    "GetAssetAncestryUseCase",
    "GetAssetTreeUseCase",
    "ListAssetMovementsUseCase",
    "MoveAssetCommand",
    "MoveAssetUseCase",
    "ReinstateAssetCommand",
    "ReinstateAssetUseCase",
    "RetireAssetCommand",
    "RetireAssetUseCase",
]
