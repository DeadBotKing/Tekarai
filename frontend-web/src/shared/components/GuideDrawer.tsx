import { Drawer } from "./overlays";
import { Icon, type IconName } from "./Icon";
import { useLocalization } from "../../core/localization/localizationContext";
import type { TranslationKey } from "../../core/localization/i18n";

/** App-shell event used by contextual help links outside the top bar. */
export const GUIDE_OPEN_EVENT = "tekarai:open-guide";

export interface GuidePage {
  id: string;
  title: string;
  group: string;
  route: string;
  icon: IconName;
}

interface GuideDrawerProps {
  open: boolean;
  currentPath: string;
  currentPage: string;
  pages: GuidePage[];
  onClose: () => void;
  onNavigate: (route: string) => void;
}

type GuideContext = "workOrders" | "assets" | "maintenance" | "projects" | "generic";

const quickLinkDefinitions: Array<{ id: string; hint: TranslationKey }> = [
  { id: "maintenanceWorkOrders", hint: "help.quick.workOrders" },
  { id: "maintenanceDevices", hint: "help.quick.assets" },
  { id: "maintenanceDashboardDaily", hint: "help.quick.maintenance" },
  { id: "projects", hint: "help.quick.projects" },
  { id: "documents", hint: "help.quick.documents" },
];

function contextForPath(path: string): GuideContext {
  if (path.includes("/maintenance/work-orders")) return "workOrders";
  if (path.includes("/maintenance/devices") || path.includes("/maintenance/registry")) return "assets";
  if (path.includes("/maintenance/")) return "maintenance";
  if (path.includes("/projects") || path.includes("/tasks")) return "projects";
  return "generic";
}

export function GuideDrawer({
  open,
  currentPath,
  currentPage,
  pages,
  onClose,
  onNavigate,
}: GuideDrawerProps): JSX.Element {
  const { t } = useLocalization();
  const context = contextForPath(currentPath);
  const quickLinks = quickLinkDefinitions
    .map((definition) => ({
      ...definition,
      page: pages.find((page) => page.id === definition.id),
    }))
    .filter((item) => Boolean(item.page));

  const steps: TranslationKey[] = context === "workOrders"
    ? ["help.step.workOrders.1", "help.step.workOrders.2", "help.step.workOrders.3"]
    : context === "assets"
      ? ["help.step.assets.1", "help.step.assets.2", "help.step.assets.3"]
      : context === "maintenance"
        ? ["help.step.maintenance.1", "help.step.maintenance.2", "help.step.maintenance.3"]
        : context === "projects"
          ? ["help.step.projects.1", "help.step.projects.2", "help.step.projects.3"]
          : ["help.step.generic.1", "help.step.generic.2", "help.step.generic.3"];

  return (
    <Drawer open={open} title={t("help.title")} onClose={onClose}>
      <div className="guided-help">
        <section className="guided-help__intro">
          <span className="guided-help__eyebrow">
            <Icon name="book" size={14} />
            {t("help.eyebrow")}
          </span>
          <h3>{currentPage}</h3>
          <p>{t(`help.context.${context}` as TranslationKey)}</p>
        </section>

        <section className="guided-help__section" aria-labelledby="guided-help-steps-title">
          <h3 id="guided-help-steps-title">
            <Icon name="checkCircle" size={17} />
            {t("help.stepsTitle")}
          </h3>
          <ol className="guided-help__steps">
            {steps.map((step) => <li key={step}>{t(step)}</li>)}
          </ol>
        </section>

        {quickLinks.length > 0 && (
          <section className="guided-help__section" aria-labelledby="guided-help-links-title">
            <h3 id="guided-help-links-title">
              <Icon name="grid" size={17} />
              {t("help.quickLinks")}
            </h3>
            <div className="guided-help__links">
              {quickLinks.map(({ id, hint, page }) => page && (
                <button
                  key={id}
                  type="button"
                  className="guided-help__link"
                  onClick={() => onNavigate(page.route)}
                >
                  <span className="guided-help__link-icon"><Icon name={page.icon} size={16} /></span>
                  <span className="guided-help__link-copy">
                    <strong>{page.title}</strong>
                    <small>{t(hint)}</small>
                  </span>
                  <Icon name="arrowRight" size={15} />
                </button>
              ))}
            </div>
          </section>
        )}

        <div className="guided-help__search-hint">
          <span className="guided-help__search-icon"><Icon name="search" size={16} /></span>
          <span>{t("help.searchHint")}</span>
          <kbd>Ctrl</kbd><kbd>K</kbd>
        </div>
      </div>
    </Drawer>
  );
}
