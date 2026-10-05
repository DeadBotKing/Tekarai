import { faText as t } from "../../core/localization/i18n";

/**
 * Shown while a route chunk is in flight.
 *
 * Deliberately quiet: a spinner that appears for 80 ms on a fast connection
 * reads as a glitch. The skeleton keeps the page frame stable so the layout
 * does not jump when the real page arrives.
 */
export function RouteFallback(): JSX.Element {
  return (
    <div className="route-fallback" role="status" aria-live="polite" aria-busy="true">
      <div className="route-fallback__bar" />
      <span className="route-fallback__label">{t("common.loading")}</span>
    </div>
  );
}
