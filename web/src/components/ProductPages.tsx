import { useState } from "react";
import type { MouseEvent, ReactNode } from "react";
import { useSignOut } from "@reboot-dev/reboot-react";
import type { LessonPlan } from "../types/lesson";

export function navigateTo(path: string): void {
  if (window.location.pathname === path) return;
  window.history.pushState({}, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function RouteLink({ path, className, children }: { path: string; className?: string; children: ReactNode }) {
  function follow(event: MouseEvent<HTMLAnchorElement>) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    navigateTo(path);
  }

  return <a href={path} className={className} onClick={follow}>{children}</a>;
}

function Brand() {
  return (
    <RouteLink path="/" className="product-brand">
      <span className="product-brand-mark">S</span>
      <span>SAT Live Tutor</span>
    </RouteLink>
  );
}

function ArrowIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true">
      <path d="M4 10h11M11 6l4 4-4 4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true">
      <path d="m5 10 3 3 7-7" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function PublicHeader() {
  return (
    <header className="marketing-header">
      <Brand />
      <nav className="marketing-nav" aria-label="Main navigation">
        <a href="/#how-it-works">How it works</a>
        <RouteLink path="/pricing">Pricing</RouteLink>
        <RouteLink path="/app" className="nav-sign-in">Sign in</RouteLink>
        <RouteLink path="/app" className="nav-cta">Start learning</RouteLink>
      </nav>
    </header>
  );
}

function BoardPreview() {
  return (
    <div className="product-demo" aria-label="Preview of a live SAT tutoring lesson">
      <div className="demo-window-bar">
        <div className="demo-window-dots"><i /><i /><i /></div>
        <span><i className="live-dot" /> Teaching live</span>
        <span>1:42</span>
      </div>
      <div className="demo-board">
        <div className="demo-question">
          <span>SAT MATH</span>
          <p>If <em>f(x) = x² − 4x + 3</em>, what is the minimum value of <em>f</em>?</p>
          <div>A) −1 &nbsp;&nbsp; B) 0 &nbsp;&nbsp; C) 1 &nbsp;&nbsp; D) 3</div>
        </div>
        <div className="demo-work">
          <span className="demo-hand">Let’s reveal the shape.</span>
          <span className="demo-equation">f(x) = (x − 2)² − 1</span>
          <svg viewBox="0 0 330 175" role="img" aria-label="Parabola with its minimum highlighted">
            <g className="demo-grid">
              <path d="M30 20v135M30 115h280M80 20v135M130 20v135M180 20v135M230 20v135M280 20v135M30 70h280" />
            </g>
            <path className="demo-curve" d="M60 35 C105 100 135 132 180 132 C225 132 255 100 300 35" />
            <circle cx="180" cy="132" r="5" />
            <path className="demo-pointer" d="M222 146c-14 9-24 9-34-4" />
            <text x="225" y="158">minimum = −1</text>
          </svg>
        </div>
      </div>
      <div className="demo-caption"><span /> “The squared part can’t be negative, so the lowest value is negative one.”</div>
    </div>
  );
}

export function LandingPage() {
  return (
    <div className="marketing-page">
      <PublicHeader />
      <main>
        <section className="hero-section">
          <div className="hero-copy">
            <span className="eyebrow"><i /> Private beta is open</span>
            <h1>Your SAT tutor that <span>teaches out loud.</span></h1>
            <p>Paste any SAT question. Your AI tutor solves it, explains it in a natural voice, and writes the reasoning on a live visual board—just like a patient teacher beside you.</p>
            <div className="hero-actions">
              <RouteLink path="/app" className="primary-action">Try your first lesson <ArrowIcon /></RouteLink>
              <a href="#how-it-works" className="secondary-action">See how it works</a>
            </div>
            <div className="hero-proof">
              <span><CheckIcon /> SAT Math</span>
              <span><CheckIcon /> Reading &amp; Writing</span>
              <span><CheckIcon /> Voice interruption</span>
            </div>
          </div>
          <BoardPreview />
        </section>

        <section className="promise-strip" aria-label="Product promise">
          <p>Not another answer generator.</p>
          <span />
          <p>A teacher you can interrupt.</p>
          <span />
          <p>A board that explains with the voice.</p>
        </section>

        <section className="how-section" id="how-it-works">
          <div className="section-heading">
            <span className="section-kicker">One question at a time</span>
            <h2>Real teaching, not a wall of text.</h2>
            <p>The tutor chooses how to explain each question, then synchronizes speech with equations, graphs, and diagrams.</p>
          </div>
          <div className="steps-grid">
            <article>
              <span className="step-number">01</span>
              <div className="step-icon question-icon">Aa</div>
              <h3>Paste the full question</h3>
              <p>Bring any SAT Math or Reading &amp; Writing question with its answer choices.</p>
            </article>
            <article>
              <span className="step-number">02</span>
              <div className="step-icon voice-icon"><i /><i /><i /><i /><i /></div>
              <h3>Watch and listen</h3>
              <p>The tutor verifies the answer, speaks naturally, and builds the explanation on the board.</p>
            </article>
            <article>
              <span className="step-number">03</span>
              <div className="step-icon interrupt-icon">?</div>
              <h3>Interrupt when confused</h3>
              <p>Ask “why?” or request another approach. The tutor stops, listens, and teaches it differently.</p>
            </article>
          </div>
        </section>

        <section className="bottom-cta">
          <div>
            <span className="section-kicker">Built for how students learn</span>
            <h2>Turn your next SAT question into a lesson.</h2>
          </div>
          <RouteLink path="/app" className="primary-action light-action">Start learning <ArrowIcon /></RouteLink>
        </section>
      </main>
      <footer className="marketing-footer">
        <Brand />
        <p>AI can make mistakes. Verify important answers and use official SAT materials for final preparation.</p>
        <span>© 2026 SAT Live Tutor · Private beta</span>
      </footer>
    </div>
  );
}

