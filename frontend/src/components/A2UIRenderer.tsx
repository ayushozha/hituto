import { createElement, Key, ReactNode, useMemo, useState } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";
import QuizComponent from "./QuizComponent";

/**
 * Path A (A2UI) renderer. Walks a trusted, theme-locked component tree emitted by the tutor's
 * `render_ui` tool and maps each `type` to a hand-built component from a FIXED registry. Unknown
 * types are dropped (never raw-rendered); every component handles malformed props defensively.
 *
 * The model supplies only which components to compose and their (backend-validated + normalized)
 * props — never markup. The one place HTML is injected is `MathBlock`, and it injects KaTeX's OWN
 * output rendered with `trust:false` (not the raw model string), per the Phase-0 XSS policy.
 *
 * Node/prop shapes mirror the backend Pydantic models in `backend/app/pipeline/tutor.py`.
 */
export type UiNode = {
  type: string;
  props?: Record<string, unknown>;
  children?: UiNode[];
};

type ResultFn = (result: { toolName: string; [k: string]: unknown }) => void;

// --- Thin v1 components (design tokens only) ---

function Stack({
  direction = "vertical",
  gap = "md",
  children,
}: {
  direction?: string;
  gap?: string;
  children?: ReactNode;
}) {
  const gapCls = gap === "sm" ? "gap-2" : gap === "lg" ? "gap-6" : "gap-4";
  const dirCls = direction === "horizontal" ? "flex-row flex-wrap items-start" : "flex-col";
  return <div className={`flex ${dirCls} ${gapCls}`}>{children}</div>;
}

function Heading({ text, level = 2 }: { text?: string; level?: number }) {
  if (typeof text !== "string" || !text.trim()) return null;
  const lvl = Math.min(3, Math.max(1, Number(level) || 2));
  const cls =
    lvl === 1
      ? "font-display text-lg font-medium tracking-tight text-ink"
      : lvl === 2
      ? "font-display text-base font-medium text-ink"
      : "text-sm font-semibold text-ink";
  // lvl 1→h3, 2→h4, 3→h5 (keeps the app's h1/h2 for real page structure).
  return createElement(`h${lvl + 2}`, { className: cls }, text);
}

function Text({ text }: { text?: string }) {
  if (typeof text !== "string" || !text.trim()) return null;
  return <p className="text-[14px] leading-relaxed text-ink-soft">{text}</p>;
}

const CALLOUT: Record<string, string> = {
  info: "border-cobalt/25 bg-cobalt-soft text-cobalt",
  success: "border-grass/25 bg-grass-soft text-grass",
  warning: "border-lime-dark/30 bg-lime-soft text-ink",
  danger: "border-coral/30 bg-coral-soft text-coral-dark",
};

function Callout({ text, variant = "info" }: { text?: string; variant?: string }) {
  if (typeof text !== "string" || !text.trim()) return null;
  const cls = CALLOUT[variant] ?? CALLOUT.info;
  return <div className={`rounded-xl border p-3 text-[13px] leading-relaxed ${cls}`}>{text}</div>;
}

function MathBlock({ latex, display = true }: { latex?: string; display?: boolean }) {
  if (typeof latex !== "string" || !latex.trim()) return null;
  const displayMode = display !== false;
  try {
    const html = katex.renderToString(latex, {
      displayMode,
      throwOnError: false,
      // Security-relevant flag: disallow \href/\url/\includegraphics etc. from the model string.
      trust: false,
    });
    return (
      <div
        className={displayMode ? "my-1 overflow-x-auto" : "inline-block"}
        // KaTeX output (trust:false), NOT the raw model string — safe per the XSS policy.
        dangerouslySetInnerHTML={{ __html: html }}
      />
    );
  } catch {
    return <code className="font-mono text-sm text-ink-soft">{latex}</code>;
  }
}

