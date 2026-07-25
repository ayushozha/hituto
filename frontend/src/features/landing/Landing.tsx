import { useEffect, useState, type ReactNode } from "react";
import { Show, SignInButton } from "@clerk/react";

import { BrandMark } from "../../components/BrandMark";
import { ClerkAuthControls } from "../../components/ClerkAuthControls";
import { Mascot } from "../../components/Mascot";
import { hashFor } from "../../routing";

type LandingProps = {
  onStart: () => void;
  onSignIn: () => void;
};

function scrollToSection(id: string) {
  const behavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
  document.getElementById(id)?.scrollIntoView({ behavior, block: "start" });
}

function scrollToTop() {
  const behavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
  window.scrollTo({ top: 0, behavior });
}

export function Landing({ onStart, onSignIn }: LandingProps) {
  return (
    <div className="min-h-full overflow-x-clip bg-bone font-sans text-ink selection:bg-cream selection:text-brand-dark">
      <LandingHeader onStart={onStart} onSignIn={onSignIn} />
      <main>
        <HeroSection onStart={onStart} />
        <LessonPreviewSection />
        <FeaturesSection />
        <CtaSection onStart={onStart} />
      </main>
      <LandingFooter />
    </div>
  );
}

function LandingHeader({ onStart }: LandingProps) {
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    if (!menuOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [menuOpen]);

  const runMobileAction = (action: () => void) => {
    setMenuOpen(false);
    action();
  };

  return (
    <header className="sticky top-0 z-50 border-b border-ink/5 bg-bone/85 backdrop-blur">
      <div className="relative mx-auto grid h-[4.5rem] max-w-6xl grid-cols-[1fr_auto] items-center gap-3 px-5 sm:px-8 md:grid-cols-[1fr_auto_1fr]">
        <button type="button" onClick={scrollToTop} className="flex min-h-12 shrink-0 items-center gap-2.5 justify-self-start text-left">
          <BrandMark className="!h-9 !w-9 rounded-xl" />
          <span className="text-lg font-semibold tracking-[-0.01em]">Hi Tuto</span>
        </button>

        <nav className="hidden items-center justify-center gap-8 md:flex" aria-label="Main navigation">
          <NavItem onClick={() => scrollToSection("study-kit")}>Features</NavItem>
          <NavItem onClick={() => { window.location.hash = hashFor({ kind: "pricing" }); }}>Pricing</NavItem>
          <NavItem onClick={() => { window.location.hash = hashFor({ kind: "waitlist" }); }}>Waitlist</NavItem>
        </nav>

        <div className="flex shrink-0 items-center justify-self-end gap-1 sm:gap-2">
          <div className="hidden sm:block">
            <Show when="signed-out">
              <ClerkAuthControls variant="signIn" />
            </Show>
          </div>
          <Show when="signed-out">
            <PrimaryButton onClick={onStart} className="min-h-11 px-5">
              <span className="hidden sm:inline">Start free</span>
              <span className="sm:hidden">Start</span>
            </PrimaryButton>
          </Show>
          <Show when="signed-in">
            <PrimaryButton
              onClick={() => { window.location.hash = hashFor({ kind: "dashboard" }); }}
              className="min-h-11 px-5"
            >
              <span className="hidden sm:inline">Open dashboard</span>
              <span className="sm:hidden">Dashboard</span>
            </PrimaryButton>
          </Show>
          <button
            type="button"
            onClick={() => setMenuOpen((open) => !open)}
            className="grid h-11 w-11 place-items-center rounded-full border border-ink/10 bg-white text-ink shadow-chip transition hover:border-ink/25 md:hidden"
            aria-expanded={menuOpen}
            aria-controls="mobile-navigation"
            aria-label={menuOpen ? "Close navigation" : "Open navigation"}
          >
            <span className="material-symbols-outlined text-[21px]" aria-hidden="true">
              {menuOpen ? "close" : "menu"}
            </span>
          </button>
        </div>

        {menuOpen ? (
          <nav
            id="mobile-navigation"
            className="absolute inset-x-5 top-[calc(100%+0.5rem)] z-50 rounded-3xl border border-ink/5 bg-white p-2 shadow-panel sm:left-auto sm:right-8 sm:w-72 md:hidden"
            aria-label="Mobile navigation"
          >
            <MobileNavItem icon="grid_view" onClick={() => runMobileAction(() => scrollToSection("study-kit"))}>
              Features
            </MobileNavItem>
            <MobileNavItem icon="sell" onClick={() => runMobileAction(() => { window.location.hash = hashFor({ kind: "pricing" }); })}>
              Pricing
            </MobileNavItem>
            <MobileNavItem icon="mail" onClick={() => runMobileAction(() => { window.location.hash = hashFor({ kind: "waitlist" }); })}>
              Waitlist
            </MobileNavItem>
            <div className="mt-1 border-t border-ink/5 px-2 py-2">
              <Show when="signed-out">
                <SignInButton mode="modal">
                  <button
                    type="button"
                    onClick={() => setMenuOpen(false)}
                    className="flex min-h-12 w-full items-center gap-3 rounded-2xl px-2 text-left text-sm font-semibold text-ink-soft transition hover:bg-bone hover:text-ink"
                  >
                    <span className="material-symbols-outlined text-[19px] text-brand" aria-hidden="true">login</span>
                    Sign in
                  </button>
                </SignInButton>
              </Show>
            </div>
          </nav>
        ) : null}
      </div>
    </header>
  );
}

