import { getCachedToken, getFreshToken } from "./lib/authToken";
import { insforge } from "./lib/insforge";

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

/** Prefix backend tool-server paths (/gen, /image, …) for split frontend/API deploys. */
export function mediaUrl(path: string | null | undefined): string | null {
  if (!path) return null;
  if (/^https?:\/\//i.test(path)) return path;
  return apiUrl(path);
}

// Sync URL builder for contexts that cannot await (iframe `src`, WebSocket URLs). Uses the
// last token cached by getFreshToken(), kept warm by ongoing requests + AuthProvider priming.
function withAccessToken(path: string): string {
  const full = apiUrl(path);
  const token = getCachedToken();
  if (!token) return full;
  const sep = full.includes("?") ? "&" : "?";
  return `${full}${sep}access_token=${encodeURIComponent(token)}`;
}

/** Same-origin URL for a stored generate_ui (Path B) capsule, for the sandboxed iframe `src`. */
export function tutorUiUrl(courseId: string, lessonId: string, uiId: string): string {
  return withAccessToken(
    `/courses/${courseId}/lessons/${lessonId}/tutor/ui/${encodeURIComponent(uiId)}`
  );
}

export type Knobs = {
  difficulty: "beginner" | "intermediate" | "advanced";
  depth?: "single-page" | "multi-lesson";
  style_theme?: string | null;
  archetype?: "auto" | "explainer" | "simulation" | "game" | "tool" | "narrative";
  /** Capsule shell / design mode — orthogonal to lesson style (archetype). */
  design_mode?: "auto" | "studio" | "page" | "slide" | "reading";
  /** @deprecated Prefer design_mode. Accepted for older clients. */
  presentation?: "auto" | "studio" | "page" | "slide" | "reading";
  studio_mode?: "auto" | "specimen" | "simulation" | "process-cutaway";
  require_teacher_review?: boolean;
  /** Opt-in chapter-outline review before any lesson generates. */
  review_outline?: boolean;
  needs_3d?: boolean;
  subject?: string | null;
};

export type SourceRef = {
  id: string;
  title: string | null;
  filename: string;
  source_type: string | null;
};

export type CourseCard = {
  id: string;
  topic: string;
  title: string | null;
  archetype: string | null;
  status: "generating" | "outline_review" | "ready" | "failed";
  error: string | null;
  lesson_count: number;
  completed_count: number;
  tagline: string | null;
  estimated_minutes: number;
  design_mode?: NonNullable<Knobs["design_mode"]>;
  updated_at: string;
  source?: SourceRef | null;
};

export type Progress = {
  stage: string;
  detail: string;
  pct: number;
  /** Rich frames only (skeleton, gen_fragment, …) — see specs/fast_gen §4. */
  data?: Record<string, unknown> | null;
};

export type Lesson = {
  id: string;
  ordinal: number;
  title: string;
  objective: string;
  completed: boolean;
  status: "pending" | "generating" | "awaiting_review" | "ready" | "failed";
  error: string | null;
  estimated_duration: string;
  archetype: string;
  module_ordinal: number | null;
  module_title: string | null;
  is_shared: boolean;
};

export type CourseDetail = CourseCard & { lessons: Lesson[] };

export type ArtifactVersion = {
  id: string;
  lesson_id: string;
  version: number;
  kind?: "html" | "a2ui" | "reading";
  checks: Record<string, unknown>;
  created_at: string;
};

export type ArtifactA2UI = {
  kind: "a2ui";
  version: number;
  title: string;
  intent: string;
  root: { type: string; props?: Record<string, unknown>; children?: unknown[] };
  sections?: {
    id: string;
    title: string;
    root: { type: string; props?: Record<string, unknown>; children?: unknown[] };
  }[];
  checks: Record<string, unknown>;
};

/** Trusted reading companion (specs/design_agents step 4): verbatim source prose + annotations. */
export type ReadingDoc = {
  kind: "reading";
  schema_version: string;
  title: string;
  intent: string;
  source_document_id: string | null;
  sections: {
    id: string;
    title: string;
    objective: string;
    body_md: string;
    notes: { anchor: string; text: string }[];
    check: { question: string; answer: string } | null;
  }[];
  glossary: { term: string; definition: string }[];
};

export type ArtifactReading = {
  kind: "reading";
  version: number;
  doc: ReadingDoc;
  checks: Record<string, unknown>;
};

async function authHeaders(extra: HeadersInit = {}): Promise<HeadersInit> {
  const token = await getFreshToken();
  return {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...extra,
  };
}

// Parent-custodied progress reports

export type ReportEvidenceItem = {
  statement: string;
  evidence: string;
};

export type ReportContent = {
  learning_goals: string[];
  work_completed: string[];
  strengths: ReportEvidenceItem[];
  support_areas: ReportEvidenceItem[];
  teacher_observations: string;
  next_actions: string[];
};

export type ReportLearner = {
  id: string;
  display_alias: string;
  grade_band: string | null;
};

export type ReportPermissions = {
  can_edit: boolean;
  can_publish: boolean;
  can_invite: boolean;
  can_correct: boolean;
  can_acknowledge: boolean;
  can_print: boolean;
  can_manage_grants: boolean;
};

export type ProgressReport = {
  id: string;
  series_id: string;
  learner: ReportLearner;
  author_display_name: string;
  author_account_ref: string;
  version: number;
  supersedes_id: string | null;
  status: "draft" | "published";
  reporting_period_start: string | null;
  reporting_period_end: string | null;
  schema_version: 1;
  evidence_mode: "teacher_entered";
  content: ReportContent;
  published_at: string | null;
  created_at: string;
  updated_at: string;
  acknowledged_at: string | null;
  permissions: ReportPermissions;
};

export type ReportInvitation = {
  id: string;
  token: string;
  expires_at: string;
};

export type ReportDraftFields = {
  author_display_name: string;
  reporting_period_start: string | null;
  reporting_period_end: string | null;
  content: ReportContent;
};

export type CreateProgressReportInput = ReportDraftFields &
  (
    | { learner_id: string; learner?: never }
    | { learner_id?: never; learner: { display_alias: string; grade_band: string | null } }
  );

export type ReportAuditEvent = {
  id: string;
  event_type: string;
  created_at: string;
};

export type ReportHistory = {
  reports: ProgressReport[];
  events: ReportAuditEvent[];
};

export type LearnerAccessGrant = {
  id: string;
  principal_user_id: string;
  capability: string;
  accepted_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
};

async function reportApiError(response: Response, fallback: string): Promise<Error> {
  const detail = (await response.json().catch(() => ({}))).detail;
  if (typeof detail === "string") return new Error(detail);
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (!item || typeof item !== "object") return null;
        const location = Array.isArray(item.loc)
          ? item.loc.filter((part: unknown) => part !== "body").join(".")
          : "";
        const message = typeof item.msg === "string" ? item.msg : "";
        return message ? `${location ? `${location}: ` : ""}${message}` : null;
      })
      .filter((message): message is string => Boolean(message));
    if (messages.length > 0) return new Error(messages.join("; "));
  }
  return new Error(fallback);
}

