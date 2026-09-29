import { BrowserRouter } from "react-router-dom";
import { AppProviders } from "./providers/AppProviders";
import { AppRouter } from "./router/AppRouter";
import "../styles/fonts.css";
import "../styles/tokens.css";
import "../styles/globals.css";
import "../styles/maintenanceAttachments.css";
import "../styles/pmCalendar.css";
import "../styles/maintenanceCost.css";
import "../styles/chat.css";
import "../styles/uiPolish.css";
import "../styles/procurement.css";

export function App(): JSX.Element {
  return <BrowserRouter><AppProviders><AppRouter /></AppProviders></BrowserRouter>;
}
