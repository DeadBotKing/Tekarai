import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApiClient } from "../core/api/apiContext";
import { useLocalization } from "../core/localization/localizationContext";
import { PERMISSIONS } from "../core/permissions/permissionContext";
import { runtimeConfig } from "../app/configuration/runtimeConfig";
import { createRegistryService } from "../features/maintenance/registryService";
import { createDemoRegistryService } from "../features/maintenance/registryDemoData";
import type { AssetTree, AssetTreeNode } from "../shared/types/domain";
import { Toast } from "../shared/components/overlays";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  MetricCard,
  PermissionGuard,
  SectionHeader,
  TextInput,
} from "../shared/components/primitives";
import { Icon } from "../shared/components/Icon";
import { taxonomyLabel } from "../core/localization/taxonomyLabel";
import { collectIds, filterTree } from "../features/maintenance/assetTree";

/**
 * The asset hierarchy, rendered as one tree.
 *
 * The plant chain — سایت ← ساختمان ← خط تولید ← سیستم ← تجهیز اصلی ←
 * زیرتجهیز ← قطعه — was always *modellable*: locations knew their parent and
 * devices knew theirs. It was never *readable*, because nothing joined the
 * two halves. This page is that join, and it is deliberately read-only: the
 * writes (transfer, retirement) belong on the device's own profile, where the
 * rest of its facts already live.
 */

const levelTone = (level: string): "info" | "neutral" | "warning" =>
  level === "mainEquipment" ? "info" : level === "subEquipment" ? "neutral" : "warning";

const statusTone = (status: string): "success" | "danger" | "warning" | "neutral" => {
  if (status === "operational") return "success";
  if (status === "faulty") return "danger";
  if (status === "underMaintenance") return "warning";
  return "neutral";
};

interface TreeRowProps {
  node: AssetTreeNode;
  depth: number;
  expanded: Set<string>;
  onToggle: (id: string) => void;
  onOpenDevice: (id: string) => void;
}

function TreeRow({ node, depth, expanded, onToggle, onOpenDevice }: TreeRowProps): JSX.Element {
  const { t } = useLocalization();
  const isOpen = expanded.has(node.id);
  const hasChildren = node.children.length > 0;
  const isDevice = node.nodeType === "device";

  return (
    <>
      <div
        className="asset-tree__row"
        // Indentation is a margin on the inline-start side so it mirrors
        // correctly when the frame flips to LTR.
        style={{ marginInlineStart: `${depth * 1.5}rem` }}
      >
        <button
          type="button"
          className="asset-tree__toggle"
          onClick={() => hasChildren && onToggle(node.id)}
          aria-expanded={hasChildren ? isOpen : undefined}
          aria-label={node.name}
          disabled={!hasChildren}
        >
          {hasChildren ? <Icon name={isOpen ? "chevronDown" : "chevronLeft"} /> : <span />}
        </button>
        <Icon name={isDevice ? "cpu" : "building"} />
        <span className="asset-tree__code plaintext">{node.code}</span>
        <span className="asset-tree__name">{node.name}</span>
        {isDevice ? (
          <>
            <Badge tone={levelTone(node.assetLevel)}>
              {taxonomyLabel(t, "assets.level.", node.assetLevel)}
            </Badge>
            {node.status === "retired" ? (
              <Badge tone="neutral">{t("assets.retire.badge")}</Badge>
            ) : (
              <Badge tone={statusTone(node.status)}>
                {taxonomyLabel(t, "cmms.status.", node.status)}
              </Badge>
            )}
            {node.costCenterCode ? (
              <span className="asset-tree__cost plaintext">{node.costCenterCode}</span>
            ) : null}
            <Button variant="ghost" size="sm" onClick={() => onOpenDevice(node.id)}>
              {t("registry.openProfile")}
            </Button>
          </>
        ) : (
          <>
            <Badge tone="neutral">{taxonomyLabel(t, "registry.location.", node.kind)}</Badge>
            {node.deviceCount > 0 ? (
              <span className="asset-tree__count">
                {node.deviceCount} {t("assets.tree.deviceCount")}
              </span>
            ) : null}
          </>
        )}
      </div>
      {isOpen
        ? node.children.map((child) => (
            <TreeRow
              key={child.id}
              node={child}
              depth={depth + 1}
              expanded={expanded}
              onToggle={onToggle}
              onOpenDevice={onOpenDevice}
            />
          ))
        : null}
    </>
  );
}

