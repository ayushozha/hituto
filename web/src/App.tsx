import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useSignIn } from "@reboot-dev/reboot-react";
import { useTutorSession } from "./api/sat_tutor/v1/tutor_rbt_react";
import { TeachingCanvas } from "./components/TeachingCanvas";
import { Whiteboard } from "./components/Whiteboard";
import {
  DashboardPage,
  LandingPage,
  navigateTo,
  NotFoundPage,
  PricingPage,
  SignInPage,
} from "./components/ProductPages";
import { DeepgramListener, DeepgramSpeech } from "./lib/deepgram";
import { applySceneCommand, emptyScene, type SceneState } from "./lib/scene";
import {
  lessonPlanSchema,
  type LessonPlan,
  type TutorState,
} from "./types/lesson";

const SESSION_KEY = "sat-live-tutor-session-id";
const MAX_IMAGE_BYTES = 4 * 1024 * 1024;
const SUPPORTED_IMAGE_TYPES = new Set(["image/jpeg", "image/png"]);

interface SelectedQuestionImage {
  name: string;
  mediaType: "image/jpeg" | "image/png";
  dataUrl: string;
  base64: string;
  width: number;
  height: number;
}

function browserSessionId(): string {
  const current = window.localStorage.getItem(SESSION_KEY);
  if (current) return current;
  const created = `browser-${crypto.randomUUID()}`;
  window.localStorage.setItem(SESSION_KEY, created);
  return created;
}

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function estimatedSpeechMilliseconds(text: string): number {
  return Math.max(1_400, Math.min(15_000, (text.trim().split(/\s+/).length / 155) * 60_000));
}

function abortedMessage(aborted: { message: string } | undefined): string {
  return aborted?.message || "The tutor backend did not complete the request.";
}

function parseLesson(value: string): LessonPlan | undefined {
  try {
    const parsed = lessonPlanSchema.safeParse(JSON.parse(value));
    return parsed.success ? parsed.data : undefined;
  } catch {
    return undefined;
  }
}

function completedScene(lesson: LessonPlan): SceneState {
  return lesson.beats.reduce(
    (scene, beat) => beat.commands.reduce(applySceneCommand, scene),
    emptyScene,
  );
}

/**
 * Diagnoses are built by `_diagnosis_to_lesson`, which names every beat
 * `work:*`. The board is captioned differently for them: the question shown
 * is what the working was checked against, not what is being taught.
 */
function isWorkCheck(lesson: LessonPlan): boolean {
  return lesson.beats.some((beat) => beat.id.startsWith("work:"));
}

function hasTeachingActivity(lesson: LessonPlan): boolean {
  return lesson.beats.some((beat) => beat.commands.length > 0);
}

function MessageText({ text }: { text: string }) {
  return (
    <div className="chat-message-copy">
      {text.split(/\n{2,}/).filter(Boolean).map((paragraph, index) => (
        <p key={`${index}-${paragraph.slice(0, 24)}`}>{paragraph}</p>
      ))}
    </div>
  );
}

function readAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("The image could not be read."));
    reader.readAsDataURL(file);
  });
}

function imageDimensions(dataUrl: string): Promise<{ width: number; height: number }> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve({ width: image.naturalWidth, height: image.naturalHeight });
    image.onerror = () => reject(new Error("The selected file is not a readable image."));
    image.src = dataUrl;
  });
}

async function prepareQuestionImage(file: File): Promise<SelectedQuestionImage> {
  if (!SUPPORTED_IMAGE_TYPES.has(file.type)) throw new Error("Upload a PNG or JPEG image.");
  if (!file.size || file.size > MAX_IMAGE_BYTES) throw new Error("The image must be smaller than 4 MB.");
  const dataUrl = await readAsDataUrl(file);
  const dimensions = await imageDimensions(dataUrl);
  const base64 = dataUrl.slice(dataUrl.indexOf(",") + 1);
  return {
    name: file.name,
    mediaType: file.type as SelectedQuestionImage["mediaType"],
    dataUrl,
    base64,
    ...dimensions,
  };
}

