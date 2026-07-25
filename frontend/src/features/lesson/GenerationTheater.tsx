import { useEffect, useMemo, useRef, useState } from "react";

import A2UIRenderer, { type UiNode } from "../../components/A2UIRenderer";
import { Mascot } from "../../components/Mascot";
import { generateLesson, subscribeProgress, type Lesson, type Progress } from "../../api";

/**
 * Live generation theater (specs/fast_gen §4 + generative_ui_quality Track B):
 * - Mode B (HTML): sandboxed design-shell iframe + gen_fragment morphing
 * - Mode A (A2UI): host A2UIRenderer mounts validated section trees as a2ui_section frames arrive
 */

const THEATER_SOURCE = "hituto-gen-theater";

type SkeletonSection = { id: string; icon: string; title: string };

type SkeletonPayload = {
  lesson_id: string;
  title: string;
  subtitle: string;
  sections: SkeletonSection[];
};

type StreamEntry = { buffer: string; joined: boolean };

type A2UISectionLive = {
  id: string;
  title: string;
  root: UiNode;
  index: number;
};

/** Self-contained design shell: Hi-Tuto zinc tokens, shimmer skeleton, streaming surfaces. */
const SHELL_HTML = `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<style>
  :root { --paper:#FAFAFA; --ink:#18181B; --ink-soft:#52525B; --ink-faint:#A1A1AA;
          --line:#E4E4E7; --lime:#16A34A; --lime-soft:#EAF7EE; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--paper); color:var(--ink);
         font:15px/1.6 "Plus Jakarta Sans", -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
         max-width:100%; overflow-x:hidden; }
  .wrap { max-width: 860px; margin: 0 auto; padding: 40px 28px 80px; }
  .kicker { display:inline-flex; align-items:center; gap:8px; padding:6px 14px;
            border-radius:999px; background:var(--lime-soft); color:var(--lime);
            font-size:11px; font-weight:700; letter-spacing:.12em; text-transform:uppercase; }
  .kicker .dot { width:7px; height:7px; border-radius:999px; background:var(--lime);
                 animation: pulse 1.2s ease-in-out infinite; }
  h1 { margin:18px 0 6px; font-size:30px; line-height:1.15; letter-spacing:-0.02em; font-weight:700; }
  .sub { margin:0 0 34px; color:var(--ink-soft); font-size:15px; }
  .sec { margin: 0 0 26px; padding: 20px 22px; background:#fff; border:1px solid var(--line);
         border-radius:18px; }
  .sec h2 { margin:0 0 12px; font-size:16px; font-weight:700; display:flex; align-items:center; gap:10px; }
  .sec h2 .n { display:grid; place-items:center; width:26px; height:26px; border-radius:9px;
               background:var(--lime-soft); color:var(--lime); font-size:12px; font-weight:800; flex:0 0 auto; }
  .bar { height:12px; border-radius:7px; background:linear-gradient(90deg,#F4F4F5 25%,#E4E4E7 50%,#F4F4F5 75%);
         background-size:200% 100%; animation: shimmer 1.4s linear infinite; margin:10px 0; }
  .bar.w60 { width:60%; } .bar.w85 { width:85%; } .bar.w40 { width:40%; }
  img, canvas, svg { max-width:100%; height:auto; }
  @keyframes shimmer { to { background-position:-200% 0; } }
  @keyframes pulse { 50% { opacity:.35; } }
  #gen-surface { display:none; }
  #gen-surface.live { display:block; }
  #gen-surface.live ~ #gen-skeleton { display:none; }
  .gt-live:not(:empty) ~ .gt-skel, .gt-live:not(:empty) ~ h2 { display:none; }
</style>
</head>
<body>
  <div class="wrap">
    <div id="gen-surface"></div>
    <div id="gen-skeleton">
      <span class="kicker"><span class="dot"></span><span id="gt-stage">Designing your lesson</span></span>
      <h1 id="gt-title">&nbsp;</h1>
      <p class="sub" id="gt-sub">&nbsp;</p>
      <div id="gt-sections"></div>
    </div>
  </div>
<script>
  var surface = document.getElementById("gen-surface");
  var docBuffer = "";
  var secBuffers = {};
  function esc(t) { var d = document.createElement("span"); d.textContent = t == null ? "" : String(t); return d.innerHTML; }
  function skeletonCard(id, n, title) {
    return '<div class="sec" data-gt-sec="' + esc(id) + '">' +
      '<div class="gt-live"></div>' +
      '<h2><span class="n">' + n + '</span>' + esc(title) + '</h2>' +
      '<div class="gt-skel"><div class="bar w85"></div><div class="bar w60"></div></div></div>';
  }
  function renderSkeleton(p) {
    document.getElementById("gt-title").innerHTML = esc(p.title) || "&nbsp;";
    document.getElementById("gt-sub").innerHTML = esc(p.subtitle) || "&nbsp;";
    var secs = (p.sections || []).slice(0, 12);
    if (!secs.length) {
      secs = [{ id: "a", title: "" }, { id: "b", title: "" }];
    }
    document.getElementById("gt-sections").innerHTML = secs
      .map(function (s, i) { return skeletonCard(s.id || String(i), i + 1, s.title || ""); })
      .join("");
  }
  renderSkeleton({});
  function trimmed(html) {
    var cut = html.lastIndexOf(">");
    return cut > 0 ? html.slice(0, cut + 1) : "";
  }
  function sectionSlot(id) {
    var host = document.getElementById("gt-sections");
    var card = host.querySelector('[data-gt-sec="' + (window.CSS && CSS.escape ? CSS.escape(id) : id) + '"]');
    if (!card) {
      var div = document.createElement("div");
      div.innerHTML = skeletonCard(id, host.children.length + 1, "");
      card = div.firstChild;
      host.appendChild(card);
    }
    return card.querySelector(".gt-live");
  }
  function reset() {
    docBuffer = "";
    secBuffers = {};
    surface.className = "";
    surface.innerHTML = "";
    var lives = document.querySelectorAll(".gt-live");
    for (var i = 0; i < lives.length; i++) lives[i].innerHTML = "";
  }
  window.addEventListener("message", function (e) {
    if (e.source !== window.parent) return;
    var d = e.data;
    if (!d || d.source !== ${JSON.stringify(THEATER_SOURCE)}) return;
    if (d.type === "GT_SKELETON" && d.payload) renderSkeleton(d.payload);
    if (d.type === "GT_RESET") reset();
    if (d.type === "GT_FRAGMENT" && d.payload) {
      var atBottom = window.innerHeight + window.scrollY >= document.body.scrollHeight - 320;
      if (d.payload.sectionId) {
        var key = String(d.payload.sectionId);
        if (d.payload.reset) secBuffers[key] = "";
        secBuffers[key] = (secBuffers[key] || "") + (d.payload.delta || "");
        var slot = sectionSlot(key);
        var html = trimmed(secBuffers[key]);
        // innerHTML never executes <script>; half-written markup past the last ">" is trimmed.
        if (slot && html) slot.innerHTML = html;
      } else {
        if (d.payload.reset) docBuffer = "";
        docBuffer += d.payload.delta || "";
        // A whole-document stream starts with an invisible <head> — keep the skeleton
        // until body content exists, then render head <style> blocks + the body slice.
        var m = docBuffer.match(/<body[^>]*>/i);
        if (m) {
          var headPart = docBuffer.slice(0, m.index);
          var styles = (headPart.match(/<style[\\s\\S]*?<\\/style>/gi) || []).join("");
          var doc = trimmed(docBuffer.slice(m.index + m[0].length));
          if (doc) { surface.className = "live"; surface.innerHTML = styles + doc; }
        }
      }
      if (atBottom) window.scrollTo(0, document.body.scrollHeight);
    }
  });
</script>
</body>
</html>`;