function NavItem({ onClick, children }: { onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex min-h-12 items-center text-sm font-medium text-ink-soft transition hover:text-ink"
    >
      {children}
    </button>
  );
}

function MobileNavItem({ icon, onClick, children }: { icon: string; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex min-h-12 w-full items-center gap-3 rounded-2xl px-4 text-left text-sm font-semibold text-ink-soft transition hover:bg-bone hover:text-ink"
    >
      <span className="material-symbols-outlined text-[19px] text-brand" aria-hidden="true">{icon}</span>
      {children}
      <span className="material-symbols-outlined ml-auto text-[17px] text-ink-faint" aria-hidden="true">arrow_forward</span>
    </button>
  );
}

function HeroSection({ onStart }: { onStart: () => void }) {
  return (
    <section className="relative">
      <div
        className="pointer-events-none absolute inset-x-0 top-0 h-[620px] bg-[radial-gradient(60%_55%_at_50%_0%,rgba(22,163,74,0.08),transparent_72%)]"
        aria-hidden="true"
      />
      <HeroFloaters />

      <div className="relative mx-auto max-w-4xl px-5 pb-16 pt-20 text-center sm:px-8 sm:pt-24 lg:pb-24 lg:pt-28">
        <p className="inline-flex items-center gap-2.5 text-sm font-medium text-ink-soft animate-fade-up">
          Hi Tuto
          <span className="rounded-full bg-cream px-2.5 py-1 text-xs font-semibold text-brand-dark">Early access</span>
        </p>

        <h1 className="mt-6 text-balance font-archivo text-[clamp(2.85rem,6.6vw,5.5rem)] font-semibold leading-[1.02] tracking-[-0.04em] animate-fade-up" style={{ animationDelay: "80ms" }}>
          Turn any topic into an <span className="text-brand">interactive</span> course.
        </h1>

        <p className="mx-auto mt-6 max-w-2xl text-lg leading-8 text-ink-soft animate-fade-up" style={{ animationDelay: "160ms" }}>
          Enter a topic or upload your notes. Approve the roadmap, then learn through hands-on
          lessons, a lesson-aware tutor, and live voice guidance.
        </p>

        <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row animate-fade-up" style={{ animationDelay: "240ms" }}>
          <PrimaryButton onClick={onStart} className="min-h-12 px-7">
            Create a free course
            <span aria-hidden="true">→</span>
          </PrimaryButton>
          <GhostButton onClick={() => scrollToSection("lesson-preview")}>
            Try the lesson preview
            <span aria-hidden="true">↓</span>
          </GhostButton>
        </div>

        <p className="mt-5 text-sm font-medium text-ink-faint animate-fade-up" style={{ animationDelay: "300ms" }}>
          Free early access · No card required
        </p>

        <div className="mt-12 flex flex-wrap items-center justify-center gap-3 xl:hidden">
          <MascotChip />
          <UiChip icon="quiz" iconClass="bg-cream text-brand" title="Quiz" sub="4 of 5 correct" />
          <UiChip icon="description" iconClass="bg-stone-200 text-stone-600" title="chapter-4-orbits.pdf" sub="Becomes the course" />
          <UiChip icon="graphic_eq" iconClass="bg-cream text-brand" title="Voice session" sub="Sees the lesson" />
        </div>
      </div>
    </section>
  );
}