function Status({ state }: { state: TutorState }) {
  const labels: Record<TutorState, string> = {
    idle: "ready",
    thinking: "thinking",
    speaking: "teaching",
    listening: "listening",
    paused: "paused",
    done: "finished",
    error: "needs attention",
  };
  return (
    <div className={`teacher-status status-${state}`}>
      <span className="status-dot" />
      {labels[state]}
    </div>
  );
}

export default function App() {
  const [pathname, setPathname] = useState(window.location.pathname);

  useEffect(() => {
    const updatePath = () => setPathname(window.location.pathname);
    window.addEventListener("popstate", updatePath);
    return () => window.removeEventListener("popstate", updatePath);
  }, []);

  if (pathname === "/") return <LandingPage />;
  if (pathname === "/pricing") return <PricingPage />;
  if (pathname === "/app" || pathname === "/dashboard") {
    return <AuthenticatedProduct pathname={pathname} />;
  }
  return <NotFoundPage />;
}

function AuthenticatedProduct({ pathname }: { pathname: "/app" | "/dashboard" }) {
  const sessionId = useMemo(browserSessionId, []);
  const session = useTutorSession({ id: sessionId });
  const signIn = useSignIn();
  const [ready, setReady] = useState(false);
  const [authRequired, setAuthRequired] = useState(false);
  const [bootError, setBootError] = useState("");

  useEffect(() => {
    let mounted = true;
    void session.mutators
      .ensure(undefined, { idempotencyKey: crypto.randomUUID() })
      .then(({ aborted }) => {
        if (!mounted) return;
        if (!aborted) {
          setReady(true);
          return;
        }
        if (["PermissionDenied", "Unauthenticated"].includes(aborted.error.type)) {
          setAuthRequired(true);
          return;
        }
        setBootError(aborted.message || "The tutor could not start. Please refresh and try again.");
      })
      .catch((startError) => {
        if (mounted) setBootError(`The tutor could not start. ${String(startError)}`);
      });
    return () => {
      mounted = false;
    };
  }, [session, sessionId]);

  if (!ready) {
    if (authRequired) return <SignInPage onSignIn={() => signIn()} />;
    if (bootError) return <SignInPage onSignIn={() => undefined} error={bootError} />;
    return <SignInPage onSignIn={() => undefined} loading />;
  }

  if (pathname === "/dashboard") {
    return (
      <DashboardExperience sessionId={sessionId} />
    );
  }
  return <TutorExperience sessionId={sessionId} />;
}

function DashboardExperience({ sessionId }: { sessionId: string }) {
  const session = useTutorSession({ id: sessionId });
  const { response: snapshot } = session.useSnapshot();

  async function forget(): Promise<number> {
    const { response, aborted } = await session.mutators.forget(undefined, {
      idempotencyKey: crypto.randomUUID(),
    });
    if (aborted || !response) throw new Error(abortedMessage(aborted));
    return response.messagesErased;
  }

  return (
    <DashboardPage
      questionText={snapshot?.questionText || ""}
      status={snapshot?.status || ""}
      lesson={snapshot?.lessonJson ? parseLesson(snapshot.lessonJson) : undefined}
      onForget={forget}
    />
  );
}

