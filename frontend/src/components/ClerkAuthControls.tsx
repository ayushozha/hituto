import { Show, SignInButton, SignUpButton } from "@clerk/react";

import { hashFor } from "../routing";

const navLinkClass =
  "flex min-h-11 items-center text-sm font-medium text-ink-soft transition hover:text-ink";

const primaryClass =
  "inline-flex min-h-11 items-center justify-center gap-2 rounded-full bg-ink px-5 text-sm font-semibold text-white transition hover:bg-ink/80";

type ClerkAuthControlsProps = {
  /** `full` = Sign in + Sign up. `signIn` = quiet Sign in link only (landing header). */
  variant?: "full" | "signIn";
};

/** Marketing chrome auth. Dashboard profile (UserButton + Learning style) lives on Dashboard. */
export function ClerkAuthControls({ variant = "full" }: ClerkAuthControlsProps) {
  return (
    <>
      <Show when="signed-out">
        {variant === "signIn" ? (
          <SignInButton mode="modal">
            <button type="button" className={navLinkClass}>
              Sign in
            </button>
          </SignInButton>
        ) : (
          <div className="flex items-center gap-3">
            <SignInButton mode="modal">
              <button type="button" className={navLinkClass}>
                Sign in
              </button>
            </SignInButton>
            <SignUpButton mode="modal">
              <button type="button" className={primaryClass}>
                Sign up
                <span aria-hidden="true">→</span>
              </button>
            </SignUpButton>
          </div>
        )}
      </Show>
      <Show when="signed-in">
        <button
          type="button"
          onClick={() => {
            window.location.hash = hashFor({ kind: "dashboard" });
          }}
          className={primaryClass}
        >
          Open dashboard
          <span aria-hidden="true">→</span>
        </button>
      </Show>
    </>
  );
}
