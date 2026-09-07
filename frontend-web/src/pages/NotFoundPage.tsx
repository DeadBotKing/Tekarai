import { Link } from "react-router-dom";
import { useLocalization } from "../core/localization/localizationContext";
import { Button } from "../shared/components/primitives";
import { Icon } from "../shared/components/Icon";

export function NotFoundPage(): JSX.Element {
  const { t } = useLocalization();
  return <div className="full-page-state"><div className="not-found"><span className="not-found__icon"><Icon name="search" size={30} /></span><span className="eyebrow">404</span><h1>{t("error.notFoundTitle")}</h1><p>{t("error.notFoundBody")}</p><Link to="/app/dashboard"><Button variant="primary" icon="home">{t("error.backDashboard")}</Button></Link></div></div>;
}