function TutorExperience({ sessionId }: { sessionId: string }) {
  const session = useTutorSession({ id: sessionId });
  const { response: snapshot } = session.useSnapshot();
  const { response: conversation } = session.useMessages({ cursor: "", limit: 80 });
  const snapshotRef = useRef(snapshot);
  snapshotRef.current = snapshot;

  const [draft, setDraft] = useState("");
  const [questionText, setQuestionText] = useState("");
  const [lesson, setLesson] = useState<LessonPlan>();
  const [scene, setScene] = useState<SceneState>(emptyScene);
  const [caption, setCaption] = useState("");
  const [state, setState] = useState<TutorState>("idle");
  const [error, setError] = useState("");
  const [voiceNote, setVoiceNote] = useState("");
  const [selectedImage, setSelectedImage] = useState<SelectedQuestionImage>();
  const [activeBeat, setActiveBeat] = useState(-1);
  const [resumeAt, setResumeAt] = useState<number>();
  // When set, the composer submits the student's own working for diagnosis
  // instead of asking the tutor to solve something.
  const [checking, setChecking] = useState(false);
  // Text read off the whiteboard. Kept apart from `draft` so the canvas and
  // the textarea never overwrite each other.
  const [boardWork, setBoardWork] = useState("");
  const [boardCollapsed, setBoardCollapsed] = useState(false);
  // A pinned past explanation, or undefined for "whatever is live".
  const [shownLesson, setShownLesson] = useState<string>();

  const generation = useRef(0);
  const lessonRequest = useRef(0);
  const paused = useRef(false);
  const suppressSnapshotRestore = useRef(false);
  const speech = useRef(new DeepgramSpeech());
  const listener = useRef(new DeepgramListener());
  const imageInput = useRef<HTMLInputElement>(null);
  const speechConnected = useRef(false);
  const conversationEnd = useRef<HTMLDivElement>(null);

  const messages = conversation?.messages ?? [];

  useEffect(() => {
    if (suppressSnapshotRestore.current || !snapshot?.lessonJson || lesson) return;
    const restored = parseLesson(snapshot.lessonJson);
    if (restored) {
      setLesson(restored);
      setQuestionText(snapshot.questionText || restored.question_summary);
      setState("paused");
      setCaption("Lesson restored. Press replay when you’re ready.");
    }
  }, [lesson, snapshot]);

  useEffect(() => {
    if (suppressSnapshotRestore.current || lesson || state !== "idle" || snapshot?.status !== "thinking") return;
    setQuestionText(snapshot.questionText);
    setState("thinking");
    setCaption("I’m solving the problem and planning the clearest explanation…");
  }, [lesson, snapshot, state]);

  useEffect(() => () => {
    generation.current += 1;
    lessonRequest.current += 1;
    listener.current.stop();
    speech.current.close();
  }, []);

  useEffect(() => {
    conversationEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, caption, state]);

  async function waitForLesson(generationToWaitFor: number, requestId: number) {
    let elapsedSeconds = 0;
    while (lessonRequest.current === requestId) {
      const current = snapshotRef.current;
      if (
        current?.generation === generationToWaitFor &&
        (current.status === "ready" || current.status === "error")
      ) {
        return current;
      }
      if (current && current.generation > generationToWaitFor) return undefined;
      if (elapsedSeconds === 15) setCaption("I’ve solved it. Now I’m checking the answer before I teach it…");
      if (elapsedSeconds === 45) setCaption("I’m building the board so the explanation is visual and precise…");
      if (elapsedSeconds === 90) setCaption("This one is taking longer, but I’m still working—your lesson will start when it’s verified.");
      await sleep(1_000);
      elapsedSeconds += 1;
    }
    return undefined;
  }

  async function temporaryVoiceToken() {
    const started = await session.mutators.requestVoiceToken(undefined, {
      idempotencyKey: crypto.randomUUID(),
    });
    if (started.aborted || !started.response) {
      return { ok: false as const, message: abortedMessage(started.aborted) };
    }
    const voiceGeneration = started.response.generation;
    for (let attempt = 0; attempt < 160; attempt += 1) {
      const current = snapshotRef.current;
      if (current?.voiceGeneration === voiceGeneration && current.voiceStatus === "error") {
        return { ok: false as const, message: current.voiceError || "Voice token request failed." };
      }
      if (current?.voiceGeneration === voiceGeneration && current.voiceStatus === "ready") {
        const consumed = await session.mutators.consumeVoiceToken(
          { generation: voiceGeneration },
          { idempotencyKey: crypto.randomUUID() },
        );
        if (consumed.aborted || !consumed.response?.ok) {
          return {
            ok: false as const,
            message: consumed.response?.message || abortedMessage(consumed.aborted),
          };
        }
        return {
          ok: true as const,
          accessToken: consumed.response.accessToken,
          ttsModel: consumed.response.ttsModel,
        };
      }
      await sleep(100);
    }
    return { ok: false as const, message: "The temporary Deepgram token timed out." };
  }

  async function ensureSpeech(): Promise<DeepgramSpeech | undefined> {
    if (speechConnected.current && speech.current.isConnected()) return speech.current;
    speechConnected.current = false;
    const token = await temporaryVoiceToken();
    if (!token.ok) {
      setVoiceNote(token.message);
      return undefined;
    }
    try {
      await speech.current.connect(token.accessToken, token.ttsModel);
      speechConnected.current = true;
      setVoiceNote("");
      return speech.current;
    } catch (voiceError) {
      setVoiceNote(`Voice is unavailable; continuing with captions. ${String(voiceError)}`);
      return undefined;
    }
  }

  async function waitIfPaused(run: number): Promise<boolean> {
    while (paused.current && generation.current === run) await sleep(80);
    return generation.current === run;
  }

  async function playLesson(nextLesson: LessonPlan, startIndex = 0, replaceScene = true): Promise<void> {
    const run = ++generation.current;
    paused.current = false;
    setResumeAt(undefined);
    setLesson(nextLesson);
    setError("");
    if (replaceScene) setScene(emptyScene);
    const voicePromise = ensureSpeech();

    for (let index = startIndex; index < nextLesson.beats.length; index += 1) {
      if (!(await waitIfPaused(run))) return;
      const beat = nextLesson.beats[index];
      setActiveBeat(index);
      setCaption(beat.caption);
      setState("speaking");
      const voice = await voicePromise;
      if (generation.current !== run) return;
      const spoken = voice ? voice.speak(beat.spoken_text) : sleep(estimatedSpeechMilliseconds(beat.spoken_text));
      const commandDelay = Math.max(160, Math.min(650, estimatedSpeechMilliseconds(beat.spoken_text) / Math.max(2, beat.commands.length + 1)));

      for (const command of beat.commands) {
        if (!(await waitIfPaused(run))) return;
        setScene((current) => applySceneCommand(current, command));
        await sleep(commandDelay);
      }
      await spoken;
      if (generation.current !== run) return;
      if (beat.pause_after_ms) await sleep(beat.pause_after_ms);
      if (beat.checkpoint && index < nextLesson.beats.length - 1) {
        paused.current = true;
        setResumeAt(index + 1);
        setState("paused");
        setCaption(`${beat.caption}  Take a moment—continue when you’re ready.`);
        return;
      }
    }

    if (generation.current === run) {
      setActiveBeat(nextLesson.beats.length - 1);
      setState("done");
      setCaption(`Answer: ${nextLesson.final_answer}`);
    }
  }

  function interruptTeaching(nextState: TutorState = "paused"): void {
    generation.current += 1;
    paused.current = nextState === "paused";
    speech.current.interrupt();
    setState(nextState);
  }

  async function startLesson(message: string): Promise<void> {
    if (!message.trim() && !selectedImage) {
      setError("Paste an SAT question or upload a clear PNG or JPEG image.");
      return;
    }
    const requestId = ++lessonRequest.current;
    setError("");
    setVoiceNote("");
    setState("thinking");
    setCaption("I’m solving the problem and planning the clearest explanation…");
    setQuestionText(message.trim());
    setLesson(undefined);
    setScene(emptyScene);
    await speech.current.prewarm().catch(() => undefined);
    if (lessonRequest.current !== requestId) return;

    const { response, aborted } = await session.mutators.startLesson(
      {
        questionText: message.trim(),
        sourceKind: selectedImage ? "image" : "text",
        sourceMediaType: selectedImage?.mediaType || "",
        sourceBase64: selectedImage?.base64 || "",
      },
      { idempotencyKey: crypto.randomUUID() },
    );
    if (aborted || !response) {
      if (lessonRequest.current !== requestId) return;
      setState("error");
      setError(abortedMessage(aborted));
      return;
    }
    if (lessonRequest.current !== requestId) return;
    const completed = await waitForLesson(response.generation, requestId);
    if (!completed || lessonRequest.current !== requestId) return;
    if (completed.status === "error") {
      setState("error");
      setError(completed.errorMessage || "The tutor could not prepare this lesson.");
      return;
    }
    const parsed = parseLesson(completed.lessonJson);
    if (!parsed) {
      setState("error");
      setError("The model returned a lesson the teaching canvas could not validate.");
      return;
    }
    await playLesson(parsed, 0, true);
  }

  async function askFollowup(message: string): Promise<void> {
    if (!lesson || !message.trim()) return;
    const requestId = ++lessonRequest.current;
    listener.current.stop();
    interruptTeaching("thinking");
    setCaption("I’m rethinking that part and preparing a different explanation…");
    setError("");
    const { response, aborted } = await session.mutators.startReplan(
      {
        studentMessage: message.trim(),
        completedBeatIndex: Math.max(0, activeBeat),
        sourceMediaType: selectedImage?.mediaType || "",
        sourceBase64: selectedImage?.base64 || "",
      },
      { idempotencyKey: crypto.randomUUID() },
    );
    if (aborted || !response) {
      if (lessonRequest.current !== requestId) return;
      setState("error");
      setError(abortedMessage(aborted));
      return;
    }
    if (lessonRequest.current !== requestId) return;
    const completed = await waitForLesson(response.generation, requestId);
    if (!completed || lessonRequest.current !== requestId) return;
    if (completed.status === "error") {
      setState("error");
      setError(completed.errorMessage || "The tutor could not revise this explanation.");
      return;
    }
    const parsed = parseLesson(completed.lessonJson);
    if (!parsed) {
      setState("error");
      setError("The revised explanation could not be validated.");
      return;
    }
    // A follow-up is rendered as its own inline activity card. Start its board
    // clean; the previous assistant message keeps its completed scene above.
    await playLesson(parsed, 0, true);
  }

  async function checkWork(work: string, questionText: string): Promise<void> {
    if (!work.trim()) return;
    const requestId = ++lessonRequest.current;
    listener.current.stop();
    interruptTeaching("thinking");
    setError("");
    setVoiceNote("");
    setCaption("I’m reading your steps and checking them against my own working…");
    const { response, aborted } = await session.mutators.checkWork(
      { studentWork: work.trim(), questionText: questionText.trim() },
      { idempotencyKey: crypto.randomUUID() },
    );
    if (aborted || !response) {
      if (lessonRequest.current !== requestId) return;
      setState("error");
      setError(abortedMessage(aborted));
      return;
    }
    if (lessonRequest.current !== requestId) return;
    const completed = await waitForLesson(response.generation, requestId);
    if (!completed || lessonRequest.current !== requestId) return;
    if (completed.status === "error") {
      setState("error");
      setError(completed.errorMessage || "The tutor could not check this working.");
      return;
    }
    const parsed = parseLesson(completed.lessonJson);
    if (!parsed) {
      setState("error");
      setError("The feedback could not be validated.");
      return;
    }
    await playLesson(parsed, 0, true);
  }

  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (state === "thinking") return;
    const message = draft;
    const onBoard = boardWork.trim();
    // With working on the board, the text box names the question it belongs
    // to. With an empty board, the text box is the working itself.
    const working = checking ? (onBoard || message) : message;
    if (!working.trim() && !selectedImage) return;
    setDraft("");
    if (checking) {
      setBoardCollapsed(true);
      await checkWork(working, onBoard ? message : "");
    }
    else if (lesson) await askFollowup(message);
    else await startLesson(message);
  }

  async function selectQuestionImage(file: File | undefined): Promise<void> {
    if (!file) return;
    try {
      setError("");
      setSelectedImage(await prepareQuestionImage(file));
    } catch (uploadError) {
      setSelectedImage(undefined);
      setError(uploadError instanceof Error ? uploadError.message : "The image could not be added.");
    }
  }

  async function toggleMicrophone(): Promise<void> {
    if (state === "listening") {
      listener.current.stop();
      setState(lesson ? "paused" : "idle");
      return;
    }
    interruptTeaching("listening");
    setCaption("Listening…");
    const token = await temporaryVoiceToken();
    if (!token.ok) {
      setState("error");
      setError(token.message);
      return;
    }
    try {
      await listener.current.start(token.accessToken, {
        onSpeechStart: () => {
          interruptTeaching("listening");
          setCaption("I’m listening…");
        },
        onTranscript: (transcript, final) => {
          setDraft(transcript);
          setCaption(transcript);
          if (final) {
            listener.current.stop();
            void askFollowup(transcript);
          }
        },
        onError: (message) => {
          setError(`Microphone transcription stopped: ${message}`);
          setState("error");
        },
      });
    } catch (microphoneError) {
      setState("error");
      setError(`Microphone unavailable. You can still type your question. ${String(microphoneError)}`);
    }
  }

  async function togglePause(): Promise<void> {
    if (state === "paused" && lesson) {
      paused.current = false;
      await speech.current.resume();
      if (resumeAt !== undefined) await playLesson(lesson, resumeAt, false);
      else await playLesson(lesson, Math.max(0, activeBeat), false);
      return;
    }
    paused.current = true;
    await speech.current.pause();
    setState("paused");
  }

  async function replay(): Promise<void> {
    if (!lesson) return;
    speech.current.interrupt();
    await playLesson(lesson, 0, true);
  }

  async function clearLesson(): Promise<void> {
    suppressSnapshotRestore.current = true;
    lessonRequest.current += 1;
    interruptTeaching("idle");
    listener.current.stop();
    setLesson(undefined);
    setScene(emptyScene);
    setQuestionText("");
    setDraft("");
    setCaption("");
    setError("");
    setVoiceNote("");
    setSelectedImage(undefined);
    setActiveBeat(-1);
    setResumeAt(undefined);
    await session.mutators.reset(undefined, { idempotencyKey: crypto.randomUUID() });
  }

  const composerPlaceholder = checking
    ? (boardWork.trim()
        ? "Optional: paste the question this working is for…"
        : "Write your steps on the whiteboard above, or type them here…")
    : lesson
      ? "Ask why, interrupt, or request a different explanation…"
      : "Ask any SAT question, paste the choices, or upload an image…";
  const currentGeneration = snapshot?.generation ?? 0;
  const pinned = shownLesson
    ? messages.find((message) => message.id === shownLesson)
    : undefined;
  const pinnedLesson = pinned?.lessonJson ? parseLesson(pinned.lessonJson) : undefined;
  const panelIsLive = !pinnedLesson;
  const panelLesson = pinnedLesson ?? lesson;
  const panelScene = pinnedLesson ? completedScene(pinnedLesson) : scene;
  const hasCurrentAssistant = messages.some(
    (message) => message.role === "assistant" && message.generation === currentGeneration,
  );

  return (
    <main className="app-shell chat-app-shell">
      <header className="topbar">
        <a className="brand" href="/dashboard" aria-label="SAT Live Tutor dashboard" onClick={(event) => { event.preventDefault(); navigateTo("/dashboard"); }}>
          <span className="brand-mark">S</span>
          <span>SAT Tutor</span>
        </a>
        <div className="classroom-header-actions">
          <button type="button" onClick={() => void clearLesson()}>New chat</button>
          <Status state={state} />
        </div>
      </header>

      <div className="workspace">
        <div className="chat-column">
      <section className="chat-thread" aria-label="SAT tutor conversation">
        {messages.length === 0 && state === "idle" && (
          <div className="chat-welcome">
            <div className="tutor-avatar tutor-avatar-large">S</div>
            <p className="chat-welcome-kicker">Your personal SAT teacher</p>
            <h1>What are you working on?</h1>
            <p>Send any SAT question. I’ll talk through it naturally and open a live visual lesson only when it helps.</p>
          </div>
        )}

        {messages.map((message) => {
          const messageLesson = message.lessonJson ? parseLesson(message.lessonJson) : undefined;
          const isActiveActivity = Boolean(
            lesson && message.role === "assistant" && message.generation === currentGeneration,
          );
          const activityScene = isActiveActivity && lesson
            ? scene
            : messageLesson
              ? completedScene(messageLesson)
              : emptyScene;
          const visibleLesson = isActiveActivity && lesson ? lesson : messageLesson;
          return (
            <article
              className={`chat-turn chat-turn-${message.role}`}
              key={message.id}
              aria-label={message.role === "user" ? "You" : "SAT Tutor"}
            >
              {message.role === "assistant" && <div className="tutor-avatar">S</div>}
              <div className={`chat-bubble ${visibleLesson && hasTeachingActivity(visibleLesson) ? "has-activity" : ""}`}>
                <div className="chat-message-label">{message.role === "user" ? "You" : "SAT Tutor"}</div>
                {message.sourceKind === "image" && selectedImage && message.role === "user" && (
                  <div className="chat-upload-preview">
                    <img src={selectedImage.dataUrl} alt="Uploaded SAT question" />
                    <span>Question image</span>
                  </div>
                )}
                <MessageText text={message.text} />

                {visibleLesson && hasTeachingActivity(visibleLesson) && (
                  <button
                    type="button"
                    className={`activity-chip ${isActiveActivity ? "is-active" : ""}`}
                    onClick={() => setShownLesson(isActiveActivity ? undefined : message.id)}
                  >
                    <i />
                    {isActiveActivity ? "Showing on the board" : "View this explanation"}
                  </button>
                )}
              </div>
            </article>
          );
        })}

        {state === "thinking" && !hasCurrentAssistant && (
          <article className="chat-turn chat-turn-assistant" aria-label="SAT Tutor is thinking">
            <div className="tutor-avatar">S</div>
            <div className="chat-bubble chat-thinking-bubble">
              <div className="chat-message-label">SAT Tutor</div>
              <div className="thinking-dots" aria-hidden="true"><i /><i /><i /></div>
              <p>{caption || "I’m solving this and choosing the clearest way to teach it…"}</p>
            </div>
          </article>
        )}

        {error && state === "error" && !hasCurrentAssistant && (
          <article className="chat-turn chat-turn-assistant" aria-label="SAT Tutor error">
            <div className="tutor-avatar">S</div>
            <div className="chat-bubble chat-error-bubble"><MessageText text={error} /></div>
          </article>
        )}
        <div ref={conversationEnd} />
      </section>

      <form className="composer chat-composer" onSubmit={(event) => void submit(event)}>
        {/* An unlabelled icon hid this entirely; the two modes are now named. */}
        <div className="composer-modes" role="group" aria-label="What do you want the tutor to do?">
          <button
            type="button"
            className={!checking ? "is-active" : ""}
            aria-pressed={!checking}
            onClick={() => setChecking(false)}
            disabled={state === "thinking"}
          >
            Ask a question
          </button>
          <button
            type="button"
            className={checking ? "is-active" : ""}
            aria-pressed={checking}
            onClick={() => setChecking(true)}
            disabled={state === "thinking"}
          >
            Check my work
          </button>
        </div>

        {checking && (
          <Whiteboard
            onExtract={setBoardWork}
            extracted={boardWork}
            collapsed={boardCollapsed}
            onToggle={() => setBoardCollapsed((current) => !current)}
          />
        )}

        {selectedImage && (
          <div className="image-attachment">
            <img src={selectedImage.dataUrl} alt="Selected SAT question" />
            <span><strong>{lesson || state !== "idle" ? "Current question image" : "Ready to send"}</strong>{selectedImage.name}</span>
            {!lesson && <button type="button" onClick={() => setSelectedImage(undefined)} aria-label="Remove question image">×</button>}
          </div>
        )}
        <div className="composer-row">
          <input
            ref={imageInput}
            className="visually-hidden"
            type="file"
            accept="image/png,image/jpeg"
            aria-label="Upload an SAT question image"
            onChange={(event) => {
              void selectQuestionImage(event.target.files?.[0]);
              event.currentTarget.value = "";
            }}
          />
          <button
            className="icon-button upload-button"
            type="button"
            aria-label="Upload an SAT question image"
            title="Upload a PNG or JPEG question"
            onClick={() => imageInput.current?.click()}
            disabled={Boolean(lesson) || state === "thinking"}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <rect x="3.5" y="4" width="17" height="16" rx="3" />
              <circle cx="9" cy="9" r="1.5" />
              <path d="m5.5 17 4.2-4.2 3.1 3.1 2.2-2.2 3.5 3.3" />
            </svg>
          </button>
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder={composerPlaceholder}
            rows={1}
            aria-label="Message the SAT tutor"
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
          />
          <button
            className={`icon-button mic-button ${state === "listening" ? "mic-live" : ""}`}
            type="button"
            aria-label={state === "listening" ? "Stop listening" : "Speak to the tutor"}
            title={state === "listening" ? "Stop listening" : "Speak to the tutor"}
            onClick={() => void toggleMicrophone()}
            disabled={!lesson || state === "thinking"}
          >
            <span className="mic-glyph" />
          </button>
          <button
            className="teach-button"
            type="submit"
            disabled={
              state === "thinking"
              || (checking
                ? !boardWork.trim() && !draft.trim()
                : lesson
                  ? !draft.trim()
                  : !draft.trim() && !selectedImage)
            }
          >
            {state === "thinking" ? "Thinking…" : checking ? "Check my work" : "Send"}
          </button>
        </div>
        <div className="composer-hint">
          {voiceNote
            || (checking
              ? (boardWork.trim()
                ? "I’ll mark the first step that breaks. Add the question above if it isn’t the one we’re on."
                : "Paste your own steps. I’ll mark the first one that breaks, not solve it for you.")
              : lesson
                ? "Interrupt at any time—type or use the microphone."
                : "Questions, answer choices, and clear PNG/JPEG images are supported.")}
        </div>
      </form>
        </div>

        <aside className="board-panel" aria-label="Teaching board">
          {panelLesson ? (
            <>
              <div className="board-panel-header">
                <span>
                  <i />
                  {isWorkCheck(panelLesson)
                    ? "Your working, checked"
                    : panelIsLive ? "Live visual explanation" : "Earlier explanation"}
                </span>
                <div className="board-panel-controls">
                  {panelIsLive ? (
                    <>
                      <button type="button" onClick={() => void togglePause()} disabled={state === "thinking" || state === "listening"}>
                        {state === "paused" ? "Continue" : "Pause"}
                      </button>
                      <button type="button" onClick={() => void replay()} disabled={state === "thinking" || state === "listening"}>Replay</button>
                    </>
                  ) : (
                    <button type="button" onClick={() => setShownLesson(undefined)}>Back to live</button>
                  )}
                </div>
              </div>
              <TeachingCanvas
                questionLabel={isWorkCheck(panelLesson) ? "Checked against" : "SAT question"}
                questionText={panelIsLive ? (questionText || snapshot?.questionText || panelLesson.question_summary) : panelLesson.question_summary}
                sourceImageUrl={panelIsLive ? selectedImage?.dataUrl : undefined}
                sourceImageSize={panelIsLive && selectedImage ? { width: selectedImage.width, height: selectedImage.height } : undefined}
                commands={panelScene.elements}
                camera={panelScene.camera}
                caption={panelIsLive ? caption : `Answer: ${panelLesson.final_answer}`}
                tutorState={panelIsLive ? state : "done"}
                errorMessage={panelIsLive ? error : ""}
              />
            </>
          ) : (
            <div className="board-empty">
              <div className="empty-board-icon"><span>2x + 3 = 11</span><i /></div>
              <p>The board opens here when a visual helps.</p>
            </div>
          )}
        </aside>
      </div>
    </main>
  );
}
