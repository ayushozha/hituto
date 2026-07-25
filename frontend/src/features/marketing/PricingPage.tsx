import { PricingTable } from "@clerk/react";

import { Mascot } from "../../components/Mascot";
import { AUTH_DISABLED } from "../../context/AuthContext";
import { MarketingFooter, MarketingHeader } from "./MarketingChrome";

const individualAllowances = [
  {
    title: "Course credit",
    icon: "route",
    iconClass: "bg-cream text-brand",
    description:
      "One credit creates one new course from a topic or your own material, including its roadmap and up to five interactive lessons. Reviewing the roadmap before generation does not spend a credit.",
  },
  {
    title: "Real-time voice tutor minutes",
    icon: "graphic_eq",
    iconClass: "bg-stone-200 text-stone-600",
    description:
      "Minutes count only while you are connected to a live voice session with Hi Tuto. Reading lessons and asking the text tutor questions do not use voice minutes.",
  },
  {
    title: "Generated lesson visuals",
    icon: "image",
    iconClass: "bg-sky/10 text-sky",
    description:
      "One newly generated AI image uses one visual. Reopening a lesson or reusing an existing image costs nothing, and built-in charts, diagrams, and interactive canvases do not use this allowance.",
  },
  {
    title: "Interactive 3D lab credit",
    icon: "deployed_code",
    iconClass: "bg-ink/5 text-ink-soft",
    description:
      "One credit creates one custom AI-generated 3D model for a studio lesson. Lightweight procedural 3D activities do not use a credit, and a failed generation will not count.",
  },
] as const;

const crewAllowances = [
  {
    title: "Pooled course credits",
    icon: "all_inclusive",
    iconClass: "bg-cream text-brand",
    description:
      "The crew receives one shared monthly balance. Eight pooled credits means eight courses across the whole crew—not eight courses for every member.",
  },
  {
    title: "Learner seats",
    icon: "group",
    iconClass: "bg-stone-200 text-stone-600",
    description:
      "A seat is one named member with their own sign-in, progress, and learning history. Five seats can cover a family, a tutor with learners, or a small study group.",
  },
  {
    title: "Group progress",
    icon: "monitoring",
    iconClass: "bg-sky/10 text-sky",
    description:
      "The crew can see which shared lessons are started or completed and where someone may need help. Private tutor conversations are not exposed to the group.",
  },
  {
    title: "Tutor handoffs",
    icon: "forward_to_inbox",
    iconClass: "bg-ink/5 text-ink-soft",
    description:
      "A tutor, parent, or study lead can leave the next lesson, context, and follow-up notes for a learner. It keeps coaching organized; it does not include a live human tutor.",
  },
] as const;