export async function listProgressReports(
  scope: "authored" | "family",
): Promise<ProgressReport[]> {
  const qs = new URLSearchParams({ scope });
  const response = await fetch(apiUrl(`/reports?${qs}`), { headers: await authHeaders() });
  if (!response.ok) throw await reportApiError(response, "failed to load reports");
  return response.json();
}

export async function listReportLearners(
  scope: "authoring" | "custody" = "authoring",
): Promise<ReportLearner[]> {
  const qs = new URLSearchParams({ scope });
  const response = await fetch(apiUrl(`/reports/learners?${qs}`), {
    headers: await authHeaders(),
  });
  if (!response.ok) throw await reportApiError(response, "failed to load learners");
  return response.json();
}

export async function createProgressReport(
  input: CreateProgressReportInput,
): Promise<ProgressReport> {
  const response = await fetch(apiUrl("/reports"), {
    method: "POST",
    headers: await authHeaders({ "content-type": "application/json" }),
    body: JSON.stringify(input),
  });
  if (!response.ok) throw await reportApiError(response, "failed to create report");
  return response.json();
}

export async function getProgressReport(id: string): Promise<ProgressReport> {
  const response = await fetch(apiUrl(`/reports/${encodeURIComponent(id)}`), {
    headers: await authHeaders(),
  });
  if (!response.ok) throw await reportApiError(response, "failed to load report");
  return response.json();
}

export async function updateProgressReport(
  id: string,
  input: ReportDraftFields,
): Promise<ProgressReport> {
  const response = await fetch(apiUrl(`/reports/${encodeURIComponent(id)}`), {
    method: "PATCH",
    headers: await authHeaders({ "content-type": "application/json" }),
    body: JSON.stringify(input),
  });
  if (!response.ok) throw await reportApiError(response, "failed to save report");
  return response.json();
}

export async function publishProgressReport(
  id: string,
): Promise<{ report: ProgressReport; invitation: ReportInvitation | null }> {
  const response = await fetch(apiUrl(`/reports/${encodeURIComponent(id)}/publish`), {
    method: "POST",
    headers: await authHeaders(),
  });
  if (!response.ok) throw await reportApiError(response, "failed to publish report");
  return response.json();
}

export async function createReportCorrection(id: string): Promise<ProgressReport> {
  const response = await fetch(apiUrl(`/reports/${encodeURIComponent(id)}/corrections`), {
    method: "POST",
    headers: await authHeaders(),
  });
  if (!response.ok) throw await reportApiError(response, "failed to create correction");
  return response.json();
}

export async function createReportInvitation(id: string): Promise<ReportInvitation> {
  const response = await fetch(apiUrl(`/reports/${encodeURIComponent(id)}/invitations`), {
    method: "POST",
    headers: await authHeaders(),
  });
  if (!response.ok) throw await reportApiError(response, "failed to create invitation");
  return response.json();
}

export async function revokeReportInvitations(id: string): Promise<void> {
  const response = await fetch(apiUrl(`/reports/${encodeURIComponent(id)}/invitations`), {
    method: "DELETE",
    headers: await authHeaders(),
  });
  if (!response.ok) {
    throw await reportApiError(response, "failed to revoke invitations");
  }
}

export async function claimReportInvitation(
  token: string,
  targetLearnerId: string | null = null,
): Promise<ProgressReport> {
  const response = await fetch(apiUrl("/report-invitations/claim"), {
    method: "POST",
    headers: await authHeaders({ "content-type": "application/json" }),
    body: JSON.stringify({ token, target_learner_id: targetLearnerId }),
  });
  if (!response.ok) {
    throw await reportApiError(
      response,
      "This invitation is unavailable. It may be expired, revoked, or already claimed.",
    );
  }
  return response.json();
}

