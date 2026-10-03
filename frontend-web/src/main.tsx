import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";
import { registerServiceWorker } from "./core/offline/registerServiceWorker";
import { prefetchDecoder } from "./features/scanning/codeScanner";

const root = document.getElementById("root");
if (!root) throw new Error("Tekarai root element is missing");

createRoot(root).render(<StrictMode><App /></StrictMode>);

// Offline shell: production only, and never fatal — see registerServiceWorker.
registerServiceWorker();

// Warm the barcode decoder chunk while there is still a connection, so the
// first scan in a signal-free basement does not need the network.
prefetchDecoder();