function TableBlock({
  headers,
  rows,
  caption,
}: {
  headers?: string[];
  rows?: string[][];
  caption?: string;
}) {
  const body = (Array.isArray(rows) ? rows : []).filter((r) => Array.isArray(r));
  if (!body.length) return null;
  const cols = Array.isArray(headers) ? headers : [];
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left text-[13px]">
        {cols.length > 0 && (
          <thead>
            <tr>
              {cols.map((h, i) => (
                <th
                  key={i}
                  className="border-b border-line px-3 py-2 font-display text-xs font-bold uppercase tracking-wide text-ink"
                >
                  {String(h)}
                </th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {body.map((row, r) => (
            <tr key={r} className="odd:bg-paper">
              {row.map((cell, c) => (
                <td key={c} className="border-b border-line px-3 py-2 text-ink-soft">
                  {String(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {caption ? <p className="mt-2 text-[11px] italic text-ink-faint">{caption}</p> : null}
    </div>
  );
}

// Mirrors the Tailwind theme accent tokens (cobalt/coral/grass + an amber) — SVG `fill` needs a
// literal color, so these are the token hex values, not ad-hoc palette.
const CHART_COLORS = ["#2447D8", "#F05A35", "#0C8F78", "#B7860B"];

function Chart({
  kind = "bar",
  labels,
  series,
  caption,
}: {
  kind?: string;
  labels?: string[];
  series?: Array<{ label?: string; values?: number[] }>;
  caption?: string;
}) {
  const clean = (Array.isArray(series) ? series : [])
    .map((s) => ({
      label: typeof s?.label === "string" ? s.label : "",
      values: (Array.isArray(s?.values) ? s!.values : []).map(Number).filter((n) => Number.isFinite(n)),
    }))
    .filter((s) => s.values.length > 0);
  if (!clean.length) return null;

  const n = Math.max(...clean.map((s) => s.values.length));
  const vals = clean.flatMap((s) => s.values);
  const max = Math.max(1, ...vals);
  const min = Math.min(0, ...vals);
  const W = 320;
  const H = 160;
  const PAD = 24;
  const plotW = W - PAD * 2;
  const plotH = H - PAD * 2;
  const span = max - min || 1;
  const x = (i: number) => PAD + (n <= 1 ? plotW / 2 : (i / (n - 1)) * plotW);
  const y = (v: number) => PAD + plotH - ((v - min) / span) * plotH;
  const cats = Array.isArray(labels) ? labels : [];

  return (
    <div className="w-full">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={caption || "chart"}>
        <line x1={PAD} y1={PAD + plotH} x2={W - PAD} y2={PAD + plotH} stroke="#D9D3C4" strokeWidth="1" />
        {kind === "line"
          ? clean.map((s, si) => (
              <polyline
                key={si}
                fill="none"
                stroke={CHART_COLORS[si % CHART_COLORS.length]}
                strokeWidth="2"
                points={s.values.map((v, i) => `${x(i)},${y(v)}`).join(" ")}
              />
            ))
          : clean.map((s, si) => {
              const barW = ((plotW / n) * 0.7) / clean.length;
              return s.values.map((v, i) => {
                const gx = PAD + (i + 0.15) * (plotW / n) + si * barW;
                return (
                  <rect
                    key={`${si}-${i}`}
                    x={gx}
                    y={y(v)}
                    width={Math.max(1, barW - 1)}
                    height={PAD + plotH - y(v)}
                    fill={CHART_COLORS[si % CHART_COLORS.length]}
                  />
                );
              });
            })}
      </svg>
      {cats.length > 0 && (
        <div className="mt-1 flex justify-between px-5 text-[10px] text-ink-faint">
          {cats.slice(0, n).map((c, i) => (
            <span key={i} className="truncate">
              {String(c)}
            </span>
          ))}
        </div>
      )}
      {clean.some((s) => s.label) && (
        <div className="mt-2 flex flex-wrap gap-3">
          {clean.map((s, si) => (
            <span key={si} className="flex items-center gap-1.5 text-[11px] text-ink-soft">
              <span
                className="inline-block h-2.5 w-2.5 rounded-sm"
                style={{ background: CHART_COLORS[si % CHART_COLORS.length] }}
              />
              {s.label || `Series ${si + 1}`}
            </span>
          ))}
        </div>
      )}
      {caption ? <p className="mt-1 text-[11px] italic text-ink-faint">{caption}</p> : null}
    </div>
  );
}

function Steps({ steps }: { steps?: Array<{ title?: string; detail?: string }> }) {
  const items = Array.isArray(steps) ? steps : [];
  if (!items.length) return null;
  return (
    <ol className="space-y-2.5">
      {items.map((step, i) => (
        <li key={i} className="flex gap-3">
          <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full bg-cobalt-soft text-xs font-bold text-cobalt">
            {i + 1}
          </span>
          <div className="min-w-0">
            {step?.title ? <div className="text-sm font-medium text-ink">{step.title}</div> : null}
            {step?.detail ? (
              <div className="text-[13px] leading-relaxed text-ink-soft">{step.detail}</div>
            ) : null}
          </div>
        </li>
      ))}
    </ol>
  );
}

// --- Slider (reactive readouts via a SAFE expression parser — never eval/Function) ---

const _FUNCS: Record<string, (...a: number[]) => number> = {
  sqrt: Math.sqrt, cbrt: Math.cbrt, abs: Math.abs, sign: Math.sign,
  sin: Math.sin, cos: Math.cos, tan: Math.tan,
  asin: Math.asin, acos: Math.acos, atan: Math.atan,
  exp: Math.exp, log: Math.log, ln: Math.log, log10: Math.log10, log2: Math.log2,
  pow: Math.pow, min: Math.min, max: Math.max,
  round: Math.round, floor: Math.floor, ceil: Math.ceil,
};
const _CONSTS: Record<string, number> = { pi: Math.PI, e: Math.E, tau: Math.PI * 2 };

/**
 * Compile arithmetic in the variable `x` into a `(x)=>number` closure via a hand-written
 * recursive-descent parser. Only numbers, `x`, a fixed constant/function whitelist, `+ - * / % ^`,
 * parentheses, and commas are accepted; ANY other character or unknown identifier makes it return
 * null. No `eval`, no `new Function` — the model string can never execute as code.
 */
function compileExpr(src: string): ((x: number) => number) | null {
  if (typeof src !== "string" || !src.trim()) return null;
  const tokens: string[] = [];
  const re = /\s*([0-9]*\.?[0-9]+(?:[eE][+-]?[0-9]+)?|[a-zA-Z_][a-zA-Z0-9_]*|[+\-*/%^(),])/g;
  let idx = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(src)) !== null) {
    if (m.index !== idx) return null; // a gap means an illegal character
    tokens.push(m[1]);
    idx = re.lastIndex;
  }
  if (idx !== src.length || !tokens.length) return null;

  type Fn = (x: number) => number;
  let pos = 0;
  const peek = () => tokens[pos];
  const next = () => tokens[pos++];

  const parseExpr = (): Fn => {
    let left = parseTerm();
    while (peek() === "+" || peek() === "-") {
      const op = next();
      const r = parseTerm();
      const l = left;
      left = op === "+" ? (x) => l(x) + r(x) : (x) => l(x) - r(x);
    }
    return left;
  };
  const parseTerm = (): Fn => {
    let left = parsePower();
    while (peek() === "*" || peek() === "/" || peek() === "%") {
      const op = next();
      const r = parsePower();
      const l = left;
      left = op === "*" ? (x) => l(x) * r(x) : op === "/" ? (x) => l(x) / r(x) : (x) => l(x) % r(x);
    }
    return left;
  };
  const parsePower = (): Fn => {
    const base = parseUnary();
    if (peek() === "^") {
      next();
      const exp = parsePower(); // right-associative
      return (x) => Math.pow(base(x), exp(x));
    }
    return base;
  };
  const parseUnary = (): Fn => {
    if (peek() === "-") { next(); const a = parseUnary(); return (x) => -a(x); }
    if (peek() === "+") { next(); return parseUnary(); }
    return parseAtom();
  };
  const parseAtom = (): Fn => {
    const t = peek();
    if (t === undefined) throw new Error("eof");
    if (t === "(") {
      next();
      const e = parseExpr();
      if (next() !== ")") throw new Error("paren");
      return e;
    }
    if (/^[0-9.]/.test(t)) { next(); const v = parseFloat(t); return () => v; }
    if (/^[a-zA-Z_]/.test(t)) {
      next();
      if (t === "x") return (x) => x;
      if (t in _CONSTS) { const v = _CONSTS[t]; return () => v; }
      if (peek() === "(") {
        next();
        const args: Fn[] = [];
        if (peek() !== ")") {
          args.push(parseExpr());
          while (peek() === ",") { next(); args.push(parseExpr()); }
        }
        if (next() !== ")") throw new Error("args");
        const fn = _FUNCS[t];
        if (!fn) throw new Error("fn");
        return (x) => fn(...args.map((a) => a(x)));
      }
      throw new Error("ident");
    }
    throw new Error("unexpected");
  };

  try {
    const fn = parseExpr();
    if (pos !== tokens.length) return null;
    return fn;
  } catch {
    return null;
  }
}

const fmtNum = (n: number) => String(Math.round(n * 1000) / 1000);

function SliderBlock({
  label,
  min = 0,
  max = 100,
  step = 1,
  value,
  unit = "",
  readouts,
}: {
  label?: string;
  min?: number;
  max?: number;
  step?: number;
  value?: number;
  unit?: string;
  readouts?: Array<{ label?: string; expr?: string; unit?: string; precision?: number }>;
}) {
  const lo = Number.isFinite(min) ? Number(min) : 0;
  const hi = Number.isFinite(max) && Number(max) > lo ? Number(max) : lo + 1;
  const st = Number.isFinite(step) && Number(step) > 0 ? Number(step) : 1;
  const init = Number.isFinite(value) ? Math.min(hi, Math.max(lo, Number(value))) : lo;
  const [val, setVal] = useState(init);
  const outs = useMemo(
    () =>
      (Array.isArray(readouts) ? readouts : []).map((r) => ({
        label: typeof r?.label === "string" ? r.label : "",
        unit: typeof r?.unit === "string" ? r.unit : "",
        precision: Number.isFinite(r?.precision) ? Math.min(6, Math.max(0, Number(r!.precision))) : 2,
        fn: compileExpr(r?.expr ?? ""),
      })),
    [readouts]
  );
  if (typeof label !== "string" || !label.trim()) return null;

  return (
    <div className="rounded-xl border border-line bg-surface p-3">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm font-medium text-ink">{label}</span>
        <span className="font-mono text-sm text-cobalt">
          {fmtNum(val)}
          {unit ? ` ${unit}` : ""}
        </span>
      </div>
      <input
        type="range"
        min={lo}
        max={hi}
        step={st}
        value={val}
        onChange={(e) => setVal(Number(e.target.value))}
        className="mt-2 w-full accent-cobalt"
      />
      {outs.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
          {outs.map((o, i) => {
            const r = o.fn ? o.fn(val) : NaN;
            const text = Number.isFinite(r) ? (r as number).toFixed(o.precision) : "—";
            return (
              <span key={i} className="text-[13px]">
                {o.label ? <span className="text-ink-faint">{o.label}: </span> : null}
                <span className="font-mono text-ink">
                  {text}
                  {o.unit ? ` ${o.unit}` : ""}
                </span>
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}

// --- Diagram (layered longest-path auto-layout, hand-drawn SVG — no graph lib) ---

type DBox = { x: number; y: number; w: number; h: number; label: string };

function computeDiagram(
  rawNodes: unknown,
  rawEdges: unknown,
  direction: string
): { boxes: DBox[]; links: Array<{ x1: number; y1: number; x2: number; y2: number; label: string }>; W: number; H: number } | null {
  const ns = (Array.isArray(rawNodes) ? rawNodes : [])
    .filter((n: any) => n && n.id != null)
    .map((n: any) => ({ id: String(n.id), label: String(n.label ?? n.id) }));
  if (!ns.length) return null;
  const ids = new Set(ns.map((n) => n.id));
  const es = (Array.isArray(rawEdges) ? rawEdges : [])
    .map((e: any) => ({
      source: String(e?.source ?? ""),
      target: String(e?.target ?? ""),
      label: typeof e?.label === "string" ? e.label : "",
    }))
    .filter((e) => ids.has(e.source) && ids.has(e.target));

  // Longest-path layering: relax layer[target] = max(.., layer[source]+1). Capped by node count
  // so cycles terminate (a back-edge just stops raising the layer).
  const layer = new Map(ns.map((n) => [n.id, 0]));
  for (let i = 0; i < ns.length; i++) {
    let changed = false;
    for (const e of es) {
      const nl = (layer.get(e.source) || 0) + 1;
      if (nl > (layer.get(e.target) || 0)) {
        layer.set(e.target, nl);
        changed = true;
      }
    }
    if (!changed) break;
  }
  const layers: Array<Array<{ id: string; label: string }>> = [];
  for (const n of ns) {
    const l = layer.get(n.id) || 0;
    (layers[l] ||= []).push(n);
  }

  const isTB = direction !== "LR";
  const NH = 36;
  const gapMain = 56;
  const gapCross = 20;
  const M = 16;
  const widthOf = (label: string) => Math.min(220, Math.max(64, label.length * 7 + 28));
  const crossExtent = (ln: Array<{ label: string }>) =>
    isTB
      ? ln.reduce((s, n) => s + widthOf(n.label), 0) + gapCross * (ln.length - 1)
      : ln.length * NH + gapCross * (ln.length - 1);

  const extents = layers.map((ln) => (ln ? crossExtent(ln) : 0));
  const maxCross = Math.max(1, ...extents);

  const boxMap = new Map<string, DBox>();
  let mainCursor = M;
  layers.forEach((ln, li) => {
    if (!ln) return;
    const thick = isTB ? NH : Math.max(...ln.map((n) => widthOf(n.label)));
    let cross = M + (maxCross - extents[li]) / 2;
    ln.forEach((n) => {
      const w = widthOf(n.label);
      if (isTB) {
        boxMap.set(n.id, { x: cross, y: mainCursor, w, h: NH, label: n.label });
        cross += w + gapCross;
      } else {
        boxMap.set(n.id, { x: mainCursor, y: cross, w, h: NH, label: n.label });
        cross += NH + gapCross;
      }
    });
    mainCursor += thick + gapMain;
  });

  const mainSpan = mainCursor - gapMain + M;
  const W = isTB ? M * 2 + maxCross : mainSpan;
  const H = isTB ? mainSpan : M * 2 + maxCross;

  const links = es
    .map((e) => {
      const a = boxMap.get(e.source);
      const b = boxMap.get(e.target);
      if (!a || !b) return null;
      return isTB
        ? { x1: a.x + a.w / 2, y1: a.y + a.h, x2: b.x + b.w / 2, y2: b.y, label: e.label }
        : { x1: a.x + a.w, y1: a.y + a.h / 2, x2: b.x, y2: b.y + b.h / 2, label: e.label };
    })
    .filter(Boolean) as Array<{ x1: number; y1: number; x2: number; y2: number; label: string }>;

  return { boxes: [...boxMap.values()], links, W, H };
}

function DiagramBlock({
  nodes,
  edges,
  direction = "TB",
  caption,
}: {
  nodes?: unknown;
  edges?: unknown;
  direction?: string;
  caption?: string;
}) {
  const layout = useMemo(() => computeDiagram(nodes, edges, direction), [nodes, edges, direction]);
  if (!layout) return null;
  const { boxes, links, W, H } = layout;
  const clip = (s: string) => (s.length > 30 ? `${s.slice(0, 29)}…` : s);

  return (
    <div className="w-full overflow-x-auto">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        style={{ maxWidth: W }}
        role="img"
        aria-label={caption || "diagram"}
      >
        <defs>
          <marker
            id="tl-diagram-arrow"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="7"
            markerHeight="7"
            orient="auto-start-reverse"
          >
            <path d="M0,0 L10,5 L0,10 z" fill="#858777" />
          </marker>
        </defs>
        {links.map((l, i) => (
          <g key={`l${i}`}>
            <line
              x1={l.x1}
              y1={l.y1}
              x2={l.x2}
              y2={l.y2}
              stroke="#858777"
              strokeWidth="1.5"
              markerEnd="url(#tl-diagram-arrow)"
            />
            {l.label ? (
              <text
                x={(l.x1 + l.x2) / 2}
                y={(l.y1 + l.y2) / 2 - 3}
                textAnchor="middle"
                fontSize="10"
                fill="#858777"
              >
                {clip(l.label)}
              </text>
            ) : null}
          </g>
        ))}
        {boxes.map((b, i) => (
          <g key={`b${i}`}>
            <rect
              x={b.x}
              y={b.y}
              width={b.w}
              height={b.h}
              rx="8"
              fill="#E6EBFF"
              stroke="#2447D8"
              strokeWidth="1.5"
            />
            <text
              x={b.x + b.w / 2}
              y={b.y + b.h / 2}
              textAnchor="middle"
              dominantBaseline="central"
              fontSize="12"
              fill="#171713"
            >
              {clip(b.label)}
            </text>
          </g>
        ))}
      </svg>
      {caption ? <p className="mt-1 text-[11px] italic text-ink-faint">{caption}</p> : null}
    </div>
  );
}

type MapListing = {
  id?: string;
  lat: number;
  lng: number;
  label?: string;
  beds?: number;
  baths?: number;
  sqft?: number;
  list_price?: number;
};

function MapBlock({
  title,
  center,
  listings,
  prediction,
  copy,
  caption,
}: {
  title?: string;
  center?: { lat?: number; lng?: number };
  listings?: MapListing[];
  prediction?: { mode?: string; student_inputs?: string[] };
  copy?: Record<string, string>;
  caption?: string;
}) {
  const pins = Array.isArray(listings) ? listings : [];
  const [selected, setSelected] = useState(0);
  const pin = pins[Math.min(selected, Math.max(0, pins.length - 1))];
  const [sqft, setSqft] = useState(Number(pin?.sqft) || 1200);
  const [beds, setBeds] = useState(Number(pin?.beds) || 2);

  const estimate = useMemo(() => {
    // Deterministic demo predictor — not a real model.
    const base = 420;
    return Math.round(base * sqft + beds * 85000);
  }, [sqft, beds]);

  const cLat = Number(center?.lat ?? 37.8);
  const cLng = Number(center?.lng ?? -122.3);
  const project = (lat: number, lng: number) => {
    const x = 50 + (lng - cLng) * 180;
    const y = 50 - (lat - cLat) * 220;
    return { x: Math.max(8, Math.min(92, x)), y: Math.max(8, Math.min(92, y)) };
  };

  return (
    <div className="overflow-hidden rounded-2xl border border-ink/5 bg-white shadow-chip">
      <div className="border-b border-ink/5 bg-sand px-3 py-2">
        <p className="text-[13px] font-bold text-ink">{title || "Map lab"}</p>
        {copy?.task ? <p className="text-[11px] text-ink-soft">{copy.task}</p> : null}
      </div>
      <div className="grid gap-3 p-3 md:grid-cols-2">
        <svg viewBox="0 0 100 100" className="aspect-square w-full rounded-xl bg-mint/40" role="img" aria-label="Map">
          <rect width="100" height="100" fill="#ECFDF3" />
          <path d="M0 55 Q25 40 50 55 T100 50" fill="none" stroke="#BBF7D0" strokeWidth="8" />
          {pins.map((p, i) => {
            const { x, y } = project(Number(p.lat), Number(p.lng));
            const active = i === selected;
            return (
              <g key={p.id || i} onClick={() => setSelected(i)} style={{ cursor: "pointer" }}>
                <circle cx={x} cy={y} r={active ? 4.5 : 3.2} fill={active ? "#16A34A" : "#14380E"} />
                <text x={x} y={y - 5} textAnchor="middle" fontSize="3.2" fill="#18181B">
                  {(p.label || p.id || "").slice(0, 14)}
                </text>
              </g>
            );
          })}
        </svg>
        <div className="space-y-2">
          {pin ? (
            <>
              <p className="text-[12px] font-semibold text-ink">{pin.label || pin.id}</p>
              <p className="text-[11px] text-ink-soft">
                List {pin.list_price != null ? `$${Number(pin.list_price).toLocaleString()}` : "—"}
                {pin.sqft != null ? ` · ${pin.sqft} sqft` : ""}
                {pin.beds != null ? ` · ${pin.beds} bd` : ""}
              </p>
            </>
          ) : (
            <p className="text-[12px] text-ink-soft">No listings yet.</p>
          )}
          {(prediction?.mode || "linear_demo") !== "none" && (
            <div className="space-y-2 rounded-xl bg-sand p-2">
              <label className="block text-[11px] font-semibold text-ink">
                Sqft
                <input
                  type="range"
                  min={400}
                  max={4000}
                  step={50}
                  value={sqft}
                  onChange={(e) => setSqft(Number(e.target.value))}
                  className="mt-1 w-full"
                />
              </label>
              <label className="block text-[11px] font-semibold text-ink">
                Beds
                <input
                  type="range"
                  min={0}
                  max={6}
                  step={1}
                  value={beds}
                  onChange={(e) => setBeds(Number(e.target.value))}
                  className="mt-1 w-full"
                />
              </label>
              <p className="text-[12px] font-bold text-lime-dark">
                Demo estimate: ${estimate.toLocaleString()}
              </p>
            </div>
          )}
        </div>
      </div>
      {caption ? <p className="px-3 pb-2 text-[11px] italic text-ink-faint">{caption}</p> : null}
    </div>
  );
}

function EmbedBlock({
  title,
  html,
  caption,
}: {
  title?: string;
  html?: string;
  caption?: string;
  slot_id?: string;
}) {
  const srcDoc = (html || "").trim();
  return (
    <div className="overflow-hidden rounded-2xl border border-ink/5 bg-white shadow-chip">
      <div className="border-b border-ink/5 bg-sand px-3 py-2">
        <p className="text-[13px] font-bold text-ink">{title || "Interactive demo"}</p>
        {caption ? <p className="text-[11px] text-ink-soft">{caption}</p> : null}
      </div>
      {srcDoc ? (
        <iframe
          title={title || "embed"}
          sandbox="allow-scripts"
          srcDoc={srcDoc}
          className="h-[320px] w-full border-0 bg-paper"
        />
      ) : (
        <p className="p-4 text-[12px] text-ink-soft">
          Embed slot ready — regenerate this section to fill the interactive demo.
        </p>
      )}
    </div>
  );
}

// --- Fixed registry + recursive walk ---

function renderNode(node: UiNode | undefined, key: Key, onResult?: ResultFn): ReactNode {
  if (!node || typeof node !== "object") return null;
  const props = (node.props ?? {}) as any;
  const children = Array.isArray(node.children)
    ? node.children.map((child, i) => renderNode(child, i, onResult))
    : null;

  switch (node.type) {
    case "stack":
      return (
        <Stack key={key} direction={props.direction} gap={props.gap}>
          {children}
        </Stack>
      );
    case "heading":
      return <Heading key={key} text={props.text} level={props.level} />;
    case "text":
      return <Text key={key} text={props.text} />;
    case "callout":
      return <Callout key={key} text={props.text} variant={props.variant} />;
    case "math":
      return <MathBlock key={key} latex={props.latex} display={props.display} />;
    case "steps":
      return <Steps key={key} steps={props.steps} />;
    case "table":
      return <TableBlock key={key} headers={props.headers} rows={props.rows} caption={props.caption} />;
    case "chart":
      return (
        <Chart key={key} kind={props.kind} labels={props.labels} series={props.series} caption={props.caption} />
      );
    case "slider":
      return (
        <SliderBlock
          key={key}
          label={props.label}
          min={props.min}
          max={props.max}
          step={props.step}
          value={props.value}
          unit={props.unit}
          readouts={props.readouts}
        />
      );
    case "diagram":
      return (
        <DiagramBlock
          key={key}
          nodes={props.nodes}
          edges={props.edges}
          direction={props.direction}
          caption={props.caption}
        />
      );
    case "map":
      return (
        <MapBlock
          key={key}
          title={props.title}
          center={props.center}
          listings={props.listings}
          prediction={props.prediction}
          copy={props.task_copy || props.copy}
          caption={props.caption}
        />
      );
    case "embed":
      return (
        <EmbedBlock
          key={key}
          title={props.title}
          html={props.html}
          caption={props.caption}
          slot_id={props.slot_id}
        />
      );
    case "quiz":
      return (
        <QuizComponent
          key={key}
          topic={props.topic ?? ""}
          questions={props.questions ?? []}
          onResult={
            onResult
              ? (score, total, metadata) =>
                  onResult({ toolName: "create_quiz", score, total, ...metadata })
              : undefined
          }
          onRetry={
            onResult
              ? (attempt) => onResult({ toolName: "practice_retried", attempt })
              : undefined
          }
        />
      );
    // Unknown types are dropped — never raw-rendered.
    default:
      return null;
  }
}

export default function A2UIRenderer({ root, onResult }: { root?: UiNode; onResult?: ResultFn }) {
  return <>{renderNode(root, "root", onResult)}</>;
}
