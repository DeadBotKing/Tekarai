import { useMemo, useState, type ReactNode } from "react";
import { Navigate, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { navigationConfig, type NavigationItem } from "../app/configuration/navigation";
import { useAuth } from "../core/auth/authContext";
import { runtimeConfig } from "../app/configuration/runtimeConfig";
import { useFeatureFlags } from "../core/flags/featureFlags";
import { useLocalization } from "../core/localization/localizationContext";
import { localeMeta } from "../core/localization/i18n";
import { useNotifications } from "../core/notifications/notificationContext";
import { usePermissions } from "../core/permissions/permissionContext";
import { useTenant } from "../core/tenant/tenantContext";
import { useTheme } from "../core/theme/themeContext";
import { demoDocuments, demoProjects, demoTasks } from "../features/demo/demoData";
import { Icon, type IconName } from "../shared/components/Icon";
import { Avatar, IconButton } from "../shared/components/primitives";
import { Drawer } from "../shared/components/overlays";

interface SearchResult { id: string; title: string; kind: string; route: string; detail: string }

export function AppShell(): JSX.Element {
  const { t, locale, cycleLocale } = useLocalization();
  const { theme, toggleTheme } = useTheme();
  const { tenants, selectedTenant, selectTenant } = useTenant();
  const { session, logout } = useAuth();
  const { has } = usePermissions();
  const { isEnabled } = useFeatureFlags();
  const { unreadCount } = useNotifications();
  const location = useLocation();
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [search, setSearch] = useState("");

  const visibleNavigation = useMemo(() => navigationConfig.map((group) => ({
    ...group,
    children: group.children?.filter((item) => (!item.permission || has(item.permission)) && (!item.featureFlag || isEnabled(item.featureFlag))),
  })).filter((group) => (group.children?.length ?? 0) > 0 && (!group.featureFlag || isEnabled(group.featureFlag))), [has, isEnabled]);
  const results = useMemo<SearchResult[]>(() => {
    const query = search.trim().toLowerCase();
    if (!query) return [];
    return [
      ...demoProjects.filter((item) => `${item.name} ${item.code}`.toLowerCase().includes(query)).map((item) => ({ id: item.id, title: item.name, kind: "Project", route: "/app/projects", detail: item.code })),
      ...demoTasks.filter((item) => `${item.title} ${item.project}`.toLowerCase().includes(query)).map((item) => ({ id: item.id, title: item.title, kind: "Task", route: "/app/tasks", detail: item.project })),
      ...demoDocuments.filter((item) => `${item.name} ${item.category}`.toLowerCase().includes(query)).map((item) => ({ id: item.id, title: item.name, kind: "Document", route: "/app/documents", detail: item.category })),
    ].slice(0, 8);
  }, [search]);

  const closeOverlays = (): void => { setMobileOpen(false); setProfileOpen(false); setSearchOpen(false); };
  const openSearch = (): void => { setSearchOpen(true); setSearch(""); };
  const handleLogout = async (): Promise<void> => { closeOverlays(); await logout(); navigate("/login", { replace: true }); };
  const currentPath = location.pathname;

  return <div className={`app-shell ${collapsed ? "app-shell--collapsed" : ""}`}>
    <aside className={`sidebar ${mobileOpen ? "is-mobile-open" : ""}`} aria-label={t("nav.workspace")}>
      <div className="sidebar__brand"><span className="brand-mark">T</span>{!collapsed && <div><strong>{runtimeConfig.appName}</strong><span>{t("app.tagline")}</span></div>}<IconButton className="sidebar__collapse" icon={collapsed ? "chevronRight" : "chevronLeft"} label={collapsed ? t("nav.expand") : t("nav.collapse")} onClick={() => setCollapsed((value) => !value)} /></div>
      <div className="sidebar__tenant"><span className="tenant-avatar">{selectedTenant.name.slice(0, 1)}</span>{!collapsed && <div><span>{t("header.tenant")}</span><strong>{selectedTenant.name}</strong></div>}</div>
      <nav className="sidebar__nav">
        {visibleNavigation.map((group) => <div className="nav-group" key={group.id}><div className="nav-group__label">{!collapsed && <span>{t(group.label)}</span>}</div>{group.children?.map((item) => <NavItem key={item.id} item={item} collapsed={collapsed} activePath={currentPath} onNavigate={closeOverlays} />)}</div>)}
      </nav>
      <div className="sidebar__bottom"><NavItem item={{ id: "settings", label: "nav.settings", icon: "settings", route: "/app/settings", permission: "settings.manage" }} collapsed={collapsed} activePath={currentPath} onNavigate={closeOverlays} /><button className="sidebar__user" type="button" onClick={() => setProfileOpen((value) => !value)} aria-label={t("header.profile")}><Avatar name={session?.user.displayName ?? "User"} size="sm" tone="purple" />{!collapsed && <div><strong>{session?.user.displayName}</strong><span>{session?.user.role}</span></div>}<Icon name="chevronUp" size={14} /></button></div>
    </aside>
    {mobileOpen && <button className="sidebar-backdrop" type="button" aria-label={t("nav.closeMenu")} onClick={() => setMobileOpen(false)} />}
    <div className="app-shell__main">
      <header className="topbar"><div className="topbar__left"><IconButton className="mobile-menu-button" icon="menu" label={t("nav.openMenu")} onClick={() => setMobileOpen(true)} /><div className="breadcrumb"><span>{t("nav.workspace")}</span><Icon name="chevronRight" size={14} /><strong>{breadcrumbFor(currentPath, t)}</strong></div></div><div className="topbar__actions"><button type="button" className="global-search-trigger" onClick={openSearch}><Icon name="search" size={17} /><span>{t("header.search")}</span><kbd>⌘ K</kbd></button><div className="topbar__divider" /><div className="topbar__select"><Icon name="building" size={16} /><select aria-label={t("header.tenant")} value={selectedTenant.id} onChange={(event) => selectTenant(event.target.value)}>{tenants.map((tenant) => <option key={tenant.id} value={tenant.id}>{tenant.name}</option>)}</select><Icon name="chevronDown" size={14} /></div><IconButton icon={theme === "light" ? "moon" : "sun"} label={t("header.theme")} onClick={toggleTheme} /><button type="button" className="language-button" aria-label={t("header.language")} onClick={cycleLocale}>{localeMeta[locale].nativeLabel}</button><NavLink to="/app/notifications" className="notification-button" aria-label={`${t("header.notifications")}${unreadCount ? `, ${unreadCount} ${t("notification.unread")}` : ""}`}><Icon name="bell" size={18} />{unreadCount > 0 && <span>{unreadCount}</span>}</NavLink><div className="profile-wrap"><IconButton icon="more" label={t("common.more")} onClick={() => setProfileOpen((value) => !value)} />{profileOpen && <div className="profile-menu"><div className="profile-menu__identity"><Avatar name={session?.user.displayName ?? "User"} size="md" tone="purple" /><div><strong>{session?.user.displayName}</strong><span>{session?.user.email}</span></div></div><div className="divider" /><NavLink to="/app/settings" onClick={() => setProfileOpen(false)}><Icon name="settings" size={16} />{t("nav.settings")}</NavLink><button type="button" onClick={() => void handleLogout()}><Icon name="logout" size={16} />{t("nav.signOut")}</button></div>}</div></div></header>
      <main className="main-content"><Outlet /></main>
      <footer className="app-footer"><span>© 2026 {runtimeConfig.appName}</span><div><span>{t("footer.version")}</span><a href="#help">{t("footer.help")}</a><a href="#privacy">{t("footer.privacy")}</a></div></footer>
    </div>
    <Drawer open={searchOpen} title={t("header.search")} onClose={() => setSearchOpen(false)}><div className="global-search"><SearchInput value={search} onChange={setSearch} placeholder={t("header.searchHint")} /><div className="global-search__hint">Search is tenant-aware and only returns resources available to your current permissions.</div>{search && results.length === 0 && <div className="global-search__empty"><Icon name="search" size={22} /><strong>{t("common.noResults")}</strong><span>Try a project, task or document name.</span></div>}{results.length > 0 && <div className="global-search__results">{results.map((result) => <button key={`${result.kind}-${result.id}`} type="button" onClick={() => { setSearchOpen(false); navigate(result.route); }}><span className="global-search__result-icon"><Icon name={result.kind === "Project" ? "folder" : result.kind === "Task" ? "checkSquare" : "file"} size={16} /></span><span><strong>{result.title}</strong><small>{result.kind} · {result.detail}</small></span><Icon name="arrowRight" size={15} /></button>)}</div>}</div></Drawer>
  </div>;
}

function SearchInput({ value, onChange, placeholder }: { value: string; onChange: (value: string) => void; placeholder: string }): JSX.Element { return <div className="search-box search-box--large"><Icon name="search" size={18} /><input autoFocus value={value} aria-label={placeholder} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} /></div>; }

