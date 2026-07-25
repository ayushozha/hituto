import { CourseCard } from "../api";

export function StatusPill({ status }: { status: CourseCard["status"] }) {
  const map = {
    generating: "border-coral-dark bg-peach text-coral-dark",
    outline_review: "border-cobalt bg-lilac text-cobalt-dark",
    ready: "border-lime-dark bg-lime text-lime-dark",
    failed: "border-rose-600 bg-rose-100 text-rose-700",
  } as const;

  return (
    <span className={`rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider ${map[status]}`}>
      {status === "outline_review" ? "review outline" : status}
    </span>
  );
}
