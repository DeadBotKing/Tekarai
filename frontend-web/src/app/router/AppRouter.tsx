import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell, ProtectedRoute } from "../../layouts/AppShell";
import { LoginPage } from "../../pages/LoginPage";
import { DashboardPage } from "../../pages/DashboardPage";
import { ProjectsPage } from "../../pages/ProjectsPage";
import { TasksPage } from "../../pages/TasksPage";
import { DocumentsPage } from "../../pages/DocumentsPage";
import { ReportsPage } from "../../pages/ReportsPage";
import { IntelligencePage } from "../../pages/IntelligencePage";
import { AdministrationPage } from "../../pages/AdministrationPage";
import { NotificationsPage } from "../../pages/NotificationsPage";
import { SettingsPage } from "../../pages/SettingsPage";
import { NotFoundPage } from "../../pages/NotFoundPage";
import { OperationsResourcePage } from "../../pages/OperationsResourcePage";

export function AppRouter(): JSX.Element {
  return <Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route path="/" element={<Navigate to="/app/dashboard" replace />} />
    <Route path="/app" element={<ProtectedRoute><AppShell /></ProtectedRoute>}>
      <Route index element={<Navigate to="dashboard" replace />} />
      <Route path="dashboard" element={<DashboardPage />} />
      <Route path="projects" element={<ProjectsPage />} />
      <Route path="tasks" element={<TasksPage />} />
      <Route path="documents" element={<DocumentsPage />} />
      <Route path="organization/employees" element={<OperationsResourcePage />} />
      <Route path="organization/departments" element={<OperationsResourcePage />} />
      <Route path="devices" element={<OperationsResourcePage />} />
      <Route path="reports" element={<ReportsPage />} />
      <Route path="intelligence" element={<IntelligencePage />} />
      <Route path="administration/*" element={<AdministrationPage />} />
      <Route path="notifications" element={<NotificationsPage />} />
      <Route path="settings" element={<SettingsPage />} />
      <Route path="*" element={<NotFoundPage />} />
    </Route>
    <Route path="*" element={<NotFoundPage />} />
  </Routes>;
}
