"""Unit tests for the pure asset-hierarchy rules.

No database: these are the arithmetic that decides whether a parent/child
link is legal, so they must be cheap enough to assert exhaustively.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.maintenance.domain.services.assetHierarchyRules import (
    AssetHierarchyError,
    MAX_HIERARCHY_DEPTH,
    ancestorChain,
    assertAssetNesting,
    assertDepthWithinLimit,
    assertLocationNesting,
    assertNoCycle,
    assetNestingIsValid,
    defaultChildLevel,
    descendantIds,
    locationNestingIsValid,
    resolveChildLevel,
    wouldCreateCycle,
)


class LocationNestingTests(SimpleTestCase):
    def test_acceptsTheCanonicalChain(self) -> None:
        chain = ["site", "building", "line", "system"]
        for parent, child in zip(chain, chain[1:]):
            self.assertTrue(
                locationNestingIsValid(parent, child), f"{child} under {parent}"
            )

    def test_refusesAnInvertedPair(self) -> None:
        self.assertFalse(locationNestingIsValid("line", "site"))
        self.assertFalse(locationNestingIsValid("system", "building"))

    def test_allowsSiblingsAtTheSameRank(self) -> None:
        # A room inside an area is ordinary plant reality, not a mistake.
        self.assertTrue(locationNestingIsValid("area", "room"))

    def test_unknownKindIsNeverRefused(self) -> None:
        # The vocabulary is deliberately open: a plant may invent «سوله».
        self.assertTrue(locationNestingIsValid("سوله", "site"))
        self.assertTrue(locationNestingIsValid("line", "سوله"))

    def test_assertRaisesWithTheOffendingNames(self) -> None:
        with self.assertRaises(AssetHierarchyError) as caught:
            assertLocationNesting("line", "خط تولید ۱", "site")
        self.assertIn("خط تولید ۱", str(caught.exception))


class AssetNestingTests(SimpleTestCase):
    def test_childMustBeStrictlyDeeper(self) -> None:
        self.assertTrue(assetNestingIsValid("mainEquipment", "subEquipment"))
        self.assertTrue(assetNestingIsValid("subEquipment", "component"))
        self.assertTrue(assetNestingIsValid("mainEquipment", "component"))

    def test_refusesEqualOrInvertedLevels(self) -> None:
        self.assertFalse(assetNestingIsValid("mainEquipment", "mainEquipment"))
        self.assertFalse(assetNestingIsValid("component", "subEquipment"))
        self.assertFalse(assetNestingIsValid("component", "component"))

    def test_assertRaisesForAComponentOwningSomething(self) -> None:
        with self.assertRaises(AssetHierarchyError):
            assertAssetNesting("component", "یاتاقان", "subEquipment")

    def test_defaultChildLevelStepsDownOneRung(self) -> None:
        self.assertEqual(defaultChildLevel("mainEquipment"), "subEquipment")
        self.assertEqual(defaultChildLevel("subEquipment"), "component")

    def test_defaultChildLevelStopsAtTheBottom(self) -> None:
        self.assertEqual(defaultChildLevel("component"), "component")

    def test_unknownLevelFallsBackToMainEquipment(self) -> None:
        self.assertEqual(defaultChildLevel(""), "mainEquipment")


class ResolveChildLevelTests(SimpleTestCase):
    """`mainEquipment` is every legacy row's default, so it means
    "unclassified" — derived from the parent, not enforced against it."""

    def test_aValidLevelIsLeftAlone(self) -> None:
        self.assertEqual(
            resolveChildLevel("mainEquipment", "پرس", "subEquipment"), "subEquipment"
        )

    def test_anUnclassifiedChildIsDerived(self) -> None:
        self.assertEqual(
            resolveChildLevel("mainEquipment", "پرس", "mainEquipment"), "subEquipment"
        )
        self.assertEqual(
            resolveChildLevel("subEquipment", "موتور", "mainEquipment"), "component"
        )

    def test_aStatedLevelIsEnforced(self) -> None:
        with self.assertRaises(AssetHierarchyError):
            resolveChildLevel("mainEquipment", "پرس", "mainEquipment", stated=True)

    def test_aRealConflictIsNeverRewritten(self) -> None:
        # The child is explicitly a sub-assembly; demoting it to a component
        # to make the link fit would destroy what the user recorded.
        with self.assertRaises(AssetHierarchyError):
            resolveChildLevel("component", "یاتاقان", "subEquipment")


class CycleTests(SimpleTestCase):
    def setUp(self) -> None:
        # line → machine → motor → bearing
        self.parents = {
            "line": None,
            "machine": "line",
            "motor": "machine",
            "bearing": "motor",
        }

    def test_ancestorChainWalksToTheRoot(self) -> None:
        self.assertEqual(
            ancestorChain("bearing", self.parents), ["motor", "machine", "line"]
        )

    def test_selfParentIsACycle(self) -> None:
        self.assertTrue(wouldCreateCycle("motor", "motor", self.parents))

    def test_descendantAsParentIsACycle(self) -> None:
        # Filing the line under its own bearing closes the loop.
        self.assertTrue(wouldCreateCycle("line", "bearing", self.parents))

    def test_unrelatedParentIsFine(self) -> None:
        self.parents["spare"] = None
        self.assertFalse(wouldCreateCycle("spare", "machine", self.parents))

    def test_detachingIsNeverACycle(self) -> None:
        self.assertFalse(wouldCreateCycle("motor", None, self.parents))
        self.assertFalse(wouldCreateCycle("motor", "", self.parents))

    def test_anAlreadyCorruptChainDoesNotHang(self) -> None:
        # If a loop ever reached the database, the walk must still terminate.
        corrupt = {"a": "b", "b": "a"}
        self.assertEqual(ancestorChain("a", corrupt), ["b"])

    def test_assertNoCycleRaises(self) -> None:
        with self.assertRaises(AssetHierarchyError):
            assertNoCycle("line", "bearing", self.parents)


class DepthTests(SimpleTestCase):
    def test_refusesAChainPastTheLimit(self) -> None:
        parents: dict[str, str | None] = {"n0": None}
        for index in range(1, MAX_HIERARCHY_DEPTH + 2):
            parents[f"n{index}"] = f"n{index - 1}"
        deepest = f"n{MAX_HIERARCHY_DEPTH + 1}"
        with self.assertRaises(AssetHierarchyError):
            assertDepthWithinLimit(deepest, parents)

    def test_allowsAShallowChain(self) -> None:
        assertDepthWithinLimit("machine", {"machine": "line", "line": None})

    def test_rootIsAlwaysAllowed(self) -> None:
        assertDepthWithinLimit(None, {})


class DescendantTests(SimpleTestCase):
    def setUp(self) -> None:
        self.children = {
            "line": ["machineA", "machineB"],
            "machineA": ["motor"],
            "motor": ["bearing"],
        }

    def test_collectsTheWholeSubtree(self) -> None:
        self.assertEqual(
            sorted(descendantIds("line", self.children)),
            ["bearing", "machineA", "machineB", "motor"],
        )

    def test_leafHasNoDescendants(self) -> None:
        self.assertEqual(descendantIds("bearing", self.children), [])

    def test_aCycleDoesNotLoopForever(self) -> None:
        self.assertEqual(
            sorted(descendantIds("a", {"a": ["b"], "b": ["a"]})), ["b"]
        )
