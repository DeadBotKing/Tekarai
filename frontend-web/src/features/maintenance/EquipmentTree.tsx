import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { usePermissions, PERMISSIONS } from "../../core/permissions/permissionContext";
import { runtimeConfig } from "../../app/configuration/runtimeConfig";
import { Badge, Button, PermissionGuard } from "../../shared/components/primitives";
import { Icon } from "../../shared/components/Icon";
import type { MaintenanceDevice, WorkOrder } from "../../shared/types/domain";
import { demoWorkOrders } from "./maintenanceDemoData";
import { buildDeviceTree, type DeviceTreeNode } from "./wave1";
import type { createMaintenanceService } from "./maintenanceService";

export function EquipmentTree({ devices, service, onMessage }: {
  devices: MaintenanceDevice[]; service: ReturnType<typeof createMaintenanceService>; onMessage: (message: string) => void;
}): JSX.Element {
  const { has } = usePermissions();
  const canReadOrders = has(PERMISSIONS.maintenanceWorkOrderList);
  const [orders, setOrders] = useState<WorkOrder[]>([]);
  useEffect(() => {
    let active = true;
    if (!canReadOrders) { setOrders([]); return; }
    if (runtimeConfig.demoMode) { setOrders(demoWorkOrders); return; }
    service.listWorkOrders().then((rows) => { if (active) setOrders(rows); }).catch(() => { if (active) onMessage("دریافت شمار دستورکارهای نمای درخت ناموفق بود."); });
    return () => { active = false; };
  }, [canReadOrders, service, onMessage]);
  const nodes = useMemo(() => buildDeviceTree(devices, orders), [devices, orders]);
  return <div style={{ padding: 12 }}><DeviceTreeNodes nodes={nodes} depth={0} /></div>;
}

function DeviceTreeNodes({ nodes, depth }: { nodes: DeviceTreeNode[]; depth: number }): JSX.Element {
  const navigate = useNavigate();
  return <>{nodes.map(node => <div key={node.key}>
    <div className="inspection-item" style={{ paddingInlineStart: depth * 20 }}>
      <span><Icon name={node.children.length ? "folder" : "grid"} size={14} /> <strong>{node.label}</strong></span>
      <div className="section-actions">
        {node.devices.length > 0 && <Badge tone="neutral">{node.devices.length} دستگاه</Badge>}
        {node.openWorkOrders > 0 && <Badge tone="warning">{node.openWorkOrders} درخواست باز</Badge>}
      </div>
    </div>
    {node.devices.map(device => <div key={device.id} style={{ paddingInlineStart: depth * 20 + 24 }}>
      <PermissionGuard permission={PERMISSIONS.maintenanceDeviceView} fallback={<span>{device.code} — {device.name}</span>}>
        <Button variant="ghost" icon="cpu" onClick={() => navigate(`/app/maintenance/devices/${device.id}/profile`)}>{device.code} — {device.name}</Button>
      </PermissionGuard>
    </div>)}
    {node.children.length > 0 && <DeviceTreeNodes nodes={node.children} depth={depth + 1} />}
  </div>)}</>;
}
