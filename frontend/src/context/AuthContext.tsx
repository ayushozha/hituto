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
export const AUTH_DISABLED = import.meta.env.VITE_AUTH_DISABLED === "1";

export function AuthProvider({ children }: { children: ReactNode }) {
  return AUTH_DISABLED ? (
    <LocalAuthProvider>{children}</LocalAuthProvider>
  ) : (
    <ClerkAuthProvider>{children}</ClerkAuthProvider>
  );
}

function LocalAuthProvider({ children }: { children: ReactNode }) {
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

/** Kept separate so no Clerk hook runs when the app boots without ClerkProvider. */
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

export function useAuth() {
  return useContext(AuthContext);
}
