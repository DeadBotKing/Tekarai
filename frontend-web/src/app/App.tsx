import { BrowserRouter } from "react-router-dom";
import { AppProviders } from "./providers/AppProviders";
import { AppRouter } from "./router/AppRouter";
import "../styles/tokens.css";
import "../styles/globals.css";

export function App(): JSX.Element {
  return <BrowserRouter><AppProviders><AppRouter /></AppProviders></BrowserRouter>;
}