export async function acknowledgeProgressReport(
  id: string,
): Promise<{ acknowledged_at: string }> {
  const response = await fetch(apiUrl(`/reports/${encodeURIComponent(id)}/acknowledge`), {
    method: "POST",
    headers: await authHeaders(),
  });
  if (!response.ok) throw await reportApiError(response, "failed to acknowledge report");
  return response.json();
}

export async function recordProgressReportPrint(id: string): Promise<void> {
  const response = await fetch(apiUrl(`/reports/${encodeURIComponent(id)}/print`), {
    method: "POST",
    headers: await authHeaders(),
  });
  if (!response.ok && response.status !== 204) {
    throw await reportApiError(response, "failed to record print");
  }
}

export async function getProgressReportHistory(id: string): Promise<ReportHistory> {
  const response = await fetch(apiUrl(`/reports/${encodeURIComponent(id)}/history`), {
    headers: await authHeaders(),
  });
  if (!response.ok) throw await reportApiError(response, "failed to load report history");
  return response.json();
}

export async function getReportLearnerGrants(
  learnerId: string,
): Promise<LearnerAccessGrant[]> {
  const response = await fetch(
    apiUrl(`/reports/learners/${encodeURIComponent(learnerId)}/grants`),
    { headers: await authHeaders() },
  );
  if (!response.ok) throw await reportApiError(response, "failed to load report access");
  return response.json();
}

export async function revokeReportLearnerGrant(
  learnerId: string,
  grantId: string,
): Promise<void> {
  const response = await fetch(
    apiUrl(
      `/reports/learners/${encodeURIComponent(learnerId)}/grants/${encodeURIComponent(grantId)}`,
    ),
    { method: "DELETE", headers: await authHeaders() },
  );
  if (!response.ok && response.status !== 204) {
    throw await reportApiError(response, "failed to revoke report access");
  }
}

// Billing API

export type Allowance = {
  used: number;
  total: number;
  remaining: number;
};

export type BillingUsage = {
  plan: string;
  plan_slug: string;
  is_free: boolean;
  enforced: boolean;
  course_credits: Allowance;
  voice_minutes: Allowance;
  visuals: Allowance;
  lab_credits: Allowance;
  max_lessons_per_course: number;
  renews_at: string;
};

export async function fetchBillingUsage(): Promise<BillingUsage> {
  const r = await fetch(apiUrl("/billing/usage"), { headers: await authHeaders() });
  if (!r.ok) throw new Error("failed to load billing usage");
  return r.json();
}

// Course API

export async function listCourses(
  filters: { q?: string; status?: string } = {},
  options: { signal?: AbortSignal } = {},
): Promise<CourseCard[]> {
  const qs = new URLSearchParams();
  if (filters.q) qs.set("q", filters.q);
  if (filters.status && filters.status !== "all") qs.set("status", filters.status);
  const r = await fetch(apiUrl(`/courses${qs.toString() ? `?${qs}` : ""}`), {
    headers: await authHeaders(),
    signal: options.signal,
  });
  if (!r.ok) throw new Error("failed to list courses");
  return r.json();
}

export async function getCourse(id: string): Promise<CourseDetail> {
  const r = await fetch(apiUrl(`/courses/${id}`), { headers: await authHeaders() });
  if (!r.ok) throw new Error("failed to load course");
  return r.json();
}

export async function createCourse(topic: string, knobs: Knobs): Promise<CourseCard> {
  const r = await fetch(apiUrl("/courses"), {
    method: "POST",
    headers: await authHeaders({ "content-type": "application/json" }),
    body: JSON.stringify({ topic, knobs }),
  });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? "create failed");
  return r.json();
}

export async function deleteCourse(id: string): Promise<void> {
  await fetch(apiUrl(`/courses/${id}`), { method: "DELETE", headers: await authHeaders() });
}

export async function updateCourse(
  id: string,
  patch: { title: string },
): Promise<CourseCard> {
  const r = await fetch(apiUrl(`/courses/${id}`), {
    method: "PATCH",
    headers: await authHeaders({ "content-type": "application/json" }),
    body: JSON.stringify(patch),
  });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? "failed to update course");
  return r.json();
}

export async function completeLesson(courseId: string, lessonId: string): Promise<CourseDetail> {
  const r = await fetch(apiUrl(`/courses/${courseId}/lessons/${lessonId}/complete`), {
    method: "POST",
    headers: await authHeaders(),
  });
  if (!r.ok) throw new Error("failed to complete lesson");
  return r.json();
}

export async function regenerateLesson(courseId: string, lessonId: string): Promise<CourseCard> {
  const r = await fetch(apiUrl(`/courses/${courseId}/lessons/${lessonId}/regenerate`), {
    method: "POST",
    headers: await authHeaders(),
  });
  if (!r.ok) throw new Error("failed to regenerate lesson");
  return r.json();
}

export async function generateLesson(courseId: string, lessonId: string): Promise<CourseCard> {
  const r = await fetch(apiUrl(`/courses/${courseId}/lessons/${lessonId}/generate`), {
    method: "POST",
    headers: await authHeaders(),
  });
  if (!r.ok) throw new Error("failed to generate lesson");
  return r.json();
}

export async function refineCourse(
  courseId: string,
  prompt: string,
  lessonId?: string,
  target?: { target_id?: string; target_html?: string },
): Promise<CourseCard> {
  const r = await fetch(apiUrl(`/courses/${courseId}/refinements`), {
    method: "POST",
    headers: await authHeaders({ "content-type": "application/json" }),
    body: JSON.stringify({
      prompt,
      lesson_id: lessonId,
      target_id: target?.target_id,
      target_html: target?.target_html,
    }),
  });
  if (!r.ok) throw new Error("failed to refine course");
  return r.json();
}

