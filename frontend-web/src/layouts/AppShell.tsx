import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Navigate, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { navigationConfig, type NavigationItem } from "../app/configuration/navigation";
import { useAuth } from "../core/auth/authContext";
import { useApiClient } from "../core/api/apiContext";
import { createMaintenanceService } from "../features/maintenance/maintenanceService";
import { runtimeConfig } from "../app/configuration/runtimeConfig";
import { useFeatureFlags } from "../core/flags/featureFlags";
import { useLocalization } from "../core/localization/localizationContext";
import { localeMeta } from "../core/localization/i18n";
import { useNotifications } from "../core/notifications/notificationContext";
import { usePermissions } from "../core/permissions/permissionContext";
import { useTenant } from "../core/tenant/tenantContext";
import { useTheme } from "../core/theme/themeContext";
import { Icon, type IconName } from "../shared/components/Icon";
import { Avatar, IconButton } from "../shared/components/primitives";
import { OfflineIndicator } from "../shared/components/OfflineIndicator";
import { DemoModeBanner } from "../shared/components/DemoModeBanner";
import { AccentSwatches } from "../shared/components/AccentSwatches";
import { Drawer } from "../shared/components/overlays";
import { MobileNav, SideNav } from "./SideNav";

interface PageResult { id: string; title: string; group: string; route: string; icon: IconName }
interface Crumb { group: string; page: string }


interface EntityResult {
  kind: "device" | "workOrder";
  id: string;
  title: string;
  subtitle: string;
  route: string;
}