export function PricingPage() {
  return (
    <div className="min-h-full overflow-x-clip bg-bone font-sans text-ink selection:bg-cream selection:text-brand-dark">
      <MarketingHeader active="pricing" />

      <main>
        <section className="relative">
          <div
            className="pointer-events-none absolute inset-x-0 top-0 h-[520px] bg-[radial-gradient(60%_55%_at_50%_0%,rgba(22,163,74,0.08),transparent_72%)]"
            aria-hidden="true"
          />
          <div className="relative mx-auto max-w-3xl px-5 pb-6 pt-16 text-center sm:px-8 sm:pt-20">
            <span className="inline-flex items-center gap-2 rounded-full border border-ink/5 bg-white px-3.5 py-1.5 text-xs font-semibold text-ink-soft shadow-chip animate-fade-up">
              <span className="h-1.5 w-1.5 rounded-full bg-brand" aria-hidden="true" />
              Plans powered by Clerk Billing
            </span>
            <h1
              className="mt-6 text-balance font-archivo text-[clamp(2.85rem,6vw,5rem)] font-semibold leading-[1.02] tracking-[-0.04em] animate-fade-up"
              style={{ animationDelay: "80ms" }}
            >
              Learn the thing. Keep the <span className="text-brand">momentum</span>.
            </h1>
            <p
              className="mx-auto mt-6 max-w-2xl text-lg leading-8 text-ink-soft animate-fade-up"
              style={{ animationDelay: "160ms" }}
            >
              Start with one idea for free. Paid plans pair clear monthly allowances with the
              expensive AI tools that make a lesson feel alive—no vague “unlimited” promise.
            </p>
            <Mascot
              mood="celebrate"
              className="mx-auto mt-8 h-16 w-16 animate-mascot-bob animate-fade-up"
              title="Hi Tuto celebrating a learning win"
            />
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-5 py-12 sm:px-8 lg:py-16" aria-labelledby="plans-heading">
          <h2 id="plans-heading" className="sr-only">
            Subscription plans
          </h2>
          {AUTH_DISABLED ? (
            <div className="rounded-3xl border border-ink/5 bg-white p-8 text-center shadow-chip">
              <p className="font-archivo text-xl font-semibold tracking-[-0.02em]">
                Pricing is unavailable in local demo mode.
              </p>
              <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-ink-soft">
                Enable Clerk authentication with a publishable key to load live subscription plans.
              </p>
            </div>
          ) : (
            <div className="flex justify-center [&_.cl-rootBox]:w-full [&_.cl-pricingTable]:w-full">
              <PricingTable
                for="user"
                newSubscriptionRedirectUrl="/#dashboard"
                appearance={{
                  elements: {
                    rootBox: "w-full max-w-6xl",
                    pricingTable: "gap-5",
                    pricingTableCard: "rounded-3xl border border-ink/5 bg-white shadow-chip",
                    pricingTableCardHeader: "p-7 sm:p-8",
                    pricingTableCardTitle: "font-archivo text-2xl font-semibold tracking-[-0.02em]",
                    pricingTableCardFee: "font-archivo text-5xl font-semibold tracking-[-0.03em]",
                    pricingTableCardFeatures: "px-7 pb-4 sm:px-8",
                    pricingTableCardFeaturesListItemTitle: "text-sm font-medium",
                    pricingTableCardFooter: "p-7 pt-4 sm:p-8",
                    buttonPrimary: "min-h-12 rounded-full bg-ink text-sm font-semibold text-white hover:bg-ink/80",
                  },
                }}
              />
            </div>
          )}

          <section className="mt-16 lg:mt-20" aria-labelledby="allowances-heading">
            <div className="grid gap-6 lg:grid-cols-[1fr_0.72fr] lg:items-end">
              <div className="max-w-3xl">
                <span className="inline-flex items-center gap-2 rounded-full border border-ink/5 bg-white px-3.5 py-1.5 text-xs font-semibold text-ink-soft shadow-chip">
                  <span className="h-1.5 w-1.5 rounded-full bg-brand" aria-hidden="true" />
                  Allowances, decoded
                </span>
                <h2
                  id="allowances-heading"
                  className="mt-5 text-balance font-archivo text-3xl font-semibold tracking-[-0.03em] sm:text-4xl"
                >
                  What do those credits actually mean?
                </h2>
              </div>
              <div className="rounded-2xl bg-cream p-6">
                <p className="font-archivo text-lg font-semibold tracking-[-0.01em] text-brand-dark">
                  Keep what you create.
                </p>
                <p className="mt-1.5 text-sm font-medium leading-6 text-brand-dark/75">
                  You can reopen completed courses whenever you like. Allowances count new AI
                  generation and live voice time—not ordinary studying.
                </p>
              </div>
            </div>

            <AllowanceGroup
              eyebrow="For individual learners"
              title="Creating and learning"
              items={individualAllowances}
            />
            <AllowanceGroup
              eyebrow="Study Crew terms"
              title="Sharing the learning space"
              items={crewAllowances}
            />
          </section>

          <div className="mt-10 flex flex-col gap-5 rounded-2xl border border-ink/5 bg-white p-6 shadow-chip sm:flex-row sm:items-center sm:justify-between sm:px-8">
            <div>
              <p className="font-archivo text-lg font-semibold tracking-[-0.01em]">The honest fine print</p>
              <p className="mt-1.5 max-w-3xl text-sm leading-6 text-ink-soft">
                Checkout runs through Clerk Billing. In development you can try the shared Clerk
                payment gateway; production will use your connected Stripe account. Manage or cancel
                anytime from your profile.
              </p>
            </div>
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-5 pb-20 sm:px-8 lg:pb-24">
          <div className="grid gap-10 rounded-3xl bg-ink px-7 py-12 text-white sm:px-10 lg:grid-cols-[0.8fr_1.2fr] lg:px-12 lg:py-16">
            <div>
              <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3.5 py-1.5 text-xs font-semibold text-white/70">
                <span className="h-1.5 w-1.5 rounded-full bg-brand" aria-hidden="true" />
                Questions, answered
              </span>
              <h2 className="mt-5 text-balance font-archivo text-3xl font-semibold tracking-[-0.03em] sm:text-4xl">
                No pricing maze.
              </h2>
              <p className="mt-4 leading-7 text-white/60">
                Pick a plan above to open checkout. Early Explorer stays free while you try the loop.
              </p>
            </div>
            <div className="space-y-3">
              <Faq
                question="What does one course credit include?"
                answer="One credit turns a topic into a roadmap and up to five generated interactive lessons. Reviewing the roadmap does not use another credit."
              />
              <Faq
                question="Why are voice, visuals, and 3D counted separately?"
                answer="They use different specialist AI services. Clear allowances keep the monthly price predictable instead of making light users subsidize heavy generation."
              />
              <Faq
                question="What happens when I reach an allowance?"
                answer="Your existing courses stay available. You can wait for the monthly reset or upgrade—never an automatic overage charge."
              />
              <Faq
                question="Can I use Hi Tuto free right now?"
                answer="Yes. Early Explorer is free. Creating an account never starts a paid subscription until you choose a paid plan."
              />
              <Faq
                question="Where do I manage billing?"
                answer="Open Plan & usage from your dashboard profile menu to see remaining allowances, or manage payment methods and cancel from your Clerk profile anytime."
              />
              <Faq
                question="How do plan allowances update after I upgrade?"
                answer="Clerk Billing puts your active plan on the session. Hi Tuto reads that plan on each request and shows the matching monthly course, voice, visual, and 3D lab allowances."
              />
            </div>
          </div>
        </section>
      </main>

      <MarketingFooter />
    </div>
  );
}

