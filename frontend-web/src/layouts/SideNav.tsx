import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import type { NavigationItem } from "../app/configuration/navigation";
import { useLocalization } from "../core/localization/localizationContext";
import { Icon, type IconName } from "../shared/components/Icon";

/**
 * The navigation sidebar, drawn after MaintainX: a light, friendly rail on
 * the start edge (the right, in Persian) — small-caps section labels, one
 * pill-highlighted item for the current page, sub-menus that expand in
 * place. Every page stays two clicks away: section → item, with parents
 * pre-opening to reveal the active child.
 */

const routeOf = (item: NavigationItem): string =>
  item.route ?? item.children?.find((child) => child.route)?.route ?? "/app/dashboard";

const isActivePath = (path: string, route: string): boolean => {
  if (route === "/app/dashboard") return path === route;
  return path === route || path.startsWith(`${route}/`);
};

interface SideNavProps {
  groups: NavigationItem[];
  currentPath: string;
  onNavigate?: () => void;
}

export function SideNav({ groups, currentPath, onNavigate }: SideNavProps): JSX.Element {
  const { t } = useLocalization();
  return (
    <nav className="sidenav__nav" aria-label={t("nav.workspace")}>
      {groups.map((group) => (
        <div className="sidenav__group" key={group.id}>
          <div className="sidenav__group-label">{t(group.label)}</div>
          {(group.children ?? []).map((item) => (
            <SideItem key={item.id} item={item} currentPath={currentPath} onNavigate={onNavigate} />
          ))}
        </div>
      ))}
    </nav>
  );
}

function SideItem({
  item,
  currentPath,
  onNavigate,
}: {
  item: NavigationItem;
  currentPath: string;
  onNavigate?: () => void;
}): JSX.Element {
  const { t } = useLocalization();
  const children = item.children?.filter((child) => child.route) ?? [];
  const route = routeOf(item);
  const active = isActivePath(currentPath, route);

  if (children.length === 0) {
    return (
      <NavLink
        to={route}
        className={`side-item ${active ? "is-active" : ""}`}
        onClick={onNavigate}
      >
        <Icon name={item.icon as IconName} size={16} />
        <span>{t(item.label)}</span>
        {item.badge ? <span className="side-item__badge">{item.badge}</span> : null}
      </NavLink>
    );
  }

  return <SideParent item={item} children={children} currentPath={currentPath} onNavigate={onNavigate} />;
}

function SideParent({
  item,
  children,
  currentPath,
  onNavigate,
}: {
  item: NavigationItem;
  children: NavigationItem[];
  currentPath: string;
  onNavigate?: () => void;
}): JSX.Element {
  const { t } = useLocalization();
  const childActive = children.some((child) => isActivePath(currentPath, child.route ?? ""));
  const [open, setOpen] = useState(childActive);
  const childActiveRef = childActive;
  useEffect(() => {
    if (childActiveRef) setOpen(true);
  }, [childActiveRef]);

  return (
    <div className="side-item-group">
      <button
        type="button"
        className={`side-item side-item--parent ${childActive ? "is-active" : ""} ${open ? "is-open" : ""}`}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <Icon name={item.icon as IconName} size={16} />
        <span>{t(item.label)}</span>
        <Icon name="chevronDown" size={12} className="side-item__chevron" />
      </button>
      {open &&
        children.map((child) => {
          const active = isActivePath(currentPath, child.route ?? "");
          return (
            <NavLink
              key={child.id}
              to={child.route ?? "/app/dashboard"}
              className={`side-item side-item--sub ${active ? "is-active" : ""}`}
              onClick={onNavigate}
            >
              <Icon name={child.icon as IconName} size={15} />
              <span>{t(child.label)}</span>
            </NavLink>
          );
        })}
    </div>
  );
}

/**
 * The same tree for the mobile drawer: sections as native disclosure
 * widgets, the active section pre-opened — a plain list a phone can scroll.
 */
export function MobileNav({ groups, currentPath, onNavigate }: SideNavProps): JSX.Element {
  const { t } = useLocalization();
  return (
    <nav className="mobilenav" aria-label={t("nav.workspace")}>
      {groups.map((group) => {
        const children = group.children ?? [];
        const childActive = children.some((child) => isActivePath(currentPath, routeOf(child)));
        const directs = children.filter((child) => child.route);
        const submenus = children.filter((child) => !child.route && child.children?.length);
        return (
          <details className="mobilenav__group" key={group.id} open={childActive || undefined}>
            <summary className="mobilenav__group-label">
              <Icon name={group.icon as IconName} size={16} />
              <span>{t(group.label)}</span>
              <Icon name="chevronDown" size={13} className="mobilenav__chevron" />
            </summary>
            <div className="mobilenav__group-body">
              {directs.map((item) => (
                <MobileLink key={item.id} item={item} currentPath={currentPath} onNavigate={onNavigate} />
              ))}
              {submenus.map((submenu) => (
                <div className="mobilenav__section" key={submenu.id}>
                  <span className="mobilenav__section-label">{t(submenu.label)}</span>
                  {(submenu.children ?? []).map((item) => (
                    <MobileLink key={item.id} item={item} currentPath={currentPath} onNavigate={onNavigate} />
                  ))}
                </div>
              ))}
            </div>
          </details>
        );
      })}
    </nav>
  );
}

function MobileLink({
  item,
  currentPath,
  onNavigate,
}: {
  item: NavigationItem;
  currentPath: string;
  onNavigate?: () => void;
}): JSX.Element {
  const { t } = useLocalization();
  const active = isActivePath(currentPath, item.route ?? "");
  return (
    <NavLink
      to={item.route ?? "/app/dashboard"}
      className={`mobilenav__item ${active ? "is-active" : ""}`}
      onClick={onNavigate}
    >
      <Icon name={item.icon as IconName} size={15} />
      <span>{t(item.label)}</span>
    </NavLink>
  );
}