export async function saveLessonArtifact(
  courseId: string,
  lessonId: string,
  html: string,
): Promise<ArtifactVersion> {
  const r = await fetch(apiUrl(`/courses/${courseId}/lessons/${lessonId}/artifact`), {
    method: "PUT",
    headers: await authHeaders({ "content-type": "application/json" }),
    body: JSON.stringify({ html }),
  });
  if (!r.ok) {
    const detail = (await r.json().catch(() => ({}))).detail;
    throw new Error(typeof detail === "string" ? detail : "failed to save artifact");
  }
  return r.json();
}

export async function patchA2UISection(
  courseId: string,
  lessonId: string,
  sectionId: string,
  opts: {
    root?: Record<string, unknown>;
    title?: string;
    instruction?: string;
    insert?: { type: string; hint?: string; placement?: string; index?: number };
    replace_node_path?: number[];
  },
): Promise<ArtifactA2UI> {
  const r = await fetch(
    apiUrl(`/courses/${courseId}/lessons/${lessonId}/artifact/a2ui/sections/${encodeURIComponent(sectionId)}`),
    {
      method: "PATCH",
      headers: await authHeaders({ "content-type": "application/json" }),
      body: JSON.stringify(opts),
    },
  );
  if (!r.ok) {
    const detail = (await r.json().catch(() => ({}))).detail;
    throw new Error(typeof detail === "string" ? detail : "failed to patch A2UI section");
  }
  return r.json();
}

export async function patchHtmlSection(
  courseId: string,
  lessonId: string,
  sectionId: string,
  opts: { instruction: string; target_html?: string },
): Promise<ArtifactVersion> {
  const r = await fetch(
    apiUrl(`/courses/${courseId}/lessons/${lessonId}/artifact/html/sections/${encodeURIComponent(sectionId)}`),
    {
      method: "PATCH",
      headers: await authHeaders({ "content-type": "application/json" }),
      body: JSON.stringify(opts),
    },
  );
  if (!r.ok) {
    const detail = (await r.json().catch(() => ({}))).detail;
    throw new Error(typeof detail === "string" ? detail : "failed to patch HTML section");
  }
  return r.json();
}

/** Allowlisted slash-insert types mirrored from backend INSERTABLE_TYPES. */
export const A2UI_SLASH_CATALOGUE: { type: string; label: string; blurb: string }[] = [
  { type: "quiz", label: "Quiz", blurb: "Practice questions" },
  { type: "map", label: "Map", blurb: "Geo / valuation lab" },
  { type: "chart", label: "Chart", blurb: "Bar or line chart" },
  { type: "slider", label: "Slider", blurb: "Interactive calculator" },
  { type: "table", label: "Table", blurb: "Comparison table" },
  { type: "steps", label: "Steps", blurb: "Step-by-step" },
  { type: "diagram", label: "Diagram", blurb: "Node graph" },
  { type: "callout", label: "Callout", blurb: "Tip / warning" },
  { type: "math", label: "Math", blurb: "KaTeX formula" },
  { type: "embed", label: "Embed", blurb: "Sandboxed sim slot" },
  { type: "text", label: "Text", blurb: "Paragraph" },
  { type: "heading", label: "Heading", blurb: "Section heading" },
];

export async function listVersions(courseId: string, lessonId?: string): Promise<ArtifactVersion[]> {
  const qs = new URLSearchParams();
  if (lessonId) qs.set("lesson_id", lessonId);
  const r = await fetch(apiUrl(`/courses/${courseId}/versions${qs.toString() ? `?${qs}` : ""}`), {
    headers: await authHeaders(),
  });
  if (!r.ok) throw new Error("failed to list versions");
  return r.json();
}

/** Subscribe to a course's generation progress over SSE (R3). */
export function subscribeProgress(id: string, onProgress: (p: Progress) => void): () => void {
  const token = getCachedToken();
  const qs = token ? `?access_token=${encodeURIComponent(token)}` : "";
  const es = new EventSource(apiUrl(`/courses/${id}/events${qs}`));
  es.addEventListener("progress", (e) => onProgress(JSON.parse((e as MessageEvent).data)));
  return () => es.close();
}

// Chapter-outline HITL (course-authoring-flow §3)

export type OutlineLesson = {
  title: string;
  objective: string;
  archetype: string;
  estimated_duration: string;
  chapter_ids: string[];
};

export type OutlineChapter = {
  id: string;
  title: string;
  description: string;
  source_chapter_ids: string[];
  lessons: OutlineLesson[];
};

export type OutlineDoc = {
  version: number;
  revision: number;
  status: "outline_review" | "approved";
  design: string;
  title: string;
  subtitle: string;
  chapters: OutlineChapter[];
  feedback_log: string[];
};

export type OutlineOut = {
  course_id: string;
  course_status: string;
  outline: OutlineDoc | null;
  max_revisions: number;
};

export async function getOutline(courseId: string): Promise<OutlineOut> {
  const r = await fetch(apiUrl(`/courses/${courseId}/outline`), { headers: await authHeaders() });
  if (!r.ok) throw new Error("failed to load outline");
  return r.json();
}

