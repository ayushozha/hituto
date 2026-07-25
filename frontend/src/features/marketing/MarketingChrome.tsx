import { BrandMark } from "../../components/BrandMark";
import { ClerkAuthControls } from "../../components/ClerkAuthControls";
import { hashFor } from "../../routing";

type MarketingPage = "pricing" | "waitlist";

function go(kind: "landing" | "pricing" | "waitlist") {
  window.location.hash = hashFor({ kind });
}

function NavButton({ active, onClick, children, className = "" }: {
  active?: boolean;
  onClick: () => void;
  children: string;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      className={`flex min-h-12 items-center text-sm transition ${
        active ? "font-semibold text-ink" : "font-medium text-ink-soft hover:text-ink"
      } ${className}`}
    >
      {children}
    </button>
  );
}

export function MarketingHeader({ active }: { active?: MarketingPage }) {
  return (
    <header className="sticky top-0 z-50 border-b border-ink/5 bg-bone/85 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-5 py-3 sm:px-8">
        <button
          type="button"
          onClick={() => go("landing")}
          className="flex min-h-12 shrink-0 items-center gap-2.5 text-left"
        >
          <BrandMark className="!h-9 !w-9 rounded-xl" />
          <span className="text-lg font-semibold tracking-[-0.01em]">Hi Tuto</span>
        </button>

        <nav className="flex shrink-0 items-center gap-4 sm:gap-6" aria-label="Public navigation">
          <NavButton active={active === "pricing"} onClick={() => go("pricing")} className="hidden sm:flex">
            Pricing
          </NavButton>
          <NavButton active={active === "waitlist"} onClick={() => go("waitlist")} className="hidden sm:flex">
            Waitlist
          </NavButton>
          <ClerkAuthControls />
        </nav>
      </div>
    </header>
  );
}

export function MarketingFooter() {
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

export function Sparkle({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 100 100" className={className} aria-hidden="true">
      <path d="M50 4C55 34 66 45 96 50C66 55 55 66 50 96C45 66 34 55 4 50C34 45 45 34 50 4Z" fill="currentColor" />
    </svg>
  );
}
