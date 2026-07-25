import { useEffect, useState } from "react";
import { PricingTable, UserButton, useClerk } from "@clerk/react";

import { Allowance, BillingUsage, fetchBillingUsage } from "../../api";
import { BrandMark } from "../../components/BrandMark";
import { Mascot } from "../../components/Mascot";
import { AUTH_DISABLED } from "../../context/AuthContext";
import { hashFor } from "../../routing";

type MeterDef = {
  key: keyof Pick<BillingUsage, "course_credits" | "voice_minutes" | "visuals" | "lab_credits">;
  title: string;
  unit: string;
  icon: string;
  hint: string;
};

const METERS: MeterDef[] = [
  {
    key: "course_credits",
    title: "Course credits",
    unit: "courses",
    icon: "route",
    hint: "One credit builds a roadmap and up to five interactive lessons. Reviewing a roadmap first is free.",
  },
  {
    key: "voice_minutes",
    title: "Voice tutor",
    unit: "min",
    icon: "graphic_eq",
    hint: "Minutes count only while you are connected to a live voice session.",
  },
  {
    key: "visuals",
    title: "Lesson visuals",
    unit: "images",
    icon: "image",
    hint: "New AI images use one visual each. Charts, diagrams, and reused images are free.",
  },
  {
    key: "lab_credits",
    title: "3D lab credits",
    unit: "models",
    icon: "deployed_code",
    hint: "One credit for each custom AI-generated 3D model. Procedural activities do not count.",
  },
];