export async function reviewOutline(
  courseId: string,
  body:
    | { action: "approve" }
    | { action: "edit"; outline: OutlineDoc }
    | { action: "revise"; feedback: string },
): Promise<OutlineOut> {
  const r = await fetch(apiUrl(`/courses/${courseId}/outline/review`), {
    method: "POST",
    headers: await authHeaders({ "content-type": "application/json" }),
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? "outline review failed");
  return r.json();
}

export const artifactUrl = (id: string) => withAccessToken(`/courses/${id}/artifact`);
export const lessonArtifactUrl = (courseId: string, lessonId: string, version?: number) =>
  withAccessToken(
    `/courses/${courseId}/lessons/${lessonId}/artifact${version ? `?version=${version}` : ""}`,
  );

export async function getLessonArtifactA2UI(
  courseId: string,
  lessonId: string,
  version?: number,
): Promise<ArtifactA2UI> {
  const qs = version != null ? `?version=${version}` : "";
  const r = await fetch(
    apiUrl(`/courses/${courseId}/lessons/${lessonId}/artifact/a2ui${qs}`),
    { headers: await authHeaders() },
  );
  if (!r.ok) throw new Error("a2ui artifact not ready");
  return r.json();
}

export async function getLessonArtifactReading(
  courseId: string,
  lessonId: string,
  version?: number,
): Promise<ArtifactReading> {
  const qs = version != null ? `?version=${version}` : "";
  const r = await fetch(
    apiUrl(`/courses/${courseId}/lessons/${lessonId}/artifact/reading${qs}`),
    { headers: await authHeaders() },
  );
  if (!r.ok) throw new Error("reading artifact not ready");
  return r.json();
}

/** Shareable path without auth token (requires signed-in session to open). */
export const lessonArtifactPath = (courseId: string, lessonId: string, version?: number) =>
  apiUrl(`/courses/${courseId}/lessons/${lessonId}/artifact${version ? `?version=${version}` : ""}`);

// Public share links (opt-in, revocable, anonymous read-only) ---------------

export type SharedLesson = {
  title: string;
  archetype: string;
  estimated_duration: string;
  course_title: string | null;
};

/** Owner mints (or re-fetches) a public share token for a lesson. */
export async function createShareLink(courseId: string, lessonId: string): Promise<string> {
  const r = await fetch(apiUrl(`/courses/${courseId}/lessons/${lessonId}/share`), {
    method: "POST",
    headers: await authHeaders(),
  });
  if (!r.ok) throw new Error("failed to create share link");
  return (await r.json()).share_token as string;
}

/** Owner revokes a lesson's public share link. */
export async function revokeShareLink(courseId: string, lessonId: string): Promise<void> {
  const r = await fetch(apiUrl(`/courses/${courseId}/lessons/${lessonId}/share`), {
    method: "DELETE",
    headers: await authHeaders(),
  });
  if (!r.ok && r.status !== 204) throw new Error("failed to revoke share link");
}

/** Public lesson metadata for the read-only shared view (no auth token attached). */
export async function getSharedLesson(token: string): Promise<SharedLesson> {
  const r = await fetch(apiUrl(`/shared/lessons/${encodeURIComponent(token)}`));
  if (!r.ok) throw new Error("lesson not found");
  return r.json();
}

/** Public artifact URL for the shared iframe — deliberately carries no auth token. */
export const sharedLessonArtifactUrl = (token: string) =>
  apiUrl(`/shared/lessons/${encodeURIComponent(token)}/artifact`);

// Source types

export type SourceOut = {
  id: string;
  filename: string;
  mime_type: string;
  status:
    | "uploaded"
    | "transcribing"
    | "checkpointing"
    | "parsing"
    | "outlining"
    | "mapping"
    | "chunking"
    | "indexing"
    | "ready"
    | "failed";
  title: string | null;
  source_type: string | null;
  page_count: number | null;
  duration_seconds: number | null;
  checkpoint_count: number;
  error: string | null;
  created_at: string;
};

export type SourceOutline = {
  id: string;
  title: string | null;
  source_type: string | null;
  page_count: number | null;
  duration_seconds: number | null;
  checkpoint_count: number;
  sections: string[];
  warnings: string[];
  suggested_modes: string[];
};

export type LessonSourcePack = {
  source_document_id: string;
  retrieval_query: string;
  chunk_count: number;
  pages: number[];
  sections: string[];
  citations: { claim: string; source_url: string }[];
  chapter_ids?: string[];
};

export type VideoCheckpoint = {
  id: string;
  at_seconds: number;
  kind: "quiz" | "visual" | "reading";
  title: string;
  prompt: string;
  body: string;
  options: string[];
  answer_index: number | null;
  explanation: string;
  visual_points: string[];
};

export type VideoGuide = {
  source_id: string;
  title: string;
  filename: string;
  duration_seconds: number;
  transcript_provider: string;
  playback_kind: "native" | "youtube";
  media_url: string | null;
  youtube_video_id: string | null;
  checkpoints: VideoCheckpoint[];
};

// Source API

export async function uploadSource(file: File): Promise<SourceOut> {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch(apiUrl("/sources/upload"), { method: "POST", headers: await authHeaders(), body: fd });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? "upload failed");
  return r.json();
}

export async function createVideoLinkSource(input: {
  url: string;
  title?: string;
  transcript?: string;
}): Promise<SourceOut> {
  const r = await fetch(apiUrl("/sources/video/link"), {
    method: "POST",
    headers: await authHeaders({ "content-type": "application/json" }),
    body: JSON.stringify(input),
  });
  if (!r.ok) {
    throw new Error((await r.json().catch(() => ({}))).detail ?? "video link failed");
  }
  return r.json();
}

