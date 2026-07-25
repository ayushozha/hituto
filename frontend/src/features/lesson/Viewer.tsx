import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent, RefObject } from "react";

import {
  ArtifactA2UI,
  ArtifactReading,
  ArtifactVersion,
  CourseCard,
  CourseDetail,
  Lesson,
  completeLesson,
  createShareLink,
  generateLesson,
  getCourse,
  getHealth,
  getLessonArtifactA2UI,
  getLessonArtifactReading,
  getVideoGuide,
  lessonArtifactUrl,
  listVersions,
  refineCourse,
  revokeShareLink,
  saveLessonArtifact,
  sourceMediaUrl,
  subscribeProgress,
  patchA2UISection,
  patchHtmlSection,
  A2UI_SLASH_CATALOGUE,
  type Progress,
  type VideoGuide,
} from "../../api";
import A2UIRenderer, { type UiNode } from "../../components/A2UIRenderer";
import {
  AgentCursor,
  AgentProvider,
  FrameRelay,
  useAgentBridge,
  type PageSnapshot,
} from "@guidebridge/react";
import { agentBridgeWsUrl } from "../../api";
import { useAuth } from "../../context/AuthContext";
import VoiceInstructor from "../../components/VoiceInstructor";
import type { TutorTranscriptLine } from "../../components/VoiceInstructor";
import { Mascot } from "../../components/Mascot";
import {
  getDocumentHtml,
  setEditMode,
  subscribeCapsuleLearningEvents,
  subscribeElementSelected,
  type SelectedElement,
} from "../../lib/lessonBridge";
import {
  recordQuizResult,
  recordLearningEvent,
  useLessonLearningSession,
} from "../../lib/learningEvents";
import { GenerationTheater } from "./GenerationTheater";
import { ReadingLesson } from "./ReadingLesson";
import { VideoAgentActions } from "./VideoAgentActions";
import { VideoLearningGuide } from "./VideoLearningGuide";

type ViewerProps = {
  course: CourseCard;
  initialLesson: Lesson;
  onBack: () => void;
  onCourseChanged: (course: CourseCard) => void;
};