export function AssetHierarchyPage(): JSX.Element {
  const { t } = useLocalization();
  const navigate = useNavigate();
  const api = useApiClient();
  const registry = useMemo(
    () => (runtimeConfig.demoMode ? createDemoRegistryService() : createRegistryService(api)),
    [api],
  );

  const [tree, setTree] = useState<AssetTree | null>(null);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState("");
  const [search, setSearch] = useState("");
  const [includeRetired, setIncludeRetired] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  // A failed fetch and a genuinely empty plant both render as "no rows".
  // Without this the user is told nothing is here when in fact the request
  // never landed, so the error is kept rather than left to a toast that
  // disappears before it can be read.
  const [loadError, setLoadError] = useState("");

  const load = useCallback(
    async (signal?: AbortSignal) => {
      setLoading(true);
      setLoadError("");
      try {
        const result = await registry.getAssetTree({ includeRetired }, signal);
        setTree(result);
        // Open the top two levels on arrival: deep plants are unreadable
        // fully expanded, and fully collapsed they say nothing at all.
        setExpanded((previous) => {
          if (previous.size > 0) return previous;
          const next = new Set<string>();
          result.roots.forEach((root) => {
            next.add(root.id);
            root.children.forEach((child) => next.add(child.id));
          });
          return next;
        });
      } catch (error) {
        if ((error as Error)?.name !== "AbortError") {
          setLoadError((error as Error).message || t("error.networkBody"));
        }
      } finally {
        setLoading(false);
      }
    },
    [includeRetired, registry, t],
  );

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const visibleRoots = useMemo(
    () => filterTree(tree?.roots ?? [], search),
    [tree, search],
  );

  // A filtered view is useless collapsed — the matches are usually deep.
  useEffect(() => {
    if (!search.trim() || !tree) return;
    setExpanded(new Set(collectIds(filterTree(tree.roots, search))));
  }, [search, tree]);

  const toggle = useCallback((id: string) => {
    setExpanded((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const expandAll = useCallback(() => {
    setExpanded(new Set(collectIds(tree?.roots ?? [])));
  }, [tree]);

  const collapseAll = useCallback(() => setExpanded(new Set()), []);

  const openDevice = useCallback(
    (deviceId: string) => navigate(`/app/maintenance/devices/${deviceId}/profile`),
    [navigate],
  );

  return (
    <PermissionGuard permission={PERMISSIONS.maintenanceDeviceList}>
      <div className="page">
        <SectionHeader title={t("assets.tree.title")} subtitle={t("assets.tree.subtitle")} />

        <div className="metric-grid">
          <MetricCard
            icon="building"
            label={t("assets.tree.locations")}
            value={tree?.counts.locations ?? 0}
          />
          <MetricCard icon="cpu" label={t("assets.tree.devices")} value={tree?.counts.devices ?? 0} />
          <MetricCard
            icon="warning"
            tone={tree && tree.counts.unplacedDevices > 0 ? "amber" : "blue"}
            label={t("assets.tree.unplaced")}
            value={tree?.counts.unplacedDevices ?? 0}
          />
        </div>

        <Card>
          <div className="toolbar">
            <TextInput
              label={t("assets.tree.search")}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={t("assets.tree.search")}
              icon="search"
            />
            <Button variant="ghost" onClick={expandAll}>
              {t("assets.tree.expandAll")}
            </Button>
            <Button variant="ghost" onClick={collapseAll}>
              {t("assets.tree.collapseAll")}
            </Button>
            <label className="checkbox-field">
              <input
                type="checkbox"
                checked={includeRetired}
                onChange={(event) => setIncludeRetired(event.target.checked)}
              />
              <span>{t("assets.tree.includeRetired")}</span>
            </label>
          </div>

          {loading ? (
            <LoadingState label={t("assets.tree.title")} />
          ) : loadError ? (
            <ErrorState
              title={t("error.networkTitle")}
              description={loadError}
              retry={() => void load()}
            />
          ) : visibleRoots.length === 0 ? (
            <EmptyState
              title={search.trim() ? t("assets.tree.noMatch") : t("assets.tree.empty")}
            />
          ) : (
            <div className="asset-tree">
              {visibleRoots.map((root) => (
                <TreeRow
                  key={root.id}
                  node={root}
                  depth={0}
                  expanded={expanded}
                  onToggle={toggle}
                  onOpenDevice={openDevice}
                />
              ))}
            </div>
          )}
        </Card>

        {tree && tree.unplacedDevices.length > 0 ? (
          <Card>
            <SectionHeader
              title={t("assets.tree.unplaced")}
              subtitle={t("assets.tree.unplacedHint")}
            />
            <div className="asset-tree">
              {tree.unplacedDevices.map((node) => (
                <TreeRow
                  key={node.id}
                  node={node}
                  depth={0}
                  expanded={expanded}
                  onToggle={toggle}
                  onOpenDevice={openDevice}
                />
              ))}
            </div>
          </Card>
        ) : null}

        {toast ? <Toast message={toast} tone="error" onClose={() => setToast("")} /> : null}
      </div>
    </PermissionGuard>
  );
}
