import { useEffect, useId, useState } from "react";
import { NavLink } from "react-router-dom";
import type { NavigationItem } from "../app/configuration/navigation";
import { useLocalization } from "../core/localization/localizationContext";
import { Icon } from "../shared/components/Icon";

interface SideNavProps {
  groups: NavigationItem[];
  currentPath: string;
  onNavigate?: () => void;
}

const isActivePath = (path: string, item: NavigationItem): boolean => {
  if (!item.route) return false;
  const route = item.route;
  if (item.exact || route === "/app/dashboard") return path === route;
  return path === route || path.startsWith(`${route}/`);
};

const isDirect = (group: NavigationItem): boolean =>
  ["workspace", "records", "communication"].includes(group.id) &&
  group.children?.length === 1 && Boolean(group.children[0].route);

export function SideNav(props: SideNavProps): JSX.Element {
  return <GroupedNavigation {...props} mobile={false} />;
}

export function MobileNav(props: SideNavProps): JSX.Element {
  return <GroupedNavigation {...props} mobile />;
}

function GroupedNavigation({ groups, currentPath, onNavigate, mobile }: SideNavProps & { mobile: boolean }): JSX.Element {
  const { t } = useLocalization();
  const instance = useId();
  const sections = groups.filter((group) => !isDirect(group));
  const activeGroup = sections.find((group) => group.children?.some((item) => isActivePath(currentPath, item)))?.id ?? null;
  const [openGroup, setOpenGroup] = useState<string | null>(activeGroup);

  useEffect(() => {
    setOpenGroup(activeGroup);
  }, [activeGroup, currentPath]);

  const renderLink = (item: NavigationItem, nested: boolean): JSX.Element => (
    <NavLink
      key={item.id}
      to={item.route ?? "/app/dashboard"}
      end={item.exact}
      className={`side-item ${nested ? "side-item--sub" : "nav-quick-link"} ${isActivePath(currentPath, item) ? "is-active" : ""}`}
      onClick={onNavigate}
    >
      <Icon name={item.icon} size={17} />
      <span>{item.displayLabel ?? t(item.label)}</span>
      {item.badge ? <span className="side-item__badge">{item.badge}</span> : null}
    </NavLink>
  );

  return (
    <nav className={`${mobile ? "mobilenav" : "sidenav__nav"} grouped-nav`} aria-label={t("nav.workspace")}>
      <div className="nav-quick-links">
        {groups.filter(isDirect).map((group) => renderLink(group.children![0], false))}
      </div>
      <div className="nav-sections">
        {sections.map((group) => {
          const children = group.children ?? [];
          const open = openGroup === group.id;
          const active = activeGroup === group.id;
          const panelId = `navigation-${instance}-${group.id}`;
          const triggerId = `${panelId}-trigger`;
          return (
            <section className={`nav-section ${open ? "is-open" : ""} ${active ? "is-active" : ""}`} key={group.id}>
              <button
                id={triggerId}
                type="button"
                className={`nav-section__trigger ${active ? "is-active" : ""}`}
                aria-expanded={open}
                aria-controls={panelId}
                onClick={() => setOpenGroup(open ? null : group.id)}
              >
                <span className="nav-section__icon"><Icon name={group.icon} size={18} /></span>
                <span className="nav-section__title">{group.displayLabel ?? t(group.label)}</span>
                <span className="nav-section__count" aria-hidden="true">{children.length}</span>
                <Icon name="chevronDown" size={13} className="nav-section__chevron" />
              </button>
              {open && (
                <div id={panelId} role="region" aria-labelledby={triggerId} className="nav-section__body">
                  {children.map((item) => renderLink(item, true))}
                </div>
              )}
            </section>
          );
        })}
      </div>
    </nav>
  );
}
