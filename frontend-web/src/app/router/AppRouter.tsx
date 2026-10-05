import { Suspense, lazy, type ComponentType } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell, ProtectedRoute } from "../../layouts/AppShell";
import { LoginPage } from "../../pages/LoginPage";
import { RouteFallback } from "./RouteFallback";

/**
 * Route-level code splitting.
 *
 * Every page used to sit in the entry chunk, which meant a technician opening
 * the login screen on a phone downloaded all 35 pages plus the Excel writer,
 * the QR encoder and the camera-based barcode scanner — ~390 kB gzipped
 * before anything could be rendered. Each route is now its own chunk, so the
 * first paint carries the shell and the login form and nothing else.
 *
 * `LoginPage` stays eagerly imported on purpose: it is the first thing an
 * unauthenticated visitor sees, and a suspense flash on the very first paint
 * looks like a broken app rather than a fast one.
 */

/** Normalizes named exports into the default shape `lazy()` expects. */
const named = <T extends Record<string, unknown>, K extends keyof T>(
  loader: () => Promise<T>,
  exportName: K,
) =>
  lazy(() =>
    loader().then((module) => ({ default: module[exportName] as ComponentType<unknown> })),
  );

const DashboardPage = named(() => import("../../pages/DashboardPage"), "DashboardPage");
const ProjectsPage = named(() => import("../../pages/ProjectsPage"), "ProjectsPage");
const TasksPage = named(() => import("../../pages/TasksPage"), "TasksPage");
const MaintenanceDashboardPage = named(
  () => import("../../pages/MaintenanceDashboardPage"),
  "MaintenanceDashboardPage",
);
const MaintenanceDevicesPage = named(
  () => import("../../pages/MaintenanceDevicesPage"),
  "MaintenanceDevicesPage",
);
const MaintenanceInspectionsPage = lazy(() => import("../../pages/MaintenanceInspectionsPage"));
const EquipmentRegistryPage = named(
  () => import("../../pages/EquipmentRegistryPage"),
  "EquipmentRegistryPage",
);
const DeviceProfilePage = named(() => import("../../pages/DeviceProfilePage"), "DeviceProfilePage");
const MaintenanceLocationsPage = named(
  () => import("../../pages/MaintenanceLocationsPage"),
  "MaintenanceLocationsPage",
);
const AssetHierarchyPage = named(
  () => import("../../pages/AssetHierarchyPage"),
  "AssetHierarchyPage",
);
const MaintenancePersonnelPage = named(
  () => import("../../pages/MaintenancePersonnelPage"),
  "MaintenancePersonnelPage",
);
const FleetAnalyticsPage = named(
  () => import("../../pages/FleetAnalyticsPage"),
  "FleetAnalyticsPage",
);
const MaintenancePmCalendarPage = named(
  () => import("../../pages/MaintenancePmCalendarPage"),
  "MaintenancePmCalendarPage",
);
const WorkCalendarPage = named(() => import("../../pages/WorkCalendarPage"), "WorkCalendarPage");
const PerformanceReviewPage = named(
  () => import("../../pages/PerformanceReviewPage"),
  "PerformanceReviewPage",
);
const MeterReadingsPage = named(() => import("../../pages/MeterReadingsPage"), "MeterReadingsPage");
const OfflineQueuePage = named(() => import("../../pages/OfflineQueuePage"), "OfflineQueuePage");
const MaintenanceReportPage = named(
  () => import("../../pages/MaintenanceReportPage"),
  "MaintenanceReportPage",
);
const MaintenanceWorkReportPage = lazy(() => import("../../pages/MaintenanceWorkReportPage"));
const DeviceReportPage = named(() => import("../../pages/DeviceReportPage"), "DeviceReportPage");
const DeviceTimelinePage = named(
  () => import("../../pages/DeviceTimelinePage"),
  "DeviceTimelinePage",
);
const WorkOrdersPage = named(() => import("../../pages/WorkOrdersPage"), "WorkOrdersPage");
const SparePartsPage = named(() => import("../../pages/SparePartsPage"), "SparePartsPage");
const ProcurementPage = named(() => import("../../pages/ProcurementPage"), "ProcurementPage");
const AccountPage = named(() => import("../../pages/AccountPage"), "AccountPage");
const DocumentsPage = named(() => import("../../pages/DocumentsPage"), "DocumentsPage");
const IntelligencePage = named(() => import("../../pages/IntelligencePage"), "IntelligencePage");
const AdministrationPage = named(
  () => import("../../pages/AdministrationPage"),
  "AdministrationPage",
);
const ChatPage = named(() => import("../../pages/ChatPage"), "ChatPage");
const NotificationsPage = named(() => import("../../pages/NotificationsPage"), "NotificationsPage");
const SettingsPage = named(() => import("../../pages/SettingsPage"), "SettingsPage");
const NotFoundPage = named(() => import("../../pages/NotFoundPage"), "NotFoundPage");

export function AppRouter(): JSX.Element {
  return <Suspense fallback={<RouteFallback />}>
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<Navigate to="/app/dashboard" replace />} />
      <Route path="/app" element={<ProtectedRoute><AppShell /></ProtectedRoute>}>
        <Route index element={<Navigate to="dashboard" replace />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="projects" element={<ProjectsPage />} />
        <Route path="tasks" element={<TasksPage />} />
        <Route path="maintenance/dashboard" element={<MaintenanceDashboardPage />} />
        <Route path="maintenance/devices" element={<MaintenanceDevicesPage />} />
        <Route path="maintenance/registry" element={<EquipmentRegistryPage />} />
        <Route path="maintenance/devices/:deviceId/profile" element={<DeviceProfilePage />} />
        <Route path="maintenance/locations" element={<MaintenanceLocationsPage />} />
        <Route path="maintenance/asset-tree" element={<AssetHierarchyPage />} />
        <Route path="maintenance/personnel" element={<MaintenancePersonnelPage />} />
        <Route path="maintenance/fleet" element={<FleetAnalyticsPage />} />
        <Route path="maintenance/reports" element={<MaintenanceReportPage />} />
        <Route path="maintenance/work-report" element={<MaintenanceWorkReportPage />} />
        <Route path="maintenance/devices/:deviceId/report" element={<DeviceReportPage />} />
        <Route path="maintenance/devices/:deviceId/timeline" element={<DeviceTimelinePage />} />
        <Route path="maintenance/work-orders" element={<WorkOrdersPage />} />
        <Route path="maintenance/warehouse" element={<SparePartsPage />} />
        <Route path="maintenance/procurement" element={<ProcurementPage />} />
        <Route path="account" element={<AccountPage />} />
        <Route path="maintenance/inspections" element={<MaintenanceInspectionsPage />} />
        <Route path="maintenance/pm-calendar" element={<MaintenancePmCalendarPage />} />
        <Route path="maintenance/work-calendar" element={<WorkCalendarPage />} />
        <Route path="maintenance/performance-review" element={<PerformanceReviewPage />} />
        <Route path="maintenance/meter-readings" element={<MeterReadingsPage />} />
        <Route path="maintenance/offline-queue" element={<OfflineQueuePage />} />
        <Route path="documents" element={<DocumentsPage />} />
        <Route path="intelligence" element={<IntelligencePage />} />
        <Route path="administration/*" element={<AdministrationPage />} />
        <Route path="chat" element={<ChatPage />} />
        <Route path="notifications" element={<NotificationsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  </Suspense>;
}
