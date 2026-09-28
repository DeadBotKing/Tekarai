import { useLocalization } from "../../core/localization/localizationContext";
import { ACCENTS, useTheme } from "../../core/theme/themeContext";
import { Icon } from "./Icon";

// سواچ‌های انتخاب رنگ اصلی سایت — در تاپ‌بار و صفحه‌ی تنظیمات مشترک است.
export function AccentSwatches(): JSX.Element {
  const { t } = useLocalization();
  const { accent, setAccent } = useTheme();
  return (
    <div className="accent-swatches" role="radiogroup" aria-label={t("header.accent")}>
      {ACCENTS.map((entry) => (
        <button
          key={entry.id}
          type="button"
          role="radio"
          aria-checked={accent === entry.id}
          className={`accent-swatch${accent === entry.id ? " is-active" : ""}`}
          style={{ background: entry.primary }}
          title={t(`accent.${entry.id}`)}
          aria-label={t(`accent.${entry.id}`)}
          onClick={() => setAccent(entry.id)}
        >
          {accent === entry.id ? <Icon name="check" size={13} /> : null}
        </button>
      ))}
    </div>
  );
}
