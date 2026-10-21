import { runtimeConfig } from "../../app/configuration/runtimeConfig";
import { useLocalization } from "../../core/localization/localizationContext";

/**
 * A permanent marker that the data on screen is fabricated.
 *
 * The short label remains visible in compact headers; the explanatory detail
 * is shown when there is room and kept in the accessible name/title always.
 */
export function DemoModeBanner(): JSX.Element | null {
  const { t } = useLocalization();
  if (!runtimeConfig.demoMode) return null;

  const label = t("header.demo");
  const detail = t("demo.banner.detail");
  const accessibleText = `${label} — ${detail}`;

  return (
    <div
      className="demo-banner"
      role="status"
      aria-label={accessibleText}
      title={accessibleText}
    >
      <span className="demo-banner__dot" aria-hidden="true" />
      <span className="demo-banner__label">{label}</span>
      <span className="demo-banner__detail">{detail}</span>
    </div>
  );
}
