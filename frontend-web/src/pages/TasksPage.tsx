import { useMemo, useState } from "react";
import { useLocalization } from "../core/localization/localizationContext";
import { PERMISSIONS } from "../core/permissions/permissionContext";
import { demoTasks } from "../features/demo/demoData";
import type { Task } from "../shared/types/domain";
import { DataTable, type DataTableColumn } from "../shared/components/DataTable";
import { Modal, Toast } from "../shared/components/overlays";
import { Avatar, Badge, Button, Card, PermissionGuard, SectionHeader, SelectInput, TextInput } from "../shared/components/primitives";
import { Icon } from "../shared/components/Icon";

const taskColumns = (t: ReturnType<typeof useLocalization>["t"], onOpen: (task: Task) => void): DataTableColumn<Task>[] => [
  { key: "title", label: t("task.title"), accessor: (row) => row.title, sortable: true, width: "30%", render: (row) => <button type="button" className="link-cell" onClick={() => onOpen(row)}><span className={`task-priority-dot task-priority-dot--${row.priority}`} />{row.title}</button> },
  { key: "project", label: t("task.project"), accessor: (row) => row.project, sortable: true, render: (row) => <span className="muted-cell">{row.project}</span> },
  { key: "status", label: t("task.status"), accessor: (row) => row.status, sortable: true, render: (row) => <Badge tone={row.status === "done" ? "success" : row.status === "review" ? "purple" : row.status === "inProgress" ? "info" : "neutral"} dot>{row.status === "inProgress" ? t("common.status.inProgress") : row.status === "review" ? "Review" : row.status === "done" ? t("common.status.completed") : "Backlog"}</Badge> },
  { key: "priority", label: t("task.priority"), accessor: (row) => row.priority, sortable: true, render: (row) => <Badge tone={row.priority === "critical" ? "danger" : row.priority === "high" ? "warning" : "neutral"}>{row.priority}</Badge> },
  { key: "assignee", label: t("task.assignee"), accessor: (row) => row.assignee, render: (row) => <div className="person-cell"><Avatar name={row.assignee} size="sm" tone="purple" /><span>{row.assignee}</span></div> },
  { key: "dueDate", label: t("task.due"), accessor: (row) => row.dueDate, sortable: true },
];

const columns: { key: Task["status"]; label: string }[] = [
  { key: "backlog", label: "Backlog" }, { key: "inProgress", label: "In progress" }, { key: "review", label: "Review" }, { key: "done", label: "Done" },
];

export function TasksPage(): JSX.Element {
  const { t } = useLocalization();
  const [tasks, setTasks] = useState<Task[]>(demoTasks);
  const [view, setView] = useState<"list" | "board" | "timeline" | "calendar">("list");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [createOpen, setCreateOpen] = useState(false);
  const [activeTask, setActiveTask] = useState<Task | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [toast, setToast] = useState("");
  const filtered = useMemo(() => tasks.filter((task) => (status === "all" || task.status === status) && `${task.title} ${task.project} ${task.assignee}`.toLowerCase().includes(search.toLowerCase())), [search, status, tasks]);
  const createTask = (): void => { if (!newTitle.trim()) return; const task: Task = { id: `task-${Date.now()}`, title: newTitle.trim(), project: "Nova Plant Modernization", status: "backlog", priority: "normal", assignee: "Maya Chen", dueDate: "2026-09-30", estimate: "1d" }; setTasks((current) => [task, ...current]); setNewTitle(""); setCreateOpen(false); setToast("Task created successfully."); };
  const moveTask = (task: Task, nextStatus: Task["status"]): void => setTasks((current) => current.map((item) => item.id === task.id ? { ...item, status: nextStatus } : item));

  return <div className="page"><SectionHeader eyebrow={t("nav.projects")} title={t("task.title")} subtitle={t("task.subtitle")} actions={<PermissionGuard permission={PERMISSIONS.taskCreate}><Button variant="primary" icon="plus" onClick={() => setCreateOpen(true)}>{t("task.new")}</Button></PermissionGuard>} />
    <Card className="content-card" padding="none"><div className="view-toolbar"><div className="segmented-control" role="tablist" aria-label="Task views">{(["list", "board", "timeline", "calendar"] as const).map((item) => <button key={item} role="tab" aria-selected={view === item} className={view === item ? "is-active" : ""} onClick={() => setView(item)}>{item === "list" ? t("task.list") : item === "board" ? t("task.board") : item === "timeline" ? t("task.timeline") : t("task.calendar")}</button>)}</div><div className="list-toolbar"><div className="search-box"><Icon name="search" size={16} /><input value={search} aria-label={t("task.search")} placeholder={t("task.search")} onChange={(event) => setSearch(event.target.value)} /></div><SelectInput aria-label={t("task.status")} value={status} onChange={(event) => setStatus(event.target.value)} options={[{ value: "all", label: t("task.status") }, ...columns.map((item) => ({ value: item.key, label: item.label }))]} /></div></div>{view === "list" && <DataTable columns={taskColumns(t, setActiveTask)} data={filtered} rowKey={(row) => row.id} search="" empty={{ title: t("task.empty") }} exportName="tekarai-tasks" />}{view === "board" && <TaskBoard tasks={filtered} onMove={moveTask} onOpen={setActiveTask} />}{view === "timeline" && <TaskTimeline tasks={filtered} />}{view === "calendar" && <TaskCalendar tasks={filtered} />}</Card>
    <Modal open={createOpen} title={t("task.createTitle")} onClose={() => setCreateOpen(false)} footer={<><Button variant="secondary" onClick={() => setCreateOpen(false)}>{t("common.cancel")}</Button><Button variant="primary" icon="check" onClick={createTask}>{t("task.save")}</Button></>}><TextInput label={t("task.taskName")} required value={newTitle} onChange={(event) => setNewTitle(event.target.value)} autoFocus /><div className="form-grid form-grid--compact"><SelectInput label={t("task.priority")} options={[{ value: "normal", label: t("common.priority.normal") }, { value: "high", label: t("common.priority.high") }, { value: "critical", label: t("common.priority.critical") }]} defaultValue="normal" /><TextInput label={t("task.due")} type="date" defaultValue="2026-09-30" /></div></Modal>
    <Modal open={Boolean(activeTask)} title={activeTask?.title ?? t("task.title")} onClose={() => setActiveTask(null)} footer={<Button variant="secondary" onClick={() => setActiveTask(null)}>{t("common.close")}</Button>}>{activeTask && <div className="detail-panel"><div className="detail-stats"><div><span>{t("task.project")}</span><strong>{activeTask.project}</strong></div><div><span>{t("task.assignee")}</span><strong>{activeTask.assignee}</strong></div><div><span>{t("task.status")}</span><strong>{activeTask.status}</strong></div><div><span>{t("task.due")}</span><strong>{activeTask.dueDate}</strong></div></div><p className="detail-panel__description">Estimate: {activeTask.estimate}</p></div>}</Modal>
    {toast && <Toast message={toast} onClose={() => setToast("")} />}
  </div>;
}