/* Floating product-UI chips scattered around the hero headline (xl and up). */
function HeroFloaters() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 hidden xl:block">
      <div className="absolute left-[4%] top-[16%] -rotate-3 animate-drift">
        <UiChip icon="quiz" iconClass="bg-cream text-brand" title="Quiz" sub="4 of 5 correct" />
      </div>
      <div className="absolute left-[7%] top-[52%] rotate-2 animate-drift" style={{ animationDelay: "900ms" }}>
        <UiChip icon="description" iconClass="bg-stone-200 text-stone-600" title="chapter-4-orbits.pdf" sub="Becomes the course" />
      </div>
      <div className="absolute bottom-[8%] left-[13%] rotate-1 animate-drift" style={{ animationDelay: "1700ms" }}>
        <UiChip icon="check_circle" iconClass="bg-cream text-brand" title="Roadmap" sub="Approved by you" />
      </div>
      <div className="absolute left-[23%] top-[5%] rotate-2 animate-drift" style={{ animationDelay: "2600ms" }}>
        <MascotChip />
      </div>
      <div className="absolute right-[4%] top-[14%] rotate-3 animate-drift" style={{ animationDelay: "500ms" }}>
        <UiChip icon="graphic_eq" iconClass="bg-cream text-brand" title="Voice session" sub="Live · sees the lesson" />
      </div>
      <div className="absolute right-[7%] top-[50%] -rotate-2 animate-drift" style={{ animationDelay: "1300ms" }}>
        <UiChip icon="forum" iconClass="bg-sky/10 text-sky" title="Tutor reply" sub="“Slope is a rate of change.”" />
      </div>
      <div className="absolute bottom-[9%] right-[12%] rotate-2 animate-drift" style={{ animationDelay: "2100ms" }}>
        <UiChip icon="link" iconClass="bg-ink/5 text-ink-soft" title="agentworld.app/lesson/seasons" sub="Read-only link" />
      </div>
    </div>
  );
}

function MascotChip() {
  return (
    <div className="flex items-center gap-2.5 rounded-2xl border border-ink/5 bg-white py-3 pl-3 pr-4 text-left shadow-chip">
      <Mascot mood="study" className="h-8 w-8 shrink-0" />
      <span className="min-w-0">
        <span className="block truncate text-[13px] font-semibold leading-4">Meet Hi Tuto</span>
        <span className="mt-0.5 block truncate text-[11px] font-medium leading-4 text-ink-faint">Your study sidekick</span>
      </span>
    </div>
  );
}

