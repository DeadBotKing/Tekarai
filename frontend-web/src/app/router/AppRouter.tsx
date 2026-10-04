import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell, ProtectedRoute } from "../../layouts/AppShell";
import { LoginPage } from "../../pages/LoginPage";
import { DashboardPage } from "../../pages/DashboardPage";
import { ProjectsPage } from "../../pages/ProjectsPage";
import { TasksPage } from "../../pages/TasksPage";
import { MaintenanceDashboardPage } from "../../pages/MaintenanceDashboardPage";
import { MaintenanceDevicesPage } from "../../pages/MaintenanceDevicesPage";
import MaintenanceInspectionsPage from "../../pages/MaintenanceInspectionsPage";
import { EquipmentRegistryPage } from "../../pages/EquipmentRegistryPage";
import { DeviceProfilePage } from "../../pages/DeviceProfilePage";
import { MaintenanceLocationsPage } from "../../pages/MaintenanceLocationsPage";
import { AssetHierarchyPage } from "../../pages/AssetHierarchyPage";
import { MaintenancePersonnelPage } from "../../pages/MaintenancePersonnelPage";
import { FleetAnalyticsPage } from "../../pages/FleetAnalyticsPage";
import { MaintenancePmCalendarPage } from "../../pages/MaintenancePmCalendarPage";
import { MeterReadingsPage } from "../../pages/MeterReadingsPage";
import { OfflineQueuePage } from "../../pages/OfflineQueuePage";
import { MaintenanceReportPage } from "../../pages/MaintenanceReportPage";
import MaintenanceWorkReportPage from "../../pages/MaintenanceWorkReportPage";
import { DeviceReportPage } from "../../pages/DeviceReportPage";
import { DeviceTimelinePage } from "../../pages/DeviceTimelinePage";
import { WorkOrdersPage } from "../../pages/WorkOrdersPage";
import { SparePartsPage } from "../../pages/SparePartsPage";
import { ProcurementPage } from "../../pages/ProcurementPage";
import { AccountPage } from "../../pages/AccountPage";
import { DocumentsPage } from "../../pages/DocumentsPage";
import { IntelligencePage } from "../../pages/IntelligencePage";
import { AdministrationPage } from "../../pages/AdministrationPage";
import { ChatPage } from "../../pages/ChatPage";
import { NotificationsPage } from "../../pages/NotificationsPage";
import { SettingsPage } from "../../pages/SettingsPage";
import { NotFoundPage } from "../../pages/NotFoundPage";

export function AppRouter(): JSX.Element {
  return <Routes>
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
  </Routes>;
}
