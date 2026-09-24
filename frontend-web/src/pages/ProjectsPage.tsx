import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useApiClient } from "../core/api/apiContext";
import { useLocalization } from "../core/localization/localizationContext";
import { PERMISSIONS } from "../core/permissions/permissionContext";
import { demoProjects } from "../features/demo/demoData";
import { createProjectService } from "../features/projects/projectService";
import { runtimeConfig } from "../app/configuration/runtimeConfig";
import type { Project } from "../shared/types/domain";
import { DataTable, type DataTableColumn } from "../shared/components/DataTable";
import { Drawer, Modal, Toast } from "../shared/components/overlays";
import { Avatar, Button, Card, CardHeader, PermissionGuard, ProgressBar, SectionHeader, SelectInput, StatusBadge, TextArea, TextInput } from "../shared/components/primitives";
import { Icon } from "../shared/components/Icon";
import { JalaliDatePicker } from "../shared/components/JalaliDatePicker";
import { formatJalali } from "../core/localization/jalali";

interface ProjectForm { name: string; description: string; owner: string; dueDate: string; }
const emptyForm: ProjectForm = { name: "", description: "", owner: "Maya Chen", dueDate: "2026-12-31" };

export function ProjectsPage(): JSX.Element {
  const { t } = useLocalization();
  const api = useApiClient();
  const service = useMemo(() => createProjectService(api), [api]);
  const [searchParams, setSearchParams] = useSearchParams();
  const [projects, setProjects] = useState<Project[]>(demoProjects);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [form, setForm] = useState<ProjectForm>(emptyForm);
  const [editing, setEditing] = useState<Project | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [formError, setFormError] = useState("");
  const [toast, setToast] = useState("");

  const refresh = useCallback(async (): Promise<void> => {
    if (runtimeConfig.demoMode) return;
    try { setProjects(await service.list()); } catch { /* keep last known state */ }
  }, [service]);
  useEffect(() => { void refresh(); }, [refresh]);

  useEffect(() => {
    if (searchParams.get("create") === "1") {
      setEditing(null); setEditorOpen(true); setForm(emptyForm); setSearchParams({}, { replace: true });
    }
  }, [searchParams, setSearchParams]);
  const openEditor = (project?: Project): void => { setEditing(project ?? null); setEditorOpen(true); setForm(project ? { name: project.name, description: project.description, owner: project.owner, dueDate: project.dueDate } : emptyForm); setFormError(""); };
  const saveProject = async (): Promise<void> => {
    if (!form.name.trim()) { setFormError(t("auth.required")); return; }
    setFormError("");
    if (runtimeConfig.demoMode) {
      if (editing) {
        const updated = { ...editing, ...form, progress: editing.progress };
        setProjects((current) => current.map((item) => item.id === editing.id ? updated : item));
        setToast(t("project.updateSuccess"));
      } else {
        const newProject: Project = { id: `project-${Date.now()}`, code: `NEW-${String(projects.length + 1).padStart(2, "0")}`, name: form.name.trim(), description: form.description.trim(), owner: form.owner, status: "pending", health: 100, progress: 0, dueDate: form.dueDate, members: 1, tasks: 0, color: "#2878ff" };
        setProjects((current) => [newProject, ...current]);
        setToast(t("project.createSuccess"));
      }
      setEditing(null); setEditorOpen(false); setForm(emptyForm);
      return;
    }
    try {
      if (editing) {
        await service.update(editing.id, { name: form.name.trim(), description: form.description.trim(), owner: form.owner, dueDate: form.dueDate, progress: editing.progress, health: editing.health });
        setToast(t("project.updateSuccess"));
      } else {
        await service.create({ name: form.name.trim(), description: form.description.trim(), owner: form.owner, dueDate: form.dueDate });
        setToast(t("project.createSuccess"));
      }
      setEditing(null); setEditorOpen(false); setForm(emptyForm);
      await refresh();
    } catch (error) {
      setFormError(error instanceof Error ? error.message : t("project.saveFailed"));
    }
  };
  const columns = useMemo<DataTableColumn<Project>[]>(() => [
    { key: "name", label: t("project.title"), accessor: (row) => `${row.name} ${row.code}`, sortable: true, width: "28%", render: (row) => <div className="project-cell"><span className="project-cell__icon" style={{ backgroundColor: `${row.color}1a`, color: row.color }}><Icon name="folder" size={17} /></span><div><strong>{row.name}</strong><span>{row.code}</span></div></div> },
    { key: "status", label: t("project.status"), accessor: (row) => row.status, sortable: true, render: (row) => <StatusBadge status={row.status} /> },
    { key: "owner", label: t("project.owner"), accessor: (row) => row.owner, sortable: true, render: (row) => <div className="person-cell"><Avatar name={row.owner} size="sm" tone="purple" /><span>{row.owner}</span></div> },
    { key: "health", label: t("project.health"), accessor: (row) => row.health, sortable: true, render: (row) => <div className="health-cell"><span className={row.health < 70 ? "text-danger" : "text-success"}>{row.health}%</span><ProgressBar value={row.health} showValue={false} tone={row.health < 70 ? "amber" : "green"} /></div> },
    { key: "progress", label: t("project.progress"), accessor: (row) => row.progress, sortable: true, render: (row) => <div className="progress-cell"><ProgressBar value={row.progress} showValue={false} tone={row.status === "atRisk" ? "amber" : "blue"} /><span>{row.progress}%</span></div> },
    { key: "dueDate", label: t("project.due"), accessor: (row) => row.dueDate, sortable: true, render: (row) => <span>{formatJalali(row.dueDate, { style: "short" })}</span> },
    { key: "members", label: t("project.members"), accessor: (row) => row.members, sortable: true, render: (row) => <span className="members-count"><Icon name="users" size={15} />{row.members}</span> },
    { key: "actions", label: t("project.actions"), hideable: false, render: (row) => <div className="row-actions"><Button variant="ghost" size="sm" icon="external" aria-label={t("project.open")} onClick={() => setSelectedProject(row)}>{t("common.view")}</Button><PermissionGuard permission={PERMISSIONS.projectUpdate}><Button variant="ghost" size="sm" icon="edit" aria-label={t("common.edit")} onClick={() => openEditor(row)} /></PermissionGuard></div> },
  ], [t]);
  const filtered = status === "all" ? projects : projects.filter((project) => project.status === status);

  return <div className="page"><SectionHeader eyebrow={t("nav.workspace")} title={t("project.title")} subtitle={t("project.subtitle")} actions={<PermissionGuard permission={PERMISSIONS.projectCreate}><Button variant="primary" icon="plus" onClick={() => openEditor()}>{t("project.new")}</Button></PermissionGuard>} />
    <Card className="content-card" padding="none"><CardHeader title={`${projects.length} ${t("project.title").toLowerCase()}`} action={<div className="list-toolbar"><div className="search-box"><Icon name="search" size={16} /><input value={search} aria-label={t("project.search")} placeholder={t("project.search")} onChange={(event) => setSearch(event.target.value)} /></div><SelectInput aria-label={t("project.status")} value={status} onChange={(event) => setStatus(event.target.value)} options={[{ value: "all", label: t("project.status") }, { value: "active", label: t("common.status.active") }, { value: "inProgress", label: t("common.status.inProgress") }, { value: "atRisk", label: t("common.status.atRisk") }, { value: "onHold", label: t("common.status.onHold") }, { value: "completed", label: t("common.status.completed") }, { value: "archived", label: t("common.status.archived") }]} /></div>} /><DataTable columns={columns} data={filtered} rowKey={(row) => row.id} search={search} onRowClick={setSelectedProject} empty={{ title: t("common.noResults"), description: t("project.search") }} exportName="tekarai-projects" /></Card>
    <Modal open={editorOpen} title={editing ? t("project.editTitle") : t("project.createTitle")} onClose={() => { setEditing(null); setEditorOpen(false); setSearchParams({}, { replace: true }); }} footer={<><Button variant="secondary" onClick={() => { setEditing(null); setEditorOpen(false); setSearchParams({}, { replace: true }); }}>{t("project.cancel")}</Button><Button variant="primary" icon="check" onClick={saveProject}>{t("project.save")}</Button></>}><div className="form-grid"><TextInput label={t("project.name")} required value={form.name} error={formError} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} /><TextInput label={t("project.ownerField")} value={form.owner} onChange={(event) => setForm((current) => ({ ...current, owner: event.target.value }))} /><TextArea className="form-grid__full" label={t("project.description")} rows={4} value={form.description} onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))} /><JalaliDatePicker label={t("project.dueField")} value={form.dueDate} onChange={(date) => setForm((current) => ({ ...current, dueDate: date }))} /></div></Modal>
    <Drawer open={Boolean(selectedProject)} title={selectedProject?.name ?? t("project.title")} onClose={() => setSelectedProject(null)}>{selectedProject && <ProjectDetail project={selectedProject} onEdit={() => { setSelectedProject(null); openEditor(selectedProject); }} />}</Drawer>
    {toast && <Toast message={toast} onClose={() => setToast("")} />}
  </div>;
}

