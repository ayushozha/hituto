import React, { useState, useEffect } from "react";
import WidgetCard from "./WidgetCard";

// Safe arithmetic evaluator — a small recursive-descent parser supporting
// + - * / and parentheses over numeric literals. Used instead of `new Function`
// so tutor-supplied formula strings can never execute arbitrary JavaScript.
function evalArithmetic(expr: string): number | null {
  let i = 0;
  const s = expr.replace(/\s+/g, "");

  const peek = () => s[i];
  const parseExpr = (): number => {
    let value = parseTerm();
    while (peek() === "+" || peek() === "-") {
      const op = s[i++];
      const rhs = parseTerm();
      value = op === "+" ? value + rhs : value - rhs;
    }
    return value;
  };
  const parseTerm = (): number => {
    let value = parseFactor();
    while (peek() === "*" || peek() === "/") {
      const op = s[i++];
      const rhs = parseFactor();
      value = op === "*" ? value * rhs : value / rhs;
    }
    return value;
  };
  const parseFactor = (): number => {
    if (peek() === "+" || peek() === "-") {
      const op = s[i++];
      const v = parseFactor();
      return op === "-" ? -v : v;
    }
    if (peek() === "(") {
      i++; // consume '('
      const v = parseExpr();
      if (peek() !== ")") throw new Error("unbalanced parentheses");
      i++; // consume ')'
      return v;
    }
    const start = i;
    while (i < s.length && /[0-9.]/.test(s[i])) i++;
    if (i === start) throw new Error(`unexpected token at ${i}`);
    const num = Number(s.slice(start, i));
    if (Number.isNaN(num)) throw new Error("invalid number");
    return num;
  };

  try {
    if (!/^[0-9+\-*/(). ]+$/.test(expr)) return null;
    const result = parseExpr();
    if (i !== s.length) return null;
    return Number.isFinite(result) ? result : null;
  } catch {
    return null;
  }
}

// ==========================================
// 1. Interactive Diagram Component
// ==========================================

export interface DiagramNodeProps {
  id: string;
  label: string;
  description: string;
}

export interface DiagramProps {
  title: string;
  mermaidDefinition: string; // fallback or reference
  nodes: DiagramNodeProps[];
}