function NavItem({ item, collapsed, activePath, onNavigate }: { item: NavigationItem; collapsed: boolean; activePath: string; onNavigate: () => void }): JSX.Element {
  const { t } = useLocalization();
  const route = item.route ?? "/app/dashboard";
  const active = activePath === route || (route !== "/app/dashboard" && activePath.startsWith(route));
  return <NavLink to={route} className={`nav-item ${active ? "is-active" : ""}`} onClick={onNavigate} title={collapsed ? t(item.label) : undefined}><Icon name={item.icon as IconName} size={17} /><span>{!collapsed && t(item.label)}</span>{!collapsed && item.badge && <span className="nav-item__badge">{item.badge}</span>}</NavLink>;
}

function breadcrumbFor(path: string, t: (key: "nav.dashboard" | "nav.projects" | "nav.tasks" | "nav.documents" | "nav.reports" | "nav.projectIntelligence" | "nav.administration" | "nav.settings" | "nav.notifications") => string): string {
  if (path.includes("notifications")) return t("nav.notifications");
  if (path.includes("administration")) return t("nav.administration");
  if (path.includes("intelligence")) return t("nav.projectIntelligence");
  if (path.includes("projects")) return t("nav.projects");
  if (path.includes("tasks")) return t("nav.tasks");
  if (path.includes("documents")) return t("nav.documents");
  if (path.includes("reports")) return t("nav.reports");
  if (path.includes("settings")) return t("nav.settings");
  return t("nav.dashboard");
}

export function ProtectedRoute({ children }: { children: ReactNode }): JSX.Element {
  const { isAuthenticated, isLoading } = useAuth();
  if (isLoading) return <div className="full-page-state"><span className="spinner" /></div>;
  if (!isAuthenticated) return <NavigateToLogin />;
  return <>{children}</>;
}

function NavigateToLogin(): JSX.Element { return <Navigate to="/login" replace />; }
