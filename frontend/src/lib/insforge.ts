import { createClient } from "@insforge/sdk";

// Auth is handled by Clerk (see lib/authToken.ts). This client is only used for the
// InsForge-hosted waitlist table via the anon key.
export const insforge = createClient({
  baseUrl: import.meta.env.VITE_INSFORGE_URL,
  anonKey: import.meta.env.VITE_INSFORGE_ANON_KEY,
});