export function Viewer({ course, initialLesson, onBack, onCourseChanged }: ViewerProps) {
  const [detail, setDetail] = useState<CourseDetail | null>(null);
  const [lesson, setLesson] = useState<Lesson>(initialLesson);
  useLessonLearningSession(course.id, lesson.id);
  const [versions, setVersions] = useState<ArtifactVersion[]>([]);
  const [version, setVersion] = useState<number | undefined>();
  const [prompt, setPrompt] = useState("");
  const [slashOpen, setSlashOpen] = useState(false);
  const [pendingInsertType, setPendingInsertType] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [celebrating, setCelebrating] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(false);
  const [conversationHistory, setConversationHistory] = useState<TutorTranscriptLine[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const [shared, setShared] = useState(false);
  const [linkActive, setLinkActive] = useState(initialLesson.is_shared);
  const [a2uiDoc, setA2uiDoc] = useState<ArtifactA2UI | null>(null);
  const [a2uiSectionId, setA2uiSectionId] = useState<string | null>(null);
  const [readingArt, setReadingArt] = useState<ArtifactReading | null>(null);
  const [videoGuide, setVideoGuide] = useState<VideoGuide | null>(null);
  const [editMode, setEditModeOn] = useState(false);
  const [selection, setSelection] = useState<SelectedElement | null>(null);
  const [saving, setSaving] = useState(false);
  const [iframeKey, setIframeKey] = useState(0);
  const [iframeLoaded, setIframeLoaded] = useState(false);
  const [editThread, setEditThread] = useState<
    Array<{ id: string; role: "user" | "assistant"; text: string; status?: "thinking" | "done" | "failed" }>
  >([]);
  const [refineProgress, setRefineProgress] = useState<Progress | null>(null);
  const threadEndRef = useRef<HTMLDivElement | null>(null);
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  // Host container for the video branch — VideoAgentActions drives its <video> element.
  const videoHostRef = useRef<HTMLDivElement | null>(null);
  const { user } = useAuth();
  // Set by <LessonAgentFrame> once the GuideBridge iframe relay is mounted;
  // VoiceInstructor uses it to push the LIVE PAGE MAP tutor context.
  const [getPageSnapshot, setGetPageSnapshot] = useState<
    (() => Promise<PageSnapshot>) | null
  >(null);

  useEffect(
    () =>
      subscribeCapsuleLearningEvents(iframeRef, (event) => {
        recordLearningEvent(
          event.eventType,
          { courseId: course.id, lessonId: lesson.id },
          event.data,
          { source: "capsule" },
        );
      }),
    [course.id, lesson.id, iframeKey],
  );

  useEffect(() => {
    setConversationHistory([]);
    setHistoryOpen(false);
    setAssistantOpen(false);
  }, [lesson.id]);

  useEffect(() => {
    setLinkActive(lesson.is_shared);
  }, [lesson.id, lesson.is_shared]);

  async function load() {
    const d = await getCourse(course.id);
    setDetail(d);
    const current = d.lessons.find((l) => l.id === lesson.id) ?? initialLesson;
    setLesson(current);
    const [vs, guide] = await Promise.all([
      listVersions(course.id, current.id),
      d.source?.source_type === "video"
        ? getVideoGuide(course.id, current.id)
        : Promise.resolve(null),
    ]);
    setVideoGuide(guide);
    setVersions(vs);
    const latest = vs[0]?.version;
    // Prefer the newest artifact when one appears (regenerate / late mesh). Keep an
    // explicit older selection until a higher version lands.
    setVersion((prev) => {
      if (latest == null) return prev;
      if (prev == null || latest > prev) return latest;
      return prev;
    });
  }

  useEffect(() => {
    load().catch((e) => setErr(String((e as Error).message)));
  }, [course.id, lesson.id]);

  useEffect(() => {
    getHealth()
      .then((h) => setVoiceEnabled(h.voice?.enabled ?? false))
      .catch(() => setVoiceEnabled(false));
  }, []);

  useEffect(() => {
    if (!detail) return;
    const currentIndex = detail.lessons.findIndex((l) => l.id === lesson.id);
    if (currentIndex !== -1 && currentIndex < detail.lessons.length - 1) {
      const nextL = detail.lessons[currentIndex + 1];
      if (nextL.status === "pending") {
        generateLesson(course.id, nextL.id).catch(() => {});
      }
    }
  }, [detail, lesson.id]);

  const artifact = useMemo(() => {
    return lessonArtifactUrl(course.id, lesson.id, version);
  }, [course.id, lesson.id, version]);

  // Show the capsule loading state again whenever the iframe navigates to a new URL.
  useEffect(() => {
    setIframeLoaded(false);
  }, [artifact]);

  const currentArtifactVersion =
    versions.find((candidate) => candidate.version === version) ?? versions[0];
  const currentKind = currentArtifactVersion?.kind ?? "html";
  const isVideoCourse = Boolean(
    detail?.source?.source_type === "video" || course.source?.source_type === "video",
  );
  const isStudio = currentArtifactVersion?.checks?.presentation === "studio";

  // fast_gen §2.2: a background 3D mesh can upgrade the lesson after v1 ships — while
  // the current artifact is flagged, listen for mesh_ready and hot-swap to the version
  // the late-join persisted.
  const meshPending = Boolean(currentArtifactVersion?.checks?.mesh_pending);
  useEffect(() => {
    if (!meshPending) return;
    const stop = subscribeProgress(course.id, (p) => {
      const d = p.data as Record<string, unknown> | null | undefined;
      if (p.stage !== "mesh_ready" || d?.lesson_id !== lesson.id) return;
      const upgraded = Number(d?.version);
      void load()
        .then(() => {
          if (Number.isFinite(upgraded)) setVersion(upgraded);
        })
        .catch(() => {});
    });
    return stop;
  }, [meshPending, course.id, lesson.id]);

  useEffect(() => {
    if (!isVideoCourse || !videoGuide || versions.length > 0) return;
    if (!["pending", "generating", "awaiting_review"].includes(lesson.status)) return;

    if (lesson.status === "pending") {
      void generateLesson(course.id, lesson.id).catch(() => {});
    }
    const timer = window.setInterval(() => {
      void load().catch((e) => setErr(String((e as Error).message)));
    }, 2500);
    return () => window.clearInterval(timer);
  }, [
    course.id,
    isVideoCourse,
    lesson.id,
    lesson.status,
    videoGuide?.source_id,
    versions.length,
  ]);

  useEffect(() => {
    if (currentKind !== "a2ui") {
      setA2uiDoc(null);
      return;
    }
    let cancelled = false;
    getLessonArtifactA2UI(course.id, lesson.id, version)
      .then((doc) => {
        if (!cancelled) setA2uiDoc(doc);
      })
      .catch(() => {
        if (!cancelled) setA2uiDoc(null);
      });
    return () => {
      cancelled = true;
    };
  }, [course.id, lesson.id, version, currentKind]);

  useEffect(() => {
    if (currentKind !== "reading") {
      setReadingArt(null);
      return;
    }
    let cancelled = false;
    getLessonArtifactReading(course.id, lesson.id, version)
      .then((art) => {
        if (!cancelled) setReadingArt(art);
      })
      .catch(() => {
        if (!cancelled) setReadingArt(null);
      });
    return () => {
      cancelled = true;
    };
  }, [course.id, lesson.id, version, currentKind]);

  // Sync Edit mode into the opaque iframe via the trusted bridge.
  useEffect(() => {
    if (currentKind === "a2ui") return;
    if (!panelOpen || !editMode) {
      void setEditMode(iframeRef.current, false).catch(() => {});
      return;
    }
    void setEditMode(iframeRef.current, true).catch(() => {});
    const unsub = subscribeElementSelected(iframeRef.current, setSelection);
    return () => {
      unsub();
      void setEditMode(iframeRef.current, false).catch(() => {});
    };
  }, [editMode, panelOpen, iframeKey, currentKind, artifact]);

  useEffect(() => {
    if (!panelOpen) {
      setEditModeOn(false);
      setSelection(null);
    }
  }, [panelOpen]);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [editThread, refineProgress, busy]);

  async function shareLesson() {
    setErr(null);
    try {
      const token = await createShareLink(course.id, lesson.id);
      const url = `${window.location.origin}/#s/${token}`;
      if (navigator.share) {
        await navigator.share({ title: lesson.title, url });
        return;
      }
      await navigator.clipboard.writeText(url);
      setLinkActive(true);
      setShared(true);
      setTimeout(() => setShared(false), 2000);
    } catch (e) {
      setErr(String((e as Error).message));
    }
  }

  async function stopSharing() {
    setErr(null);
    try {
      await revokeShareLink(course.id, lesson.id);
      setLinkActive(false);
      setShared(false);
    } catch (e) {
      setErr(String((e as Error).message));
    }
  }

  async function markComplete() {
    const d = await completeLesson(course.id, lesson.id);
    setDetail(d);
    const completedLesson = d.lessons.find((candidate) => candidate.id === lesson.id);
    if (completedLesson) setLesson(completedLesson);
    setCelebrating(true);
  }

  async function retryVideoCompanion() {
    setErr(null);
    try {
      await generateLesson(course.id, lesson.id);
      setLesson((current) => ({ ...current, status: "generating", error: null }));
    } catch (e) {
      setErr(String((e as Error).message));
    }
  }

  async function refine() {
    if (!prompt.trim()) return;
    const request = prompt.trim();
    const userId = `u-${Date.now()}`;
    const asstId = `a-${Date.now()}`;
    setBusy(true);
    setErr(null);
    setRefineProgress({ stage: "queued", detail: "Updating section…", pct: 8 });
    const a2uiTarget =
      currentKind === "a2ui"
        ? a2uiSectionId || a2uiDoc?.sections?.[0]?.id || "main"
        : null;
    const htmlSectionId =
      currentKind !== "a2ui" && currentKind !== "reading"
        ? selection?.dataLessonSection || null
        : null;

    let insertType = pendingInsertType;
    let instruction = request;
    const slashMatch = request.match(/^\/([a-zA-Z_]+)\s*([\s\S]*)$/);
    if (!insertType && slashMatch) {
      const t = slashMatch[1].toLowerCase();
      if (A2UI_SLASH_CATALOGUE.some((c) => c.type === t)) {
        insertType = t;
        instruction = (slashMatch[2] || "").trim() || t;
      }
    }

    setEditThread((t) => [
      ...t,
      {
        id: userId,
        role: "user",
        text: a2uiTarget
          ? `${request}\n\n(section · ${a2uiTarget}${insertType ? ` · /${insertType}` : ""})`
          : htmlSectionId
            ? `${request}\n\n(section · ${htmlSectionId})`
            : selection
              ? `${request}\n\n(on <${selection.tag}> · ${selection.textSummary.slice(0, 80) || selection.id})`
              : request,
      },
      {
        id: asstId,
        role: "assistant",
        text: "Working on your edit…",
        status: "thinking",
      },
    ]);
    setPrompt("");
    setPendingInsertType(null);
    setSlashOpen(false);

    if (a2uiTarget) {
      try {
        const body: Parameters<typeof patchA2UISection>[3] = insertType
          ? { insert: { type: insertType, hint: instruction, placement: "append" } }
          : { instruction: instruction };
        const updated = await patchA2UISection(course.id, lesson.id, a2uiTarget, body);
        setA2uiDoc(updated);
        const vs = await listVersions(course.id, lesson.id);
        setVersions(vs);
        setVersion(updated.version);
        setBusy(false);
        setRefineProgress(null);
        setEditThread((t) =>
          t.map((m) =>
            m.id === asstId
              ? {
                  ...m,
                  status: "done",
                  text: insertType
                    ? `Inserted /${insertType} into “${a2uiTarget}” — only that section updated.`
                    : `Updated section “${a2uiTarget}” — only that section reloaded.`,
                }
              : m,
          ),
        );
      } catch (e) {
        setErr(String((e as Error).message));
        setBusy(false);
        setRefineProgress(null);
        setEditThread((t) =>
          t.map((m) =>
            m.id === asstId
              ? { ...m, status: "failed", text: String((e as Error).message) }
              : m,
          ),
        );
      }
      return;
    }

    if (htmlSectionId) {
      try {
        const art = await patchHtmlSection(course.id, lesson.id, htmlSectionId, {
          instruction: request,
          target_html: selection?.outerHTML,
        });
        const vs = await listVersions(course.id, lesson.id);
        setVersions(vs);
        setVersion(art.version);
        setIframeKey((k) => k + 1);
        setSelection(null);
        setBusy(false);
        setRefineProgress(null);
        setEditThread((t) =>
          t.map((m) =>
            m.id === asstId
              ? {
                  ...m,
                  status: "done",
                  text: `Updated section “${htmlSectionId}” only — other sections unchanged.`,
                }
              : m,
          ),
        );
      } catch (e) {
        setErr(String((e as Error).message));
        setBusy(false);
        setRefineProgress(null);
        setEditThread((t) =>
          t.map((m) =>
            m.id === asstId
              ? { ...m, status: "failed", text: String((e as Error).message) }
              : m,
          ),
        );
      }
      return;
    }

    if (selection && !htmlSectionId) {
      const ok = window.confirm(
        "Could not resolve a lesson section for this selection. Rewrite the entire lesson page? (Sibling content may change.)",
      );
      if (!ok) {
        setBusy(false);
        setRefineProgress(null);
        setEditThread((t) =>
          t.map((m) =>
            m.id === asstId
              ? {
                  ...m,
                  status: "failed",
                  text: "Cancelled — pick a marked section or clear selection.",
                }
              : m,
          ),
        );
        return;
      }
    }

    try {
      const card = await refineCourse(course.id, request, lesson.id, {
        target_id: selection?.id,
        target_html: selection?.outerHTML,
      });
      onCourseChanged(card);
      setLesson((l) => ({ ...l, status: "generating" }));
      const stop = subscribeProgress(course.id, (p) => {
        setRefineProgress(p);
        setEditThread((t) =>
          t.map((m) =>
            m.id === asstId && m.status === "thinking"
              ? { ...m, text: p.detail || m.text }
              : m,
          ),
        );
        if (p.stage === "ready" || p.stage === "failed") {
          stop();
          const ok = p.stage === "ready";
          void load()
            .then(() => {
              setIframeKey((k) => k + 1);
              setBusy(false);
              setRefineProgress(null);
              setEditThread((t) =>
                t.map((m) =>
                  m.id === asstId
                    ? {
                        ...m,
                        status: ok ? "done" : "failed",
                        text: ok
                          ? "Full lesson regenerate finished (legacy path)."
                          : p.detail || "Edit failed. Try again with a clearer request.",
                      }
                    : m,
                ),
              );
            })
            .catch((e) => {
              setErr(String((e as Error).message));
              setBusy(false);
              setRefineProgress(null);
              setEditThread((t) =>
                t.map((m) =>
                  m.id === asstId
                    ? { ...m, status: "failed", text: String((e as Error).message) }
                    : m,
                ),
              );
            });
        }
      });
    } catch (e) {
      setErr(String((e as Error).message));
      setBusy(false);
      setRefineProgress(null);
      setEditThread((t) =>
        t.map((m) =>
          m.id === asstId
            ? { ...m, status: "failed", text: String((e as Error).message) }
            : m,
        ),
      );
    }
  }

  async function saveEdits() {
    setSaving(true);
    setErr(null);
    try {
      await setEditMode(iframeRef.current, false);
      setEditModeOn(false);
      const { html } = await getDocumentHtml(iframeRef.current);
      const art = await saveLessonArtifact(course.id, lesson.id, html);
      const vs = await listVersions(course.id, lesson.id);
      setVersions(vs);
      setVersion(art.version);
      setSelection(null);
      setIframeKey((k) => k + 1);
    } catch (e) {
      setErr(String((e as Error).message));
    } finally {
      setSaving(false);
    }
  }

  async function cancelEdits() {
    setEditModeOn(false);
    setSelection(null);
    void setEditMode(iframeRef.current, false).catch(() => {});
    setIframeKey((k) => k + 1);
  }

  // fast_gen §4: no artifact yet → live generation theater (skeleton + streamed
  // fragments in a sandboxed shell iframe) instead of a dead artifact URL. When the
  // pipeline persists, onFinished reloads and the real gated capsule takes over.
  const showTheater =
    versions.length === 0 &&
    ["pending", "generating", "awaiting_review", "failed"].includes(lesson.status);

  // Provider-less core surface — the AgentProvider wraps it exactly once per page
  // (capsule branch below, or the whole video branch), never nested: two providers
  // would open two bridge sockets claiming the same session.
  const surfaceCore = showTheater ? (
    <GenerationTheater
      courseId={course.id}
      lesson={lesson}
      onFinished={() => void load().catch((e) => setErr(String((e as Error).message)))}
    />
  ) : currentKind === "reading" ? (
    <div className="h-full overflow-y-auto bg-bone">
      {readingArt?.doc ? (
        <ReadingLesson doc={readingArt.doc} />
      ) : (
        <p className="p-6 text-sm text-ink-soft">Loading reading companion…</p>
      )}
    </div>
  ) : currentKind === "a2ui" ? (
    <div className="h-full overflow-y-auto bg-bone p-6 md:p-8">
      {a2uiDoc?.root ? (
        <A2UIRenderer
          root={a2uiDoc.root as UiNode}
          onResult={(result) =>
            recordQuizResult({ courseId: course.id, lessonId: lesson.id }, result)
          }
        />
      ) : (
        <p className="text-sm text-ink-soft">Loading lesson surface…</p>
      )}
    </div>
  ) : (
    // GuideBridge: the LessonAgentFrame relay routes agent observe/act into the
    // sandboxed iframe (whose HTML carries the injected guidebridge runtime).
    //
    // Mount the iframe only once the artifact URL is final: rendering it first with
    // the version-less URL and then flipping `src` to `?version=N` mid-load can
    // leave a sandboxed iframe stuck blank (cancelled first navigation). While the
    // versions load we show the loading state instead. `detail` loaded + no
    // versions means there is genuinely nothing versioned yet — fall through to
    // the version-less URL, which serves the latest artifact.
    (() => {
      const urlReady = version !== undefined || (detail !== null && versions.length === 0);
      return (
        <>
          {(!urlReady || !iframeLoaded) && (
            <div
              className="absolute inset-0 z-10 flex h-full flex-col items-center justify-center gap-3 bg-white"
              role="status"
              aria-label="Loading lesson"
            >
              <div className="h-6 w-6 animate-spin-slow rounded-full border-2 border-ink/15 border-t-ink" />
              <p className="text-sm font-semibold text-ink-soft">Loading lesson…</p>
            </div>
          )}
          {urlReady && (
            <>
              <iframe
                key={iframeKey}
                ref={iframeRef}
                title={lesson.title}
                src={artifact}
                sandbox="allow-scripts"
                className={`h-full w-full bg-transparent ${iframeLoaded ? "" : "invisible"}`}
                onLoad={() => {
                  setIframeLoaded(true);
                  if (editMode && panelOpen) {
                    void setEditMode(iframeRef.current, true).catch(() => {});
                  }
                }}
              />
              <LessonAgentFrame iframeRef={iframeRef} onSnapshot={setGetPageSnapshot} />
            </>
          )}
        </>
      );
    })()
  );

  // autoDiscover=false: the agent may only see the lesson surface (iframe runtime or
  // registered app actions), never the surrounding app chrome.
  const lessonSurface =
    showTheater || currentKind === "a2ui" || currentKind === "reading" ? (
      surfaceCore
    ) : (
      <AgentProvider
        url={agentBridgeWsUrl(course.id, lesson.id)}
        sessionId={`${user?.id ?? "anonymous"}:${lesson.id}`}
        autoDiscover={false}
      >
        {surfaceCore}
        <AgentCursor label="Tutor" color="#2C50EE" />
      </AgentProvider>
    );

  return (
    <div className="flex h-full flex-col bg-bone font-sans text-ink">
      <header className="sticky top-0 z-30 flex flex-wrap items-center gap-3 border-b border-ink/5 bg-bone/85 px-4 py-3 backdrop-blur sm:px-5">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <button
            type="button"
            onClick={onBack}
            className="inline-flex h-11 shrink-0 items-center gap-1.5 rounded-full border border-ink/5 bg-white px-3.5 text-sm font-semibold text-ink shadow-chip transition hover:bg-sand"
            aria-label="Back to roadmap"
          >
            <span className="material-symbols-outlined text-[18px]" aria-hidden="true">arrow_back</span>
            <span className="hidden sm:inline">Roadmap</span>
          </button>
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-faint">
              {lesson.archetype ? `${lesson.archetype} chapter` : "Chapter"}
            </p>
            <h1 className="truncate font-archivo text-base font-semibold leading-tight tracking-[-0.01em] text-ink sm:text-lg">
              {lesson.title}
            </h1>
          </div>
        </div>

        <div className="ml-auto flex shrink-0 items-center gap-2">
          {voiceEnabled && (
            <button
              type="button"
              onClick={() => setHistoryOpen(true)}
              className={`inline-flex h-11 items-center gap-1.5 rounded-full px-3 text-xs font-semibold transition sm:px-3.5 ${
                historyOpen
                  ? "bg-ink text-white"
                  : "border border-ink/5 bg-white text-ink shadow-chip hover:bg-sand"
              }`}
              title="Show tutor conversation history"
              aria-label="Show tutor conversation history"
            >
              <span className="material-symbols-outlined text-[16px]" aria-hidden="true">history</span>
              <span className="hidden sm:inline">Chat</span>
              {conversationHistory.length > 0 && (
                <span
                  className={`rounded-full px-1.5 py-0.5 text-[10px] font-bold tabular-nums ${
                    historyOpen ? "bg-white/15 text-white" : "bg-sand text-ink-soft"
                  }`}
                >
                  {conversationHistory.length}
                </span>
              )}
            </button>
          )}
          {versions.length > 0 && (
            <select
              value={version}
              onChange={(e) => setVersion(Number(e.target.value))}
              className="hidden h-10 rounded-full border border-ink/10 bg-white px-3 text-xs font-semibold text-ink-soft shadow-chip outline-none transition focus:border-ink/30 focus:ring-4 focus:ring-ink/5 sm:block"
              aria-label="Lesson version"
            >
              {versions.map((v) => (
                <option key={v.id} value={v.version}>
                  v{v.version} {v.checks?.passed === false ? "(failed)" : ""}
                </option>
              ))}
            </select>
          )}
          {(!isVideoCourse || versions.length > 0) && (
            <button
              type="button"
              onClick={() => setPanelOpen(!panelOpen)}
              className={`inline-flex h-11 items-center gap-1.5 rounded-full px-3 text-xs font-semibold transition sm:px-3.5 ${
                panelOpen
                  ? "bg-ink text-white"
                  : "border border-ink/5 bg-white text-ink shadow-chip hover:bg-sand"
              }`}
              title={panelOpen ? "Close edit sidebar" : "Edit this chapter"}
              aria-label={panelOpen ? "Close edit sidebar" : "Edit this chapter"}
            >
              <span className="material-symbols-outlined text-[16px]" aria-hidden="true">
                {panelOpen ? "dock_to_left" : "edit_note"}
              </span>
              <span className="hidden sm:inline">{panelOpen ? "Done" : "Edit"}</span>
            </button>
          )}
          {!lesson.completed && (
            <button
              type="button"
              onClick={markComplete}
              className="inline-flex h-11 items-center gap-1.5 rounded-full bg-ink px-4 text-xs font-semibold text-white transition hover:bg-ink/80"
              title="Mark this chapter complete"
              aria-label="Mark this chapter complete"
            >
              <span className="material-symbols-outlined text-[16px]" aria-hidden="true">check_circle</span>
              <span className="hidden sm:inline">Complete</span>
            </button>
          )}
          <button
            type="button"
            onClick={shareLesson}
            title="Create a public link anyone can open without signing in"
            aria-label={shared ? "Public link copied" : linkActive ? "Copy public link" : "Share lesson"}
            className={`inline-flex h-11 items-center gap-1.5 rounded-full px-3 text-xs font-semibold transition sm:px-3.5 ${
              shared
                ? "bg-mint text-lime-dark"
                : "border border-ink/5 bg-white text-ink shadow-chip hover:bg-sand"
            }`}
          >
            <span className="material-symbols-outlined text-[16px]" aria-hidden="true">
              {shared ? "check" : "ios_share"}
            </span>
            <span className="hidden sm:inline">
              {shared ? "Link copied!" : linkActive ? "Copy link" : "Share"}
            </span>
          </button>
          {linkActive && (
            <button
              type="button"
              onClick={stopSharing}
              title="Revoke the public link — shared URLs stop working immediately"
              aria-label="Stop sharing lesson"
              className="inline-flex h-11 items-center gap-1.5 rounded-full border border-ink/5 bg-white px-3 text-xs font-semibold text-ink-soft shadow-chip transition hover:bg-coral-soft hover:text-coral-dark"
            >
              <span className="material-symbols-outlined text-[16px]" aria-hidden="true">link_off</span>
              <span className="hidden sm:inline">Stop sharing</span>
            </button>
          )}
        </div>
      </header>
      {err && (
        <div className="bg-coral-soft px-4 py-2 text-sm font-semibold text-coral-dark">{err}</div>
      )}
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden lg:flex-row">
        <div className={`relative h-full min-w-0 flex-1 ${isStudio ? "p-1.5 sm:p-2" : "p-3"}`}>
            {videoGuide ? (
            // One AgentProvider for the whole video surface (specs/design_agents §6):
            // VideoAgentActions registers seek/play/pause as bridge app actions the
            // voice tutor invokes; the companion capsule (when built) shares the same
            // session via surfaceCore — never a second nested provider.
            <AgentProvider
              url={agentBridgeWsUrl(course.id, lesson.id)}
              sessionId={`${user?.id ?? "anonymous"}:${lesson.id}`}
              autoDiscover={false}
            >
            <VideoAgentActions containerRef={videoHostRef} />
            <div ref={videoHostRef} className="h-full overflow-y-auto pb-28 sm:pb-0">
              <VideoLearningGuide
                guide={videoGuide}
                mediaUrl={videoGuide.media_url ?? sourceMediaUrl(videoGuide.source_id)}
                onQuizResult={(result) =>
                  recordQuizResult({ courseId: course.id, lessonId: lesson.id }, result)
                }
              />
              {versions.length > 0 ? (
                <section className="mx-auto max-w-7xl px-3 pb-5 pt-4 sm:px-5" aria-label="Interactive deep dive">
                  <div className="overflow-hidden rounded-3xl border border-ink/5 bg-white shadow-chip">
                    <div className="relative h-[min(720px,72vh)] min-h-[480px] overflow-hidden bg-transparent">
                      {surfaceCore}
                    </div>
                  </div>
                </section>
              ) : (
                <section className="mx-auto max-w-7xl px-3 pb-5 pt-4 sm:px-5">
                  <div
                    className={`flex items-center gap-3 rounded-2xl border p-4 ${
                      lesson.status === "failed"
                        ? "border-coral/15 bg-coral-soft text-coral-dark"
                        : "border-ink/5 bg-white text-ink shadow-chip"
                    }`}
                  >
                    {lesson.status === "failed" ? (
                      <span className="material-symbols-outlined text-[22px]" aria-hidden="true">
                        priority_high
                      </span>
                    ) : (
                      <div className="h-5 w-5 shrink-0 animate-spin-slow rounded-full border-2 border-ink/20 border-t-ink" />
                    )}
                    <div>
                      <p className="text-sm font-semibold">
                        {lesson.status === "failed"
                          ? "Interactive companion needs another try"
                          : "Interactive companion is building"}
                      </p>
                      <p className="mt-0.5 text-[11px] font-semibold opacity-75">
                        Video training is ready now. The companion is separate from playback.
                      </p>
                    </div>
                    {lesson.status === "failed" && (
                      <button
                        type="button"
                        onClick={retryVideoCompanion}
                        className="ml-auto shrink-0 rounded-full bg-white px-3.5 py-2 text-[11px] font-semibold text-coral-dark shadow-chip transition hover:bg-coral/5"
                      >
                        Retry
                      </button>
                    )}
                  </div>
                </section>
              )}
            </div>
            <AgentCursor label="Tutor" color="#2C50EE" />
            </AgentProvider>
            ) : (
              <div
                className={`relative h-full overflow-hidden ${
                  isStudio
                    ? "rounded-2xl"
                    : "rounded-3xl border border-ink/5 bg-white shadow-chip"
                }`}
              >
                {lessonSurface}
              </div>
            )}
        </div>
        {panelOpen && (
          <aside className="flex h-full min-h-0 w-full shrink-0 flex-col p-3 pt-0 lg:w-[384px] lg:pl-0 lg:pt-3">
            <div className="animate-panel-in flex min-h-0 flex-1 flex-col overflow-hidden">
              {/* Thread — Lovable-style: no fake greeting, messages only */}
              <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 py-4">
                {editThread.length === 0 && !busy && (
                  <div className="flex flex-1 flex-col items-center justify-center px-2 text-center">
                    <div className="mb-3 grid h-14 w-14 place-items-center rounded-2xl bg-mint">
                      <Mascot mood="tutor" className="h-10 w-10" />
                    </div>
                    <p className="font-archivo text-base font-semibold tracking-[-0.01em] text-ink">What should we change?</p>
                    <p className="mt-1 max-w-[16rem] text-[12px] font-medium leading-snug text-ink-faint">
                      Ask in plain language
                      {selection ? ", or tweak the selected block" : ""}.
                    </p>
                  </div>
                )}

                {editThread.map((m) =>
                  m.role === "user" ? (
                    <div
                      key={m.id}
                      className="ml-auto w-max max-w-[88%] self-end rounded-2xl bg-ink px-3.5 py-2.5 text-[13px] font-medium leading-relaxed text-white"
                    >
                      <p className="whitespace-pre-line">{m.text}</p>
                    </div>
                  ) : m.status === "thinking" ? (
                    <div
                      key={m.id}
                      className="flex w-max max-w-[92%] flex-col gap-2 self-start rounded-2xl border border-ink/5 bg-sand px-3.5 py-2.5 text-ink"
                    >
                      <div className="flex items-center gap-2">
                        <Mascot mood="mark" className="h-7 w-7 shrink-0" />
                        <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
                          Working…
                        </span>
                      </div>
                      {(refineProgress?.detail || m.text) && (
                        <p className="text-[12px] font-medium leading-snug text-ink-soft">
                          {refineProgress?.detail || m.text}
                        </p>
                      )}
                      {refineProgress && typeof refineProgress.pct === "number" && (
                        <div className="h-1.5 overflow-hidden rounded-full bg-ink/10">
                          <div
                            className="h-full rounded-full bg-lime transition-all duration-500 ease-out"
                            style={{ width: `${Math.max(6, Math.min(100, refineProgress.pct))}%` }}
                          />
                        </div>
                      )}
                    </div>
                  ) : (
                    <div
                      key={m.id}
                      className={`mr-auto flex w-max max-w-[88%] items-start gap-2 self-start rounded-2xl border px-3.5 py-2.5 text-[13px] font-medium leading-relaxed ${
                        m.status === "failed"
                          ? "border-coral/15 bg-coral-soft text-coral-dark"
                          : "border-ink/5 bg-sand text-ink"
                      }`}
                    >
                      {m.status !== "failed" && <Mascot mood="mark" className="mt-0.5 h-7 w-7 shrink-0" />}
                      <p className="whitespace-pre-line">{m.text}</p>
                    </div>
                  ),
                )}
                <div ref={threadEndRef} />
              </div>

              {/* Tools + composer — anchored bottom like Lovable */}
              <div className="shrink-0 space-y-2.5 border-t border-ink/5 px-3 pb-3 pt-2.5">
                {editThread.length === 0 && !busy && (
                  <div className="flex flex-wrap gap-1.5 px-0.5">
                    {(selection
                      ? ["Make this clearer", "Add a short tip", "Harder quiz"]
                      : ["Add a quiz", "Warmer colors", "Tighten the intro"]
                    ).map((chip) => (
                      <button
                        key={chip}
                        type="button"
                        disabled={busy || saving}
                        onClick={() => setPrompt(chip)}
                        className="rounded-full border border-ink/10 px-3 py-1.5 text-[11px] font-semibold text-ink-soft transition hover:border-ink/20 hover:text-ink disabled:opacity-50"
                      >
                        {chip}
                      </button>
                    ))}
                  </div>
                )}

                {currentKind === "a2ui" && (a2uiDoc?.sections?.length ?? 0) > 0 && (
                  <div className="rounded-2xl border border-ink/10 p-2">
                    <p className="mb-1.5 px-1 text-[10px] font-bold uppercase tracking-wide text-ink-faint">
                      Edit section
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {a2uiDoc!.sections!.map((sec) => (
                        <button
                          key={sec.id}
                          type="button"
                          onClick={() => setA2uiSectionId(sec.id)}
                          className={`rounded-full px-3 py-1.5 text-[11px] font-semibold transition ${
                            (a2uiSectionId || a2uiDoc!.sections![0]?.id) === sec.id
                              ? "bg-ink text-white"
                              : "border border-ink/10 text-ink-soft hover:text-ink"
                          }`}
                        >
                          {sec.title || sec.id}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {currentKind !== "a2ui" && (
                  <div
                    className={`rounded-2xl border p-2 transition ${
                      editMode ? "border-lime/30 bg-mint/60" : "border-ink/10"
                    }`}
                  >
                    <div className="flex items-center gap-1.5">
                      <button
                        type="button"
                        onClick={() => setEditModeOn((v) => !v)}
                        disabled={busy || saving}
                        className={`inline-flex h-10 flex-1 items-center justify-center gap-1.5 rounded-full px-3 text-[12px] font-semibold transition ${
                          editMode
                            ? "bg-ink text-white"
                            : "border border-ink/10 text-ink-soft hover:text-ink"
                        }`}
                      >
                        <span className="material-symbols-outlined text-[17px]">
                          {editMode ? "near_me" : "arrow_selector_tool"}
                        </span>
                        {editMode ? "Click something on the page" : "Select on page"}
                      </button>
                      {editMode && (
                        <>
                          <button
                            type="button"
                            onClick={() => void saveEdits()}
                            disabled={busy || saving}
                            className="inline-flex h-10 items-center gap-1 rounded-full bg-ink px-3 text-[11px] font-semibold text-white transition hover:bg-ink/80 disabled:opacity-50"
                            title="Save in-page edits"
                          >
                            <span
                              className={`material-symbols-outlined text-[15px] ${saving ? "animate-spin-slow" : ""}`}
                            >
                              {saving ? "progress_activity" : "check"}
                            </span>
                            Save
                          </button>
                          <button
                            type="button"
                            onClick={() => void cancelEdits()}
                            disabled={busy || saving}
                            className="inline-flex h-10 items-center rounded-full border border-ink/10 px-3 text-[11px] font-semibold text-ink-faint transition hover:text-ink disabled:opacity-50"
                            title="Discard unsaved edits"
                          >
                            Reset
                          </button>
                        </>
                      )}
                    </div>
                    {selection && (
                      <div className="mt-2 flex items-center gap-2 rounded-xl border border-ink/10 px-2.5 py-2">
                        <span className="material-symbols-outlined text-[15px] text-lime">ads_click</span>
                        <p className="min-w-0 flex-1 truncate text-[11px] font-semibold text-ink-soft">
                          <span className="font-mono font-semibold text-ink">&lt;{selection.tag}&gt;</span>
                          {selection.textSummary ? ` · ${selection.textSummary}` : ""}
                        </p>
                        <button
                          type="button"
                          className="grid h-6 w-6 shrink-0 place-items-center rounded-full text-ink-faint hover:bg-ink/5 hover:text-ink"
                          onClick={() => setSelection(null)}
                          aria-label="Clear selection"
                        >
                          <span className="material-symbols-outlined text-[14px]">close</span>
                        </button>
                      </div>
                    )}
                  </div>
                )}

                {(pendingInsertType || (currentKind === "a2ui" && a2uiSectionId)) && (
                  <div className="flex flex-wrap items-center gap-1.5 px-0.5">
                    {pendingInsertType && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-mint px-2.5 py-1 text-[11px] font-semibold text-lime-dark">
                        /{pendingInsertType}
                        <button
                          type="button"
                          className="text-ink-faint hover:text-ink"
                          onClick={() => setPendingInsertType(null)}
                          aria-label="Clear insert type"
                        >
                          ×
                        </button>
                      </span>
                    )}
                    {currentKind === "a2ui" && (
                      <span className="rounded-full border border-ink/10 px-2.5 py-1 text-[11px] font-semibold text-ink-soft">
                        section · {a2uiSectionId || a2uiDoc?.sections?.[0]?.id || "main"}
                      </span>
                    )}
                    {selection?.dataLessonSection && currentKind !== "a2ui" && (
                      <span className="rounded-full border border-ink/10 px-2.5 py-1 text-[11px] font-semibold text-ink-soft">
                        section · {selection.dataLessonSection}
                      </span>
                    )}
                  </div>
                )}

                {slashOpen && currentKind === "a2ui" && (
                  <div className="max-h-40 overflow-y-auto rounded-2xl border border-ink/10 bg-bone p-1.5">
                    {A2UI_SLASH_CATALOGUE.filter((c) =>
                      !prompt.startsWith("/")
                        ? true
                        : c.type.startsWith(prompt.slice(1).split(/\s/)[0]?.toLowerCase() || ""),
                    ).map((c) => (
                      <button
                        key={c.type}
                        type="button"
                        className="flex w-full items-center justify-between rounded-xl px-2.5 py-1.5 text-left hover:bg-ink/5"
                        onClick={() => {
                          setPendingInsertType(c.type);
                          setPrompt((p) => {
                            const rest = p.replace(/^\/[a-zA-Z_]*\s*/, "");
                            return rest;
                          });
                          setSlashOpen(false);
                        }}
                      >
                        <span className="text-[12px] font-semibold text-ink">/{c.type}</span>
                        <span className="text-[11px] text-ink-faint">{c.blurb}</span>
                      </button>
                    ))}
                  </div>
                )}

                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    void refine();
                  }}
                  className="flex items-end gap-2 rounded-2xl border border-ink/10 p-2"
                >
                  <textarea
                    value={prompt}
                    onChange={(e) => {
                      const v = e.target.value;
                      setPrompt(v);
                      setSlashOpen(currentKind === "a2ui" && (v === "/" || /^\/[a-zA-Z_]*$/.test(v)));
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Escape") setSlashOpen(false);
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        if (!busy && !saving && prompt.trim()) void refine();
                      }
                    }}
                    disabled={busy || saving}
                    rows={2}
                    placeholder={
                      currentKind === "a2ui"
                        ? "Edit this section… or type /map /quiz"
                        : selection?.dataLessonSection
                          ? `Change section “${selection.dataLessonSection}”…`
                          : selection
                            ? "Change the selected block…"
                            : "Ask for a change…"
                    }
                    className="min-h-[44px] min-w-0 flex-1 resize-none rounded-xl border-0 bg-transparent px-3 py-2.5 text-sm font-medium text-ink outline-none placeholder:text-ink-faint disabled:opacity-50"
                  />
                  <button
                    type="submit"
                    disabled={busy || saving || !prompt.trim()}
                    className="mb-0.5 grid h-10 w-10 shrink-0 place-items-center rounded-full bg-ink text-white transition hover:bg-ink/80 disabled:opacity-50"
                    title="Send"
                    aria-label="Send"
                  >
                    <span
                      className={`material-symbols-outlined text-[18px] ${busy ? "animate-spin-slow" : ""}`}
                    >
                      {busy ? "progress_activity" : "arrow_upward"}
                    </span>
                  </button>
                </form>
              </div>
            </div>
          </aside>
        )}
      </div>

      {voiceEnabled && (
        <AssistantDock
          courseId={course.id}
          lessonId={lesson.id}
          iframeRef={iframeRef}
          getPageSnapshot={getPageSnapshot}
          open={assistantOpen}
          offsetForEditPanel={panelOpen}
          conversationHistory={conversationHistory}
          onConversationHistoryChange={setConversationHistory}
          onOpenChange={setAssistantOpen}
        />
      )}

      {historyOpen && (
        <ConversationHistorySheet
          lines={conversationHistory}
          onClose={() => setHistoryOpen(false)}
        />
      )}

      {celebrating && (
        <CelebrationModal
          lessonTitle={lesson.title}
          estimatedDuration={lesson.estimated_duration}
          onClose={() => {
            setCelebrating(false);
            onBack();
          }}
        />
      )}
    </div>
  );
}

/**
 * Registers the GuideBridge iframe relay and reports its snapshot fn upward.
 *
 * Implemented here (instead of package `useAgentFrame`) so the FrameRelay is
 * always created inside the effect. The published `@guidebridge/react@0.2.0`
 * hook memoized the relay and disposed it when bridge status flipped to
 * `connected`, then reused the dead instance — observe/highlight timed out and
 * the tutor reported it could not reach the lesson frame.
 */
function LessonAgentFrame({
  iframeRef,
  onSnapshot,
}: {
  iframeRef: RefObject<HTMLIFrameElement | null>;
  onSnapshot: React.Dispatch<React.SetStateAction<(() => Promise<PageSnapshot>) | null>>;
}) {
  const { registerFrame } = useAgentBridge();
  useEffect(() => {
    const relay = new FrameRelay(iframeRef, { timeoutMs: 10_000 });
    const unregister = registerFrame(relay);
    void relay.waitReady();
    // Functional-updater form: store the snapshot fn itself, not call it.
    onSnapshot(() => () => relay.snapshot());
    return () => {
      unregister();
      relay.dispose();
      onSnapshot(null);
    };
  }, [iframeRef, registerFrame, onSnapshot]);
  return null;
}

function AssistantDock({
  courseId,
  lessonId,
  iframeRef,
  getPageSnapshot,
  open,
  offsetForEditPanel,
  conversationHistory,
  onConversationHistoryChange,
  onOpenChange,
}: {
  courseId: string;
  lessonId: string;
  iframeRef: RefObject<HTMLIFrameElement | null>;
  getPageSnapshot: (() => Promise<PageSnapshot>) | null;
  open: boolean;
  offsetForEditPanel: boolean;
  conversationHistory: TutorTranscriptLine[];
  onConversationHistoryChange: (lines: TutorTranscriptLine[]) => void;
  onOpenChange: (open: boolean) => void;
}) {
  const [draft, setDraft] = useState("");
  const [startNonce, setStartNonce] = useState(0);
  const [startVoice, setStartVoice] = useState(false);
  const [initialText, setInitialText] = useState("");

  function beginVoice() {
    setInitialText("");
    setStartVoice(true);
    setStartNonce((n) => n + 1);
    onOpenChange(true);
  }

  function submitText(e: FormEvent) {
    e.preventDefault();
    const text = draft.trim().replace(/\s+/g, " ");
    if (!text) return;
    setDraft("");
    setInitialText(text);
    setStartVoice(false);
    setStartNonce((n) => n + 1);
    onOpenChange(true);
  }

  return (
    <div
      className={`pointer-events-none fixed bottom-5 left-1/2 z-40 flex -translate-x-1/2 flex-col items-center gap-3 ${
        offsetForEditPanel ? "lg:left-[calc(50%-192px)]" : ""
      }`}
    >
      {open ? (
        <VoiceInstructor
          key={`${lessonId}-${startNonce}`}
          courseId={courseId}
          lessonId={lessonId}
          iframeRef={iframeRef}
          getPageSnapshot={getPageSnapshot}
          autoStart={startVoice}
          initialText={initialText}
          initialTranscript={conversationHistory}
          onTranscriptChange={onConversationHistoryChange}
          onClose={() => onOpenChange(false)}
        />
      ) : (
        <form
          onSubmit={submitText}
          className="pointer-events-auto flex w-[min(580px,calc(100vw-28px))] items-center gap-2 rounded-2xl bg-ink p-2 text-white shadow-panel ring-2 ring-lime/40 animate-fade-up"
        >
          <button
            type="button"
            onClick={beginVoice}
            className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-white/10 text-white transition hover:bg-white/20"
            title="Start audio mode"
            aria-label="Start audio mode"
          >
            <span className="material-symbols-outlined text-[20px]" aria-hidden="true" style={{ fontVariationSettings: '"FILL" 1' }}>
              mic
            </span>
          </button>
          <div className="flex h-11 min-w-0 flex-1 items-center gap-1.5 rounded-full bg-white/10 px-3">
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              className="h-full min-w-0 flex-1 rounded-full border-0 bg-transparent text-[14px] font-medium text-white outline-none placeholder:text-white/40 focus:ring-0"
              placeholder="Ask your tutor…"
            />
            <button
              type="submit"
              disabled={!draft.trim()}
              className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-lime text-white transition hover:brightness-110 disabled:opacity-40"
              title="Send message"
              aria-label="Send message"
            >
              <span className="material-symbols-outlined text-[18px]" aria-hidden="true">send</span>
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

function ConversationHistorySheet({
  lines,
  onClose,
}: {
  lines: TutorTranscriptLine[];
  onClose: () => void;
}) {
  const finals = lines.filter((line) => line.final && line.text.trim());

  return (
    <div className="animate-fade-in fixed inset-0 z-50 flex justify-end bg-ink/35 p-0 backdrop-blur-sm sm:p-4">
      <button
        type="button"
        className="absolute inset-0 cursor-default"
        aria-label="Close conversation history"
        onClick={onClose}
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="tutor-history-title"
        className="animate-fade-up relative flex h-full w-full max-w-md flex-col bg-bone shadow-panel sm:rounded-3xl"
      >
        <div className="flex items-center gap-3 border-b border-ink/5 px-4 py-4 sm:px-5">
          <div className="min-w-0 flex-1">
            <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-faint">Tutor</p>
            <h2 id="tutor-history-title" className="font-archivo text-lg font-semibold tracking-[-0.02em] text-ink">
              Conversation
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="grid h-11 w-11 place-items-center rounded-full border border-ink/5 bg-white text-ink shadow-chip transition hover:bg-sand"
            title="Close"
            aria-label="Close conversation history"
          >
            <span className="material-symbols-outlined text-[18px]">close</span>
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4 sm:px-5">
          {finals.length === 0 ? (
            <div className="rounded-2xl border border-ink/5 bg-white px-4 py-8 text-center shadow-chip">
              <Mascot mood="mark" className="mx-auto mb-3 h-14 w-14" />
              <p className="text-sm font-semibold text-ink">No conversation yet</p>
              <p className="mt-1 text-sm text-ink-soft">
                Ask the tutor a question and it will show up here for this chapter.
              </p>
            </div>
          ) : (
            finals.map((line) => {
              const learner = line.speaker === "learner";
              return (
                <div
                  key={line.id}
                  className={`flex ${learner ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[92%] rounded-2xl px-4 py-2.5 text-sm font-medium leading-snug ${
                      learner ? "bg-ink text-white" : "bg-sky-dark text-white shadow-chip"
                    }`}
                  >
                    <span
                      className={`mr-2 text-[10px] font-semibold uppercase tracking-[0.16em] ${
                        learner ? "text-white/70" : "text-white/75"
                      }`}
                    >
                      {learner ? "You" : "Tutor"}
                    </span>
                    {line.text}
                  </div>
                </div>
              );
            })
          )}
        </div>

        <div className="border-t border-ink/5 px-4 py-3 sm:px-5">
          <p className="text-xs font-medium text-ink-faint">
            Kept for this chapter while you stay on the page. Closing the lesson clears it.
          </p>
        </div>
      </aside>
    </div>
  );
}

function CelebrationModal({
  lessonTitle,
  estimatedDuration,
  onClose,
}: {
  lessonTitle: string;
  estimatedDuration: string;
  onClose: () => void;
}) {
  const confetti = ["#2C50EE", "#C7ED45", "#FF6A3C", "#15A66A", "#1B1A16"];

  return (
    <div className="animate-fade-in fixed inset-0 z-50 grid place-items-center bg-ink/45 p-4 backdrop-blur-md">
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        {Array.from({ length: 28 }).map((_, i) => (
          <span
            key={i}
            className="animate-confetti absolute top-0 h-2.5 w-2.5 rounded-[2px]"
            style={{
              left: `${(i * 37) % 100}%`,
              background: confetti[i % confetti.length],
              animationDelay: `${(i % 7) * 0.12}s`,
            }}
          />
        ))}
      </div>

      <div className="animate-pop-in relative w-full max-w-md overflow-hidden rounded-3xl bg-ink p-8 text-center text-white shadow-panel">
        <Mascot mood="celebrate" className="mx-auto mb-3 h-32 w-32" />
        <p className="mb-1 text-xs font-semibold uppercase tracking-[0.14em] text-white/50">Chapter mastered</p>
        <h2 className="font-archivo text-3xl font-semibold tracking-[-0.03em]">Nice work!</h2>
        <p className="mt-2 text-sm font-medium text-white/70">{lessonTitle}</p>

        <div className="my-6 flex items-center justify-around rounded-2xl border border-white/10 bg-white/5 px-6 py-4">
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-wider text-white/50">Time invested</div>
            <div className="font-archivo text-xl font-medium text-white">{estimatedDuration}</div>
          </div>
          <div className="h-9 w-px bg-white/10" />
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-wider text-white/50">XP earned</div>
            <div className="font-archivo text-xl font-medium text-lime">+100</div>
          </div>
        </div>

        <p className="px-2 text-[13px] leading-relaxed text-white/65">
          You completed the interactive exercises and validated the core checks. The next chapter is unlocked.
        </p>

        <button
          onClick={onClose}
          className="mt-6 inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-full bg-white px-5 text-sm font-semibold text-ink transition hover:bg-white/90"
        >
          Continue roadmap
        </button>
      </div>
    </div>
  );
}
