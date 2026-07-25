/** Hash-based SPA routes (no router library). */

export type AuthMode = "login" | "signup";

export type AppRoute =
  | { kind: "landing" }
  | { kind: "auth"; mode: AuthMode }
  | { kind: "pricing" }
  | { kind: "waitlist" }
  | { kind: "dashboard" }
  | { kind: "billing" }
  | { kind: "course"; courseId: string }
  | { kind: "lesson"; courseId: string; lessonId: string }
  | { kind: "shared"; token: string };

/** In-page landing anchors — must not be treated as app routes. */
export const LANDING_SECTION_IDS = new Set(["how-it-works", "study-kit", "lesson-preview"]);

export function parseHash(hash: string): AppRoute {
  const raw = (hash || "#").replace(/^#\/?/, "").replace(/\/$/, "");
  // OAuth providers sometimes append ?access_token=… onto the hash fragment.
  const path = raw.split("?")[0] ?? "";
  if (!path || LANDING_SECTION_IDS.has(path)) return { kind: "landing" };
  if (path === "auth/signup") return { kind: "auth", mode: "signup" };
  if (path === "auth" || path === "auth/login") return { kind: "auth", mode: "login" };
  if (path === "pricing") return { kind: "pricing" };
  if (path === "waitlist") return { kind: "waitlist" };
  // Accept legacy #studio bookmarks; canonical route is #dashboard.
  if (path === "dashboard" || path === "studio") return { kind: "dashboard" };
  if (path === "billing") return { kind: "billing" };

  // Public share link — read-only, never auth-gated (see isDashboardRoute).
  const sharedMatch = path.match(/^s\/([^/]+)$/);
  if (sharedMatch) {
    return { kind: "shared", token: sharedMatch[1] };
  }

  const lessonMatch = path.match(/^(?:dashboard|studio)\/course\/([^/]+)\/lesson\/([^/]+)$/);
  if (lessonMatch) {
    return { kind: "lesson", courseId: lessonMatch[1], lessonId: lessonMatch[2] };
  }

  const courseMatch = path.match(/^(?:dashboard|studio)\/course\/([^/]+)$/);
  if (courseMatch) {
    return { kind: "course", courseId: courseMatch[1] };
  }

  return { kind: "landing" };
}

export function hashFor(route: AppRoute): string {
  switch (route.kind) {
    case "landing":
      return "#";
    case "auth":
      return route.mode === "signup" ? "#auth/signup" : "#auth";
    case "pricing":
      return "#pricing";
    case "waitlist":
      return "#waitlist";
    case "dashboard":
      return "#dashboard";
    case "billing":
      return "#billing";
    case "course":
      return `#dashboard/course/${route.courseId}`;
    case "lesson":
      return `#dashboard/course/${route.courseId}/lesson/${route.lessonId}`;
    case "shared":
      return `#s/${route.token}`;
  }
}

export function isDashboardRoute(route: AppRoute): boolean {
  return (
    route.kind === "dashboard" ||
    route.kind === "billing" ||
    route.kind === "course" ||
    route.kind === "lesson"
  );
}

/** @deprecated Prefer isDashboardRoute */
export const isStudioRoute = isDashboardRoute;

const RETURN_KEY = "hituto_return_hash";

/** Remember where the user was before sign-in (course/lesson deep links). */
export function saveReturnHash(hash: string): void {
  const route = parseHash(hash);
  // Only restore dashboard deep links after auth — never landing section anchors.
  if (isDashboardRoute(route)) {
    sessionStorage.setItem(RETURN_KEY, hashFor(route));
  }
}

export function consumeReturnHash(): string {
  const saved = sessionStorage.getItem(RETURN_KEY);
  sessionStorage.removeItem(RETURN_KEY);
  if (!saved) return hashFor({ kind: "dashboard" });
  const route = parseHash(saved);
  return isDashboardRoute(route) ? hashFor(route) : hashFor({ kind: "dashboard" });
}