const OPEN_ORDER_STATUSES = new Set(["submitted", "routed", "assigned", "inProgress", "waitingApproval"]);

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
  const [menuOpen, setMenuOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [accentOpen, setAccentOpen] = useState(false);
  const [search, setSearch] = useState("");

  // Close the accent picker on outside click / Escape.
  useEffect(() => {
    if (!accentOpen) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!(event.target as HTMLElement).closest(".accent-menu-wrap")) setAccentOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setAccentOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [accentOpen]);
  const [entityResults, setEntityResults] = useState<EntityResult[]>([]);
  const [searching, setSearching] = useState(false);

  // Live entity search (devices + work orders) while typing — debounced.
  const api = useApiClient();
  useEffect(() => {
    if (runtimeConfig.demoMode) { setEntityResults([]); return; }
    const query = search.trim();
    if (query.length < 2) { setEntityResults([]); return; }
    let cancelled = false;
    setSearching(true);
    const timer = window.setTimeout(() => {
      const client = createMaintenanceService(api);
      void Promise.allSettled([
        client.listDevices({ search: query }),
        client.listWorkOrders({ search: query }),
      ]).then(([deviceBatch, orderBatch]) => {
        if (cancelled) return;
        const deviceRows = deviceBatch.status === "fulfilled"
          ? (deviceBatch.value as Array<{ id: string; code: string; name: string; department: string }>)
            .slice(0, 4)
            .map((device) => ({ kind: "device" as const, id: device.id, title: `${device.code} — ${device.name}`, subtitle: device.department, route: `/app/maintenance/devices/${device.id}/profile` }))
          : [];
        const orderRows = orderBatch.status === "fulfilled"
          ? (orderBatch.value as Array<{ id: string; title: string; status: string }>)
            .filter((order) => OPEN_ORDER_STATUSES.has(order.status))
            .slice(0, 4)
            .map((order) => ({ kind: "workOrder" as const, id: order.id, title: order.title, subtitle: order.status, route: `/app/maintenance/work-orders?search=${encodeURIComponent(query)}`, status: order.status }))
          : [];
        setEntityResults([...deviceRows, ...orderRows]);
        setSearching(false);
      });
    }, 350);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [search, api]);

  const visibleNavigation = useMemo(
    () => filterNavigationItems(navigationConfig, has, isEnabled).filter((group) => (group.children?.length ?? 0) > 0),
    [has, isEnabled],
  );

  const allFlatItems = useMemo(() => {
    const out: Array<{ item: NavigationItem; group: NavigationItem }> = [];
    const walk = (nodes: NavigationItem[] | undefined, group: NavigationItem): void => {
      nodes?.forEach((node) => {
        if (node.route) out.push({ item: node, group });
        walk(node.children, group);
      });
    };
    visibleNavigation.forEach((group) => walk(group.children, group));
    return out;
  }, [visibleNavigation]);

  // Real global search: navigate between actual pages of the app (permission-aware).
  const allPages = useMemo<PageResult[]>(
    () =>
      allFlatItems.map(({ item, group }) => ({
        id: item.id,
        title: t(item.label),
        group: t(group.label),
        route: item.route ?? "/app/dashboard",
        icon: item.icon,
      })),
    [allFlatItems, t],
  );

  const results = useMemo<PageResult[]>(() => {
    const query = normalizeText(search);
    if (!query) return [];
    return allPages
      .filter((page) => normalizeText(page.title).includes(query) || normalizeText(page.group).includes(query))
      .slice(0, 8);
  }, [allPages, search]);

  const crumb = useMemo<Crumb>(() => {
    let best: { item: NavigationItem; group: NavigationItem } | null = null;
    for (const { item, group } of allFlatItems) {
      if (!item.route) continue;
      const match =
        currentRoute(location.pathname) === item.route ||
        currentRoute(location.pathname).startsWith(`${item.route}/`);
      if (match && (!best || item.route.length > (best.item.route?.length ?? 0))) best = { item, group };
    }
    return best
      ? { group: t(best.group.label), page: t(best.item.label) }
      : { group: t("nav.workspace"), page: t("nav.dashboard") };
  }, [visibleNavigation, location.pathname, t]);

  const closeOverlays = (): void => {
    setMenuOpen(false);
    setProfileOpen(false);
    setSearchOpen(false);
  };
  const openSearch = (): void => {
    setSearchOpen(true);
    setSearch("");
  };
  const handleLogout = async (): Promise<void> => {
    closeOverlays();
    await logout();
    navigate("/login", { replace: true });
  };
  const currentPath = location.pathname;

  // حالت فشرده‌ی نمای — جداول/نمودارها مرتب‌تر (می‌توان با حذف این کلاس به حالت قبل برگشت)
  useEffect(() => {
    document.body.classList.add("layout-compact");
    return () => document.body.classList.remove("layout-compact");
  }, []);

  // Ctrl/⌘+K opens the page search anywhere in the app.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setSearchOpen((open) => !open);
        setSearch("");
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <div className="app-shell">
      <aside className="sidenav" aria-label={t("nav.workspace")}>
        <div className="sidenav__brand">
          <span className="brand-mark">T</span>
          <div>
            <strong>{runtimeConfig.appName}</strong>
            <span>{t("app.tagline")}</span>
          </div>
        </div>
        <div className="sidenav__tenant">
          <span className="tenant-avatar">{selectedTenant.name.slice(0, 1)}</span>
          <div>
            <span>{t("header.tenant")}</span>
            <strong>{selectedTenant.name}</strong>
          </div>
        </div>
        <SideNav groups={visibleNavigation} currentPath={currentPath} onNavigate={closeOverlays} />
      </aside>
      <div className="app-shell__main">
        <header className="topbar">
          <div className="topbar__left">
            <IconButton className="mobile-menu-button" icon="menu" label={t("nav.openMenu")} onClick={() => setMenuOpen(true)} />
            <div className="breadcrumb">
              <span>{crumb.group}</span>
              <Icon name="chevronRight" size={14} />
              <strong>{crumb.page}</strong>
            </div>
          </div>
          <div className="topbar__actions">
            <DemoModeBanner />
            <OfflineIndicator />
            <button type="button" className="global-search-trigger" onClick={openSearch}>
              <Icon name="search" size={17} />
              <span>{t("header.search")}</span>
              <kbd>Ctrl K</kbd>
            </button>
            <div className="topbar__divider" />
            {tenants.length > 1 && (
              <div className="topbar__select">
                <Icon name="building" size={16} />
                <select aria-label={t("header.tenant")} value={selectedTenant.id} onChange={(event) => selectTenant(event.target.value)}>
                  {tenants.map((tenant) => (
                    <option key={tenant.id} value={tenant.id}>
                      {tenant.name}
                    </option>
                  ))}
                </select>
                <Icon name="chevronDown" size={14} />
              </div>
            )}
            <div className="accent-menu-wrap">
              <IconButton icon="sparkles" label={t("header.accent")} onClick={() => setAccentOpen((open) => !open)} />
              {accentOpen && (
                <div className="accent-menu" role="menu" aria-label={t("header.accent")}>
                  <span className="accent-menu__label">{t("settings.accent")}</span>
                  <AccentSwatches />
                </div>
              )}
            </div>
            <IconButton icon={theme === "light" ? "moon" : "sun"} label={t("header.theme")} onClick={toggleTheme} />
            <button type="button" className="language-button" aria-label={t("header.language")} onClick={cycleLocale}>
              {localeMeta[locale].nativeLabel}
            </button>
            <NavLink
              to="/app/notifications"
              className="notification-button"
              aria-label={`${t("header.notifications")}${unreadCount ? `, ${unreadCount} ${t("notification.unread")}` : ""}`}
            >
              <Icon name="bell" size={18} />
              {unreadCount > 0 && <span>{unreadCount}</span>}
            </NavLink>
            <div className="profile-wrap">
              <button type="button" className="profile-avatar-button" aria-label={t("header.profile")} onClick={() => setProfileOpen((value) => !value)}>
                <Avatar name={session?.user.displayName ?? "User"} size="sm" tone="purple" />
              </button>
              {profileOpen && (
                <>
                  <button className="menu-backdrop" type="button" aria-label={t("nav.closeMenu")} onClick={() => setProfileOpen(false)} />
                  <div className="profile-menu">
                    <div className="profile-menu__identity">
                      <Avatar name={session?.user.displayName ?? "User"} size="md" tone="purple" />
                      <div>
                        <strong>{session?.user.displayName}</strong>
                        <span>{session?.user.email}</span>
                      </div>
                    </div>
                    <div className="divider" />
                    <NavLink to="/app/settings" onClick={() => setProfileOpen(false)}>
                      <Icon name="settings" size={16} />
                      {t("nav.settings")}
                    </NavLink>
                    <button type="button" onClick={() => void handleLogout()}>
                      <Icon name="logout" size={16} />
                      {t("nav.signOut")}
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        </header>
        <main className="main-content">
          <Outlet />
        </main>
        <footer className="app-footer">
          <span>© 2026 {runtimeConfig.appName}</span>
          <span>{t("footer.version")}</span>
        </footer>
      </div>
      <Drawer open={menuOpen} title={t("nav.workspace")} onClose={() => setMenuOpen(false)}>
        <div className="mobilenav__identity">
          <Avatar name={session?.user.displayName ?? "User"} size="md" tone="purple" />
          <div>
            <strong>{session?.user.displayName}</strong>
            <span>{selectedTenant.name}</span>
          </div>
        </div>
        <MobileNav groups={visibleNavigation} currentPath={currentPath} onNavigate={() => setMenuOpen(false)} />
      </Drawer>

      <Drawer open={searchOpen} title={t("header.search")} onClose={() => setSearchOpen(false)}>
        <div className="global-search">
          <div className="search-box search-box--large">
            <Icon name="search" size={18} />
            <input
              autoFocus
              value={search}
              aria-label={t("header.searchHint")}
              placeholder={t("header.searchHint")}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          {entityResults.length > 0 && (
            <div className="global-search__results">
              {entityResults.map((entity) => (
                <button
                  key={`${entity.kind}-${entity.id}`}
                  type="button"
                  onClick={() => {
                    setSearchOpen(false);
                    navigate(entity.route);
                  }}
                >
                  <span className="global-search__result-icon">
                    <Icon name={entity.kind === "device" ? "cpu" : "checkSquare"} size={16} />
                  </span>
                  <span>
                    <strong>{entity.title}</strong>
                    <small>{entity.kind === "device" ? t("search.devices") : t("search.workOrders")}{entity.subtitle ? ` · ${entity.subtitle}` : ""}</small>
                  </span>
                  <Icon name="arrowRight" size={15} />
                </button>
              ))}
            </div>
          )}
          {search && results.length === 0 && entityResults.length === 0 && !searching && (
            <div className="global-search__empty">
              <Icon name="search" size={22} />
              <strong>{t("common.noResults")}</strong>
              <span>{t("header.searchEmptyHint")}</span>
            </div>
          )}
          {results.length > 0 && (
            <div className="global-search__results">
              {results.map((page) => (
                <button
                  key={page.id}
                  type="button"
                  onClick={() => {
                    setSearchOpen(false);
                    navigate(page.route);
                  }}
                >
                  <span className="global-search__result-icon">
                    <Icon name={page.icon} size={16} />
                  </span>
                  <span>
                    <strong>{page.title}</strong>
                    <small>{page.group}</small>
                  </span>
                  <Icon name="arrowRight" size={15} />
                </button>
              ))}
            </div>
          )}
        </div>
      </Drawer>
    </div>
  );
}

/** Persian/Arabic-insensitive matching for the page search (normalizes ی/ی, ک/ك, ZWNJ). */
function normalizeText(value: string): string {
  return value
    .toLowerCase()
    .replace(/\u200c/g, "")
    .replace(/ي/g, "ی")
    .replace(/ك/g, "ک")
    .trim();
}

function currentRoute(pathname: string): string {
  return pathname.replace(/\/+$/, "");
}

const filterNavigationItems = (
  items: NavigationItem[] | undefined,
  has: (permission: string) => boolean,
  isEnabled: (flag: string) => boolean,
): NavigationItem[] =>
  (items ?? [])
    .map((item) => ({ ...item, children: filterNavigationItems(item.children, has, isEnabled) }))
    .filter((item) => {
      if (item.permission && !has(item.permission)) return false;
      if (item.featureFlag && !isEnabled(item.featureFlag)) return false;
      return Boolean(item.route) || Boolean(item.children?.length);
    })
    .map((item) => ({ ...item, children: item.children?.length ? item.children : undefined }));

export function ProtectedRoute({ children }: { children: ReactNode }): JSX.Element {
  const { isAuthenticated, isLoading } = useAuth();
  if (isLoading)
    return (
      <div className="full-page-state">
        <span className="spinner" />
      </div>
    );
  if (!isAuthenticated) return <NavigateToLogin />;
  return <>{children}</>;
}

function NavigateToLogin(): JSX.Element {
  return <Navigate to="/login" replace />;
}
