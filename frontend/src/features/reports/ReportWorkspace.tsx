import { useEffect, useMemo, useRef, useState } from "react";

import {
  CreateProgressReportInput,
  LearnerAccessGrant,
  ProgressReport,
  ReportContent,
  ReportDraftFields,
  ReportHistory,
  ReportInvitation,
  ReportLearner,
  acknowledgeProgressReport,
  createProgressReport,
  createReportCorrection,
  createReportInvitation,
  getProgressReport,
  getProgressReportHistory,
  getReportLearnerGrants,
  listReportLearners,
  publishProgressReport,
  recordProgressReportPrint,
  revokeReportInvitations,
  revokeReportLearnerGrant,
  updateProgressReport,
} from "../../api";
import { useAuth } from "../../context/AuthContext";
import { hashFor, setHashNavigationBlocker } from "../../routing";
import { ReportHeader } from "./ReportHeader";

type ViewMode = "edit" | "preview";
type BusyAction =
  | "save"
  | "publish"
  | "invite"
  | "revoke-invites"
  | "correct"
  | "acknowledge"
  | null;

const REPORT_LIMITS = {
  authorName: 160,
  listItem: 2_000,
  evidenceStatement: 2_000,
  evidenceDetail: 4_000,
  observations: 8_000,
  learningGoals: 20,
  workCompleted: 30,
  evidenceItems: 20,
  nextActions: 20,
} as const;