export function PricingPage() {
  return (
    <div className="marketing-page pricing-page">
      <PublicHeader />
      <main className="pricing-main">
        <div className="section-heading pricing-heading">
          <span className="eyebrow"><i /> Founding access</span>
          <h1>Learn free during private beta.</h1>
          <p>We are validating lesson quality before charging students. There is no fake checkout and no card required today.</p>
        </div>
        <div className="pricing-card">
          <div>
            <span className="plan-label">Private beta</span>
            <h2>$0 <small>today</small></h2>
            <p>Use the complete live tutor while we measure accuracy, speed, and teaching quality.</p>
          </div>
          <ul>
            <li><CheckIcon /> SAT Math and Reading &amp; Writing</li>
            <li><CheckIcon /> Live voice teaching and captions</li>
            <li><CheckIcon /> Animated equations, graphs, and diagrams</li>
            <li><CheckIcon /> Typed and spoken interruptions</li>
          </ul>
          <RouteLink path="/app" className="primary-action">Join the private beta <ArrowIcon /></RouteLink>
          <span className="pricing-note">Paid plans and limits will be published before billing is enabled.</span>
        </div>
      </main>
      <footer className="marketing-footer compact-footer">
        <Brand />
        <span>© 2026 SAT Live Tutor · Private beta</span>
      </footer>
    </div>
  );
}

export function SignInPage({ onSignIn, error = "", loading = false }: { onSignIn: () => void; error?: string; loading?: boolean }) {
  return (
    <div className="auth-page">
      <header className="marketing-header"><Brand /><RouteLink path="/" className="back-home">Back to home</RouteLink></header>
      <main className="auth-main">
        <div className={`auth-card ${error ? "is-error" : ""}`}>
          <span className="eyebrow"><i /> Your personal SAT teacher</span>
          <h1>{error ? "The classroom couldn’t open." : "Ready when you are."}</h1>
          <p>{error || "Sign in to start a live voice lesson. Your tutor will solve, draw, and explain—and you can interrupt at any time."}</p>
          {!error && <button type="button" className="primary-action" onClick={onSignIn} disabled={loading}>{loading ? "Opening…" : "Continue to your tutor"}<ArrowIcon /></button>}
          <small>Private beta · No credit card required</small>
        </div>
      </main>
    </div>
  );
}

function DashboardHeader() {
  const signOut = useSignOut();
  return (
    <header className="dashboard-header">
      <Brand />
      <nav aria-label="Student navigation">
        <RouteLink path="/dashboard" className="is-active">Dashboard</RouteLink>
        <RouteLink path="/app">Live tutor</RouteLink>
      </nav>
      <button type="button" className="account-button" onClick={() => signOut()} aria-label="Sign out">
        <span>Student</span><i>S</i>
      </button>
    </header>
  );
}

function lessonStatus(status: string): string {
  if (status === "thinking") return "Tutor is preparing this lesson";
  if (status === "ready") return "Ready to replay";
  if (status === "error") return "Needs another try";
  return "Saved on this device";
}

