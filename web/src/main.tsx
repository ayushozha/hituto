import React from "react";
import ReactDOM from "react-dom/client";
import { RebootClientProvider } from "@reboot-dev/reboot-react";
import "katex/dist/katex.min.css";
import "./styles.css";
import App from "./App";

const rebootUrl =
  (import.meta.env.VITE_REBOOT_URL as string | undefined) ?? window.location.origin;

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <RebootClientProvider url={rebootUrl}>
      <App />
    </RebootClientProvider>
  </React.StrictMode>,
);