export function sourceMediaUrl(sourceId: string): string {
  return withAccessToken(`/sources/${sourceId}/media`);
}

export async function getSource(id: string): Promise<SourceOut> {
  const r = await fetch(apiUrl(`/sources/${id}`), { headers: await authHeaders() });
  if (!r.ok) throw new Error("failed to load source");
  return r.json();
}

export async function getSourceOutline(id: string): Promise<SourceOutline> {
  const r = await fetch(apiUrl(`/sources/${id}/outline`), { headers: await authHeaders() });
  if (!r.ok) throw new Error("failed to load source outline");
  return r.json();
}

export async function createCourseFromSource(
  id: string,
  opts: {
    difficulty?: string;
    lesson_count?: number;
    mode?: string;
    selected_sections?: string[];
    design_mode?: Knobs["design_mode"];
    /** @deprecated Prefer design_mode. */
    presentation?: Knobs["presentation"];
    studio_mode?: Knobs["studio_mode"];
    review_outline?: boolean;
  },
): Promise<CourseDetail> {
  const r = await fetch(apiUrl(`/sources/${id}/courses`), {
    method: "POST",
    headers: await authHeaders({ "content-type": "application/json" }),
    body: JSON.stringify(opts),
  });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? "create failed");
  return r.json();
}

export async function getLessonSourcePack(
  courseId: string,
  lessonId: string,
): Promise<LessonSourcePack | null> {
  const r = await fetch(apiUrl(`/courses/${courseId}/lessons/${lessonId}/source-pack`), {
    headers: await authHeaders(),
  });
  if (!r.ok) return null;
  return r.json();
}

export async function appendVideoToCourse(
  courseId: string,
  sourceId: string,
  description?: string,
): Promise<CourseDetail> {
  const r = await fetch(apiUrl(`/courses/${courseId}/videos`), {
    method: "POST",
    headers: await authHeaders({ "content-type": "application/json" }),
    body: JSON.stringify({
      source_id: sourceId,
      ...(description?.trim() ? { description: description.trim() } : {}),
    }),
  });
  if (!r.ok) {
    throw new Error((await r.json().catch(() => ({}))).detail ?? "failed to add video");
  }
  return r.json();
}

export async function appendChapterToCourse(
  courseId: string,
  input: { title: string; description: string; archetype?: NonNullable<Knobs["archetype"]> },
): Promise<CourseDetail> {
  const r = await fetch(apiUrl(`/courses/${courseId}/chapters`), {
    method: "POST",
    headers: await authHeaders({ "content-type": "application/json" }),
    body: JSON.stringify(input),
  });
  if (!r.ok) {
    throw new Error((await r.json().catch(() => ({}))).detail ?? "failed to add chapter");
  }
  return r.json();
}

export async function getVideoGuide(
  courseId: string,
  lessonId?: string,
): Promise<VideoGuide | null> {
  const query = lessonId ? `?lesson_id=${encodeURIComponent(lessonId)}` : "";
  const r = await fetch(apiUrl(`/courses/${courseId}/video-guide${query}`), {
    headers: await authHeaders(),
  });
  if (!r.ok) return null;
  return r.json();
}

// Tutor types

export type ChatToolCall = {
  name: string;
  arguments: any;
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  tool_call?: ChatToolCall | null;
  /** Current learner-edited whiteboard state, attached only to the active tutor turn. */
  whiteboard_state?: { elements: Record<string, unknown>[] } | null;
  /** Current coding-lab workspace / last AG-UI run result for the active tutor turn. */
  coding_lab_state?: Record<string, unknown> | null;
};

// Tutor API

export async function sendTutorChatMessage(
  courseId: string,
  lessonId: string,
  messages: ChatMessage[]
): Promise<ChatMessage> {
  const r = await fetch(apiUrl(`/courses/${courseId}/lessons/${lessonId}/tutor/chat`), {
    method: "POST",
    headers: await authHeaders({ "content-type": "application/json" }),
    body: JSON.stringify({ messages }),
  });
  if (!r.ok) throw new Error("failed to send message to tutor");
  return r.json();
}

/** AG-UI-style frames from POST /tutor/chat/stream (see backend stream_tutor_events). */
export type TutorStreamFrame =
  | { type: "RUN_STARTED" }
  | { type: "TEXT_MESSAGE_CONTENT"; delta: string }
  | { type: "TOOL_CALL_START"; toolCallId: string; toolCallName: string }
  | { type: "TOOL_CALL_ARGS"; toolCallId: string; delta: string }
  | { type: "TOOL_CALL_END"; toolCallId: string; toolCallName: string; arguments: any | null }
  | { type: "RUN_FINISHED" }
  | { type: "RUN_ERROR"; detail: string }
  | { type: "CODING_LAB_RUN_RESULT"; [k: string]: unknown }
  | { type: "CODING_LAB_CHECK_RESULT"; [k: string]: unknown }
  | { type: "CODING_LAB_FILES_CHANGED"; [k: string]: unknown };

/**
 * Stream a tutor turn over SSE-on-fetch (EventSource can't POST a body). Parses `data:` frames and
 * invokes `onFrame` for each. Falls back to POST /tutor/chat at the call site if this throws.
 */