function ProjectDetail({ project, onEdit }: { project: Project; onEdit: () => void }): JSX.Element {
  const { t } = useLocalization();
  return <div className="detail-panel"><div className="detail-panel__hero"><span className="project-cell__icon" style={{ backgroundColor: `${project.color}1a`, color: project.color }}><Icon name="folder" size={22} /></span><div><span className="eyebrow">{project.code}</span><h3>{project.name}</h3><StatusBadge status={project.status} /></div></div><p className="detail-panel__description">{project.description}</p><div className="detail-stats"><div><span>{t("project.health")}</span><strong className={project.health < 70 ? "text-danger" : "text-success"}>{project.health}%</strong></div><div><span>{t("project.progress")}</span><strong>{project.progress}%</strong></div><div><span>{t("project.members")}</span><strong>{project.members}</strong></div><div><span>{t("project.due")}</span><strong>{formatJalali(project.dueDate, { style: "short" })}</strong></div></div><Card padding="sm"><CardHeader title={t("project.progress")} /><ProgressBar value={project.progress} label={t("project.progress")} tone="blue" /></Card><div className="detail-panel__actions"><Button variant="secondary" icon="edit" onClick={onEdit}>{t("common.edit")}</Button><Button variant="ghost" icon="checkSquare">{t("project.tasksTab")}</Button></div></div>;
}
