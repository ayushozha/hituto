import { ClerkProvider } from "@clerk/react";
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { AUTH_DISABLED, AuthProvider } from "./context/AuthContext";
import "./index.css";

const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

if (!AUTH_DISABLED && !PUBLISHABLE_KEY) {
  throw new Error("Missing VITE_CLERK_PUBLISHABLE_KEY");
}

const app = (
  <React.StrictMode>
    <AuthProvider>
      <App />
    </AuthProvider>
  </React.StrictMode>
);

ReactDOM.createRoot(document.getElementById("root")!).render(
  AUTH_DISABLED ? (
    app
  ) : (
    <ClerkProvider publishableKey={PUBLISHABLE_KEY!} afterSignOutUrl="/">
      {app}
    </ClerkProvider>
  ),
);