type AllowanceItem = {
  readonly title: string;
  readonly icon: string;
  readonly iconClass: string;
  readonly description: string;
};

function AllowanceGroup({
  eyebrow,
  title,
  items,
}: {
  eyebrow: string;
  title: string;
  items: readonly AllowanceItem[];
}) {
  return (
    <div className="mt-12">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-2">
        <h3 className="font-archivo text-xl font-semibold tracking-[-0.02em] sm:text-2xl">{title}</h3>
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-faint">{eyebrow}</p>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {items.map((item) => (
          <article
            key={item.title}
            className="flex items-start gap-4 rounded-2xl border border-ink/5 bg-white p-6 shadow-chip"
          >
            <span
              className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ${item.iconClass}`}
              aria-hidden="true"
            >
              <span className="material-symbols-outlined text-[20px]">{item.icon}</span>
            </span>
            <div>
              <h4 className="text-[15px] font-semibold leading-snug">{item.title}</h4>
              <p className="mt-1.5 text-sm leading-6 text-ink-soft">{item.description}</p>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

function Faq({ question, answer }: { question: string; answer: string }) {
  return (
    <article className="rounded-2xl border border-white/10 bg-white/5 p-5 sm:p-6">
      <h3 className="text-[15px] font-semibold">{question}</h3>
      <p className="mt-1.5 text-sm leading-6 text-white/65">{answer}</p>
    </article>
  );
}
