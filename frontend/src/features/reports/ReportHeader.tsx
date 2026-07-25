import { UserButton } from "@clerk/react";

import { BrandMark } from "../../components/BrandMark";
import { AUTH_DISABLED } from "../../context/AuthContext";
import { discardReturnHash, hashFor } from "../../routing";

type ReportHeaderProps = {
  privateHandoff?: boolean;
  navigationBlocked?: boolean;
  onNavigate?: () => boolean;
};

export function ReportHeader({
  privateHandoff = false,
  navigationBlocked = false,
  onNavigate,
}: ReportHeaderProps) {
  function navigate(destination: string) {
    if (onNavigate && !onNavigate()) return;
    if (privateHandoff) {
      discardReturnHash();
      window.location.replace(destination);
      return;
    }
    window.location.hash = destination;
  }

  return (
    <header className="sticky top-0 z-40 border-b border-ink/5 bg-bone/85 backdrop-blur print:hidden">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-2 px-3 py-3 min-[360px]:px-5 sm:gap-4 sm:px-8">
        {privateHandoff ? (
          <div className="flex min-h-12 shrink-0 items-center gap-2.5">
            <BrandMark className="!h-9 !w-9 rounded-xl" />
            <span className="hidden text-lg font-semibold tracking-[-0.01em] min-[360px]:inline">
              Agent World
            </span>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => navigate(hashFor({ kind: "dashboard" }))}
            className="flex min-h-12 shrink-0 items-center gap-2.5 text-left"
            aria-label="Go to dashboard home"
          >
            <BrandMark className="!h-9 !w-9 rounded-xl" />
            <span className="hidden text-lg font-semibold tracking-[-0.01em] min-[360px]:inline">
              Agent World
            </span>
          </button>
        )}
        {privateHandoff ? (
          <div className="flex shrink-0 items-center gap-2">
            <span className="hidden items-center gap-1.5 text-xs font-semibold text-ink-soft min-[430px]:inline-flex">
              <span className="material-symbols-outlined text-[17px]" aria-hidden="true">
                lock
              </span>
              Private invitation
            </span>
            <button
              type="button"
              onClick={() => navigate(hashFor({ kind: "reports" }))}
              className="inline-flex min-h-11 items-center rounded-full border border-ink/10 bg-white px-4 text-sm font-semibold text-ink transition hover:border-ink/20"
            >
              Exit
            </button>
          </div>
        ) : (
          <div className="flex shrink-0 items-center gap-1 min-[360px]:gap-2">
            <button
              type="button"
              onClick={() => navigate(hashFor({ kind: "dashboard" }))}
              className="hidden min-h-11 items-center rounded-full px-3 text-sm font-medium text-ink-soft transition hover:text-ink sm:inline-flex sm:px-4"
            >
              Courses
            </button>
            <button
              type="button"
              onClick={() => navigate(hashFor({ kind: "reports" }))}
              className="inline-flex min-h-11 items-center rounded-full bg-white px-3 text-sm font-semibold text-ink shadow-chip transition hover:bg-sand min-[360px]:px-4"
            >
              Reports
            </button>
            {AUTH_DISABLED ? (
              <span
                className="grid h-9 w-9 place-items-center rounded-full bg-ink text-xs font-semibold text-white"
                title="Local demo user"
                aria-label="Local demo user"
              >
                D
              </span>
            ) : navigationBlocked ? (
              <span
                className="grid h-9 w-9 place-items-center rounded-full border border-ink/10 bg-white text-ink-soft"
                title="Save or discard draft changes before opening account controls"
                aria-label="Account controls unavailable while this draft has unsaved changes"
              >
                <span className="material-symbols-outlined text-[17px]" aria-hidden="true">
                  lock
                </span>
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
        )}
      </div>
    </header>
  );
}
