import { useEffect, useRef, useState } from "react";

import { CourseCard, CourseDetail, Lesson, Progress, deleteCourse, getCourse, getProfile, listCourses, subscribeProgress, updateCourse } from "./api";
import { useAuth } from "./context/AuthContext";
import { Dashboard, StatusFilter } from "./features/courses/Dashboard";
import { CreateCourseModal } from "./features/courses/CreateCourseModal";
import { OnboardingPage } from "./features/onboarding/OnboardingPage";
import { Landing } from "./features/landing/Landing";
import { AuthPage } from "./features/auth/AuthPage";
import { PricingPage } from "./features/marketing/PricingPage";
import { WaitlistPage } from "./features/marketing/WaitlistPage";
import { BillingPage } from "./features/billing/BillingPage";
import { Roadmap } from "./features/roadmap/Roadmap";
import { Viewer } from "./features/lesson/Viewer";
import { SharedLessonView } from "./features/lesson/SharedLessonView";
import { AppRoute, consumeReturnHash, hashFor, isDashboardRoute, parseHash, saveReturnHash } from "./routing";

/** Local demo: allow marketing landing even with the synthetic "dev" user. */
const AUTH_DISABLED = import.meta.env.VITE_AUTH_DISABLED === "1";

export default function App() {
  const { user, loading: authLoading } = useAuth();
  const [route, setRoute] = useState<AppRoute>(() => parseHash(window.location.hash));
  const [courses, setCourses] = useState<CourseCard[]>([]);
  const [creating, setCreating] = useState(false);
  const [viewingRoadmap, setViewingRoadmap] = useState<CourseCard | null>(null);
  const [viewing, setViewing] = useState<CourseCard | null>(null);
  const [activeLesson, setActiveLesson] = useState<Lesson | null>(null);
  const [deepLinkErr, setDeepLinkErr] = useState<string | null>(null);
  const [progress, setProgress] = useState<Record<string, Progress>>({});
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const coursesLoadSeq = useRef(0);
  const coursesAbortRef = useRef<AbortController | null>(null);
  const queryRef = useRef(query);
  const statusRef = useRef(status);
  queryRef.current = query;
  statusRef.current = status;

  // Learner-profile gate (specs/learner_profile): once per signed-in user, check whether
  // onboarding was completed; if not, dashboard routes redirect to #onboarding.
  const userKey = user?.id ?? null;
  const [profileGate, setProfileGate] = useState<{ user: string; onboarded: boolean } | null>(null);

  useEffect(() => {
    const sync = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);

  useEffect(() => {
    if (authLoading) return;
    if (route.kind === "auth" && user) {
      const next = consumeReturnHash();
      if (window.location.hash === next) {
        setRoute(parseHash(next));
      } else {
        window.location.hash = next;
      }
      return;
    }
    // Signed-in users belong in the dashboard, not on the marketing landing.
    // Skip when auth is disabled so local demos can still open `#` / landing.
    if (route.kind === "landing" && user && !AUTH_DISABLED) {
      const dashboardHash = hashFor({ kind: "dashboard" });
      if (window.location.hash === dashboardHash) {
        setRoute({ kind: "dashboard" });
      } else {
        window.location.hash = dashboardHash;
      }
      return;
    }
    if (isDashboardRoute(route) && !user) {
      saveReturnHash(window.location.hash);
      const authHash = hashFor({ kind: "auth", mode: "login" });
      // Setting the same hash does not fire hashchange — sync route explicitly.
      if (window.location.hash === authHash) {
        setRoute({ kind: "auth", mode: "login" });
      } else {
        window.location.hash = authHash;
      }
    }
  }, [authLoading, route, user]);

  useEffect(() => {
    if (authLoading || !user || !userKey || !isDashboardRoute(route)) return;
    if (profileGate?.user === userKey) return;
    let cancelled = false;
    getProfile()
      .then((p) => {
        if (!cancelled) setProfileGate({ user: userKey, onboarded: p.onboarded_at != null });
      })
      .catch(() => {
        // Fail open: a profile fetch error must never block the app.
        if (!cancelled) setProfileGate({ user: userKey, onboarded: true });
      });
    return () => {
      cancelled = true;
    };
  }, [authLoading, user, userKey, route.kind, profileGate]);

  const refresh = () => {
    coursesAbortRef.current?.abort();
    const controller = new AbortController();
    coursesAbortRef.current = controller;
    const seq = ++coursesLoadSeq.current;
    let timedOut = false;
    const timeout = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, 12_000);
    setLoadError(null);

    return listCourses(
      { q: queryRef.current, status: statusRef.current },
      { signal: controller.signal },
    )
      .then((nextCourses) => {
        if (seq !== coursesLoadSeq.current) return;
        setCourses(nextCourses);
        setLoadError(null);
      })
      .catch((err) => {
        if (seq !== coursesLoadSeq.current) return;
        // Superseded by a newer refresh — ignore intentional abort.
        if (err?.name === "AbortError" && !timedOut) return;
        console.error("failed to load courses:", err);
        setCourses([]);
        setLoadError(
          err?.name === "AbortError"
            ? "Course loading timed out. Check that the backend on :8077 is responding, then try again."
            : "Could not load courses. Check your session and backend connection, then try again.",
        );
      })
      .finally(() => {
        window.clearTimeout(timeout);
        if (seq === coursesLoadSeq.current) setLoading(false);
      });
  };

  useEffect(() => {
    if (!isDashboardRoute(route) || authLoading || !user) return;
    if (route.kind === "dashboard") {
      setLoading(true);
      const id = window.setTimeout(refresh, 150);
      return () => {
        window.clearTimeout(id);
        coursesAbortRef.current?.abort();
      };
    }
  }, [query, status, route.kind, authLoading, user]);

  useEffect(() => {
    if (!isDashboardRoute(route) || !user) return;
    const generating = courses.filter((c) => c.status === "generating");
    const unsubs = generating.map((c) =>
      subscribeProgress(c.id, (p) => {
        setProgress((prev) => ({ ...prev, [c.id]: p }));
        // 100 = generation finished; outline_review = plan parked for teacher review.
        if (p.pct >= 100 || p.stage === "outline_review") refresh();
      }),
    );
    // SSE events are fire-and-forget (no replay): a status flip that lands before the
    // EventSource connects would strand the card on "generating" — poll as a fallback.
    const poll = generating.length > 0 ? window.setInterval(refresh, 8000) : undefined;
    return () => {
      unsubs.forEach((u) => u());
      if (poll !== undefined) window.clearInterval(poll);
    };
  }, [courses.map((c) => c.id + c.status).join(","), route.kind, user]);

  // Deep-link: #dashboard/course/{courseId} or .../lesson/{lessonId}
  useEffect(() => {
    if (authLoading || !user) return;
    if (route.kind !== "course" && route.kind !== "lesson") {
      setDeepLinkErr(null);
      if (route.kind === "dashboard") {
        setViewingRoadmap(null);
        setViewing(null);
        setActiveLesson(null);
      }
      return;
    }

    let cancelled = false;
    setDeepLinkErr(null);

    (async () => {
      try {
        const detail = await getCourse(route.courseId);
        if (cancelled) return;
        const card: CourseCard = {
          id: detail.id,
          topic: detail.topic,
          title: detail.title,
          archetype: detail.archetype,
          status: detail.status,
          error: detail.error,
          lesson_count: detail.lesson_count,
          completed_count: detail.completed_count,
          tagline: detail.tagline,
          estimated_minutes: detail.estimated_minutes,
          updated_at: detail.updated_at,
          source: detail.source,
        };

        if (route.kind === "course") {
          setViewingRoadmap(card);
          setViewing(null);
          setActiveLesson(null);
          return;
        }

        const lesson = detail.lessons.find((l) => l.id === route.lessonId);
        if (!lesson) {
          setDeepLinkErr("Lesson not found");
          window.location.hash = hashFor({ kind: "course", courseId: route.courseId });
          return;
        }
        setViewing(card);
        setActiveLesson(lesson);
        setViewingRoadmap(null);
      } catch {
        if (!cancelled) {
          setDeepLinkErr("Course not found");
          window.location.hash = hashFor({ kind: "dashboard" });
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [route, authLoading, user]);

  function onCreatedFromSource(course: CourseDetail) {
    setCreating(false);
    setCourses((prev) => [course, ...prev]);
    window.location.hash = hashFor({ kind: "course", courseId: course.id });
  }

  async function onDelete(id: string) {
    await deleteCourse(id);
    setCourses((prev) => prev.filter((c) => c.id !== id));
  }

  async function onRename(id: string, title: string) {
    const updated = await updateCourse(id, { title });
    setCourses((prev) => prev.map((c) => (c.id === id ? { ...c, ...updated } : c)));
  }

  // Public share link: read-only, rendered regardless of auth state and before
  // any auth gate (isDashboardRoute is false for it, so the redirect effect skips it).
  if (route.kind === "shared") {
    return (
      <div className="h-screen">
        <SharedLessonView token={route.token} />
      </div>
    );
  }

  if (authLoading && isDashboardRoute(route)) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bone text-ink-soft">
        Loading...
      </div>
    );
  }

  if (route.kind === "auth") {
    return <AuthPage key={route.mode} initialMode={route.mode} />;
  }

  if (route.kind === "pricing") {
    return <PricingPage />;
  }

  if (route.kind === "waitlist") {
    return <WaitlistPage />;
  }

  if (route.kind === "billing") {
    if (!user) {
      return (
        <div className="flex min-h-screen items-center justify-center bg-bone text-ink-soft">
          Redirecting to sign in…
        </div>
      );
    }
    return <BillingPage />;
  }

  if (route.kind === "landing") {
    return (
      <Landing
        onStart={() => {
          window.location.hash = AUTH_DISABLED
            ? hashFor({ kind: "dashboard" })
            : hashFor({ kind: "auth", mode: "signup" });
        }}
        onSignIn={() => {
          window.location.hash = AUTH_DISABLED
            ? hashFor({ kind: "dashboard" })
            : hashFor({ kind: "auth", mode: "login" });
        }}
      />
    );
  }

  if (!user) {
    // Studio deep-link while signed out: effect above redirects to #auth.
    // Never return null — that paints a blank page during the race.
    return (
      <div className="flex min-h-screen items-center justify-center bg-bone text-ink-soft">
        Redirecting to sign in…
      </div>
    );
  }

  if (deepLinkErr) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bone text-coral">
        {deepLinkErr}
      </div>
    );
  }

  if (viewing && activeLesson) {
    return (
      <Viewer
        course={viewing}
        initialLesson={activeLesson}
        onBack={() => {
          window.location.hash = hashFor({ kind: "course", courseId: viewing.id });
        }}
        onCourseChanged={(card) => {
          setViewing(card);
          setCourses((prev) => prev.map((c) => (c.id === card.id ? card : c)));
        }}
      />
    );
  }

  if (viewingRoadmap) {
    return (
      <Roadmap
        course={viewingRoadmap}
        onBack={() => {
          window.location.hash = hashFor({ kind: "dashboard" });
        }}
        onLaunchLesson={(lesson) => {
          window.location.hash = hashFor({
            kind: "lesson",
            courseId: viewingRoadmap.id,
            lessonId: lesson.id,
          });
        }}
      />
    );
  }

  if (route.kind === "course" || route.kind === "lesson") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bone text-ink-soft">
        Loading course…
      </div>
    );
  }

  return (
    <>
      <Dashboard
        courses={courses}
        loading={loading}
        loadError={loadError}
        progress={progress}
        query={query}
        status={status}
        onQueryChange={setQuery}
        onStatusChange={setStatus}
        onRetry={() => {
          setLoading(true);
          void refresh();
        }}
        onCreate={() => setCreating(true)}
        onOpenRoadmap={(course) => {
          window.location.hash = hashFor({ kind: "course", courseId: course.id });
        }}
        onDelete={onDelete}
        onRename={onRename}
      />
      {creating && (
        <CreateCourseModal
          onClose={() => setCreating(false)}
          onCreated={(card) => {
            setCreating(false);
            setCourses((prev) => [card, ...prev]);
            window.location.hash = hashFor({ kind: "course", courseId: card.id });
          }}
          onCreatedFromSource={onCreatedFromSource}
        />
      )}
      {/* First-run learner-profile onboarding pops over the app; afterwards it only
          opens from the profile menu's "Learning style" action. */}
      {profileGate && !profileGate.onboarded && (
        <OnboardingPage
          mode="firstRun"
          onDone={() => setProfileGate((g) => (g ? { ...g, onboarded: true } : g))}
        />
      )}
    </>
  );
}
