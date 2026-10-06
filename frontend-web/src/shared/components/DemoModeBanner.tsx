import { runtimeConfig } from "../../app/configuration/runtimeConfig";

/**
 * A permanent marker that the data on screen is fabricated.
 *
 * Demo mode looks exactly like the real application: the same pages, the same
 * Persian labels, plausible device names and work orders. Someone shown a
 * screen has no way to tell whether a number came from the database or from a
 * fixture file, which is how a demo gets mistaken for a working deployment.
 * The marker is deliberately hard to miss and cannot be dismissed.
 */
export function DemoModeBanner(): JSX.Element | null {
  if (!runtimeConfig.demoMode) return null;
  return (
    <div className="demo-banner" role="status">
      <span className="demo-banner__dot" aria-hidden="true" />
      حالت نمایشی — داده‌ها ساختگی است و در هیچ پایگاه‌داده‌ای ذخیره نمی‌شود.
    </div>
  );
}