// `mermaidDefinition` stays in the tool schema for future rendering support,
// but the component only visualizes the structured `nodes` today.
export function DiagramComponent({ title, nodes }: DiagramProps) {
  const [activeNode, setActiveNode] = useState<DiagramNodeProps | null>(nodes[0] || null);

  return (
    <WidgetCard title={title} eyebrow="Concept map" tone="diagram">
      <div className="mb-3 flex flex-col gap-3 rounded-2xl border border-ink/5 bg-white p-3">
        <div className="flex flex-wrap items-center justify-center gap-2 py-2">
          {nodes.map((node, idx) => (
            <React.Fragment key={node.id}>
              <button
                type="button"
                onClick={() => setActiveNode(node)}
                className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition duration-150 ${
                  activeNode?.id === node.id
                    ? "border-brand bg-cream text-brand-dark"
                    : "border-ink/5 bg-sand text-ink-soft hover:border-brand/30 hover:text-ink"
                }`}
              >
                {node.label}
              </button>
              {idx < nodes.length - 1 && (
                <span className="font-mono text-xs font-semibold text-ink-faint">→</span>
              )}
            </React.Fragment>
          ))}
        </div>
      </div>

      {activeNode && (
        <div className="rounded-2xl border border-ink/5 bg-white p-3 text-xs font-medium leading-relaxed">
          <div className="mb-1 font-semibold text-brand-dark">{activeNode.label}</div>
          <p className="text-ink-soft">{activeNode.description}</p>
        </div>
      )}
    </WidgetCard>
  );
}

// ==========================================
// 2. Formula Calculator Component
// ==========================================

export interface FormulaVar {
  name: string;
  label: string;
  unit: string;
  defaultValue: number;
}

export interface FormulaCalculatorProps {
  title: string;
  formula: string;
  variables: FormulaVar[];
  steps: string[];
}

export function FormulaCalculator({ title, formula, variables, steps }: FormulaCalculatorProps) {
  const [vals, setVals] = useState<Record<string, number>>(() => {
    const initial: Record<string, number> = {};
    variables.forEach((v) => {
      initial[v.name] = v.defaultValue;
    });
    return initial;
  });

  const [result, setResult] = useState<number | null>(null);

  const handleInputChange = (name: string, value: string) => {
    const parsed = parseFloat(value);
    setVals((prev) => ({ ...prev, [name]: isNaN(parsed) ? 0 : parsed }));
  };

  // Evaluate the math formula safely
  useEffect(() => {
    // E.g., D = log(N) / log(S)
    try {
      if (formula.includes("log(N) / log(S)")) {
        const n = vals["N"] ?? 4;
        const s = vals["S"] ?? 2;
        if (s > 1 && n > 0) {
          const res = Math.log(n) / Math.log(s);
          setResult(parseFloat(res.toFixed(3)));
        } else {
          setResult(null);
        }
      } else if (formula.includes("E = m * c^2")) {
        const m = vals["m"] ?? 1;
        const c = 299792458; // m/s
        setResult(m * c * c);
      } else {
        // Generic fallback math evaluation (e.g. N * S or standard addition)
        let mathExpr = formula;
        Object.entries(vals).forEach(([k, v]) => {
          mathExpr = mathExpr.replace(new RegExp(k, "g"), String(v));
        });
        mathExpr = mathExpr.replace(/=/g, "").trim();
        const res = evalArithmetic(mathExpr);
        setResult(res === null ? null : parseFloat(res.toFixed(3)));
      }
    } catch {
      setResult(null);
    }
  }, [vals, formula]);

  return (
    <WidgetCard title={title} eyebrow="Formula solver" tone="calculator">
      <div className="mb-4 rounded-2xl border border-brand/20 bg-cream py-3 text-center font-mono text-sm font-semibold text-brand-dark">
        {formula}
      </div>

      <div className="mb-4 grid gap-3">
        {variables.map((v, idx) => (
          <div key={idx} className="flex items-center justify-between gap-3">
            <span className="text-xs font-semibold text-ink">
              {v.label} ({v.name})
            </span>
            <div className="flex w-1/2 items-center gap-1.5">
              <input
                type="number"
                value={vals[v.name] ?? ""}
                onChange={(e) => handleInputChange(v.name, e.target.value)}
                className="h-9 w-full rounded-xl border border-ink/10 bg-white px-2 font-mono text-xs font-semibold text-ink outline-none transition focus:border-brand/40 focus:ring-2 focus:ring-brand/20"
              />
              <span className="text-[10px] font-semibold uppercase text-ink-faint">{v.unit}</span>
            </div>
          </div>
        ))}
      </div>

      {result !== null && (
        <div className="mb-4 rounded-2xl border border-ink/5 bg-white p-3 text-center">
          <div className="text-[9px] font-semibold uppercase tracking-wider text-ink-faint">
            Computed output
          </div>
          <div className="mt-0.5 font-mono text-xl font-semibold text-ink">{result}</div>
        </div>
      )}

      {steps.length > 0 && (
        <div className="flex flex-col gap-1.5 rounded-2xl border border-ink/5 bg-white p-3 text-[11px] font-medium leading-relaxed text-ink-soft">
          <span className="text-[8px] font-semibold uppercase tracking-wider text-ink-faint">
            Derivation steps
          </span>
          {steps.map((step, idx) => (
            <div key={idx} className="flex gap-2">
              <span className="font-semibold text-brand-dark">{idx + 1}.</span>
              <span className="text-ink">{step}</span>
            </div>
          ))}
        </div>
      )}
    </WidgetCard>
  );
}
