"""Rules that keep the asset hierarchy a tree.

The plant reads as one chain:

    سایت ← ساختمان ← خط تولید ← سیستم ← تجهیز اصلی ← زیرتجهیز ← قطعه

The first four links are locations, the last three are devices. Both halves
are self-referencing, and a self-referencing table without guards is one bad
write away from a cycle — after which every ancestry walk, every rolled-up
cost and every tree render loops until something times out.

Pure functions on purpose: no ORM, no HTTP. They take the facts already
loaded by the caller and answer yes or no, so the arithmetic can be tested
without a database.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from apps.maintenance.domain.valueObjects.maintenanceState import (
    ASSET_LEVEL_RANK,
    ASSET_LEVELS,
    ASSET_MAIN_EQUIPMENT,
    LOCATION_KIND_RANK,
)
from apps.sharedKernel.domain.errors import DomainError

#: A plant deeper than this is a data-entry mistake, not a plant. The guard
#: exists so a corrupted chain cannot be walked forever even if a cycle
#: somehow slips past the checks below.
MAX_HIERARCHY_DEPTH = 12


class AssetHierarchyError(DomainError):
    """A parent/child link that would break the tree (422, message shown)."""


def locationNestingIsValid(parentKind: str, childKind: str) -> bool:
    """May a `childKind` node sit under a `parentKind` node?

    Only catalogued kinds are ranked; anything a plant invented is allowed
    anywhere, because the kind vocabulary is deliberately open.
    """
    parentRank = LOCATION_KIND_RANK.get(parentKind)
    childRank = LOCATION_KIND_RANK.get(childKind)
    if parentRank is None or childRank is None:
        return True
    return childRank >= parentRank


def assertLocationNesting(parentKind: str, parentName: str, childKind: str) -> None:
    if not locationNestingIsValid(parentKind, childKind):
        raise AssetHierarchyError(
            f"«{childKind}» نمی‌تواند زیرمجموعهٔ «{parentName}» ({parentKind}) باشد؛ "
            f"ترتیب سلسله‌مراتب رعایت نشده است."
        )


def assetNestingIsValid(parentLevel: str, childLevel: str) -> bool:
    """A child device must sit strictly deeper than its parent."""
    parentRank = ASSET_LEVEL_RANK.get(parentLevel)
    childRank = ASSET_LEVEL_RANK.get(childLevel)
    if parentRank is None or childRank is None:
        return True
    return childRank > parentRank


def assertAssetNesting(parentLevel: str, parentName: str, childLevel: str) -> None:
    if not assetNestingIsValid(parentLevel, childLevel):
        raise AssetHierarchyError(
            f"یک «{childLevel}» نمی‌تواند زیرمجموعهٔ «{parentName}» ({parentLevel}) باشد؛ "
            f"زیرمجموعه باید یک سطح پایین‌تر از والد خود باشد."
        )


def resolveChildLevel(
    parentLevel: str,
    parentName: str,
    childLevel: str,
    *,
    stated: bool = False,
) -> str:
    """The level a child should carry once filed under `parentLevel`.

    Every device predating the hierarchy carries the default
    ``mainEquipment``, which means "not classified yet" rather than "this is
    definitely a top-level machine". Refusing those writes would have broken
    every existing parent/child link in the plant, so an unstated default is
    *derived* instead: file a machine under a line and it becomes a
    sub-assembly on its own.

    A level the user actually chose is never silently rewritten — that would
    destroy information — so a real conflict is refused and explained.
    """
    if assetNestingIsValid(parentLevel, childLevel):
        return childLevel
    if not stated and childLevel == ASSET_MAIN_EQUIPMENT:
        return defaultChildLevel(parentLevel)
    assertAssetNesting(parentLevel, parentName, childLevel)
    return childLevel


def defaultChildLevel(parentLevel: str) -> str:
    """The level a new child gets when the caller did not state one."""
    rank = ASSET_LEVEL_RANK.get(parentLevel)
    if rank is None:
        return ASSET_MAIN_EQUIPMENT
    for level in ASSET_LEVELS:
        if ASSET_LEVEL_RANK[level] == rank + 1:
            return level
    return ASSET_LEVELS[-1]


def ancestorChain(
    startId: str,
    parentOf: Mapping[str, str | None],
    *,
    maxDepth: int = MAX_HIERARCHY_DEPTH,
) -> list[str]:
    """Walk upward from `startId`, nearest parent first.

    Stops at the root, at `maxDepth`, or the moment a node repeats — a
    corrupted chain yields a short list instead of hanging the request.
    """
    chain: list[str] = []
    seen = {startId}
    current = parentOf.get(startId)
    while current and len(chain) < maxDepth:
        if current in seen:
            break
        chain.append(current)
        seen.add(current)
        current = parentOf.get(current)
    return chain


def wouldCreateCycle(
    nodeId: str,
    newParentId: str | None,
    parentOf: Mapping[str, str | None],
) -> bool:
    """Would re-parenting `nodeId` under `newParentId` close a loop?

    True when the node is its own new parent, or when the proposed parent is
    already one of the node's descendants.
    """
    if not newParentId:
        return False
    if newParentId == nodeId:
        return True
    return nodeId in ancestorChain(newParentId, parentOf)


def assertNoCycle(
    nodeId: str,
    newParentId: str | None,
    parentOf: Mapping[str, str | None],
    *,
    label: str = "این تجهیز",
) -> None:
    if wouldCreateCycle(nodeId, newParentId, parentOf):
        raise AssetHierarchyError(f"{label} نمی‌تواند زیرمجموعهٔ خودش یا یکی از زیرمجموعه‌هایش باشد.")


def assertDepthWithinLimit(
    newParentId: str | None,
    parentOf: Mapping[str, str | None],
    *,
    maxDepth: int = MAX_HIERARCHY_DEPTH,
) -> None:
    if newParentId is None:
        return
    depth = len(ancestorChain(newParentId, parentOf, maxDepth=maxDepth)) + 2
    if depth > maxDepth:
        raise AssetHierarchyError(f"عمق سلسله‌مراتب از حد مجاز ({maxDepth} سطح) بیشتر می‌شود.")


def descendantIds(
    rootId: str,
    childrenOf: Mapping[str, Iterable[str]],
    *,
    maxDepth: int = MAX_HIERARCHY_DEPTH,
) -> list[str]:
    """Every node below `rootId`, breadth-first and cycle-safe.

    Used to refuse retiring an asset that still carries live children, and to
    scope a subtree in the tree endpoint.
    """
    collected: list[str] = []
    seen = {rootId}
    frontier = [rootId]
    for _ in range(maxDepth):
        nextFrontier: list[str] = []
        for parent in frontier:
            for child in childrenOf.get(parent, ()):
                if child in seen:
                    continue
                seen.add(child)
                collected.append(child)
                nextFrontier.append(child)
        if not nextFrontier:
            break
        frontier = nextFrontier
    return collected