function DeleteMyData({ onForget }: { onForget: () => Promise<number> }) {
  const [stage, setStage] = useState<"idle" | "confirming" | "working" | "done">("idle");
  const [erased, setErased] = useState(0);

  if (stage === "done") {
    return (
      <section className="dashboard-panel data-panel">
        <span className="panel-kicker">Your data</span>
        <h2>Erased.</h2>
        <p>
          Your questions, working, and {erased} message{erased === 1 ? "" : "s"} were
          overwritten, and the keys protecting anything encrypted were destroyed. None of it
          can be recovered.
        </p>
      </section>
    );
  }

  return (
    <section className="dashboard-panel data-panel">
      <span className="panel-kicker">Your data</span>
      <h2>Delete everything you have asked me</h2>
      <p>
        Your questions, your working, and every lesson are overwritten rather than hidden,
        and the keys protecting anything encrypted are destroyed. This cannot be undone.
      </p>
      {stage === "idle" ? (
        <button type="button" className="danger-action" onClick={() => setStage("confirming")}>
          Delete my data
        </button>
      ) : (
        <div className="danger-confirm">
          <strong>Permanently erase everything? This cannot be undone.</strong>
          <div>
            <button
              type="button"
              className="danger-action"
              disabled={stage === "working"}
              onClick={() => {
                setStage("working");
                void onForget()
                  .then((count) => {
                    setErased(count);
                    setStage("done");
                  })
                  .catch(() => setStage("idle"));
              }}
            >
              {stage === "working" ? "Erasing…" : "Yes, erase it"}
            </button>
            <button type="button" onClick={() => setStage("idle")} disabled={stage === "working"}>
              Keep my data
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

export function DashboardPage({ questionText, status, lesson, onForget }: { questionText: string; status: string; lesson?: LessonPlan; onForget: () => Promise<number> }) {
  const hasLesson = Boolean(questionText || lesson);
  return (
    <div className="dashboard-page">
      <DashboardHeader />
      <main className="dashboard-main">
        <section className="dashboard-welcome">
          <div>
            <span className="section-kicker">Your study room</span>
            <h1>What do you want to understand today?</h1>
            <p>Bring one question. Leave with the idea behind it.</p>
          </div>
          <RouteLink path="/app" className="primary-action">Start a live lesson <ArrowIcon /></RouteLink>
        </section>

        <div className="dashboard-grid">
          <section className="dashboard-panel recent-panel">
            <div className="panel-heading">
              <div><span className="panel-kicker">Current lesson</span><h2>{hasLesson ? "Continue where you left off" : "Your first lesson starts here"}</h2></div>
              {hasLesson && <span className={`lesson-state state-${status || "saved"}`}><i />{lessonStatus(status)}</span>}
            </div>
            {hasLesson ? (
              <div className="recent-lesson">
                <div className="domain-badge">{lesson?.domain === "reading_writing" ? "Reading & Writing" : "SAT Math"}</div>
                <h3>{lesson?.question_summary || questionText}</h3>
                <p>{questionText}</p>
                <div className="recent-lesson-footer">
                  <span>{lesson ? `${lesson.beats.length} teaching moments · Voice + visual board` : "Lesson preparation in progress"}</span>
                  <RouteLink path="/app">Open lesson <ArrowIcon /></RouteLink>
                </div>
              </div>
            ) : (
              <div className="empty-lesson">
                <div className="empty-board-icon"><span>2x + 3 = 11</span><i /></div>
                <div><h3>Paste any complete SAT question</h3><p>Your tutor will verify it, explain it aloud, and draw only what helps.</p></div>
                <RouteLink path="/app" className="secondary-action">Ask your first question</RouteLink>
              </div>
            )}
          </section>

          <aside className="dashboard-panel beta-panel">
            <span className="panel-kicker">Private beta</span>
            <h2>Your complete tutor is unlocked.</h2>
            <p>There are no paid limits during the beta. We are using this period to prove lesson quality before billing.</p>
            <div className="beta-capability"><CheckIcon /><span><strong>Live voice</strong>Natural explanation and interruption</span></div>
            <div className="beta-capability"><CheckIcon /><span><strong>Visual board</strong>Equations, graphs, charts, and diagrams</span></div>
            <RouteLink path="/pricing">View beta access</RouteLink>
          </aside>
        </div>

        <section className="dashboard-panel getting-started">
          <div><span className="panel-kicker">A better way to ask</span><h2>Get the strongest lesson</h2></div>
          <ol>
            <li><span>1</span><p><strong>Include the choices</strong>Paste the complete question so the tutor can verify the exact answer.</p></li>
            <li><span>2</span><p><strong>Let the board build</strong>Listen while each visual appears with the explanation.</p></li>
            <li><span>3</span><p><strong>Interrupt immediately</strong>Say “show me another way” the moment something stops making sense.</p></li>
          </ol>
        </section>

        <DeleteMyData onForget={onForget} />
      </main>
    </div>
  );
}

export function NotFoundPage() {
  return (
    <div className="auth-page">
      <header className="marketing-header"><Brand /></header>
      <main className="auth-main"><div className="auth-card"><span className="eyebrow"><i /> 404</span><h1>That page isn’t here.</h1><p>The live tutor is ready when you are.</p><RouteLink path="/" className="primary-action">Go home <ArrowIcon /></RouteLink></div></main>
    </div>
  );
}
