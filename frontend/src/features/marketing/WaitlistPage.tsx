import { useState } from "react";

import { joinWaitlist } from "../../api";
import { Mascot } from "../../components/Mascot";
import { hashFor } from "../../routing";
import { MarketingFooter, MarketingHeader } from "./MarketingChrome";

export function WaitlistPage() {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [message, setMessage] = useState("");

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!email) return;
    setStatus("loading");
    setMessage("");

    try {
      await joinWaitlist(email.trim());
      setStatus("success");
      setMessage("You’re in. We’ll send the good stuff, not the noisy stuff.");
      setEmail("");
    } catch (error: unknown) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "We couldn’t save your spot yet. Try once more?");
    }
  };

  return (
    <div className="min-h-full overflow-x-clip bg-bone font-sans text-ink selection:bg-cream selection:text-brand-dark">
      <MarketingHeader active="waitlist" />

      <main>
        <section className="relative">
          <div
            className="pointer-events-none absolute inset-x-0 top-0 h-[560px] bg-[radial-gradient(60%_55%_at_50%_0%,rgba(22,163,74,0.08),transparent_72%)]"
            aria-hidden="true"
          />
          <div className="relative mx-auto grid max-w-6xl gap-12 px-5 py-14 sm:px-8 sm:py-16 lg:grid-cols-[1.05fr_0.95fr] lg:items-center lg:py-20">
            <div className="animate-fade-up">
              <span className="inline-flex items-center gap-2 rounded-full border border-ink/5 bg-white px-3.5 py-1.5 text-xs font-semibold text-ink-soft shadow-chip">
                <span className="h-1.5 w-1.5 rounded-full bg-brand" aria-hidden="true" />
                Founding plan updates
              </span>
              <h1 className="mt-6 text-balance font-archivo text-[clamp(2.85rem,5.6vw,5rem)] font-semibold leading-[1.02] tracking-[-0.04em]">
                Get the next chapter <span className="text-brand">first</span>.
              </h1>
              <p className="mt-6 max-w-xl text-lg leading-8 text-ink-soft">
                Free starter access is open. Join this list for new-feature notes, paid-plan launch
                details, and founding pricing as Hi Tuto grows.
              </p>

              <div className="mt-9 flex flex-wrap gap-3">
                <ProofChip icon="graphic_eq" iconClass="bg-cream text-brand" label="Voice access news" />
                <ProofChip icon="group" iconClass="bg-stone-200 text-stone-600" label="Study Crew plans" />
                <ProofChip icon="sell" iconClass="bg-ink/5 text-ink-soft" label="Founding pricing" />
              </div>
            </div>

            <div className="rounded-3xl border border-ink/5 bg-white p-7 shadow-panel sm:p-9 animate-fade-up" style={{ animationDelay: "120ms" }}>
              <Mascot mood="tutor" className="mx-auto h-20 w-20 animate-mascot-bob" title="Hi Tuto ready to help you study" />

              {status === "success" ? (
                <div className="mt-6 rounded-2xl bg-cream p-7 text-center animate-pop-in" role="status">
                  <span className="material-symbols-outlined text-[40px] text-brand" aria-hidden="true">celebration</span>
                  <h2 className="mt-3 font-archivo text-2xl font-semibold tracking-[-0.02em] text-brand-dark">Your spot is saved.</h2>
                  <p className="mt-2 text-sm font-medium leading-6 text-brand-dark/75">{message}</p>
                  <button
                    type="button"
                    onClick={() => { window.location.hash = hashFor({ kind: "landing" }); }}
                    className="mt-6 inline-flex min-h-12 items-center justify-center gap-2 rounded-full bg-ink px-6 text-sm font-semibold text-white transition hover:bg-ink/80"
                  >
                    Back to Hi Tuto
                    <span aria-hidden="true">→</span>
                  </button>
                </div>
              ) : (
                <div className="mt-6 text-center">
                  <h2 className="font-archivo text-2xl font-semibold tracking-[-0.02em] sm:text-3xl">Be early to what comes next.</h2>
                  <p className="mt-3 text-sm leading-6 text-ink-soft">
                    Honest product updates and founding-plan details. Free starter access does not require this list.
                  </p>

                  <form onSubmit={handleSubmit} className="mt-6 text-left">
                    <label htmlFor="waitlist-email" className="text-sm font-semibold text-ink">Email address</label>
                    <input
                      id="waitlist-email"
                      type="email"
                      value={email}
                      onChange={(event) => { setEmail(event.target.value); setStatus("idle"); setMessage(""); }}
                      placeholder="you@example.com"
                      autoComplete="email"
                      required
                      disabled={status === "loading"}
                      className="mt-2 min-h-14 w-full rounded-2xl border border-ink/10 bg-white px-4 text-sm font-medium text-ink shadow-chip outline-none transition placeholder:text-ink-faint focus:border-ink/30 focus:ring-4 focus:ring-ink/5 disabled:opacity-60"
                    />
                    <button
                      type="submit"
                      disabled={status === "loading"}
                      className="mt-4 inline-flex min-h-14 w-full items-center justify-center gap-2 rounded-full bg-ink text-sm font-semibold text-white transition hover:bg-ink/80 disabled:opacity-50"
                    >
                      {status === "loading" ? "Saving your spot…" : "Join the updates list"}
                      <span className={`material-symbols-outlined text-[20px] ${status === "loading" ? "animate-spin" : ""}`} aria-hidden="true">
                        {status === "loading" ? "progress_activity" : "arrow_forward"}
                      </span>
                    </button>
                    {message && status === "error" && <p className="mt-3 text-sm font-semibold text-coral-dark" role="alert">{message}</p>}
                    <p className="mt-4 text-center text-xs font-medium leading-5 text-ink-faint">No charge. No daily drip campaign. Leave whenever you like.</p>
                  </form>
                </div>
              )}
            </div>
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-5 pb-20 sm:px-8 lg:pb-24">
          <div className="grid gap-8 rounded-3xl bg-ink px-7 py-12 text-white sm:px-10 lg:grid-cols-[0.75fr_1.25fr] lg:items-center lg:px-12 lg:py-16">
            <div>
              <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3.5 py-1.5 text-xs font-semibold text-white/70">
                <span className="h-1.5 w-1.5 rounded-full bg-brand" aria-hidden="true" />
                Why Hi Tuto
              </span>
              <h2 className="mt-5 text-balance font-archivo text-3xl font-semibold tracking-[-0.03em] sm:text-4xl">Not another answer machine.</h2>
            </div>
            <p className="text-lg leading-8 text-white/70">
              Hi Tuto starts with the moment something stops making sense. It breaks the idea into a
              clear path, turns it into something you can try, and gives the tutor context from the
              lesson—so you understand it instead of copying an answer.
            </p>
          </div>
        </section>
      </main>

      <MarketingFooter />
    </div>
  );
}

function ProofChip({ icon, iconClass = "", label }: { icon: string; iconClass?: string; label: string }) {
  return (
    <div className="flex items-center gap-2.5 rounded-2xl border border-ink/5 bg-white py-2.5 pl-2.5 pr-4 shadow-chip">
      <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-xl ${iconClass}`}>
        <span className="material-symbols-outlined text-[18px]" aria-hidden="true">{icon}</span>
      </span>
      <span className="text-[13px] font-semibold">{label}</span>
    </div>
  );
}