export async function streamTutorChat(
  courseId: string,
  lessonId: string,
  messages: ChatMessage[],
  onFrame: (frame: TutorStreamFrame) => void,
  signal?: AbortSignal
): Promise<void> {
  const r = await fetch(apiUrl(`/courses/${courseId}/lessons/${lessonId}/tutor/chat/stream`), {
    method: "POST",
    headers: await authHeaders({ "content-type": "application/json", accept: "text/event-stream" }),
    body: JSON.stringify({ messages }),
    signal,
  });
  if (!r.ok || !r.body) throw new Error("failed to open tutor stream");

  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let sep: number;
    // SSE events are separated by a blank line.
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const dataLine = block.split("\n").find((l) => l.startsWith("data:"));
      if (!dataLine) continue;
      const payload = dataLine.slice(5).trim();
      if (!payload) continue;
      try {
        onFrame(JSON.parse(payload) as TutorStreamFrame);
      } catch {
        // ignore keep-alive / malformed frames
      }
    }
  }
}

export async function syncTutorWhiteboard(
  courseId: string,
  lessonId: string,
  sessionId: string,
  elements: Record<string, unknown>[],
): Promise<void> {
  const r = await fetch(
    apiUrl(`/courses/${courseId}/lessons/${lessonId}/tutor/whiteboards/${sessionId}`),
    {
      method: "PUT",
      headers: await authHeaders({ "content-type": "application/json" }),
      body: JSON.stringify({ elements }),
    },
  );
  if (!r.ok) throw new Error("failed to sync whiteboard");
}

export async function syncTutorCodingLab(
  courseId: string,
  lessonId: string,
  sessionId: string,
  files: { path: string; content: string }[],
): Promise<void> {
  const r = await fetch(
    apiUrl(`/courses/${courseId}/lessons/${lessonId}/tutor/coding-labs/${sessionId}`),
    {
      method: "PUT",
      headers: await authHeaders({ "content-type": "application/json" }),
      body: JSON.stringify({ files }),
    },
  );
  if (!r.ok) throw new Error("failed to sync coding lab");
}

export async function recordTutorCodingLabRun(
  courseId: string,
  lessonId: string,
  sessionId: string,
  payload: {
    ok: boolean;
    passed?: boolean | null;
    stdout: string;
    stderr: string;
    language?: string;
    event?: string;
    files?: { path: string; content: string }[];
  },
): Promise<void> {
  const r = await fetch(
    apiUrl(`/courses/${courseId}/lessons/${lessonId}/tutor/coding-labs/${sessionId}/run`),
    {
      method: "POST",
      headers: await authHeaders({ "content-type": "application/json" }),
      body: JSON.stringify(payload),
    },
  );
  if (!r.ok) throw new Error("failed to record coding lab run");
}

// Health + Voice API

export type Health = {
  ok: boolean;
  llm: string;
  llm_endpoint: string;
  llm_model: string;
  search: string;
  embedding: string;
  vector_store: string;
  voice: { enabled: boolean; brain: string };
};

export async function getHealth(): Promise<Health> {
  const r = await fetch(apiUrl("/health"));
  if (!r.ok) throw new Error("health check failed");
  return r.json();
}

