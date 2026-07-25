import { useAuth as useClerkAuth, useClerk, useUser } from "@clerk/react";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { getFreshToken, registerTokenGetter } from "../lib/authToken";

type AuthUser = {
  id: string;
  email?: string;
};

type AuthContextValue = {
  user: AuthUser | null;
  loading: boolean;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue>({
  user: null,
  loading: true,
  signOut: async () => {},
});

/** Local hacking: VITE_AUTH_DISABLED=1 skips Clerk and uses a synthetic "dev" user. */
const AUTH_DISABLED = import.meta.env.VITE_AUTH_DISABLED === "1";

function ClerkAuthProvider({ children }: { children: ReactNode }) {
  const { isLoaded, isSignedIn, userId, getToken } = useClerkAuth();
  const { user: clerkUser } = useUser();
  const { signOut: clerkSignOut } = useClerk();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!isLoaded) {
      setLoading(true);
      return;
    }

    if (!isSignedIn || !userId) {
      registerTokenGetter(null);
      setUser(null);
      setLoading(false);
      return;
    }

    // Clerk's getToken() caches internally and refetches only near expiry, so the request
    // layer can call it per request for an always-live token. Prime the cache once here.
    registerTokenGetter(() => getToken());
    setUser({ id: userId, email: clerkUser?.primaryEmailAddress?.emailAddress });
    void getFreshToken();
    setLoading(false);
  }, [isLoaded, isSignedIn, userId, getToken, clerkUser]);

  async function signOut() {
    await clerkSignOut();
    registerTokenGetter(null);
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, loading, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

function DevAuthProvider({ children }: { children: ReactNode }) {
  useEffect(() => {
    registerTokenGetter(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user: { id: "dev", email: "dev@local" },
        loading: false,
        signOut: async () => {},
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function AuthProvider({ children }: { children: ReactNode }) {
  // Clerk hooks must only run under <ClerkProvider>. When auth is disabled we skip
  // Clerk entirely so the app boots without a publishable key.
  if (AUTH_DISABLED) {
    return <DevAuthProvider>{children}</DevAuthProvider>;
  }
  return <ClerkAuthProvider>{children}</ClerkAuthProvider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
