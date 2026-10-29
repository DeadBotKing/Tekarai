import { BrowserRouter } from "react-router-dom";
import { AppProviders } from "./providers/AppProviders";
import { AppRouter } from "./router/AppRouter";
import "../styles/fonts.css";
import "../styles/tokens.css";
import "../styles/globals.css";
import "../styles/globalsContinuation.css";
import "../styles/maintenanceAttachments.css";
import "../styles/pmCalendar.css";
import "../styles/maintenanceCost.css";
import "../styles/dashboardViews.css";
import "../styles/chat.css";
import "../styles/uiPolish.css";
import "../styles/procurement.css";
import "../styles/organization.css";
import "../styles/fieldOps.css";
import "../styles/sidenav.css";
import "../styles/rtl.css";
import "../styles/density.css";
import "../styles/cmmsPolish.css";
import "../styles/userGuide.css";
import "../styles/shellPolish.css";
import "../styles/dashboardOnboarding.css";
import "../styles/pageCanvas.css";
import "../styles/metricsPolish.css";
import "../styles/dashboardHierarchy.css";
import "../styles/contextStickers.css";
import "../styles/warmHome.css";

export function App(): JSX.Element {
  return <BrowserRouter><AppProviders><AppRouter /></AppProviders></BrowserRouter>;
}