export function voiceWebSocketUrl(courseId: string, lessonId: string): string {
  const url = new URL(
    withAccessToken(`/courses/${courseId}/lessons/${lessonId}/voice/ws`),
    window.location.href,
  );
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

/** GuideBridge page-control WebSocket (agent observe/act on the lesson iframe). */
export function agentBridgeWsUrl(courseId: string, lessonId: string): string {
  const url = new URL(
    withAccessToken(`/courses/${courseId}/lessons/${lessonId}/agent-bridge/ws`),
    window.location.href,
  );
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

// Private personal-learning insights

export type LearningEventType =
  | "lesson_view_started"
  | "lesson_view_ended"
  | "active_time_increment"
  | "hint_requested"
  | "widget_opened"
  | "quiz_submitted"
  | "practice_retried"
  | "capsule_control_used"
  | "capsule_section_viewed"
  | "studio_mode_opened"
  | "studio_part_selected"
  | "studio_control_changed"
  | "studio_playback_completed"
  | "studio_reset"
  | "studio_degraded";

export type LearningEventInput = {
  event_id: string;
  event_type: LearningEventType;
  occurred_at: string;
  course_id?: string;
  lesson_id?: string;
  session_id?: string;
  source?: "web" | "capsule";
  schema_version: 1;
  payload: Record<string, unknown>;
};

export type InsightMetrics = {
  active_minutes: number;
  active_days: number;
  lessons_viewed: number;
  lessons_completed: number;
  tutor_questions: number;
  tutor_responses: number;
  average_tutor_response_seconds: number | null;
  quiz_attempts: number;
  answers_correct: number;
  answers_total: number;
  quiz_accuracy: number | null;
  average_answer_seconds: number | null;
  hints_requested: number;
  explanations_requested: number;
  practice_retries: number;
};

export type LearningInterest = {
  course_id: string;
  title: string;
  evidence: string;
  active_minutes: number;
  tutor_questions: number;
  answers_total: number;
  basis: "activity" | "course_selection";
};

export type LearningStruggle = {
  course_id: string;
  lesson_id: string;
  title: string;
  evidence: string;
  confidence: "medium" | "high";
  answers_correct: number;
  answers_total: number;
  accuracy: number;
  quiz_attempts: number;
  help_requests: number;
  retries: number;
  href: string;
};

export type RecentLearningActivity = {
  kind: "lesson" | "completion" | "practice" | "tutor";
  title: string;
  detail: string;
  occurred_at: string;
  course_id?: string;
  lesson_id?: string;
  href?: string;
};

export type InsightWindow = "7d" | "30d";

export type InsightSummary = {
  window: InsightWindow;
  status: "ready" | "insufficient_data" | "disabled";
  private: true;
  generated_by: "agent" | "deterministic";
  metrics: InsightMetrics;
  report: null | {
    headline: string;
    summary: string;
    insights: Array<{
      kind: "achievement" | "momentum" | "strength" | "challenge" | "habit";
      title: string;
      body: string;
      evidence_keys: string[];
    }>;
  };
  evidence: Record<string, { label: string; value: string }>;
  interests: LearningInterest[];
  struggles: LearningStruggle[];
  recent_activity: RecentLearningActivity[];
  recommended_action: null | {
    label: string;
    href: string;
    course_id?: string;
    lesson_id?: string;
  };
  updated_at: string;
};

export type InsightPreferences = {
  analytics_enabled: boolean;
  question_content_enabled: boolean;
  updated_at: string;
};

export async function postLearningEvents(
  events: LearningEventInput[],
  options: { keepalive?: boolean } = {},
): Promise<{ accepted: number; duplicates: number }> {
  const r = await fetch(apiUrl("/insights/events/batch"), {
    method: "POST",
    headers: await authHeaders({ "content-type": "application/json" }),
    body: JSON.stringify({ events }),
    keepalive: options.keepalive,
  });
  if (!r.ok) throw new Error("failed to record learning activity");
  return r.json();
}

export async function getInsightSummary(
  window: InsightWindow = "7d",
  options: { signal?: AbortSignal } = {},
): Promise<InsightSummary> {
  const r = await fetch(apiUrl(`/insights/summary?window=${window}`), {
    headers: await authHeaders(),
    signal: options.signal,
  });
  if (!r.ok) throw new Error("failed to load learning insights");
  return r.json();
}

export async function refreshInsights(
  window: InsightWindow = "7d",
  options: { signal?: AbortSignal } = {},
): Promise<void> {
  const r = await fetch(apiUrl(`/insights/refresh?window=${window}`), {
    method: "POST",
    headers: await authHeaders(),
    signal: options.signal,
  });
  if (!r.ok) throw new Error("failed to refresh learning insights");
}

export async function getInsightPreferences(): Promise<InsightPreferences> {
  const r = await fetch(apiUrl("/insights/preferences"), { headers: await authHeaders() });
  if (!r.ok) throw new Error("failed to load insight preferences");
  return r.json();
}

export async function updateInsightPreferences(
  patch: Partial<Pick<InsightPreferences, "analytics_enabled" | "question_content_enabled">>,
): Promise<InsightPreferences> {
  const r = await fetch(apiUrl("/insights/preferences"), {
    method: "PATCH",
    headers: await authHeaders({ "content-type": "application/json" }),
    body: JSON.stringify(patch),
  });
  if (!r.ok) throw new Error("failed to update insight preferences");
  return r.json();
}

export async function deleteInsights(): Promise<void> {
  const r = await fetch(apiUrl("/insights/data"), { method: "DELETE", headers: await authHeaders() });
  if (!r.ok) throw new Error("failed to delete insights");
}

// Waitlist API

export async function joinWaitlist(email: string): Promise<{ id: string; email: string }> {
  const { data, error } = await insforge.database.from("waitlist").insert([{ email }]);
  if (error) throw new Error(error.message ?? "Failed to join waitlist");
  const row = Array.isArray(data) ? data[0] : data;
  if (!row || typeof row !== "object") {
    return { id: "", email };
  }
  const record = row as Record<string, unknown>;
  return {
    id: typeof record.id === "string" ? record.id : "",
    email: typeof record.email === "string" ? record.email : email,
  };
}

// Learner profile API (specs/learner_profile) — onboarding-captured learning preferences.

export type LearningModality = "visual" | "auditory" | "reading" | "hands_on";

export type LearningPreferences = {
  /** Ranked, first = primary, max 2. */
  modalities: LearningModality[];
  structure: "examples_first" | "theory_first" | "balanced";
  pacing: "bite_sized" | "balanced" | "deep_dive";
  practice: "frequent" | "some" | "minimal";
  prior_knowledge: "beginner" | "intermediate" | "advanced";
  goal: "curiosity" | "exam" | "career" | "school";
};

export type ProfileHints = {
  difficulty: LearningPreferences["prior_knowledge"];
  design_mode: "studio" | "page" | null;
  archetype: "simulation" | "narrative" | null;
};

export type LearnerProfile = {
  preferences: LearningPreferences;
  onboarded_at: string | null;
  updated_at: string;
  hints: ProfileHints;
};

export const DEFAULT_LEARNING_PREFERENCES: LearningPreferences = {
  modalities: [],
  structure: "balanced",
  pacing: "balanced",
  practice: "some",
  prior_knowledge: "intermediate",
  goal: "curiosity",
};

export async function getProfile(options: { signal?: AbortSignal } = {}): Promise<LearnerProfile> {
  const r = await fetch(apiUrl("/profile"), {
    headers: await authHeaders(),
    signal: options.signal,
  });
  if (!r.ok) throw new Error("failed to load learner profile");
  return r.json();
}

export async function putProfile(
  preferences: LearningPreferences,
  completed: boolean,
): Promise<LearnerProfile> {
  const r = await fetch(apiUrl("/profile"), {
    method: "PUT",
    headers: await authHeaders({ "content-type": "application/json" }),
    body: JSON.stringify({ preferences, completed }),
  });
  if (!r.ok) throw new Error("failed to save learner profile");
  return r.json();
}
