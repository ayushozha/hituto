import { useEffect, useState } from "react";

import { ProgressReport, listProgressReports } from "../../api";
import { hashFor } from "../../routing";
import { ReportHeader } from "./ReportHeader";

type ReportLists = {
  authored: ProgressReport[];
  family: ProgressReport[];
};

export function ReportsHome() {
  const [reports, setReports] = useState<ReportLists | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([listProgressReports("family"), listProgressReports("authored")])
      .then(([family, authored]) => {
        if (active) setReports({ authored, family });
      })
      .catch((reason) => {
        if (active) setError((reason as Error).message || "Could not load reports.");
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="min-h-full bg-bone font-sans text-ink selection:bg-cream selection:text-brand-dark">
      <ReportHeader />
      <main className="mx-auto max-w-6xl px-5 pb-24 pt-8 sm:px-8 sm:pt-10">
        <section className="animate-fade-up rounded-3xl border border-ink/5 bg-white p-7 shadow-chip sm:p-9">
          <div className="flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
            <div className="max-w-2xl">
              <span className="inline-flex items-center gap-2 rounded-full border border-ink/5 bg-white px-3.5 py-1.5 text-xs font-semibold text-ink-soft shadow-chip">
                <span className="h-1.5 w-1.5 rounded-full bg-brand" aria-hidden="true" />
                Parent-custodied progress
              </span>
              <h1 className="mt-5 font-archivo text-[clamp(2.25rem,5vw,3.5rem)] font-semibold leading-[1.03] tracking-[-0.04em]">
                Clear reports. <span className="text-brand">Careful handoffs.</span>
              </h1>
              <p className="mt-3 max-w-xl text-sm leading-6 text-ink-soft sm:text-[15px]">
                Write an evidence-backed update, or open reports that have been delivered to your family.
                Tutor conversations and private learning insights are never added automatically.
              </p>
            </div>
            <a
              href={hashFor({ kind: "reportNew" })}
              className="inline-flex min-h-12 shrink-0 items-center justify-center gap-2 rounded-full bg-ink px-6 text-sm font-semibold text-white transition hover:bg-ink/80"
            >
              <span className="material-symbols-outlined text-[19px]" aria-hidden="true">
                note_add
              </span>
              New report
            </a>
          </div>
        </section>

        {error ? (
          <p
            className="mt-6 rounded-2xl border border-coral/20 bg-coral-soft px-5 py-4 text-sm font-medium text-coral-dark"
            role="alert"
          >
            {error}
          </p>
        ) : null}

        {!reports && !error ? (
          <div className="mt-8 grid gap-4 sm:grid-cols-2">
            {[0, 1, 2, 3].map((item) => (
              <div
                key={item}
                className="h-44 animate-pulse rounded-3xl border border-ink/5 bg-white shadow-chip"
              />
            ))}
          </div>
        ) : null}

        {reports ? (
          <div className="mt-10 space-y-12">
            <ReportShelf
              title="Family reports"
              description="Published reports claimed into learner records you manage."
              reports={reports.family}
              empty="Claimed family reports will appear here."
            />
            <ReportShelf
              title="Written by you"
              description="Drafts and published reports where you are the attributed author."
              reports={reports.authored}
              empty="Create a report to start a careful parent handoff."
            />
          </div>
        ) : null}
      </main>
    </div>
  );
}

function ReportShelf({
  title,
  description,
  reports,
  empty,
}: {
  title: string;
  description: string;
  reports: ProgressReport[];
  empty: string;
}) {
  return (
    <section aria-labelledby={`${title.toLowerCase().replaceAll(" ", "-")}-heading`}>
      <div className="mb-4">
        <h2
          id={`${title.toLowerCase().replaceAll(" ", "-")}-heading`}
          className="font-archivo text-2xl font-semibold tracking-[-0.025em]"
        >
          {title}
        </h2>
        <p className="mt-1 text-sm leading-6 text-ink-soft">{description}</p>
      </div>
      {reports.length === 0 ? (
        <div className="rounded-3xl border border-dashed border-ink/10 bg-white/70 px-6 py-10 text-center text-sm text-ink-soft">
          {empty}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {reports.map((report) => (
            <a
              key={report.id}
              href={hashFor({ kind: "report", reportId: report.id })}
              className="group flex min-h-44 flex-col rounded-3xl border border-ink/5 bg-white p-5 shadow-chip transition hover:-translate-y-0.5 hover:shadow-lift"
            >
              <div className="flex items-start justify-between gap-3">
                <span className="grid h-10 w-10 place-items-center rounded-xl bg-cream text-brand">
                  <span className="material-symbols-outlined text-[21px]" aria-hidden="true">
                    description
                  </span>
                </span>
                <ReportStatus report={report} />
              </div>
              <h3 className="mt-4 font-archivo text-lg font-semibold tracking-[-0.02em]">
                {report.learner.display_alias}
              </h3>
              <p className="mt-1 text-xs font-medium text-ink-soft">
                {formatPeriod(report)}
                {report.learner.grade_band ? ` | ${report.learner.grade_band}` : ""}
              </p>
              <div className="mt-auto flex items-end justify-between gap-3 pt-5">
                <span className="text-xs text-ink-faint">
                  {report.status === "draft"
                    ? `Updated ${formatDate(report.updated_at)}`
                    : `By ${report.author_display_name}`}
                </span>
                <span className="material-symbols-outlined text-[18px] text-ink-faint transition group-hover:translate-x-0.5 group-hover:text-ink">
                  arrow_forward
                </span>
              </div>
            </a>
          ))}
        </div>
      )}
    </section>
  );
}

function ReportStatus({ report }: { report: ProgressReport }) {
  const acknowledged = report.acknowledged_at !== null;
  return (
    <span
      className={`rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider ${
        report.status === "draft"
          ? "bg-sand text-ink-soft"
          : acknowledged
            ? "bg-mint text-lime-dark"
            : "bg-cream text-brand-dark"
      }`}
    >
      {report.status === "draft" ? "Draft" : acknowledged ? "Acknowledged" : "Published"}
    </span>
  );
}

function formatPeriod(report: ProgressReport): string {
  if (!report.reporting_period_start && !report.reporting_period_end) return "Reporting period not set";
  if (report.reporting_period_start && report.reporting_period_end) {
    return `${formatDate(report.reporting_period_start)} - ${formatDate(report.reporting_period_end)}`;
  }
  return formatDate(report.reporting_period_start ?? report.reporting_period_end!);
}

function formatDate(value: string): string {
  const parsed = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(
    parsed,
  );
}
