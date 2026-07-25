import { SignIn, SignUp, useAuth as useClerkAuth } from "@clerk/react";
import { useEffect } from "react";

import { BrandMark } from "../../components/BrandMark";
import { Mascot } from "../../components/Mascot";
import { consumeReturnHash, hashFor, type AuthMode } from "../../routing";

export function AuthPage({ initialMode = "login" }: { initialMode?: AuthMode }) {
  const isLogin = initialMode === "login";
  const { isLoaded, isSignedIn } = useClerkAuth();

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return;
    window.location.hash = consumeReturnHash();
  }, [isLoaded, isSignedIn]);

  return (
    <div className="min-h-screen bg-bone font-sans text-ink selection:bg-cream selection:text-brand-dark lg:grid lg:grid-cols-[1.05fr_0.95fr]">
      <section className="relative hidden min-h-screen overflow-hidden bg-ink p-10 text-white lg:flex lg:flex-col xl:p-14">
        <div
          className="pointer-events-none absolute inset-x-0 top-0 h-[440px] bg-[radial-gradient(55%_50%_at_28%_0%,rgba(22,163,74,0.18),transparent_72%)]"
          aria-hidden="true"
        />

        <button
          type="button"
          onClick={() => {
            window.location.hash = hashFor({ kind: "landing" });
          }}
          className="relative z-10 flex min-h-12 items-center gap-2.5 self-start text-left transition hover:opacity-85"
        >
          <BrandMark className="!h-9 !w-9 rounded-xl" />
          <span className="text-lg font-semibold tracking-[-0.01em]">Hi Tuto</span>
        </button>

        <div className="relative z-10 my-auto py-8">
          <div className="grid grid-cols-[minmax(0,1fr)_9rem] items-center gap-5 xl:grid-cols-[minmax(0,1fr)_11rem] xl:gap-7">
            <div>
              <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3.5 py-1.5 text-xs font-semibold text-white/70">
                <span className="h-1.5 w-1.5 rounded-full bg-brand" aria-hidden="true" />
                Pick up where it clicked
              </span>
              <p className="mt-6 font-archivo text-[clamp(2.8rem,4.4vw,4.4rem)] font-semibold leading-[1.02] tracking-[-0.04em]">
                <span className="block whitespace-nowrap">Your idea.</span>
                <span className="block whitespace-nowrap text-brand">Your path.</span>
                <span className="block whitespace-nowrap">Your aha.</span>
              </p>
              <p className="mt-5 max-w-md text-sm leading-6 text-white/60 xl:text-base xl:leading-7">
                Bring the idea that is not clicking. Hi Tuto turns it into something you can see, try, and ask about.
              </p>
            </div>
            <div className="relative mx-auto h-36 w-36 xl:h-44 xl:w-44">
              <Mascot mood="study" className="h-full w-full animate-mascot-bob" title="Hi Tuto studying alongside you" />
            </div>
          </div>

          <ol className="mt-10 grid grid-cols-3 gap-3">
            <li className="rounded-2xl border border-white/10 bg-white/5 p-4">
              <span className="text-xs font-semibold text-brand">01 · Plan it</span>
              <p className="mt-1.5 text-[13px] font-medium leading-5 text-white/70">Review a clear lesson roadmap.</p>
            </li>
            <li className="rounded-2xl border border-white/10 bg-white/5 p-4">
              <span className="text-xs font-semibold text-brand">02 · Try it</span>
              <p className="mt-1.5 text-[13px] font-medium leading-5 text-white/70">Learn through hands-on interactions.</p>
            </li>
            <li className="rounded-2xl border border-white/10 bg-white/5 p-4">
              <span className="text-xs font-semibold text-brand">03 · Ask away</span>
              <p className="mt-1.5 text-[13px] font-medium leading-5 text-white/70">The tutor already knows the lesson.</p>
            </li>
          </ol>
        </div>

        <p className="relative z-10 text-xs font-medium text-white/40">© 2026 Hi Tuto · Learn curious.</p>
      </section>

      <section className="flex min-h-screen items-center px-5 py-8 sm:px-10 lg:px-14 xl:px-20">
        <div className="mx-auto w-full max-w-md animate-fade-up">
          <div className="mb-8 flex items-center justify-between lg:hidden">
            <button
              type="button"
              onClick={() => {
                window.location.hash = hashFor({ kind: "landing" });
              }}
              className="flex min-h-12 items-center gap-2.5 text-left"
            >
              <BrandMark className="!h-9 !w-9 rounded-xl" />
              <span className="text-lg font-semibold tracking-[-0.01em]">Hi Tuto</span>
            </button>
            <button
              type="button"
              onClick={() => {
                window.location.hash = hashFor({ kind: "pricing" });
              }}
              className="flex min-h-12 items-center px-2 text-sm font-medium text-ink-soft transition hover:text-ink"
            >
              Pricing
            </button>
          </div>

          <div className="mb-6">
            <span className="inline-flex items-center gap-2 rounded-full border border-ink/5 bg-white px-3.5 py-1.5 text-xs font-semibold text-ink-soft shadow-chip">
              <span className="h-1.5 w-1.5 rounded-full bg-brand" aria-hidden="true" />
              {isLogin ? "Welcome back" : "Your first course is waiting"}
            </span>
            <h1 className="mt-5 text-balance font-archivo text-[clamp(2.4rem,4.5vw,3.5rem)] font-semibold leading-[1.04] tracking-[-0.035em] text-ink">
              {isLogin ? "Back to your next idea." : "Make your first idea click."}
            </h1>
            <p className="mt-4 leading-7 text-ink-soft">
              {isLogin
                ? "Sign in to continue your courses and conversations."
                : "Create an account to build your first interactive learning path."}
            </p>
          </div>

          <div className="flex justify-center [&_.cl-rootBox]:w-full [&_.cl-cardBox]:w-full [&_.cl-card]:shadow-none">
            {isLogin ? (
              <SignIn routing="hash" signUpUrl={hashFor({ kind: "auth", mode: "signup" })} />
            ) : (
              <SignUp routing="hash" signInUrl={hashFor({ kind: "auth", mode: "login" })} />
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