function UiChip({ icon, iconClass = "", title, sub }: {
  icon: string;
  iconClass?: string;
  title: string;
  sub: string;
}) {
  return (
    <div className="flex items-center gap-2.5 rounded-2xl border border-ink/5 bg-white px-4 py-3 text-left shadow-chip">
      <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-xl ${iconClass}`}>
        <span className="material-symbols-outlined text-[18px]" aria-hidden="true">{icon}</span>
      </span>
      <span className="min-w-0">
        <span className="block truncate text-[13px] font-semibold leading-4">{title}</span>
        <span className="mt-0.5 block truncate text-[11px] font-medium leading-4 text-ink-faint">{sub}</span>
      </span>
    </div>
  );
}

type PreviewAnswer = "tilt" | "distance";

const ORBIT_STARS = [
  { l: 7, t: 16, s: 2, o: 0.55 }, { l: 14, t: 68, s: 1.5, o: 0.4 }, { l: 20, t: 30, s: 1, o: 0.35 },
  { l: 27, t: 82, s: 2, o: 0.45 }, { l: 33, t: 12, s: 1.5, o: 0.5 }, { l: 41, t: 88, s: 1, o: 0.3 },
  { l: 58, t: 10, s: 1.5, o: 0.45 }, { l: 66, t: 85, s: 2, o: 0.4 }, { l: 74, t: 22, s: 1, o: 0.35 },
  { l: 81, t: 64, s: 1.5, o: 0.5 }, { l: 88, t: 38, s: 2, o: 0.45 }, { l: 93, t: 78, s: 1, o: 0.35 },
  { l: 47, t: 6, s: 1, o: 0.3 }, { l: 4, t: 45, s: 1.5, o: 0.4 },
];

/* Pseudo-3D planetarium: Earth orbits the Sun on a squashed ellipse while its
 * axis keeps a fixed tilt — the actual reason seasons happen. Depth is faked
 * with scale/brightness/z-index; the day side always faces the Sun. */
function SolarSystemScene({ tilt }: { tilt: number }) {
  const [angle, setAngle] = useState(165);
  const [playing, setPlaying] = useState(
    () => !window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );

  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    let last = performance.now();
    const loop = (now: number) => {
      const dt = Math.min(64, now - last);
      last = now;
      setAngle((a) => (a + dt * 0.022) % 360);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [playing]);

  const rad = (angle * Math.PI) / 180;
  const left = 50 + 35 * Math.cos(rad);
  const top = 50 + 31 * Math.sin(rad);
  const front = Math.sin(rad) > 0;
  const toSun = (Math.atan2(50 - top, 50 - left) * 180) / Math.PI;

  const season =
    angle >= 145 && angle <= 215
      ? { name: "June", detail: "Northern summer" }
      : angle > 35 && angle < 145
        ? { name: "March", detail: "Spring equinox" }
        : angle > 215 && angle < 325
          ? { name: "September", detail: "Autumn equinox" }
          : { name: "December", detail: "Northern winter" };

  return (
    <div className="relative h-60 overflow-hidden rounded-2xl bg-[radial-gradient(120%_110%_at_50%_0%,#12264A_0%,#0A1830_48%,#050D1C_100%)] sm:h-64">
      {ORBIT_STARS.map((star, index) => (
        <span
          key={index}
          className="absolute rounded-full bg-white"
          style={{ left: `${star.l}%`, top: `${star.t}%`, width: star.s, height: star.s, opacity: star.o }}
          aria-hidden="true"
        />
      ))}

      {/* Orbit guide — rounded-[50%] gives a true ellipse (rounded-full would
          clamp to a stadium shape on a non-square box) */}
      <div className="absolute left-1/2 top-1/2 h-[62%] w-[70%] -translate-x-1/2 -translate-y-1/2 rounded-[50%] border border-white/20" aria-hidden="true" />

      {/* Sun */}
      <div className="absolute left-1/2 top-1/2 z-10 -translate-x-1/2 -translate-y-1/2" aria-hidden="true">
        <div className="absolute left-1/2 top-1/2 h-28 w-28 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[radial-gradient(circle,rgba(245,158,11,0.45)_0%,rgba(245,158,11,0.12)_45%,transparent_70%)]" />
        <div className="relative h-11 w-11 rounded-full bg-[radial-gradient(circle_at_36%_32%,#FFF3C4_0%,#FBBF24_48%,#EA580C_100%)] shadow-[0_0_28px_rgba(245,158,11,0.65)]" />
      </div>

      {/* Earth — axis tilt stays fixed in space as it orbits */}
      <div
        className="absolute"
        style={{
          left: `${left}%`,
          top: `${top}%`,
          zIndex: front ? 20 : 5,
          transform: `translate(-50%, -50%) scale(${front ? 1.12 : 0.82})`,
          filter: front ? "none" : "brightness(0.72)",
        }}
        aria-hidden="true"
      >
        <div className="relative h-8 w-8">
          <div className="absolute inset-0 overflow-hidden rounded-full bg-[radial-gradient(circle_at_32%_30%,#7FB3FF_0%,#2E6BE0_45%,#10367F_100%)] shadow-[0_0_14px_rgba(80,140,255,0.45)]">
            <div
              className="absolute inset-0"
              style={{
                transform: `rotate(${toSun}deg)`,
                background: "linear-gradient(90deg, rgba(2,8,20,0.92) 0%, rgba(2,8,20,0.55) 38%, transparent 58%)",
              }}
            />
          </div>
          <div
            className="absolute left-1/2 top-1/2 h-11 w-[2.5px] rounded-full bg-white/85"
            style={{ transform: `translate(-50%, -50%) rotate(${tilt}deg)` }}
          />
        </div>
      </div>

      {/* Season readout */}
      <div className="absolute left-3 top-3 rounded-xl border border-white/10 bg-white/10 px-3 py-2 backdrop-blur-sm">
        <p className="text-[13px] font-semibold leading-4 text-white">{season.name}</p>
        <p className="mt-0.5 text-[10px] font-medium leading-4 text-white/65">{season.detail}</p>
      </div>

      <p className="absolute bottom-3 left-3 max-w-[52%] text-[11px] font-medium leading-4 text-white/55">
        Earth’s axis keeps its tilt as it orbits — that’s why we get seasons.
      </p>

      <button
        type="button"
        onClick={() => setPlaying((p) => !p)}
        aria-pressed={playing}
        aria-label={playing ? "Pause Earth's orbit" : "Play Earth's orbit"}
        className="absolute bottom-3 right-3 grid h-9 w-9 place-items-center rounded-full border border-white/10 bg-white/10 text-white backdrop-blur-sm transition hover:bg-white/20"
      >
        <span className="material-symbols-outlined text-[18px]" aria-hidden="true">{playing ? "pause" : "play_arrow"}</span>
      </button>
    </div>
  );
}

function LessonPreviewSection() {
  const [tilt, setTilt] = useState(23.5);
  const [answer, setAnswer] = useState<PreviewAnswer | null>(null);
  const contrast = Math.round((tilt / 45) * 100);
  const summerWidth = 50 + contrast * 0.38;
  const winterWidth = 50 - contrast * 0.28;

  const tiltMessage =
    Math.abs(tilt - 23.5) < 0.6
      ? "Earth’s real tilt changes the angle and duration of sunlight."
      : tilt < 8
        ? "Almost no tilt means almost no seasonal contrast."
        : tilt > 36
          ? "A steeper tilt creates more extreme seasonal contrast."
          : "More tilt creates a stronger difference between summer and winter sunlight.";

  const steps = [
    { number: "01", title: "Name the idea", copy: "Start with a topic, question, or PDF." },
    { number: "02", title: "Review the roadmap", copy: "Edit the path before lessons are built." },
    { number: "03", title: "Try the lesson", copy: "Move, test, ask, and reshape the idea." },
  ];

  return (
    <section id="lesson-preview" className="scroll-mt-24">
      <div className="mx-auto max-w-6xl px-5 py-16 sm:px-8 lg:py-24">
        <div className="mx-auto max-w-2xl text-center">
          <SectionChip>Try a lesson</SectionChip>
          <h2 className="mt-5 text-balance font-archivo text-4xl font-semibold tracking-[-0.035em] sm:text-5xl">
            Move the idea. Then test yourself.
          </h2>
          <p className="mt-4 text-lg leading-8 text-ink-soft">
            This illustrative mini lesson shows one kind of interaction a Hi Tuto course can
            include. Change Earth’s tilt and watch the seasons orbit by.
          </p>
        </div>

        <div className="mt-12 rounded-[2rem] border border-ink/5 bg-white p-5 shadow-panel sm:p-8">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3.5">
              <Mascot mood="study" className="h-11 w-11 shrink-0" />
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-faint">Mini lesson · Illustrative</p>
                <h3 className="mt-1 font-archivo text-2xl font-semibold tracking-[-0.02em]">Why Earth has seasons</h3>
              </div>
            </div>
            <span className="inline-flex items-center gap-2 rounded-full bg-cream px-3 py-1.5 text-xs font-semibold text-brand-dark">
              <span className="h-1.5 w-1.5 rounded-full bg-brand animate-pulse" aria-hidden="true" />
              Live demo
            </span>
          </div>

          <div className="mt-6 grid grid-cols-1 gap-5 md:grid-cols-[1.05fr_0.95fr]">
            {/* Orbit + tilt calibrator */}
            <div className="min-w-0 rounded-3xl border border-ink/5 bg-bone p-4 sm:p-5">
              <SolarSystemScene tilt={tilt} />

              <div className="mt-5 flex items-center justify-between gap-4 px-1">
                <label htmlFor="earth-tilt" className="text-sm font-semibold">Earth’s tilt</label>
                <output htmlFor="earth-tilt" className="rounded-full border border-ink/10 bg-white px-3 py-1 text-sm font-bold text-brand-dark">
                  {tilt.toFixed(1)}°
                </output>
              </div>
              <input
                id="earth-tilt"
                type="range"
                min="0"
                max="45"
                step="0.5"
                value={tilt}
                onChange={(event) => setTilt(event.currentTarget.valueAsNumber)}
                aria-describedby="tilt-feedback"
                aria-valuetext={`${tilt.toFixed(1)} degrees. ${tiltMessage}`}
                className="mt-2 min-h-12 w-full"
              />
              <p id="tilt-feedback" className="mt-1 min-h-10 px-1 text-sm leading-5 text-ink-soft">
                {tiltMessage}
              </p>

              <div className="mt-2 space-y-2 px-1 text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
                <div className="grid grid-cols-[6rem_1fr] items-center gap-3">
                  <span>June daylight</span>
                  <span className="h-2 overflow-hidden rounded-full bg-ink/5">
                    <span className="block h-full rounded-full bg-brand transition-[width] duration-200 motion-reduce:transition-none" style={{ width: `${summerWidth}%` }} />
                  </span>
                </div>
                <div className="grid grid-cols-[6rem_1fr] items-center gap-3">
                  <span>Dec. daylight</span>
                  <span className="h-2 overflow-hidden rounded-full bg-ink/5">
                    <span className="block h-full rounded-full bg-ink/30 transition-[width] duration-200 motion-reduce:transition-none" style={{ width: `${winterWidth}%` }} />
                  </span>
                </div>
              </div>
            </div>

            {/* Quick check with the mascot tutor */}
            <div className="flex min-w-0 flex-col rounded-3xl border border-ink/5 bg-white p-5 shadow-card">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2.5">
                  <Mascot mood="tutor" className="h-8 w-8 shrink-0" />
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-faint">Hi Tuto asks</p>
                </div>
                <span className="text-xs font-medium text-ink-faint">1 of 1</span>
              </div>
              <p className="mt-4 font-archivo text-xl font-semibold tracking-[-0.01em]">What causes Earth’s seasons?</p>
              <div className="my-auto grid gap-3 pt-5">
                <QuizOption
                  label="Earth’s tilt"
                  pressed={answer === "tilt"}
                  status={answer === "tilt" ? "correct" : "idle"}
                  onClick={() => setAnswer("tilt")}
                />
                <QuizOption
                  label="Distance from the Sun"
                  pressed={answer === "distance"}
                  status={answer === "distance" ? "wrong" : "idle"}
                  onClick={() => setAnswer("distance")}
                />
              </div>
              <div className="mt-auto pt-4" aria-live="polite" role="status">
                {answer ? (
                  <div className={`flex items-center gap-3 rounded-2xl px-4 py-3 animate-pop-in ${answer === "tilt" ? "bg-cream" : "bg-peach"}`}>
                    <Mascot mood={answer === "tilt" ? "celebrate" : "study"} className="h-8 w-8 shrink-0" />
                    <p className={`text-sm font-medium leading-5 ${answer === "tilt" ? "text-brand-dark" : "text-coral-dark"}`}>
                      {answer === "tilt"
                        ? "Exactly — tilt changes the angle and duration of sunlight."
                        : "Not distance. The changing sunlight angle comes from Earth’s tilt."}
                    </p>
                  </div>
                ) : (
                  <p className="text-sm font-medium text-ink-faint">Pick an answer — Hi Tuto explains either way.</p>
                )}
              </div>
            </div>
          </div>
        </div>

        <ol className="mt-14 grid grid-cols-1 gap-8 sm:grid-cols-3" aria-label="How Hi Tuto builds a course">
          {steps.map((step) => (
            <li key={step.number} className="min-w-0">
              <p className="font-archivo text-sm font-semibold text-brand">{step.number}</p>
              <p className="mt-2 font-semibold">{step.title}</p>
              <p className="mt-1 text-sm leading-6 text-ink-soft">{step.copy}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

function QuizOption({ label, pressed, status, onClick }: {
  label: string;
  pressed: boolean;
  status: "idle" | "correct" | "wrong";
  onClick: () => void;
}) {
  const tone =
    status === "correct"
      ? "border-brand bg-cream text-brand-dark"
      : status === "wrong"
        ? "border-coral/60 bg-peach text-coral-dark"
        : "border-ink/10 bg-white hover:border-ink/30";

  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={pressed}
      className={`flex min-h-12 items-center justify-between gap-3 rounded-2xl border px-4 text-left text-sm font-semibold transition ${tone}`}
    >
      {label}
      {status === "correct" && <span className="material-symbols-outlined text-[18px]" aria-hidden="true">check</span>}
      {status === "wrong" && <span className="material-symbols-outlined text-[18px]" aria-hidden="true">close</span>}
    </button>
  );
}

function FeaturesSection() {
  return (
    <section id="study-kit" className="scroll-mt-24">
      <div className="mx-auto max-w-6xl px-5 py-16 sm:px-8 lg:py-24">
        <div className="mx-auto max-w-2xl text-center">
          <SectionChip>Features</SectionChip>
          <h2 className="mt-5 text-balance font-archivo text-4xl font-semibold tracking-[-0.035em] sm:text-5xl">
            Not a chatbot. A learning workspace.
          </h2>
          <p className="mt-4 text-lg leading-8 text-ink-soft">
            Hi Tuto builds the course, keeps the tutor grounded in the lesson, and lets you
            decide how to move through it.
          </p>
        </div>

        <div className="mt-14 grid grid-cols-1 gap-5 md:grid-cols-12">
          <FeatureCard
            className="md:col-span-7"
            tone="cream"
            eyebrow="Lesson-aware tutor"
            title="Ask for a new way through."
            copy="Ask a question in plain language. The tutor keeps the current lesson in view and offers a clearer route without replacing your course."
          >
            <div className="mt-6 rounded-3xl border border-ink/5 bg-bone p-4 sm:p-5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs font-medium text-ink-faint">Lesson: Reading a graph · Slope</span>
                <span className="rounded-full bg-cream px-2.5 py-1 text-[11px] font-semibold text-brand-dark">Context attached</span>
              </div>
              <div className="ml-auto mt-4 w-fit max-w-[88%] rounded-2xl rounded-br-md bg-ink px-4 py-2.5 text-sm font-medium text-white">
                I can calculate slope. What does it actually mean?
              </div>
              <div className="mt-3 flex items-start gap-2.5">
                <Mascot mood="tutor" className="h-8 w-8 shrink-0" />
                <p className="min-w-0 rounded-2xl rounded-tl-md border border-ink/5 bg-white px-4 py-2.5 text-sm leading-6 shadow-card">
                  Slope is the rate of change — how much <span className="font-semibold text-brand">y</span> moves
                  each time <span className="font-semibold text-brand">x</span> moves one step.
                </p>
              </div>
              <div className="mt-3 flex flex-wrap gap-2 pl-[42px]">
                <span className="rounded-full border border-ink/10 bg-white px-3 py-1.5 text-xs font-semibold text-ink-soft">Show on the graph</span>
                <span className="rounded-full border border-ink/10 bg-white px-3 py-1.5 text-xs font-semibold text-ink-soft">Use an analogy</span>
              </div>
            </div>
          </FeatureCard>

          <FeatureCard
            className="md:col-span-5"
            eyebrow="Roadmap control"
            title="Shape the roadmap."
            copy="Review the lesson order, edit a section, and approve the path before lessons are generated."
          >
            <div className="mt-6 space-y-2">
              <RoadmapRow number="1" label="Sunlight and tilt" />
              <div className="flex items-center gap-3 rounded-2xl border border-brand/50 bg-cream px-4 py-3">
                <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-brand text-[11px] font-bold text-white">2</span>
                <span className="text-sm font-semibold">Move the Earth</span>
                <span className="material-symbols-outlined ml-auto text-[18px] text-brand-dark" aria-hidden="true">edit</span>
              </div>
              <RoadmapRow number="3" label="Check the idea" />
              <p className="pt-2 text-xs font-medium text-ink-faint">Nothing is generated until you approve.</p>
            </div>
          </FeatureCard>

          <FeatureCard
            className="md:col-span-5"
            tone="sand"
            eyebrow="Your material"
            title="Turn your PDF into the course."
            copy="Upload notes, a chapter, or a paper. Lessons are planned from the document and cite the pages they use."
          >
            <div className="mt-6 rounded-3xl border border-ink/5 bg-bone p-4">
              <div className="flex items-center gap-3">
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-peach text-coral">
                  <span className="material-symbols-outlined text-[20px]" aria-hidden="true">description</span>
                </span>
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold">chapter-4-orbits.pdf</p>
                  <p className="mt-0.5 text-xs font-medium text-ink-faint">Course source</p>
                </div>
              </div>
              <div className="mt-3 flex flex-wrap gap-2 text-[11px] font-semibold">
                <span className="rounded-full bg-white px-2.5 py-1 text-ink-soft shadow-card">Pages 41–58</span>
                <span className="rounded-full bg-cream px-2.5 py-1 text-brand-dark">Cited in lesson 2</span>
              </div>
            </div>
          </FeatureCard>

          <FeatureCard
            className="md:col-span-7"
            eyebrow="Voice · with voice access"
            title="Talk through what is on screen."
            copy="In voice mode the instructor can reference the open lesson and point, highlight, or slow down the spot you name."
          >
            <div className="mt-6 rounded-3xl border border-ink/5 bg-bone p-4 sm:p-5">
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs font-medium text-ink-faint">Live voice session</span>
                <VoiceBars />
              </div>
              <div className="mt-3 flex items-start gap-2.5">
                <Mascot mood="tutor" className="h-8 w-8 shrink-0" />
                <p className="min-w-0 rounded-2xl rounded-tl-md border border-ink/5 bg-white px-4 py-2.5 text-sm leading-6 shadow-card">
                  “Watch the tilt — I’ll point to what changes.”
                </p>
              </div>
              <p className="mt-3 w-fit rounded-full border border-ink/10 bg-white px-3 py-1.5 text-xs font-semibold text-ink-soft">
                Highlighting: sunlight angle
              </p>
            </div>
          </FeatureCard>

          <FeatureCard
            className="md:col-span-12"
            tone="cream"
            eyebrow="Share"
            title="Send the experience, not a screenshot."
            copy="Create a revocable, read-only link that opens the interactive lesson itself."
          >
            <div className="mt-6 flex flex-col gap-4 sm:flex-row sm:items-center">
              <div className="flex min-w-0 flex-1 items-center gap-3 rounded-2xl border border-dashed border-ink/15 bg-bone px-4 py-3">
                <span className="material-symbols-outlined shrink-0 text-[20px] text-brand" aria-hidden="true">link</span>
                <span className="truncate text-sm font-semibold">agentworld.app/lesson/seasons</span>
              </div>
              <div className="flex shrink-0 gap-2 text-[11px] font-semibold">
                <span className="rounded-full bg-white px-2.5 py-1 text-ink-soft shadow-card">Read-only</span>
                <span className="rounded-full bg-white px-2.5 py-1 text-ink-soft shadow-card">Revocable</span>
              </div>
            </div>
          </FeatureCard>
        </div>
      </div>
    </section>
  );
}

function FeatureCard({ eyebrow, title, copy, tone = "paper", className = "", children }: {
  eyebrow: string;
  title: string;
  copy: string;
  tone?: "paper" | "cream" | "sand";
  className?: string;
  children: ReactNode;
}) {
  const toneClass = {
    paper: "bg-white",
    cream: "bg-cream/55",
    sand: "bg-sand",
  }[tone];

  return (
    <article className={`min-w-0 rounded-[2rem] border border-ink/5 p-7 shadow-chip ${toneClass} ${className}`}>
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand">{eyebrow}</p>
      <h3 className="mt-3 font-archivo text-2xl font-semibold tracking-[-0.02em]">{title}</h3>
      <p className="mt-3 max-w-xl text-[15px] leading-7 text-ink-soft">{copy}</p>
      {children}
    </article>
  );
}

function RoadmapRow({ number, label }: { number: string; label: string }) {
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-ink/5 bg-white px-4 py-3">
      <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-bone text-[11px] font-bold text-ink-soft">{number}</span>
      <span className="text-sm font-semibold">{label}</span>
    </div>
  );
}

function VoiceBars() {
  return (
    <span className="flex shrink-0 items-end gap-[3px]" aria-hidden="true">
      {[10, 16, 22, 13, 18, 9].map((height, index) => (
        <span key={index} className="w-[3px] rounded-full bg-brand" style={{ height: `${height}px` }} />
      ))}
    </span>
  );
}

function CtaSection({ onStart }: { onStart: () => void }) {
  return (
    <section className="relative">
      <div
        className="pointer-events-none absolute inset-x-0 bottom-0 h-[420px] bg-[radial-gradient(55%_60%_at_50%_100%,rgba(22,163,74,0.07),transparent_72%)]"
        aria-hidden="true"
      />
      <div className="relative mx-auto max-w-4xl px-5 py-24 text-center sm:px-8 lg:py-32">
        <Mascot mood="celebrate" className="mx-auto h-20 w-20 animate-mascot-bob" title="Hi Tuto celebrating your progress" />
        <h2 className="mt-6 text-balance font-archivo text-[clamp(2.4rem,5vw,4.5rem)] font-semibold leading-[1.04] tracking-[-0.035em]">
          Bring one confusing idea. Leave with a course you can use.
        </h2>
        <p className="mx-auto mt-5 max-w-xl text-lg leading-8 text-ink-soft">
          Early Explorer includes one starter course with interactive lessons. No card required.
        </p>
        <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <PrimaryButton onClick={onStart} className="min-h-12 px-7">
            Create my free course
            <span aria-hidden="true">→</span>
          </PrimaryButton>
          <GhostButton onClick={() => { window.location.hash = hashFor({ kind: "pricing" }); }}>
            See planned pricing
          </GhostButton>
        </div>
      </div>
    </section>
  );
}

function LandingFooter() {
  return (
    <footer className="border-t border-ink/5">
      <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-5 py-10 text-center sm:flex-row sm:px-8 sm:text-left">
        <div className="flex items-center gap-2.5">
          <BrandMark className="!h-8 !w-8 rounded-[10px]" />
          <div className="text-left">
            <p className="text-sm font-semibold tracking-[-0.01em]">Hi Tuto</p>
            <p className="text-xs text-ink-faint">Build the lesson. Find the aha.</p>
          </div>
        </div>
        <p className="text-xs text-ink-faint">© 2026 Hi Tuto</p>
      </div>
    </footer>
  );
}

function SectionChip({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-ink/5 bg-white px-3.5 py-1.5 text-xs font-semibold text-ink-soft shadow-chip">
      <span className="h-1.5 w-1.5 rounded-full bg-brand" aria-hidden="true" />
      {children}
    </span>
  );
}

function PrimaryButton({ onClick, children, className = "" }: {
  onClick: () => void;
  children: ReactNode;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center justify-center gap-2 rounded-full bg-ink text-sm font-semibold text-white transition hover:bg-ink/80 ${className}`}
    >
      {children}
    </button>
  );
}

function GhostButton({ onClick, children }: { onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex min-h-12 items-center justify-center gap-2 rounded-full px-4 text-sm font-semibold text-ink underline decoration-ink/20 decoration-2 underline-offset-4 transition hover:decoration-ink"
    >
      {children}
    </button>
  );
}
