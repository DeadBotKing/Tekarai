import { useEffect, useRef, useState } from "react";
import { NavLink } from "react-router-dom";
import type { NavigationItem } from "../app/configuration/navigation";
import { useLocalization } from "../core/localization/localizationContext";
import { Icon, type IconName } from "../shared/components/Icon";

/**
 * The navigation bar, drawn after eMaint's Persian pattern: one dark strip
 * at the top of the screen, every section a dropdown, every page two clicks
 * away at most. Groups with a single page become plain links; groups with
 * more open a panel — direct pages first, then each sub-menu as a titled
 * section. Nothing hides behind hover-only behaviour: a click opens, a
 * click elsewhere closes, Escape closes, and the open menu follows the
 * pointer between triggers like a desktop application's menubar.
 */

const routeOf = (item: NavigationItem): string =>
  item.route ?? item.children?.find((child) => child.route)?.route ?? "/app/dashboard";

const isActivePath = (path: string, route: string): boolean => {
  if (route === "/app/dashboard") return path === route;
  return path === route || path.startsWith(`${route}/`);
};

interface MenuBarProps {
  groups: NavigationItem[];
  currentPath: string;
  onNavigate?: () => void;
}

export function MenuBar({ groups, currentPath }: MenuBarProps): JSX.Element {
  const { t } = useLocalization();
  const [openId, setOpenId] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!openId) return;
    const onPointerDown = (event: PointerEvent): void => {
      if (!rootRef.current?.contains(event.target as Node)) setOpenId(null);
    };
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") setOpenId(null);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [openId]);

  return (
    <nav className="menubar" ref={rootRef} aria-label={t("nav.workspace")}>
      {groups.map((group) => {
        const children = group.children ?? [];
        const childActive = children.some((child) => isActivePath(currentPath, routeOf(child)));
        // A section that is exactly one page is a link, not a dropdown —
        // a dropdown that opens to reveal a single item is a lie.
        if (children.length === 1 && !children[0].children) {
          const only = children[0];
          return (
            <NavLink
              key={group.id}
              to={routeOf(only)}
              className={`menubar__link ${childActive ? "is-active" : ""}`}
            >
              <Icon name={only.icon as IconName} size={15} />
              <span>{t(only.label)}</span>
            </NavLink>
          );
        }
        const open = openId === group.id;
        return (
          <div className="menubar__anchor" key={group.id}>
            <button
              type="button"
              className={`menubar__trigger ${open ? "is-open" : ""} ${childActive ? "is-active" : ""}`}
              aria-haspopup="menu"
              aria-expanded={open}
              onClick={() => setOpenId(open ? null : group.id)}
              // Classic menubar feel: once a menu is open, the pointer
              // glides between sections without another click.
              onMouseEnter={() => {
                if (openId && openId !== group.id) setOpenId(group.id);
              }}
            >
              <Icon name={group.icon as IconName} size={15} />
              <span>{t(group.label)}</span>
              <Icon name="chevronDown" size={12} className="menubar__chevron" />
            </button>
            {open && <MenuPanel group={group} currentPath={currentPath} onPick={() => setOpenId(null)} />}
          </div>
        );
      })}
    </nav>
  );
}

function MenuPanel({
  group,
  currentPath,
  onPick,
}: {
  group: NavigationItem;
  currentPath: string;
  onPick: () => void;
}): JSX.Element {
  const { t } = useLocalization();
  const children = group.children ?? [];
  const directs = children.filter((child) => child.route);
  const submenus = children.filter((child) => !child.route && child.children?.length);

  return (
    <div className="menubar__panel" role="menu" aria-label={t(group.label)}>
      {directs.map((item) => (
        <MenuLink key={item.id} item={item} currentPath={currentPath} onPick={onPick} />
      ))}
      {submenus.map((submenu) => (
        <div className="menubar__section" key={submenu.id}>
          <span className="menubar__section-label">{t(submenu.label)}</span>
          {(submenu.children ?? []).map((item) => (
            <MenuLink key={item.id} item={item} currentPath={currentPath} onPick={onPick} />
          ))}
        </div>
      ))}
    </div>
  );
}

function MenuLink({
  item,
  currentPath,
  onPick,
}: {
  item: NavigationItem;
  currentPath: string;
  onPick: () => void;
}): JSX.Element {
  const { t } = useLocalization();
  const active = isActivePath(currentPath, item.route ?? "");
  return (
    <NavLink
      to={item.route ?? "/app/dashboard"}
      role="menuitem"
      className={`menubar__item ${active ? "is-active" : ""}`}
      onClick={onPick}
    >
      <Icon name={item.icon as IconName} size={15} />
      <span>{t(item.label)}</span>
      {item.badge ? <span className="menubar__item-badge">{item.badge}</span> : null}
    </NavLink>
  );
}

/**
 * The same tree, drawn for the mobile drawer: sections as native disclosure
 * widgets, the active section pre-opened. No hover semantics, no nested
 * absolute positioning — a phone gets a plain list it can scroll.
 */
export function MobileNav({ groups, currentPath, onNavigate }: MenuBarProps): JSX.Element {
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
