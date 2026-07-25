/** Hash-based SPA routes (no router library). */

export type AuthMode = "login" | "signup";

export type AppRoute =
  | { kind: "landing" }
  | { kind: "auth"; mode: AuthMode }
  | { kind: "pricing" }
  | { kind: "waitlist" }
  | { kind: "dashboard" }
  | { kind: "billing" }
  | { kind: "reports" }
  | { kind: "reportNew" }
  | { kind: "report"; reportId: string }
  | { kind: "reportInvite"; token: string }
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
  if (path === "reports") return { kind: "reports" };
  if (path === "reports/new") return { kind: "reportNew" };

  const reportInviteMatch = path.match(/^report-invite\/([A-Za-z0-9_-]+)$/);
  if (reportInviteMatch) return { kind: "reportInvite", token: reportInviteMatch[1] };

  const reportMatch = path.match(/^reports\/([^/]+)$/);
  if (reportMatch) return { kind: "report", reportId: reportMatch[1] };

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
    case "reports":
      return "#reports";
    case "reportNew":
      return "#reports/new";
    case "report":
      return `#reports/${route.reportId}`;
    case "reportInvite":
      return `#report-invite/${route.token}`;
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

export function isAuthRequiredRoute(route: AppRoute): boolean {
  return (
    isDashboardRoute(route) ||
    route.kind === "reports" ||
    route.kind === "reportNew" ||
    route.kind === "report" ||
    route.kind === "reportInvite"
  );
}

/** @deprecated Prefer isDashboardRoute */
export const isStudioRoute = isDashboardRoute;

const RETURN_KEY = "hituto_return_hash";
let hashNavigationBlocker: (() => boolean) | null = null;

export function setHashNavigationBlocker(blocker: () => boolean): () => void {
  hashNavigationBlocker = blocker;
  return () => {
    if (hashNavigationBlocker === blocker) hashNavigationBlocker = null;
  };
}

export function allowHashNavigation(): boolean {
  return hashNavigationBlocker?.() ?? true;
}

/** Remember where the user was before sign-in (course/lesson deep links). */
export function saveReturnHash(hash: string): void {
  const route = parseHash(hash);
  // Only restore dashboard deep links after auth — never landing section anchors.
  if (isAuthRequiredRoute(route)) {
    sessionStorage.setItem(RETURN_KEY, hashFor(route));
  }
}

export function consumeReturnHash(): string {
  const saved = sessionStorage.getItem(RETURN_KEY);
  sessionStorage.removeItem(RETURN_KEY);
  if (!saved) return hashFor({ kind: "dashboard" });
  const route = parseHash(saved);
  return isAuthRequiredRoute(route) ? hashFor(route) : hashFor({ kind: "dashboard" });
}

export function discardReturnHash(): void {
  sessionStorage.removeItem(RETURN_KEY);
}
