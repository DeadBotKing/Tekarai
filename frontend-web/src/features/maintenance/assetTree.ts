import type { AssetTreeNode } from "../../shared/types/domain";

/**
 * Pure helpers for rendering the asset hierarchy.
 *
 * Kept out of the page so the awkward parts — filtering a tree without
 * orphaning matches, and walking one that may contain a cycle — can be
 * tested without mounting React.
 */

/** Every id in the forest, depth-first. */
export const collectIds = (nodes: AssetTreeNode[], into: string[] = []): string[] => {
  nodes.forEach((node) => {
    into.push(node.id);
    collectIds(node.children, into);
  });
  return into;
};

/**
 * Keep a node when it matches, or when anything beneath it matches.
 *
 * Filtering by simply dropping non-matching nodes would orphan the matches
 * living underneath them — searching for a bearing would return nothing
 * because its line and machine do not contain the word. So a branch survives
 * whenever its subtree does, and the user keeps the context that tells them
 * where the hit actually sits.
 */
export const filterTree = (nodes: AssetTreeNode[], term: string): AssetTreeNode[] => {
  const needle = term.trim().toLowerCase();
  if (!needle) return nodes;
  const visit = (node: AssetTreeNode): AssetTreeNode | null => {
    const haystack = `${node.code} ${node.name} ${node.costCenterCode}`.toLowerCase();
    // A node that matches keeps its whole subtree. Filtering its children
    // too would make the hit look like a leaf and hide the sub-assemblies
    // hanging off it — which is usually the reason the user searched for it.
    if (haystack.includes(needle)) return node;
    const children = node.children
      .map(visit)
      .filter((child): child is AssetTreeNode => child !== null);
    return children.length > 0 ? { ...node, children } : null;
  };
  return nodes.map(visit).filter((node): node is AssetTreeNode => node !== null);
};

/** Devices anywhere beneath a node (locations in between do not count). */
export const countDevices = (node: AssetTreeNode): number =>
  node.children.reduce(
    (total, child) => total + (child.nodeType === "device" ? 1 : 0) + countDevices(child),
    0,
  );