export function BillingPage() {
  const [usage, setUsage] = useState<BillingUsage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchBillingUsage()
      .then((u) => {
        if (!cancelled) setUsage(u);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load your plan usage. Try again in a moment.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const renewsLabel = usage
    ? new Date(usage.renews_at).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      })
    : null;

  return (
    <div className="min-h-full bg-bone font-sans text-ink selection:bg-cream selection:text-brand-dark">
      <header className="sticky top-0 z-40 border-b border-ink/5 bg-bone/85 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-5 py-3 sm:px-8">
          <button
            type="button"
            onClick={() => {
              window.location.hash = hashFor({ kind: "dashboard" });
            }}
            className="flex min-h-12 shrink-0 items-center gap-2.5 text-left"
          >
            <BrandMark className="!h-9 !w-9 rounded-xl" />
            <span className="text-lg font-semibold tracking-[-0.01em]">Hi Tuto</span>
          </button>
          <div className="flex shrink-0 items-center gap-2.5">
            <button
              type="button"
              onClick={() => {
                window.location.hash = hashFor({ kind: "dashboard" });
              }}
              className="hidden min-h-11 items-center rounded-full px-4 text-sm font-medium text-ink-soft transition hover:text-ink sm:inline-flex"
            >
              Back to courses
            </button>
            {AUTH_DISABLED ? (
              <span className="grid h-9 w-9 place-items-center rounded-full bg-ink text-xs font-semibold text-white">
                D
              </span>
            ) : (
            <UserButton
              appearance={{
                elements: {
                  avatarBox: "h-9 w-9 rounded-full",
                  userButtonPopoverCard: "rounded-2xl shadow-panel",
                },
              }}
            />
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-5 pb-24 pt-8 sm:px-8 sm:pt-10">
        <section className="relative overflow-hidden rounded-3xl border border-ink/5 bg-white p-7 shadow-chip sm:p-9">
          <div
            className="pointer-events-none absolute inset-0 bg-[radial-gradient(60%_80%_at_100%_0%,rgba(217,119,6,0.1),transparent_65%)]"
            aria-hidden="true"
          />
          <div className="relative flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
            <div className="max-w-xl">
              <span className="inline-flex items-center gap-2 rounded-full border border-ink/5 bg-white px-3.5 py-1.5 text-xs font-semibold text-ink-soft shadow-chip">
                <span className="h-1.5 w-1.5 rounded-full bg-brand" aria-hidden="true" />
                Plan & usage
              </span>
              <h1 className="mt-5 font-archivo text-[clamp(2rem,4vw,2.75rem)] font-semibold leading-[1.05] tracking-[-0.035em]">
                {usage ? usage.plan : "Your plan"}
              </h1>
              <p className="mt-3 text-sm leading-6 text-ink-soft sm:text-[15px]">
                {usage?.is_free
                  ? "Early Explorer includes one starter course. Upgrade anytime for more credits, voice minutes, and 3D labs."
                  : "Monthly allowances reset automatically. Studying existing courses never spends credits."}
                {renewsLabel ? ` Resets ${renewsLabel}.` : ""}
              </p>
            </div>
            <div className="flex flex-wrap gap-2.5">
              {AUTH_DISABLED ? (
                <span className="inline-flex min-h-11 items-center rounded-full border border-ink/10 bg-sand px-5 text-sm text-ink-soft">
                  Billing is unavailable in local demo mode
                </span>
              ) : (
                <ManageBillingButton />
              )}
              <a
                href="#pricing"
                className="inline-flex min-h-11 items-center rounded-full bg-ink px-5 text-sm font-semibold text-white transition hover:bg-ink/80"
              >
                {usage?.is_free ? "Upgrade plan" : "Change plan"}
              </a>
            </div>
          </div>
        </section>

        {error ? (
          <p className="mt-6 rounded-2xl border border-coral/20 bg-coral-soft px-5 py-4 text-sm font-medium text-coral-dark">
            {error}
          </p>
        ) : null}

        <section className="mt-8 grid gap-4 sm:grid-cols-2" aria-label="Monthly allowances">
          {usage
            ? METERS.map((meter) => (
                <MeterCard key={meter.key} def={meter} allowance={usage[meter.key]} />
              ))
            : Array.from({ length: 4 }).map((_, i) => (
                <div
                  key={i}
                  className="h-40 animate-pulse rounded-2xl border border-ink/5 bg-white shadow-chip"
                />
              ))}
        </section>

        {usage ? (
          <p className="mt-5 text-center text-xs font-medium text-ink-faint">
            One course credit includes up to {usage.max_lessons_per_course} interactive lessons.
            {!usage.enforced
              ? " Limits are tracked now; hard blocking turns on when enforcement is enabled."
              : " Creation is blocked when course credits hit zero."}
          </p>
        ) : null}

        {usage?.is_free ? (
          <section className="mt-12" aria-labelledby="upgrade-heading">
            <div className="mb-6 flex flex-col items-start gap-4 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <h2
                  id="upgrade-heading"
                  className="font-archivo text-2xl font-semibold tracking-[-0.02em] sm:text-3xl"
                >
                  Ready for more momentum?
                </h2>
                <p className="mt-2 max-w-xl text-sm leading-6 text-ink-soft">
                  Paid plans add course credits, voice minutes, visuals, and 3D lab credits — still
                  no vague “unlimited” promise.
                </p>
              </div>
              <Mascot mood="celebrate" className="h-14 w-14" title="Hi Tuto celebrating an upgrade" />
            </div>
            {AUTH_DISABLED ? (
              <p className="rounded-2xl border border-ink/5 bg-white px-5 py-4 text-sm text-ink-soft shadow-chip">
                Clerk pricing widgets are hidden while local authentication is disabled.
              </p>
            ) : (
            <div className="flex justify-center [&_.cl-rootBox]:w-full [&_.cl-pricingTable]:w-full">
              <PricingTable
                for="user"
                newSubscriptionRedirectUrl="/#billing"
                appearance={{
                  elements: {
                    rootBox: "w-full max-w-5xl",
                    pricingTable: "gap-4",
                    pricingTableCard: "rounded-3xl border border-ink/5 bg-white shadow-chip",
                    buttonPrimary:
                      "min-h-11 rounded-full bg-ink text-sm font-semibold text-white hover:bg-ink/80",
                  },
                }}
              />
            </div>
            )}
          </section>
        ) : null}
      </main>
    </div>
  );
}

function ManageBillingButton() {
  const { openUserProfile } = useClerk();
  return (
    <button
      type="button"
      onClick={() => openUserProfile()}
      className="inline-flex min-h-11 items-center rounded-full border border-ink/10 bg-white px-5 text-sm font-semibold text-ink transition hover:border-ink/20"
    >
      Manage billing
    </button>
  );
}

function MeterCard({ def, allowance }: { def: MeterDef; allowance: Allowance }) {
  const pct =
    allowance.total > 0 ? Math.min(100, Math.round((allowance.used / allowance.total) * 100)) : 0;
  const depleted = allowance.remaining <= 0 && allowance.total > 0;
  const low = !depleted && allowance.total > 0 && allowance.remaining <= Math.max(1, Math.ceil(allowance.total * 0.15));

  return (
    <article className="rounded-2xl border border-ink/5 bg-white p-6 shadow-chip">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span
            className="grid h-10 w-10 place-items-center rounded-xl bg-cream text-brand"
            aria-hidden="true"
          >
            <span className="material-symbols-outlined text-[20px]">{def.icon}</span>
          </span>
          <div>
            <h3 className="text-[15px] font-semibold">{def.title}</h3>
            <p className="mt-0.5 text-xs font-medium text-ink-faint">
              {allowance.remaining} of {allowance.total} {def.unit} left
            </p>
          </div>
        </div>
        <span
          className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${
            depleted
              ? "bg-coral-soft text-coral-dark"
              : low
                ? "bg-cream text-brand-dark"
                : "bg-mint text-lime-dark"
          }`}
        >
          {depleted ? "Used up" : low ? "Running low" : "On track"}
        </span>
      </div>
      <div className="mt-5 h-2 overflow-hidden rounded-full bg-sand">
        <div
          className={`h-full rounded-full transition-[width] duration-500 ${
            depleted ? "bg-coral" : low ? "bg-brand" : "bg-lime"
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="mt-4 text-sm leading-6 text-ink-soft">{def.hint}</p>
    </article>
  );
}
