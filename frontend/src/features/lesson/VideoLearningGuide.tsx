import { useEffect, useMemo, useRef, useState } from "react";

import type { VideoCheckpoint, VideoGuide } from "../../api";

type VideoLearningGuideProps = {
  guide: VideoGuide;
  mediaUrl: string;
  onQuizResult: (result: Record<string, unknown>) => void;
};

type PlaybackController = {
  pause: () => void;
  play: () => void;
  seek: (seconds: number) => void;
};

type YouTubePlayer = {
  destroy: () => void;
  getCurrentTime: () => number;
  pauseVideo: () => void;
  playVideo: () => void;
  seekTo: (seconds: number, allowSeekAhead: boolean) => void;
};

type YouTubePlayerEvent = {
  data: number;
  target: YouTubePlayer;
};

type YouTubeApi = {
  Player: new (
    element: HTMLElement,
    options: {
      videoId: string;
      playerVars: Record<string, number | string>;
      events: {
        onReady: (event: YouTubePlayerEvent) => void;
        onStateChange: (event: YouTubePlayerEvent) => void;
      };
    },
  ) => YouTubePlayer;
  PlayerState: {
    ENDED: number;
    PLAYING: number;
  };
};

declare global {
  interface Window {
    YT?: YouTubeApi;
    onYouTubeIframeAPIReady?: () => void;
  }
}

let youtubeApiPromise: Promise<YouTubeApi> | null = null;

function loadYouTubeApi(): Promise<YouTubeApi> {
  if (window.YT?.Player) return Promise.resolve(window.YT);
  if (youtubeApiPromise) return youtubeApiPromise;

  youtubeApiPromise = new Promise((resolve, reject) => {
    const previousReady = window.onYouTubeIframeAPIReady;
    const timeout = window.setTimeout(
      () => reject(new Error("YouTube player took too long to load.")),
      15_000,
    );

    window.onYouTubeIframeAPIReady = () => {
      previousReady?.();
      if (!window.YT) return;
      window.clearTimeout(timeout);
      resolve(window.YT);
    };

    if (!document.querySelector('script[src="https://www.youtube.com/iframe_api"]')) {
      const script = document.createElement("script");
      script.src = "https://www.youtube.com/iframe_api";
      script.async = true;
      script.onerror = () => {
        window.clearTimeout(timeout);
        reject(new Error("Could not load the YouTube player."));
      };
      document.head.appendChild(script);
    }
  });

  return youtubeApiPromise;
}

