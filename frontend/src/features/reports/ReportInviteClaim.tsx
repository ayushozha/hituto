import { useEffect, useState } from "react";

import {
  ReportLearner,
  claimReportInvitation,
  listReportLearners,
} from "../../api";
import { useAuth } from "../../context/AuthContext";
import { discardReturnHash, hashFor } from "../../routing";
import { ReportHeader } from "./ReportHeader";

export function ReportInviteClaim({ token }: { token: string }) {
  const { user } = useAuth();
  const [claiming, setClaiming] = useState(false);
  const [loadingLearners, setLoadingLearners] = useState(true);
  const [learners, setLearners] = useState<ReportLearner[]>([]);
  const [claimMode, setClaimMode] = useState<"new" | "existing">("new");
  const [targetLearnerId, setTargetLearnerId] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    listReportLearners("custody")
      .then((items) => {
        if (active) setLearners(items);
      })
      .catch(() => {
        if (active) {
          setError("Your existing child records could not be loaded. You can still claim as a new record.");
        }
      })
      .finally(() => {
        if (active) setLoadingLearners(false);
      });
    return () => {
      active = false;
    };
  }, []);

  async function claim() {
    if (claimMode === "existing" && !targetLearnerId) {
      setError("Choose the existing child record that should receive this report.");
      return;
    }
    setClaiming(true);
    setError(null);
    try {
      const report = await claimReportInvitation(
        token,
        claimMode === "existing" ? targetLearnerId : null,
      );
      // Replace, rather than append, the token-bearing history entry after its one use.
      window.location.replace(hashFor({ kind: "report", reportId: report.id }));
    } catch {
      setError("This invitation is unavailable. It may be expired, revoked, or already claimed.");
      setClaiming(false);
    }
  }

  return (
    <div className="min-h-full bg-bone font-sans text-ink selection:bg-cream selection:text-brand-dark">
      <ReportHeader privateHandoff />
      <main className="mx-auto grid min-h-[calc(100vh-4.5rem)] max-w-2xl place-items-center px-5 py-12 sm:px-8">
        <section className="w-full rounded-3xl border border-ink/5 bg-white p-7 text-center shadow-panel sm:p-10">
          <span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-cream text-brand">
            <span className="material-symbols-outlined text-[28px]" aria-hidden="true">
              family_restroom
            </span>
          </span>
          <p className="mt-5 text-xs font-semibold uppercase tracking-[0.16em] text-brand-dark">
            Private family handoff
          </p>
          <h1 className="mt-2 font-archivo text-3xl font-semibold tracking-[-0.035em] sm:text-4xl">
            Claim a progress report
          </h1>
          <p className="mx-auto mt-4 max-w-lg text-sm leading-6 text-ink-soft">
            The invitation stays opaque until you claim it. No learner or report details are shown
            on this page.
          </p>
          {user?.email ? (
            <p className="mt-4 text-xs font-medium text-ink-faint">Claiming as {user.email}</p>
          ) : null}

          {error ? (
            <p
              className="mt-5 rounded-2xl border border-coral/20 bg-coral-soft px-4 py-3 text-sm font-medium text-coral-dark"
              role="alert"
            >
              {error}
            </p>
          ) : null}

          <fieldset className="mt-6 text-left">
            <legend className="text-sm font-semibold text-ink">Save this report to</legend>
            <label className="mt-3 flex cursor-pointer items-start gap-3 rounded-2xl border border-ink/10 p-4 transition hover:border-brand/30">
              <input
                type="radio"
                name="claim-target"
                value="new"
                checked={claimMode === "new"}
                onChange={() => setClaimMode("new")}
                className="mt-1 h-4 w-4 accent-brand"
              />
              <span>
                <span className="block text-sm font-semibold text-ink">A new child record</span>
                <span className="mt-1 block text-xs leading-5 text-ink-soft">
                  Use the private learner record that arrived with this report.
                </span>
              </span>
            </label>
            <label
              className={`mt-3 flex items-start gap-3 rounded-2xl border border-ink/10 p-4 transition ${
                learners.length > 0 ? "cursor-pointer hover:border-brand/30" : "opacity-55"
              }`}
            >
              <input
                type="radio"
                name="claim-target"
                value="existing"
                checked={claimMode === "existing"}
                onChange={() => {
                  setClaimMode("existing");
                  setTargetLearnerId((current) => current || learners[0]?.id || "");
                }}
                disabled={loadingLearners || learners.length === 0}
                className="mt-1 h-4 w-4 accent-brand"
              />
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-semibold text-ink">An existing child record</span>
                <span className="mt-1 block text-xs leading-5 text-ink-soft">
                  Attach the full correction history to a child record you already custody.
                </span>
                {claimMode === "existing" ? (
                  <>
                    <select
                      value={targetLearnerId}
                      onChange={(event) => setTargetLearnerId(event.target.value)}
                      className="mt-3 min-h-11 w-full rounded-2xl border border-ink/10 bg-white px-4 text-sm text-ink outline-none transition focus:border-brand/50 focus:ring-4 focus:ring-brand/10"
                      aria-label="Existing child record"
                    >
                      {learners.map((learner) => (
                        <option key={learner.id} value={learner.id}>
                          {learner.display_alias}
                          {learner.grade_band ? ` - ${learner.grade_band}` : ""}
                        </option>
                      ))}
                    </select>
                    <span className="mt-2 block text-xs leading-5 text-ink-soft">
                      Claiming authorizes this report's teacher to view and create future reports for
                      that child. You can revoke either capability later.
                    </span>
                  </>
                ) : null}
                {!loadingLearners && learners.length === 0 ? (
                  <span className="mt-2 block text-xs text-ink-faint">
                    No existing child records are available.
                  </span>
                ) : null}
              </span>
            </label>
          </fieldset>

          <div className="mt-7 flex flex-col-reverse justify-center gap-3 sm:flex-row">
            <button
              type="button"
              onClick={() => {
                discardReturnHash();
                window.location.replace(hashFor({ kind: "reports" }));
              }}
              className="inline-flex min-h-12 items-center justify-center rounded-full border border-ink/10 bg-white px-6 text-sm font-semibold text-ink transition hover:border-ink/20"
            >
              Not now
            </button>
            <button
              type="button"
              onClick={() => void claim()}
              disabled={
                claiming ||
                (claimMode === "existing" && !targetLearnerId)
              }
              className="inline-flex min-h-12 items-center justify-center gap-2 rounded-full bg-ink px-6 text-sm font-semibold text-white transition hover:bg-ink/80 disabled:cursor-wait disabled:opacity-50"
            >
              {claiming ? (
                <>
                  <span className="h-4 w-4 animate-spin-slow rounded-full border-2 border-white/40 border-t-white" />
                  Claiming...
                </>
              ) : (
                <>
                  <span className="material-symbols-outlined text-[18px]" aria-hidden="true">
                    verified_user
                  </span>
                  Claim report
                </>
              )}
            </button>
          </div>
        </section>
      </main>
    </div>
  );
}