function TaskBoard({ tasks, onMove, onOpen }: { tasks: Task[]; onMove: (task: Task, status: Task["status"]) => void; onOpen: (task: Task) => void }): JSX.Element {
  const { t } = useLocalization();
  return <div className="kanban">{columns.map((column) => <section className="kanban-column" key={column.key}><header><h3>{column.label}</h3><span>{tasks.filter((task) => task.status === column.key).length}</span></header><div className="kanban-column__body">{tasks.filter((task) => task.status === column.key).map((task) => <button type="button" className="task-card" key={task.id} onClick={() => onOpen(task)}><div className="task-card__top"><Badge tone={task.priority === "critical" ? "danger" : task.priority === "high" ? "warning" : "neutral"}>{task.priority}</Badge><Icon name="more" size={15} /></div><strong>{task.title}</strong><span>{task.project}</span><div className="task-card__bottom"><Avatar name={task.assignee} size="sm" tone="purple" /><span>{task.dueDate}</span></div>{column.key !== "done" && <span className="task-card__advance" onClick={(event) => { event.stopPropagation(); onMove(task, column.key === "backlog" ? "inProgress" : column.key === "inProgress" ? "review" : "done"); }}>{t("common.next")} <Icon name="arrowRight" size={13} /></span>}</button>)}</div></section>)}</div>;
}

function TaskTimeline({ tasks }: { tasks: Task[] }): JSX.Element {
  return <div className="task-timeline">{tasks.map((task) => <div className="task-timeline__row" key={task.id}><div className="task-timeline__label"><strong>{task.title}</strong><span>{task.project}</span></div><div className="task-timeline__track"><span className={`task-timeline__bar task-timeline__bar--${task.priority}`} style={{ left: `${Math.min(80, Math.max(0, Number(task.id.replace("task-", "")) * 3))}%`, width: `${task.status === "done" ? 20 : task.status === "inProgress" ? 30 : 18}%` }} /></div><span className="task-timeline__date">{task.dueDate}</span></div>)}</div>;
}

function TaskCalendar({ tasks }: { tasks: Task[] }): JSX.Element {
  const { t } = useLocalization();
  const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  return <div className="task-calendar"><div className="task-calendar__header">{days.map((day) => <strong key={day}>{day}</strong>)}</div><div className="task-calendar__grid">{Array.from({ length: 35 }, (_, index) => { const day = index - 1; const dayTasks = tasks.filter((task) => Number(task.dueDate.slice(-2)) === day + 1); return <div className={`calendar-cell ${day < 0 ? "is-muted" : ""}`} key={index}><span>{day > 0 ? day : ""}</span>{dayTasks.map((task) => <button type="button" key={task.id} className={`calendar-task calendar-task--${task.priority}`}>{task.title}</button>)}</div>; })}</div><p className="calendar-note"><Icon name="calendar" size={15} />{tasks.length} {t("task.title").toLowerCase()} scheduled in this view.</p></div>;
}
