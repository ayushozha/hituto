import { ClerkProvider } from "@clerk/react";
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { AuthProvider } from "./context/AuthContext";
import "./index.css";

const AUTH_DISABLED = import.meta.env.VITE_AUTH_DISABLED === "1";
const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

if (!AUTH_DISABLED && !PUBLISHABLE_KEY) {
  throw new Error("Missing VITE_CLERK_PUBLISHABLE_KEY");
}

const tree = (
  <AuthProvider>
    <App />
  </AuthProvider>
);

// Always mount ClerkProvider when a key exists so landing/dashboard Clerk UI
// components do not crash. AuthProvider still short-circuits to a synthetic
// "dev" user when VITE_AUTH_DISABLED=1.
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {PUBLISHABLE_KEY ? (
      <ClerkProvider publishableKey={PUBLISHABLE_KEY} afterSignOutUrl="/">
        {tree}
      </ClerkProvider>
    ) : (
      tree
    )}
  </React.StrictMode>,
);