export function ReportWorkspace({ reportId }: { reportId?: string }) {
  const { user } = useAuth();
  const [report, setReport] = useState<ProgressReport | null>(null);
  const [learners, setLearners] = useState<ReportLearner[]>([]);
  const [learnerId, setLearnerId] = useState("new");
  const [learnerAlias, setLearnerAlias] = useState("");
  const [gradeBand, setGradeBand] = useState("");
  const [draft, setDraft] = useState<ReportDraftFields>(() =>
    emptyDraft(user?.email?.split("@")[0] ?? ""),
  );
  const [viewMode, setViewMode] = useState<ViewMode>("edit");
  const [loading, setLoading] = useState(true);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState<BusyAction>(null);
  const [error, setError] = useState<string | null>(null);
  const [invitation, setInvitation] = useState<ReportInvitation | null>(null);
  const [inviteNotice, setInviteNotice] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [reportHistory, setReportHistory] = useState<ReportHistory | null>(null);
  const [grants, setGrants] = useState<LearnerAccessGrant[]>([]);
  const dirtyRef = useRef(false);

  function markClean() {
    dirtyRef.current = false;
    setDirty(false);
  }

  function markDirty() {
    dirtyRef.current = true;
    setDirty(true);
  }

  function confirmNavigation(): boolean {
    if (!dirtyRef.current) return true;
    if (!window.confirm("Discard the unsaved changes in this report draft?")) return false;
    markClean();
    return true;
  }

  useEffect(() => {
    let active = true;
    dirtyRef.current = false;
    setLoading(true);
    setReport(null);
    setBusy(null);
    setDirty(false);
    setError(null);
    setInvitation(null);
    setInviteNotice(null);
    setCopied(false);

    if (!reportId) {
      listReportLearners()
        .then((items) => {
          if (active) setLearners(items);
        })
        .catch((reason) => {
          if (active) setError((reason as Error).message || "Could not load learners.");
        })
        .finally(() => {
          if (active) setLoading(false);
        });
      return () => {
        active = false;
      };
    }

    getProgressReport(reportId)
      .then((item) => {
        if (!active) return;
        setReport(item);
        setDraft(draftFromReport(item));
        setViewMode(item.status === "draft" && item.permissions.can_edit ? "edit" : "preview");
        markClean();
      })
      .catch((reason) => {
        if (active) setError((reason as Error).message || "Could not load this report.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [reportId]);

  useEffect(() => {
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!dirtyRef.current) return;
      event.preventDefault();
      event.returnValue = "";
    };
    const removeHashBlocker = setHashNavigationBlocker(confirmNavigation);
    window.addEventListener("beforeunload", warnBeforeUnload);
    return () => {
      window.removeEventListener("beforeunload", warnBeforeUnload);
      removeHashBlocker();
    };
  }, []);

  useEffect(() => {
    if (!report || report.status !== "published") {
      setReportHistory(null);
      setGrants([]);
      return;
    }
    let active = true;
    getProgressReportHistory(report.id)
      .then((value) => {
        if (active) setReportHistory(value);
      })
      .catch(() => {});
    if (report.permissions.can_manage_grants) {
      getReportLearnerGrants(report.learner.id)
        .then((value) => {
          if (active) setGrants(value);
        })
        .catch(() => {});
    }
    return () => {
      active = false;
    };
  }, [report?.id, report?.status, report?.learner.id, report?.permissions.can_manage_grants]);

  const canEdit = report ? report.status === "draft" && report.permissions.can_edit : true;
  const inviteUrl = useMemo(
    () => (invitation ? buildInvitationUrl(invitation.token) : null),
    [invitation],
  );

  function changeDraft(next: ReportDraftFields) {
    setDraft(next);
    markDirty();
    setError(null);
  }

  async function save(): Promise<ProgressReport | null> {
    const validationError = validateDraft(draft, report ? report.learner.display_alias : learnerAlias, learnerId);
    if (validationError) {
      setError(validationError);
      return null;
    }
    setBusy("save");
    setError(null);
    try {
      if (report) {
        const saved = await updateProgressReport(report.id, cleanDraft(draft));
        setReport(saved);
        setDraft(draftFromReport(saved));
        markClean();
        return saved;
      }

      const fields = cleanDraft(draft);
      const input: CreateProgressReportInput =
        learnerId === "new"
          ? {
              ...fields,
              learner: {
                display_alias: learnerAlias.trim(),
                grade_band: gradeBand.trim() || null,
              },
            }
          : { ...fields, learner_id: learnerId };
      const saved = await createProgressReport(input);
      markClean();
      window.location.hash = hashFor({ kind: "report", reportId: saved.id });
      return saved;
    } catch (reason) {
      setError((reason as Error).message || "Could not save this report.");
      return null;
    } finally {
      setBusy(null);
    }
  }

  async function publish() {
    if (!report || !report.permissions.can_publish) return;
    if (
      !window.confirm(
        "Publish this report? Published versions are immutable. Corrections create a new version.",
      )
    ) {
      return;
    }
    if (dirty && !(await save())) return;
    setBusy("publish");
    setError(null);
    try {
      const result = await publishProgressReport(report.id);
      setReport(result.report);
      setDraft(draftFromReport(result.report));
      setInvitation(result.invitation);
      setInviteNotice(
        result.invitation
          ? null
          : "Published to the learner's existing family vault. No new custody link is needed.",
      );
      setViewMode("preview");
      markClean();
    } catch (reason) {
      setError((reason as Error).message || "Could not publish this report.");
    } finally {
      setBusy(null);
    }
  }

  async function makeInvitation() {
    if (!report?.permissions.can_invite) return;
    if (
      !window.confirm(
        "Replace the invitation? Every previous active, unclaimed link for this report series will stop working.",
      )
    ) {
      return;
    }
    setBusy("invite");
    setError(null);
    try {
      setInvitation(await createReportInvitation(report.id));
      setInviteNotice(null);
      setCopied(false);
    } catch (reason) {
      setError((reason as Error).message || "Could not create an invitation.");
    } finally {
      setBusy(null);
    }
  }

  async function revokeInvitations() {
    if (!report?.permissions.can_invite) return;
    if (
      !window.confirm(
        "Revoke every active, unclaimed invitation link for this report? Anyone who already claimed access keeps it.",
      )
    ) {
      return;
    }
    setBusy("revoke-invites");
    setError(null);
    try {
      await revokeReportInvitations(report.id);
      setInvitation(null);
      setCopied(false);
      setInviteNotice("All active, unclaimed invitation links were revoked.");
    } catch (reason) {
      setError((reason as Error).message || "Could not revoke invitations.");
    } finally {
      setBusy(null);
    }
  }

  async function makeCorrection() {
    if (!report?.permissions.can_correct) return;
    if (!window.confirm("Create a new correction draft from this published version?")) return;
    setBusy("correct");
    setError(null);
    try {
      const correction = await createReportCorrection(report.id);
      setBusy(null);
      window.location.hash = hashFor({ kind: "report", reportId: correction.id });
    } catch (reason) {
      setError((reason as Error).message || "Could not create a correction.");
      setBusy(null);
    }
  }

  async function acknowledge() {
    if (!report?.permissions.can_acknowledge || report.acknowledged_at) return;
    setBusy("acknowledge");
    setError(null);
    try {
      const result = await acknowledgeProgressReport(report.id);
      setReport({ ...report, acknowledged_at: result.acknowledged_at });
    } catch (reason) {
      setError((reason as Error).message || "Could not acknowledge this report.");
    } finally {
      setBusy(null);
    }
  }

  function printReport() {
    if (!report?.permissions.can_print) return;
    // The audit request records intent; browser print remains native and immediate.
    void recordProgressReportPrint(report.id).catch(() => {});
    window.print();
  }

  async function copyInvitation() {
    if (!inviteUrl) return;
    try {
      await navigator.clipboard.writeText(inviteUrl);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  async function revokeGrant(grant: LearnerAccessGrant) {
    if (!report?.permissions.can_manage_grants || grant.revoked_at) return;
    if (
      !window.confirm(
        `Revoke this account's ${grant.capability} access? This does not change published reports.`,
      )
    ) {
      return;
    }
    try {
      await revokeReportLearnerGrant(report.learner.id, grant.id);
      setGrants((items) =>
        items.map((item) =>
          item.id === grant.id ? { ...item, revoked_at: new Date().toISOString() } : item,
        ),
      );
    } catch (reason) {
      setError((reason as Error).message || "Could not revoke access.");
    }
  }

  if (loading) {
    return (
      <div className="min-h-full bg-bone font-sans text-ink">
        <ReportHeader navigationBlocked={dirty} onNavigate={confirmNavigation} />
        <main className="mx-auto max-w-4xl px-5 py-10 sm:px-8">
          <div className="h-44 animate-pulse rounded-3xl border border-ink/5 bg-white shadow-chip" />
          <div className="mt-5 h-96 animate-pulse rounded-3xl border border-ink/5 bg-white shadow-chip" />
        </main>
      </div>
    );
  }

  if (reportId && !report) {
    return (
      <div className="min-h-full bg-bone font-sans text-ink">
        <ReportHeader navigationBlocked={dirty} onNavigate={confirmNavigation} />
        <main className="mx-auto max-w-2xl px-5 py-16 text-center sm:px-8">
          <p className="rounded-2xl border border-coral/20 bg-coral-soft px-5 py-4 text-sm font-medium text-coral-dark">
            {error ?? "This report is unavailable."}
          </p>
          <a
            href={hashFor({ kind: "reports" })}
            className="mt-6 inline-flex min-h-11 items-center rounded-full bg-ink px-5 text-sm font-semibold text-white"
          >
            Back to reports
          </a>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-full bg-bone font-sans text-ink selection:bg-cream selection:text-brand-dark print:bg-white">
      <ReportHeader navigationBlocked={dirty} onNavigate={confirmNavigation} />
      <main className="mx-auto max-w-6xl px-5 pb-24 pt-8 sm:px-8 sm:pt-10 print:max-w-none print:p-0">
        <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between print:hidden">
          <div>
            <a
              href={hashFor({ kind: "reports" })}
              onClick={(event) => {
                if (!confirmNavigation()) event.preventDefault();
              }}
              className="inline-flex min-h-10 items-center gap-1 text-sm font-medium text-ink-soft transition hover:text-ink"
            >
              <span className="material-symbols-outlined text-[18px]" aria-hidden="true">
                arrow_back
              </span>
              All reports
            </a>
            <h1 className="mt-2 font-archivo text-3xl font-semibold tracking-[-0.035em] sm:text-4xl">
              {report ? report.learner.display_alias : "New progress report"}
            </h1>
            <p className="mt-1 text-sm text-ink-soft">
              {report?.status === "published"
                ? `Published version ${report.version}`
                : "Teacher-entered observations only"}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {canEdit ? (
              <>
                <button
                  type="button"
                  onClick={() => setViewMode((mode) => (mode === "edit" ? "preview" : "edit"))}
                  className="inline-flex min-h-11 items-center gap-2 rounded-full border border-ink/10 bg-white px-5 text-sm font-semibold text-ink transition hover:border-ink/20"
                >
                  <span className="material-symbols-outlined text-[18px]" aria-hidden="true">
                    {viewMode === "edit" ? "preview" : "edit"}
                  </span>
                  {viewMode === "edit" ? "Preview" : "Edit"}
                </button>
                <button
                  type="button"
                  onClick={() => void save()}
                  disabled={busy !== null || (!!report && !dirty)}
                  className="inline-flex min-h-11 items-center rounded-full bg-ink px-5 text-sm font-semibold text-white transition hover:bg-ink/80 disabled:opacity-45"
                >
                  {busy === "save" ? "Saving..." : report ? "Save draft" : "Create draft"}
                </button>
                {report?.permissions.can_publish ? (
                  <button
                    type="button"
                    onClick={() => void publish()}
                    disabled={busy !== null}
                    className="inline-flex min-h-11 items-center rounded-full bg-brand px-5 text-sm font-semibold text-white transition hover:bg-brand-dark disabled:opacity-45"
                  >
                    {busy === "publish" ? "Publishing..." : "Publish"}
                  </button>
                ) : null}
              </>
            ) : (
              <>
                {report?.permissions.can_invite ? (
                  <>
                    <button
                      type="button"
                      onClick={() => void makeInvitation()}
                      disabled={busy !== null}
                      className="inline-flex min-h-11 items-center gap-2 rounded-full border border-ink/10 bg-white px-5 text-sm font-semibold text-ink transition hover:border-ink/20 disabled:opacity-45"
                    >
                      <span className="material-symbols-outlined text-[18px]" aria-hidden="true">
                        forward_to_inbox
                      </span>
                      Replace invitation
                    </button>
                    <button
                      type="button"
                      onClick={() => void revokeInvitations()}
                      disabled={busy !== null}
                      className="inline-flex min-h-11 items-center gap-2 rounded-full border border-coral/20 bg-white px-5 text-sm font-semibold text-coral-dark transition hover:border-coral/40 disabled:opacity-45"
                    >
                      <span className="material-symbols-outlined text-[18px]" aria-hidden="true">
                        link_off
                      </span>
                      {busy === "revoke-invites" ? "Revoking?" : "Revoke invitations"}
                    </button>
                  </>
                ) : null}
                {report?.permissions.can_correct ? (
                  <button
                    type="button"
                    onClick={() => void makeCorrection()}
                    disabled={busy !== null}
                    className="inline-flex min-h-11 items-center gap-2 rounded-full border border-ink/10 bg-white px-5 text-sm font-semibold text-ink transition hover:border-ink/20 disabled:opacity-45"
                  >
                    <span className="material-symbols-outlined text-[18px]" aria-hidden="true">
                      difference
                    </span>
                    Correct
                  </button>
                ) : null}
                {report?.permissions.can_print ? (
                  <button
                    type="button"
                    onClick={printReport}
                    className="inline-flex min-h-11 items-center gap-2 rounded-full bg-ink px-5 text-sm font-semibold text-white transition hover:bg-ink/80"
                  >
                    <span className="material-symbols-outlined text-[18px]" aria-hidden="true">
                      print
                    </span>
                    Print
                  </button>
                ) : null}
              </>
            )}
          </div>
        </div>

        {error ? (
          <p
            className="mb-6 rounded-2xl border border-coral/20 bg-coral-soft px-5 py-4 text-sm font-medium text-coral-dark print:hidden"
            role="alert"
          >
            {error}
          </p>
        ) : null}

        {inviteNotice ? (
          <p
            className="mb-6 rounded-2xl border border-brand/20 bg-brand-soft px-5 py-4 text-sm font-medium text-brand-dark print:hidden"
            role="status"
          >
            {inviteNotice}
          </p>
        ) : null}

        {invitation && inviteUrl ? (
          <InvitationPanel
            invitation={invitation}
            url={inviteUrl}
            copied={copied}
            onCopy={() => void copyInvitation()}
            onClose={() => setInvitation(null)}
          />
        ) : null}

        {viewMode === "edit" && canEdit ? (
          <ReportEditor
            draft={draft}
            onChange={changeDraft}
            learners={learners}
            isNew={!report}
            learnerId={learnerId}
            learnerAlias={learnerAlias}
            gradeBand={gradeBand}
            onLearnerIdChange={(value) => {
              setLearnerId(value);
              markDirty();
            }}
            onLearnerAliasChange={(value) => {
              setLearnerAlias(value);
              markDirty();
            }}
            onGradeBandChange={(value) => {
              setGradeBand(value);
              markDirty();
            }}
            report={report}
          />
        ) : (
          <ReportDocument
            report={report}
            draft={draft}
            learnerAlias={report?.learner.display_alias ?? (learnerAlias.trim() || "Learner")}
            gradeBand={report?.learner.grade_band ?? (gradeBand.trim() || null)}
          />
        )}

        {report?.status === "published" ? (
          <div className="mt-8 grid gap-6 lg:grid-cols-2 print:hidden">
            <AcknowledgementPanel
              report={report}
              busy={busy}
              onAcknowledge={() => void acknowledge()}
            />
            <HistoryPanel history={reportHistory} />
            {report.permissions.can_manage_grants ? (
              <GrantPanel grants={grants} onRevoke={(grant) => void revokeGrant(grant)} />
            ) : null}
          </div>
        ) : null}
      </main>
    </div>
  );
}

function ReportEditor({
  draft,
  onChange,
  learners,
  isNew,
  learnerId,
  learnerAlias,
  gradeBand,
  onLearnerIdChange,
  onLearnerAliasChange,
  onGradeBandChange,
  report,
}: {
  draft: ReportDraftFields;
  onChange: (draft: ReportDraftFields) => void;
  learners: ReportLearner[];
  isNew: boolean;
  learnerId: string;
  learnerAlias: string;
  gradeBand: string;
  onLearnerIdChange: (value: string) => void;
  onLearnerAliasChange: (value: string) => void;
  onGradeBandChange: (value: string) => void;
  report: ProgressReport | null;
}) {
  const fieldClass =
    "mt-2 min-h-12 w-full rounded-2xl border border-ink/10 bg-white px-4 py-3 text-sm text-ink outline-none transition placeholder:text-ink-faint focus:border-brand/50 focus:ring-4 focus:ring-brand/10";

  return (
    <form className="space-y-6" onSubmit={(event) => event.preventDefault()}>
      <section className="rounded-3xl border border-ink/5 bg-white p-6 shadow-chip sm:p-7">
        <h2 className="font-archivo text-xl font-semibold tracking-[-0.02em]">Report details</h2>
        <div className="mt-5 grid gap-5 sm:grid-cols-2">
          {isNew ? (
            <>
              <label className="text-sm font-semibold text-ink">
                Learner
                <select
                  value={learnerId}
                  onChange={(event) => onLearnerIdChange(event.target.value)}
                  className={fieldClass}
                >
                  <option value="new">New learner record</option>
                  {learners.map((learner) => (
                    <option key={learner.id} value={learner.id}>
                      {learner.display_alias}
                      {learner.grade_band ? ` - ${learner.grade_band}` : ""}
                    </option>
                  ))}
                </select>
              </label>
              {learnerId === "new" ? (
                <>
                  <label className="text-sm font-semibold text-ink">
                    Learner display alias
                    <input
                      value={learnerAlias}
                      onChange={(event) => onLearnerAliasChange(event.target.value)}
                      placeholder="e.g. Sam"
                      className={fieldClass}
                      maxLength={120}
                    />
                  </label>
                  <label className="text-sm font-semibold text-ink">
                    Grade band (optional)
                    <input
                      value={gradeBand}
                      onChange={(event) => onGradeBandChange(event.target.value)}
                      placeholder="e.g. Grades 6-8"
                      className={fieldClass}
                      maxLength={80}
                    />
                  </label>
                </>
              ) : null}
            </>
          ) : (
            <div className="rounded-2xl bg-sand p-4">
              <p className="text-xs font-semibold uppercase tracking-wider text-ink-faint">Learner</p>
              <p className="mt-1 font-semibold">{report?.learner.display_alias}</p>
              {report?.learner.grade_band ? (
                <p className="mt-0.5 text-xs text-ink-soft">{report.learner.grade_band}</p>
              ) : null}
            </div>
          )}
          <label className="text-sm font-semibold text-ink">
            Author display name (self-entered)
            <input
              value={draft.author_display_name}
              onChange={(event) => onChange({ ...draft, author_display_name: event.target.value })}
              placeholder="Name shown on the report"
              className={fieldClass}
              maxLength={REPORT_LIMITS.authorName}
            />
          </label>
          <label className="text-sm font-semibold text-ink">
            Reporting period starts
            <input
              type="date"
              value={draft.reporting_period_start ?? ""}
              onChange={(event) =>
                onChange({ ...draft, reporting_period_start: event.target.value || null })
              }
              className={fieldClass}
            />
          </label>
          <label className="text-sm font-semibold text-ink">
            Reporting period ends
            <input
              type="date"
              value={draft.reporting_period_end ?? ""}
              onChange={(event) =>
                onChange({ ...draft, reporting_period_end: event.target.value || null })
              }
              className={fieldClass}
            />
          </label>
        </div>
      </section>

      <StringListEditor
        title="Learning goals"
        description="What the learner was working toward during this period."
        items={draft.content.learning_goals}
        maxItems={REPORT_LIMITS.learningGoals}
        onChange={(items) =>
          onChange({ ...draft, content: { ...draft.content, learning_goals: items } })
        }
      />
      <StringListEditor
        title="Work completed"
        description="Projects, assignments, lessons, or milestones completed."
        items={draft.content.work_completed}
        maxItems={REPORT_LIMITS.workCompleted}
        onChange={(items) =>
          onChange({ ...draft, content: { ...draft.content, work_completed: items } })
        }
      />
      <EvidenceListEditor
        title="Strengths"
        description="Pair every strength with teacher-entered evidence."
        items={draft.content.strengths}
        maxItems={REPORT_LIMITS.evidenceItems}
        onChange={(items) =>
          onChange({ ...draft, content: { ...draft.content, strengths: items } })
        }
      />
      <EvidenceListEditor
        title="Areas needing support"
        description="Describe the support need and the evidence behind it."
        items={draft.content.support_areas}
        maxItems={REPORT_LIMITS.evidenceItems}
        onChange={(items) =>
          onChange({ ...draft, content: { ...draft.content, support_areas: items } })
        }
      />
      <section className="rounded-3xl border border-ink/5 bg-white p-6 shadow-chip sm:p-7">
        <label className="text-sm font-semibold text-ink">
          Teacher observations
          <textarea
            value={draft.content.teacher_observations}
            onChange={(event) =>
              onChange({
                ...draft,
                content: { ...draft.content, teacher_observations: event.target.value },
              })
            }
            rows={6}
            maxLength={REPORT_LIMITS.observations}
            placeholder="Add direct observations. Do not paste private tutor conversations or inferred attention data."
            className={`${fieldClass} resize-y leading-6`}
          />
        </label>
      </section>
      <StringListEditor
        title="Recommended next actions"
        description="Concrete steps the learner, family, or teacher can take next."
        items={draft.content.next_actions}
        maxItems={REPORT_LIMITS.nextActions}
        onChange={(items) =>
          onChange({ ...draft, content: { ...draft.content, next_actions: items } })
        }
      />
    </form>
  );
}

function StringListEditor({
  title,
  description,
  items,
  maxItems,
  onChange,
}: {
  title: string;
  description: string;
  items: string[];
  maxItems: number;
  onChange: (items: string[]) => void;
}) {
  return (
    <section className="rounded-3xl border border-ink/5 bg-white p-6 shadow-chip sm:p-7">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-archivo text-xl font-semibold tracking-[-0.02em]">{title}</h2>
          <p className="mt-1 text-sm leading-6 text-ink-soft">{description}</p>
        </div>
        <button
          type="button"
          onClick={() => onChange([...items, ""])}
          disabled={items.length >= maxItems}
          className="inline-flex min-h-10 shrink-0 items-center gap-1 rounded-full bg-sand px-4 text-xs font-semibold text-ink transition hover:bg-line disabled:cursor-not-allowed disabled:opacity-45"
        >
          <span className="material-symbols-outlined text-[16px]" aria-hidden="true">
            add
          </span>
          Add
        </button>
      </div>
      <div className="mt-5 space-y-3">
        {(items.length > 0 ? items : [""]).map((item, index) => (
          <div key={index} className="flex items-start gap-2">
            <textarea
              value={item}
              onChange={(event) => {
                const next = items.length > 0 ? [...items] : [""];
                next[index] = event.target.value;
                onChange(next);
              }}
              rows={2}
              maxLength={REPORT_LIMITS.listItem}
              aria-label={`${title} item ${index + 1}`}
              className="min-h-12 flex-1 resize-y rounded-2xl border border-ink/10 bg-white px-4 py-3 text-sm leading-6 outline-none transition focus:border-brand/50 focus:ring-4 focus:ring-brand/10"
            />
            <button
              type="button"
              onClick={() => onChange(items.filter((_, itemIndex) => itemIndex !== index))}
              className="grid h-11 w-11 shrink-0 place-items-center rounded-full text-ink-faint transition hover:bg-coral-soft hover:text-coral-dark"
              aria-label={`Remove ${title.toLowerCase()} item ${index + 1}`}
            >
              <span className="material-symbols-outlined text-[19px]" aria-hidden="true">
                close
              </span>
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}

function EvidenceListEditor({
  title,
  description,
  items,
  maxItems,
  onChange,
}: {
  title: string;
  description: string;
  items: { statement: string; evidence: string }[];
  maxItems: number;
  onChange: (items: { statement: string; evidence: string }[]) => void;
}) {
  const rows = items.length > 0 ? items : [{ statement: "", evidence: "" }];
  return (
    <section className="rounded-3xl border border-ink/5 bg-white p-6 shadow-chip sm:p-7">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-archivo text-xl font-semibold tracking-[-0.02em]">{title}</h2>
          <p className="mt-1 text-sm leading-6 text-ink-soft">{description}</p>
        </div>
        <button
          type="button"
          onClick={() => onChange([...items, { statement: "", evidence: "" }])}
          disabled={items.length >= maxItems}
          className="inline-flex min-h-10 shrink-0 items-center gap-1 rounded-full bg-sand px-4 text-xs font-semibold text-ink transition hover:bg-line disabled:cursor-not-allowed disabled:opacity-45"
        >
          <span className="material-symbols-outlined text-[16px]" aria-hidden="true">
            add
          </span>
          Add
        </button>
      </div>
      <div className="mt-5 space-y-4">
        {rows.map((item, index) => (
          <div key={index} className="rounded-2xl bg-sand/70 p-4">
            <div className="flex items-start gap-2">
              <div className="grid min-w-0 flex-1 gap-3 sm:grid-cols-2">
                <label className="text-xs font-semibold uppercase tracking-wider text-ink-soft">
                  Statement
                  <textarea
                    value={item.statement}
                    onChange={(event) => {
                      const next = items.length > 0 ? [...items] : [...rows];
                      next[index] = { ...item, statement: event.target.value };
                      onChange(next);
                    }}
                    rows={3}
                    maxLength={REPORT_LIMITS.evidenceStatement}
                    className="mt-2 w-full resize-y rounded-2xl border border-ink/10 bg-white px-4 py-3 text-sm font-normal normal-case leading-6 tracking-normal text-ink outline-none transition focus:border-brand/50 focus:ring-4 focus:ring-brand/10"
                  />
                </label>
                <label className="text-xs font-semibold uppercase tracking-wider text-ink-soft">
                  Evidence
                  <textarea
                    value={item.evidence}
                    onChange={(event) => {
                      const next = items.length > 0 ? [...items] : [...rows];
                      next[index] = { ...item, evidence: event.target.value };
                      onChange(next);
                    }}
                    rows={3}
                    maxLength={REPORT_LIMITS.evidenceDetail}
                    className="mt-2 w-full resize-y rounded-2xl border border-ink/10 bg-white px-4 py-3 text-sm font-normal normal-case leading-6 tracking-normal text-ink outline-none transition focus:border-brand/50 focus:ring-4 focus:ring-brand/10"
                  />
                </label>
              </div>
              <button
                type="button"
                onClick={() => onChange(items.filter((_, itemIndex) => itemIndex !== index))}
                className="grid h-10 w-10 shrink-0 place-items-center rounded-full text-ink-faint transition hover:bg-coral-soft hover:text-coral-dark"
                aria-label={`Remove ${title.toLowerCase()} item ${index + 1}`}
              >
                <span className="material-symbols-outlined text-[18px]" aria-hidden="true">
                  close
                </span>
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function ReportDocument({
  report,
  draft,
  learnerAlias,
  gradeBand,
}: {
  report: ProgressReport | null;
  draft: ReportDraftFields;
  learnerAlias: string;
  gradeBand: string | null;
}) {
  return (
    <article className="rounded-3xl border border-ink/5 bg-white p-7 shadow-chip sm:p-10 print:rounded-none print:border-0 print:p-0 print:shadow-none">
      <header className="border-b border-ink/10 pb-7">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-brand-dark">
              Progress report
            </p>
            <h1 className="mt-2 font-archivo text-3xl font-semibold tracking-[-0.035em]">
              {learnerAlias}
            </h1>
            {gradeBand ? <p className="mt-1 text-sm text-ink-soft">{gradeBand}</p> : null}
          </div>
          <div className="text-left text-sm leading-6 text-ink-soft sm:text-right">
            <p>{formatPeriod(draft.reporting_period_start, draft.reporting_period_end)}</p>
            <p>Prepared by {draft.author_display_name || "Teacher"}</p>
            {report ? <p>Signed-in author ref {report.author_account_ref}</p> : null}
            {report ? <p>Version {report.version}</p> : null}
          </div>
        </div>
      </header>
      <div className="mt-8 space-y-9">
        <DocumentList title="Learning goals" items={draft.content.learning_goals} />
        <DocumentList title="Work completed" items={draft.content.work_completed} />
        <EvidenceSection title="Strengths" items={draft.content.strengths} />
        <EvidenceSection title="Areas needing support" items={draft.content.support_areas} />
        <DocumentSection title="Teacher observations">
          <p className="whitespace-pre-wrap text-sm leading-7 text-ink-soft">
            {draft.content.teacher_observations.trim() || "No observations added."}
          </p>
        </DocumentSection>
        <DocumentList title="Recommended next actions" items={draft.content.next_actions} />
      </div>
      <footer className="mt-10 border-t border-ink/10 pt-5 text-xs leading-5 text-ink-faint">
        This report contains teacher-entered observations. It does not automatically disclose private
        tutor conversations, raw questions, or inferred attention data.
      </footer>
    </article>
  );
}

function DocumentSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="font-archivo text-xl font-semibold tracking-[-0.02em]">{title}</h2>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function DocumentList({ title, items }: { title: string; items: string[] }) {
  const visible = items.filter((item) => item.trim());
  return (
    <DocumentSection title={title}>
      {visible.length > 0 ? (
        <ul className="space-y-2">
          {visible.map((item, index) => (
            <li key={index} className="flex gap-3 text-sm leading-7 text-ink-soft">
              <span className="mt-[0.65rem] h-1.5 w-1.5 shrink-0 rounded-full bg-brand" />
              <span className="whitespace-pre-wrap">{item}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-ink-faint">Nothing added yet.</p>
      )}
    </DocumentSection>
  );
}

function EvidenceSection({
  title,
  items,
}: {
  title: string;
  items: { statement: string; evidence: string }[];
}) {
  const visible = items.filter((item) => item.statement.trim() || item.evidence.trim());
  return (
    <DocumentSection title={title}>
      {visible.length > 0 ? (
        <div className="space-y-3">
          {visible.map((item, index) => (
            <div key={index} className="rounded-2xl bg-sand/70 p-4 print:bg-white print:p-0">
              <p className="whitespace-pre-wrap text-sm font-semibold leading-6 text-ink">
                {item.statement || "Observation"}
              </p>
              <p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-ink-soft">
                <span className="font-semibold text-ink">Evidence:</span>{" "}
                {item.evidence || "Not provided"}
              </p>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-ink-faint">Nothing added yet.</p>
      )}
    </DocumentSection>
  );
}

function InvitationPanel({
  invitation,
  url,
  copied,
  onCopy,
  onClose,
}: {
  invitation: ReportInvitation;
  url: string;
  copied: boolean;
  onCopy: () => void;
  onClose: () => void;
}) {
  return (
    <section className="mb-6 rounded-3xl border border-brand/20 bg-cream p-5 shadow-chip sm:p-6 print:hidden">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand-dark">
            One-time invitation
          </p>
          <h2 className="mt-1 font-archivo text-xl font-semibold tracking-[-0.02em]">
            Copy this link now
          </h2>
          <p className="mt-1 text-sm leading-6 text-ink-soft">
            The raw token is shown only in this response and expires {formatDate(invitation.expires_at)}.
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="grid h-10 w-10 shrink-0 place-items-center rounded-full text-ink-faint transition hover:bg-white hover:text-ink"
          aria-label="Close invitation"
        >
          <span className="material-symbols-outlined text-[19px]" aria-hidden="true">
            close
          </span>
        </button>
      </div>
      <div className="mt-4 flex flex-col gap-2 sm:flex-row">
        <input
          readOnly
          value={url}
          onFocus={(event) => event.currentTarget.select()}
          aria-label="Report invitation URL"
          className="min-h-11 min-w-0 flex-1 rounded-2xl border border-ink/10 bg-white px-4 text-sm text-ink outline-none transition focus:border-brand/50 focus:ring-4 focus:ring-brand/10"
        />
        <button
          type="button"
          onClick={onCopy}
          className="inline-flex min-h-11 items-center justify-center gap-2 rounded-full bg-ink px-5 text-sm font-semibold text-white transition hover:bg-ink/80"
        >
          <span className="material-symbols-outlined text-[18px]" aria-hidden="true">
            {copied ? "check" : "content_copy"}
          </span>
          {copied ? "Copied" : "Copy link"}
        </button>
      </div>
      <p className="mt-2 text-xs text-ink-faint" aria-live="polite">
        {copied ? "Invitation copied." : "If clipboard access is unavailable, select and copy the URL."}
      </p>
    </section>
  );
}

function AcknowledgementPanel({
  report,
  busy,
  onAcknowledge,
}: {
  report: ProgressReport;
  busy: BusyAction;
  onAcknowledge: () => void;
}) {
  return (
    <section className="rounded-3xl border border-ink/5 bg-white p-6 shadow-chip">
      <h2 className="font-archivo text-xl font-semibold tracking-[-0.02em]">Acknowledgement</h2>
      {report.acknowledged_at ? (
        <p className="mt-3 inline-flex items-center gap-2 rounded-full bg-mint px-3.5 py-2 text-sm font-semibold text-lime-dark">
          <span className="material-symbols-outlined text-[18px]" aria-hidden="true">
            check_circle
          </span>
          Acknowledged {formatDate(report.acknowledged_at)}
        </p>
      ) : report.permissions.can_acknowledge ? (
        <>
          <p className="mt-2 text-sm leading-6 text-ink-soft">
            Acknowledging confirms that you received and read this version. It does not mean you agree
            with every statement.
          </p>
          <button
            type="button"
            onClick={onAcknowledge}
            disabled={busy !== null}
            className="mt-4 inline-flex min-h-11 items-center rounded-full bg-ink px-5 text-sm font-semibold text-white transition hover:bg-ink/80 disabled:opacity-45"
          >
            {busy === "acknowledge" ? "Acknowledging..." : "Acknowledge receipt"}
          </button>
        </>
      ) : (
        <p className="mt-2 text-sm leading-6 text-ink-soft">Waiting for family acknowledgement.</p>
      )}
    </section>
  );
}

function HistoryPanel({ history }: { history: ReportHistory | null }) {
  return (
    <section className="rounded-3xl border border-ink/5 bg-white p-6 shadow-chip">
      <h2 className="font-archivo text-xl font-semibold tracking-[-0.02em]">Version history</h2>
      {!history ? (
        <p className="mt-3 text-sm text-ink-faint">Loading history...</p>
      ) : (
        <div className="mt-4 space-y-4">
          <div className="flex flex-wrap gap-2">
            {history.reports.map((item) => (
              <a
                key={item.id}
                href={hashFor({ kind: "report", reportId: item.id })}
                className="rounded-full bg-sand px-3 py-1.5 text-xs font-semibold text-ink-soft transition hover:text-ink"
              >
                Version {item.version}
              </a>
            ))}
          </div>
          <ol className="space-y-2">
            {history.events.slice(0, 8).map((event) => (
              <li key={event.id} className="flex items-center justify-between gap-3 text-xs">
                <span className="font-medium capitalize text-ink-soft">
                  {event.event_type.replaceAll("_", " ")}
                </span>
                <time className="shrink-0 text-ink-faint" dateTime={event.created_at}>
                  {formatDate(event.created_at)}
                </time>
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  );
}

function GrantPanel({
  grants,
  onRevoke,
}: {
  grants: LearnerAccessGrant[];
  onRevoke: (grant: LearnerAccessGrant) => void;
}) {
  return (
    <section className="rounded-3xl border border-ink/5 bg-white p-6 shadow-chip lg:col-span-2">
      <h2 className="font-archivo text-xl font-semibold tracking-[-0.02em]">Learner access</h2>
      <p className="mt-1 text-sm leading-6 text-ink-soft">
        Revoke one permission at a time. Removing report:create stops future authoring;
        report:view removes ongoing read access. Published versions stay unchanged.
      </p>
      {grants.length === 0 ? (
        <p className="mt-4 text-sm text-ink-faint">No additional grants.</p>
      ) : (
        <ul className="mt-4 divide-y divide-ink/5">
          {grants.map((grant) => {
            const canRevoke =
              grant.capability !== "custody:manage" && !grant.revoked_at;
            return (
              <li key={grant.id} className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-ink">{grant.capability}</p>
                  <p className="mt-0.5 truncate text-xs text-ink-faint">
                    Account ...{grant.principal_user_id.slice(-8)}
                    {grant.revoked_at ? ` | revoked ${formatDate(grant.revoked_at)}` : ""}
                  </p>
                </div>
                {canRevoke ? (
                  <button
                    type="button"
                    onClick={() => onRevoke(grant)}
                    className="inline-flex min-h-10 items-center justify-center rounded-full border border-coral/20 px-4 text-xs font-semibold text-coral-dark transition hover:bg-coral-soft"
                  >
                    {grant.capability === "report:create"
                      ? "Revoke future authoring"
                      : "Revoke viewing"}
                  </button>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function emptyContent(): ReportContent {
  return {
    learning_goals: [],
    work_completed: [],
    strengths: [],
    support_areas: [],
    teacher_observations: "",
    next_actions: [],
  };
}

function emptyDraft(authorDisplayName: string): ReportDraftFields {
  return {
    author_display_name: authorDisplayName,
    reporting_period_start: null,
    reporting_period_end: null,
    content: emptyContent(),
  };
}

function draftFromReport(report: ProgressReport): ReportDraftFields {
  return {
    author_display_name: report.author_display_name,
    reporting_period_start: report.reporting_period_start,
    reporting_period_end: report.reporting_period_end,
    content: structuredClone(report.content),
  };
}

function cleanDraft(draft: ReportDraftFields): ReportDraftFields {
  const cleanStrings = (items: string[]) => items.map((item) => item.trim()).filter(Boolean);
  const cleanEvidence = (items: { statement: string; evidence: string }[]) =>
    items
      .map((item) => ({ statement: item.statement.trim(), evidence: item.evidence.trim() }))
      .filter((item) => item.statement || item.evidence);
  return {
    author_display_name: draft.author_display_name.trim(),
    reporting_period_start: draft.reporting_period_start,
    reporting_period_end: draft.reporting_period_end,
    content: {
      learning_goals: cleanStrings(draft.content.learning_goals),
      work_completed: cleanStrings(draft.content.work_completed),
      strengths: cleanEvidence(draft.content.strengths),
      support_areas: cleanEvidence(draft.content.support_areas),
      teacher_observations: draft.content.teacher_observations.trim(),
      next_actions: cleanStrings(draft.content.next_actions),
    },
  };
}

function validateDraft(
  draft: ReportDraftFields,
  learnerAlias: string,
  learnerId: string,
): string | null {
  if (!draft.author_display_name.trim()) return "Add the author name shown on the report.";
  if (draft.author_display_name.trim().length > REPORT_LIMITS.authorName) {
    return `Keep the author name under ${REPORT_LIMITS.authorName} characters.`;
  }
  if (learnerId === "new" && !learnerAlias.trim()) return "Add a learner display alias.";
  if (learnerAlias.trim().length > 120) return "Keep the learner alias under 120 characters.";
  if (
    draft.reporting_period_start &&
    draft.reporting_period_end &&
    draft.reporting_period_start > draft.reporting_period_end
  ) {
    return "The reporting period end date must be on or after its start date.";
  }
  const listSections: Array<[string, string[], number]> = [
    ["learning goals", draft.content.learning_goals, REPORT_LIMITS.learningGoals],
    ["work completed", draft.content.work_completed, REPORT_LIMITS.workCompleted],
    ["recommended next actions", draft.content.next_actions, REPORT_LIMITS.nextActions],
  ];
  for (const [label, items, maxItems] of listSections) {
    if (items.length > maxItems) return `Keep ${label} to ${maxItems} items or fewer.`;
    if (items.some((item) => item.trim().length > REPORT_LIMITS.listItem)) {
      return `Keep each ${label} item under ${REPORT_LIMITS.listItem.toLocaleString()} characters.`;
    }
  }
  const evidenceSections: Array<
    [string, Array<{ statement: string; evidence: string }>]
  > = [
    ["strength", draft.content.strengths],
    ["support area", draft.content.support_areas],
  ];
  for (const [label, items] of evidenceSections) {
    if (items.length > REPORT_LIMITS.evidenceItems) {
      return `Keep ${label} evidence to ${REPORT_LIMITS.evidenceItems} items or fewer.`;
    }
    for (const item of items) {
      const statement = item.statement.trim();
      const evidence = item.evidence.trim();
      if (Boolean(statement) !== Boolean(evidence)) {
        return `Complete both the statement and evidence for every ${label}, or remove the empty row.`;
      }
      if (statement.length > REPORT_LIMITS.evidenceStatement) {
        return `Keep each ${label} statement under ${REPORT_LIMITS.evidenceStatement.toLocaleString()} characters.`;
      }
      if (evidence.length > REPORT_LIMITS.evidenceDetail) {
        return `Keep each ${label} evidence note under ${REPORT_LIMITS.evidenceDetail.toLocaleString()} characters.`;
      }
    }
  }
  if (draft.content.teacher_observations.length > REPORT_LIMITS.observations) {
    return `Keep teacher observations under ${REPORT_LIMITS.observations.toLocaleString()} characters.`;
  }
  return null;
}

function buildInvitationUrl(token: string): string {
  const url = new URL(window.location.pathname, window.location.origin);
  url.hash = hashFor({ kind: "reportInvite", token });
  return url.toString();
}

function formatPeriod(start: string | null, end: string | null): string {
  if (!start && !end) return "Reporting period not set";
  if (start && end) return `${formatDate(start)} - ${formatDate(end)}`;
  return formatDate(start ?? end!);
}

function formatDate(value: string): string {
  const parsed = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(
    parsed,
  );
}
