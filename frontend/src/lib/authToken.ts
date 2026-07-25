/**
 * Access-token registry bridging Clerk's `getToken()` to the plain `fetch` layer in `api.ts`.
 *
 * Clerk session JWTs expire after ~60s and auto-rotate, so a single cached string goes stale
 * fast. `AuthProvider` registers Clerk's `getToken` here; request builders call `getFreshToken()`
 * (Clerk caches internally, so this is cheap) to always attach a live token. The synchronous
 * `getCachedToken()` exists only for URL builders (iframe `src`, WebSocket URLs) that cannot
 * await — it returns the last value `getFreshToken()` fetched, kept warm by ongoing requests.
 */

type TokenGetter = () => Promise<string | null>;

let getter: TokenGetter | null = null;
let cachedToken: string | null = null;

/** Called by AuthProvider: pass Clerk's `getToken` when signed in, `null` when signed out. */
export function registerTokenGetter(fn: TokenGetter | null): void {
  getter = fn;
  if (!fn) cachedToken = null;
}

/** Fetch a live token (Clerk-cached; refetches only near expiry). Also refreshes the cache. */
export async function getFreshToken(): Promise<string | null> {
  if (!getter) return cachedToken;
  cachedToken = await getter();
  return cachedToken;
}

/** Last token seen by `getFreshToken()`. For sync URL builders that cannot await. */
export function getCachedToken(): string | null {
  return cachedToken;
}