function formatTime(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const secs = whole % 60;
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`
    : `${minutes}:${String(secs).padStart(2, "0")}`;
}

function loadProgress(sourceId: string): number {
  try {
    return Number(window.localStorage.getItem(`hituto-video-progress:${sourceId}`) ?? 0) || 0;
  } catch {
    return 0;
  }
}

export function isContinuousPlaybackAdvance(
  nextTime: number,
  maxWatched: number,
  lastObservedTime: number,
  elapsedMs: number,
): boolean {
  if (nextTime <= maxWatched) return false;
  const allowance = Math.min(15, Math.max(3, (elapsedMs / 1000) * 2.5 + 1));
  return (
    nextTime <= maxWatched + allowance &&
    nextTime <= lastObservedTime + allowance
  );
}

export function VideoLearningGuide({ guide, mediaUrl, onQuizResult }: VideoLearningGuideProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const playbackRef = useRef<PlaybackController | null>(null);
  const checkpointRefs = useRef<Record<string, HTMLElement | null>>({});
  const nativeSeekingRef = useRef(false);
  const lastObservedTimeRef = useRef(0);
  const lastPlaybackUpdateAtRef = useRef(performance.now());
  const initialProgress = useMemo(() => loadProgress(guide.source_id), [guide.source_id]);
  const triggeredRef = useRef(
    new Set(
      guide.checkpoints
        .filter((checkpoint) => checkpoint.at_seconds <= initialProgress)
        .map((checkpoint) => checkpoint.id),
    ),
  );
  const [currentTime, setCurrentTime] = useState(0);
  const [maxWatched, setMaxWatched] = useState(initialProgress);
  const [activeCheckpoint, setActiveCheckpoint] = useState<string | null>(null);

  const unlockedCount = guide.checkpoints.filter(
    (checkpoint) => checkpoint.at_seconds <= maxWatched,
  ).length;
  const progress = guide.duration_seconds
    ? Math.min(100, Math.round((maxWatched / guide.duration_seconds) * 100))
    : 0;

  function handleTimeUpdate(nextTime: number, allowAdvance = true) {
    const now = performance.now();
    const elapsedMs = Math.max(0, now - lastPlaybackUpdateAtRef.current);
    const lastObservedTime = lastObservedTimeRef.current;
    lastPlaybackUpdateAtRef.current = now;
    lastObservedTimeRef.current = nextTime;
    setCurrentTime(nextTime);
    if (
      !allowAdvance ||
      !isContinuousPlaybackAdvance(nextTime, maxWatched, lastObservedTime, elapsedMs)
    ) {
      return;
    }

    setMaxWatched(nextTime);
    try {
      window.localStorage.setItem(
        `hituto-video-progress:${guide.source_id}`,
        String(nextTime),
      );
    } catch {
      // Progress persistence is helpful, never required for playback.
    }

    const reached = guide.checkpoints.find(
      (checkpoint) =>
        checkpoint.at_seconds <= nextTime && !triggeredRef.current.has(checkpoint.id),
    );
    if (!reached) return;
    triggeredRef.current.add(reached.id);
    setActiveCheckpoint(reached.id);
    playbackRef.current?.pause();
    window.setTimeout(() => {
      checkpointRefs.current[reached.id]?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 80);
  }

  function replayFrom(checkpoint: VideoCheckpoint) {
    const playback = playbackRef.current;
    if (!playback) return;
    playback.seek(Math.max(0, checkpoint.at_seconds - 6));
    playback.play();
  }

  function connectNativePlayer(video: HTMLVideoElement | null) {
    videoRef.current = video;
    playbackRef.current = video
      ? {
          pause: () => video.pause(),
          play: () => {
            void video.play();
          },
          seek: (seconds) => {
            video.currentTime = seconds;
          },
        }
      : null;
  }

  return (
    <section className="bg-bone px-3 pb-3 pt-3 font-sans text-ink sm:px-5 sm:pb-5 sm:pt-5" aria-labelledby="video-guide-title">
      <div className="mx-auto grid max-w-7xl gap-4 lg:grid-cols-[minmax(0,1.45fr)_minmax(300px,0.75fr)] lg:items-stretch">
        <div className="min-w-0 rounded-3xl bg-ink p-4 text-white shadow-panel sm:p-5">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-lime">
                Video lesson
              </p>
              <h2 id="video-guide-title" className="mt-1 font-archivo text-xl font-semibold tracking-[-0.03em] sm:text-2xl">
                {guide.title}
              </h2>
            </div>
            <div className="flex shrink-0 items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-2 text-[11px] font-semibold text-white/80">
              <span className="material-symbols-outlined text-[16px] text-lime" aria-hidden="true">schedule</span>
              <span>{formatTime(currentTime)}</span>
              <span className="text-white/40">of</span>
              <span>{formatTime(guide.duration_seconds)}</span>
            </div>
          </div>

          {guide.playback_kind === "youtube" && guide.youtube_video_id ? (
            <YouTubePlayback
              videoId={guide.youtube_video_id}
              onController={(controller) => {
                playbackRef.current = controller;
              }}
              onTimeUpdate={handleTimeUpdate}
            />
          ) : (
            <video
              ref={connectNativePlayer}
              src={mediaUrl}
              controls
              playsInline
              preload="metadata"
              onSeeking={() => {
                nativeSeekingRef.current = true;
              }}
              onSeeked={(event) => {
                nativeSeekingRef.current = false;
                lastObservedTimeRef.current = event.currentTarget.currentTime;
                lastPlaybackUpdateAtRef.current = performance.now();
                setCurrentTime(event.currentTarget.currentTime);
              }}
              onTimeUpdate={(event) =>
                handleTimeUpdate(
                  event.currentTarget.currentTime,
                  !nativeSeekingRef.current,
                )
              }
              className="aspect-video w-full rounded-xl bg-black object-contain"
            >
              Your browser does not support this training video.
            </video>
          )}

          <div className="mt-4 flex items-center gap-4">
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-3">
                <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-white/50">Video progress</span>
                <span className="text-[11px] font-semibold text-white/80">{progress}% watched</span>
              </div>
              <div className="mt-2 h-2 overflow-hidden rounded-full bg-white/15">
                <div
                  className="h-full rounded-full bg-lime transition-[width] duration-300"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          </div>
        </div>

        <aside className="min-h-[340px] rounded-3xl border border-ink/5 bg-white p-4 text-ink shadow-chip sm:p-5 lg:flex lg:max-h-[min(72vh,720px)] lg:flex-col">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-faint">
                Lesson checkpoints
              </p>
              <h3 className="mt-1 font-archivo text-lg font-semibold tracking-[-0.01em]">Learn while it plays</h3>
            </div>
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-mint text-lime" aria-hidden="true">
              <span className="material-symbols-outlined text-[21px]">conversion_path</span>
            </span>
          </div>

          <div className="mt-4 flex items-center justify-between gap-3 rounded-2xl bg-mint px-3 py-2.5 text-lime-dark">
            <span className="text-[10px] font-semibold uppercase tracking-[0.13em]">Ready as you watch</span>
            <span className="rounded-full bg-white px-2.5 py-1 text-[10px] font-semibold">
              {unlockedCount}/{guide.checkpoints.length} ready
            </span>
          </div>

          <div className="mt-4 space-y-3 lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:pr-1">
            {guide.checkpoints.map((checkpoint) => {
              const unlocked = checkpoint.at_seconds <= maxWatched;
              return (
                <article
                  key={checkpoint.id}
                  ref={(node) => {
                    checkpointRefs.current[checkpoint.id] = node;
                  }}
                  className={`rounded-2xl border p-4 transition ${
                    unlocked
                      ? activeCheckpoint === checkpoint.id
                        ? "border-lime/30 bg-mint text-ink"
                        : "border-ink/5 bg-white text-ink shadow-chip"
                      : "border-ink/5 bg-sand/60 text-ink-soft"
                  }`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.12em]">
                      <span className="material-symbols-outlined text-[16px]" aria-hidden="true">
                        {unlocked
                          ? checkpoint.kind === "quiz"
                            ? "quiz"
                            : checkpoint.kind === "visual"
                              ? "schema"
                              : "auto_stories"
                          : "lock"}
                      </span>
                      {unlocked
                        ? activeCheckpoint === checkpoint.id
                          ? `Now · ${checkpoint.kind}`
                          : checkpoint.kind
                        : "Coming up"}
                    </span>
                    <button
                      type="button"
                      disabled={!unlocked}
                      onClick={() => replayFrom(checkpoint)}
                      className={`rounded-full px-2.5 py-1 text-[10px] font-semibold transition disabled:cursor-default ${
                        unlocked
                          ? "bg-ink/5 text-ink-soft hover:bg-ink/10 hover:text-ink"
                          : "bg-ink/5 text-ink-faint"
                      }`}
                      title={unlocked ? "Replay the explanation" : undefined}
                    >
                      {formatTime(checkpoint.at_seconds)}
                    </button>
                  </div>
                  {unlocked ? (
                    <UnlockedCheckpoint checkpoint={checkpoint} onQuizResult={onQuizResult} />
                  ) : (
                    <div className="mt-2">
                      <p className="font-archivo text-sm font-semibold tracking-[-0.01em] text-ink">
                        A quick idea check is waiting
                      </p>
                      <p className="mt-1 text-[11px] font-medium text-ink-soft">
                        Keep watching — this opens at {formatTime(checkpoint.at_seconds)}.
                      </p>
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        </aside>
      </div>
    </section>
  );
}

function YouTubePlayback({
  videoId,
  onController,
  onTimeUpdate,
}: {
  videoId: string;
  onController: (controller: PlaybackController | null) => void;
  onTimeUpdate: (seconds: number) => void;
}) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const onControllerRef = useRef(onController);
  const onTimeUpdateRef = useRef(onTimeUpdate);
  const [error, setError] = useState<string | null>(null);

  onControllerRef.current = onController;
  onTimeUpdateRef.current = onTimeUpdate;

  useEffect(() => {
    let cancelled = false;
    let player: YouTubePlayer | null = null;
    let timer: number | null = null;

    function stopClock() {
      if (timer !== null) window.clearInterval(timer);
      timer = null;
    }

    function tick() {
      if (player) onTimeUpdateRef.current(player.getCurrentTime());
    }

    void loadYouTubeApi()
      .then((YT) => {
        if (cancelled || !hostRef.current) return;
        player = new YT.Player(hostRef.current, {
          videoId,
          playerVars: {
            origin: window.location.origin,
            playsinline: 1,
            rel: 0,
          },
          events: {
            onReady: (event) => {
              if (cancelled) return;
              player = event.target;
              onControllerRef.current({
                pause: () => player?.pauseVideo(),
                play: () => player?.playVideo(),
                seek: (seconds) => player?.seekTo(seconds, true),
              });
            },
            onStateChange: (event) => {
              player = event.target;
              if (event.data === YT.PlayerState.PLAYING) {
                stopClock();
                tick();
                timer = window.setInterval(tick, 350);
              } else {
                tick();
                stopClock();
              }
            },
          },
        });
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason));
      });

    return () => {
      cancelled = true;
      stopClock();
      onControllerRef.current(null);
      player?.destroy();
    };
  }, [videoId]);

  return (
    <div className="relative aspect-video w-full overflow-hidden rounded-xl bg-ink">
      <div ref={hostRef} className="absolute inset-0 h-full w-full" />
      {error && (
        <div className="absolute inset-0 grid place-items-center bg-ink p-6 text-center text-sm font-semibold text-white">
          {error}
        </div>
      )}
    </div>
  );
}

function UnlockedCheckpoint({
  checkpoint,
  onQuizResult,
}: {
  checkpoint: VideoCheckpoint;
  onQuizResult: (result: Record<string, unknown>) => void;
}) {
  const [selected, setSelected] = useState<number | null>(null);
  const startedAt = useRef(Date.now());
  const isCorrect = selected !== null && selected === checkpoint.answer_index;

  function answer(index: number) {
    if (selected !== null) return;
    setSelected(index);
    onQuizResult({
      toolName: "create_quiz",
      score: index === checkpoint.answer_index ? 1 : 0,
      total: 1,
      attempt: 1,
      durationMs: Date.now() - startedAt.current,
    });
  }

  return (
    <div className="mt-2">
      <h4 className="font-archivo text-base font-semibold leading-snug tracking-[-0.01em]">{checkpoint.title}</h4>
      {checkpoint.prompt && <p className="mt-1 text-[12px] font-medium leading-relaxed text-ink-soft">{checkpoint.prompt}</p>}

      {checkpoint.kind === "quiz" ? (
        <div className="mt-3 space-y-2">
          {checkpoint.options.map((option, index) => {
            const chosen = selected === index;
            const correct = selected !== null && checkpoint.answer_index === index;
            return (
              <button
                key={`${checkpoint.id}-${index}`}
                type="button"
                onClick={() => answer(index)}
                disabled={selected !== null}
                className={`flex min-h-11 w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-[12px] font-semibold transition ${
                  correct
                    ? "bg-mint text-lime-dark"
                    : chosen
                      ? "bg-coral-soft text-coral-dark"
                      : "bg-sand text-ink hover:bg-ink/5"
                }`}
              >
                <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-ink/10 text-[10px]">
                  {String.fromCharCode(65 + index)}
                </span>
                <span>{option}</span>
              </button>
            );
          })}
          {selected !== null && (
            <p className={`text-[11px] font-semibold ${isCorrect ? "text-lime-dark" : "text-coral-dark"}`}>
              {isCorrect ? "Correct. " : "Not quite. "}
              {checkpoint.explanation}
            </p>
          )}
        </div>
      ) : checkpoint.kind === "visual" ? (
        <VisualSummary checkpoint={checkpoint} />
      ) : (
        checkpoint.body && <p className="mt-3 text-[12px] font-medium leading-relaxed text-ink-soft">{checkpoint.body}</p>
      )}
    </div>
  );
}

function VisualSummary({ checkpoint }: { checkpoint: VideoCheckpoint }) {
  const points = checkpoint.visual_points.length
    ? checkpoint.visual_points
    : checkpoint.body.split(/(?<=[.!?])\s+/).filter(Boolean).slice(0, 4);
  return (
    <div className="mt-3 grid gap-2" aria-label="Visual concept summary">
      {points.map((point, index) => (
        <div key={`${checkpoint.id}-point-${index}`} className="flex items-center gap-3 rounded-xl bg-sand px-3 py-2.5">
          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-ink text-[11px] font-semibold text-white">
            {index + 1}
          </span>
          <span className="text-[12px] font-semibold leading-snug text-ink">{point}</span>
          {index < points.length - 1 && (
            <span className="material-symbols-outlined ml-auto text-[16px] text-ink-faint" aria-hidden="true">
              arrow_downward
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