export function GenerationTheater({
  courseId,
  lesson,
  onFinished,
}: {
  courseId: string;
  lesson: Lesson;
  onFinished: () => void;
}) {
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const loadedRef = useRef(false);
  const skeletonRef = useRef<SkeletonPayload | null>(null);
  const streamsRef = useRef<Map<string, StreamEntry>>(new Map());
  const attemptRef = useRef(0);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [a2uiSections, setA2uiSections] = useState<A2UISectionLive[]>([]);
  const [skeleton, setSkeleton] = useState<SkeletonPayload | null>(null);
  const failed = lesson.status === "failed";
  const modeA = a2uiSections.length > 0;

  // A pending lesson opened directly (e.g. skipping ahead) starts generating on view.
  useEffect(() => {
    if (lesson.status === "pending") {
      void generateLesson(courseId, lesson.id).catch(() => {});
    }
  }, [courseId, lesson.id, lesson.status]);

  useEffect(() => {
    const post = (type: string, payload?: unknown) => {
      iframeRef.current?.contentWindow?.postMessage({ source: THEATER_SOURCE, type, payload }, "*");
    };
    const stop = subscribeProgress(courseId, (p) => {
      if (p.stage !== "gen_fragment" && p.stage !== "a2ui_section") setProgress(p);
      const d = (p.data ?? null) as Record<string, unknown> | null;
      if (p.stage === "skeleton" && d?.lesson_id === lesson.id) {
        skeletonRef.current = d as unknown as SkeletonPayload;
        setSkeleton(skeletonRef.current);
        if (loadedRef.current) post("GT_SKELETON", skeletonRef.current);
      } else if (p.stage === "a2ui_section" && d?.lesson_id === lesson.id) {
        const attempt = Number(d.attempt) || 0;
        if (attempt !== attemptRef.current) {
          attemptRef.current = attempt;
          setA2uiSections([]);
        }
        const id = typeof d.section_id === "string" ? d.section_id : "";
        const title = typeof d.title === "string" ? d.title : id;
        const root = d.root as UiNode | undefined;
        const index = typeof d.index === "number" ? d.index : 0;
        if (!id || !root) return;
        setA2uiSections((prev) => {
          const next = prev.filter((s) => s.id !== id);
          next.push({ id, title, root, index });
          next.sort((a, b) => a.index - b.index);
          return next;
        });
      } else if (p.stage === "gen_fragment" && d?.lesson_id === lesson.id) {
        const delta = typeof d.delta === "string" ? d.delta : "";
        const sectionId =
          typeof d.section_id === "string" && d.section_id ? d.section_id : null;
        const key = sectionId ?? "__doc";
        const attempt = Number(d.attempt) || 0;
        if (attempt !== attemptRef.current) {
          // Repair attempt: all streams restart from scratch.
          attemptRef.current = attempt;
          streamsRef.current.clear();
          setA2uiSections([]);
          if (loadedRef.current) post("GT_RESET");
        }
        let entry = streamsRef.current.get(key);
        if (!entry) {
          // Join a stream only from its first frame — a mid-document tail renders garbage.
          entry = { buffer: "", joined: Number(d.length) === delta.length };
          streamsRef.current.set(key, entry);
        }
        if (!entry.joined) return;
        entry.buffer += delta;
        if (loadedRef.current) post("GT_FRAGMENT", { sectionId, delta, reset: false });
      } else if ((p.stage === "ready" || p.stage === "failed") && p.pct >= 100) {
        onFinished();
      }
    });
    return stop;
    // onFinished intentionally captured once; parent passes a stable reload.
  }, [courseId, lesson.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const shell = useMemo(() => SHELL_HTML, []);

  const pendingSlots =
    skeleton?.sections?.filter((s) => !a2uiSections.some((a) => a.id === (s.id || ""))) ?? [];

  return (
    <div className="relative flex h-full flex-col bg-paper">
      <div className="flex items-center gap-3 border-b border-ink/5 bg-white/80 px-4 py-2.5">
        <Mascot mood={failed ? "study" : "mark"} className="h-8 w-8 shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-[12px] font-semibold text-ink">
            {failed
              ? lesson.error || "Generation failed — try again from the roadmap."
              : progress?.detail ||
                (modeA ? "Assembling interactive sections…" : "Warming up the studio…")}
          </p>
          <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-ink/10">
            <div
              className={`h-full rounded-full transition-all duration-500 ${failed ? "bg-coral" : "bg-lime"}`}
              style={{ width: `${Math.max(4, Math.min(100, failed ? 100 : progress?.pct ?? 4))}%` }}
            />
          </div>
        </div>
      </div>
      {modeA ? (
        <div className="mx-auto w-full max-w-3xl flex-1 space-y-6 overflow-y-auto px-5 py-8">
          <div>
            <p className="text-[11px] font-bold uppercase tracking-[0.12em] text-lime">
              Building your lesson
            </p>
            <h1 className="mt-2 text-2xl font-bold tracking-tight text-ink">
              {skeleton?.title || lesson.title}
            </h1>
            {skeleton?.subtitle ? (
              <p className="mt-1 text-[14px] text-ink-soft">{skeleton.subtitle}</p>
            ) : null}
          </div>
          {a2uiSections.map((sec) => (
            <section
              key={sec.id}
              className="rounded-3xl border border-ink/5 bg-white p-5 shadow-chip animate-fade-up"
            >
              <A2UIRenderer root={sec.root} />
            </section>
          ))}
          {pendingSlots.map((s, i) => (
            <div
              key={s.id || i}
              className="rounded-3xl border border-ink/5 bg-white p-5 shadow-chip"
            >
              <div className="mb-3 flex items-center gap-2 text-[14px] font-semibold text-ink">
                <span className="grid h-6 w-6 place-items-center rounded-lg bg-lime-soft text-[11px] font-bold text-lime">
                  {a2uiSections.length + i + 1}
                </span>
                {s.title || "Next section"}
              </div>
              <div className="space-y-2">
                <div className="h-3 w-5/6 animate-pulse rounded bg-sand" />
                <div className="h-3 w-3/5 animate-pulse rounded bg-sand" />
              </div>
            </div>
          ))}
        </div>
      ) : (
        <iframe
          ref={iframeRef}
          title={`Generating ${lesson.title}`}
          srcDoc={shell}
          sandbox="allow-scripts"
          className="h-full w-full flex-1 bg-transparent"
          onLoad={() => {
            loadedRef.current = true;
            const w = iframeRef.current?.contentWindow;
            if (!w) return;
            const post = (type: string, payload?: unknown) =>
              w.postMessage({ source: THEATER_SOURCE, type, payload }, "*");
            if (skeletonRef.current) post("GT_SKELETON", skeletonRef.current);
            for (const [key, entry] of streamsRef.current) {
              if (!entry.joined || !entry.buffer) continue;
              post("GT_FRAGMENT", {
                sectionId: key === "__doc" ? null : key,
                delta: entry.buffer,
                reset: true,
              });
            }
          }}
        />
      )}
    </div>
  );
}
