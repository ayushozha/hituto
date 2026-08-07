import { compile } from "mathjs";
import { useId, useMemo } from "react";
import type { GraphCommand, GraphCurve } from "../types/lesson";

interface GraphProps {
  command: GraphCommand;
  width: number;
  height: number;
}

const allowedFormulaNames = new Set(["x", "abs", "sqrt", "sin", "cos", "tan", "log", "log10", "exp", "pi", "e"]);

function compileFormula(curve: GraphCurve): ((x: number) => number) | undefined {
  if (!/^[0-9A-Za-z_+\-*/^().,\s]+$/.test(curve.formula)) return undefined;
  const names = curve.formula.match(/[A-Za-z_]+/g) ?? [];
  if (names.some((name) => !allowedFormulaNames.has(name))) return undefined;
  try {
    const evaluator = compile(curve.formula);
    return (x: number) => {
      const value = evaluator.evaluate({ x });
      return typeof value === "number" && Number.isFinite(value) ? value : Number.NaN;
    };
  } catch {
    return undefined;
  }
}

function niceStep(span: number): number {
  const rough = Math.max(Number.EPSILON, span / 7);
  const power = 10 ** Math.floor(Math.log10(rough));
  const normalized = rough / power;
  const multiple = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  return multiple * power;
}

function ticks(minimum: number, maximum: number): number[] {
  const step = niceStep(maximum - minimum);
  const values: number[] = [];
  for (let value = Math.ceil(minimum / step) * step; value <= maximum + step * 0.001; value += step) {
    values.push(Number(value.toPrecision(12)));
    if (values.length > 30) break;
  }
  return values;
}

function formatTick(value: number): string {
  if (Math.abs(value) < 1e-10) return "0";
  if (Math.abs(value) >= 100 || Math.abs(value) < 0.01) return value.toExponential(0);
  return Number(value.toFixed(3)).toString();
}

export function FunctionGraph({ command, width, height }: GraphProps) {
  const clipId = useId().replaceAll(":", "");
  const padding = { left: 42, right: 14, top: 14, bottom: 32 };
  const plotWidth = Math.max(1, width - padding.left - padding.right);
  const plotHeight = Math.max(1, height - padding.top - padding.bottom);
  const toX = (value: number) => padding.left + ((value - command.x_min) / (command.x_max - command.x_min)) * plotWidth;
  const toY = (value: number) => padding.top + ((command.y_max - value) / (command.y_max - command.y_min)) * plotHeight;
  const xTicks = useMemo(() => ticks(command.x_min, command.x_max), [command.x_min, command.x_max]);
  const yTicks = useMemo(() => ticks(command.y_min, command.y_max), [command.y_min, command.y_max]);
  const paths = useMemo(() => command.curves.map((curve) => {
    const evaluate = compileFormula(curve);
    if (!evaluate) return { curve, path: "" };
    const samples = Math.max(240, Math.min(720, Math.round(plotWidth * 1.4)));
    let path = "";
    let previousY: number | undefined;
    for (let index = 0; index <= samples; index += 1) {
      const x = command.x_min + (index / samples) * (command.x_max - command.x_min);
      const y = evaluate(x);
      const px = toX(x);
      const py = toY(y);
      const discontinuity = !Number.isFinite(py) || (previousY !== undefined && Math.abs(py - previousY) > plotHeight * 0.72);
      if (!Number.isFinite(py)) {
        previousY = undefined;
        continue;
      }
      path += `${discontinuity || previousY === undefined ? "M" : "L"}${px.toFixed(2)},${py.toFixed(2)} `;
      previousY = py;
    }
    return { curve, path };
  }), [command, plotHeight, plotWidth]);
  const axisX = command.y_min <= 0 && command.y_max >= 0 ? toY(0) : padding.top + plotHeight;
  const axisY = command.x_min <= 0 && command.x_max >= 0 ? toX(0) : padding.left;

  return (
    <div className="graph-stack" style={{ width, height }}>
      <svg
        className="function-graph"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Mathematically plotted graph"
        data-graph-engine="built-in"
      >
        <defs><clipPath id={clipId}><rect x={padding.left} y={padding.top} width={plotWidth} height={plotHeight} /></clipPath></defs>
        <rect width={width} height={height} rx="12" fill="#fff" />
        <g className="graph-grid">
          {xTicks.map((value) => <line key={`x-${value}`} x1={toX(value)} y1={padding.top} x2={toX(value)} y2={padding.top + plotHeight} />)}
          {yTicks.map((value) => <line key={`y-${value}`} x1={padding.left} y1={toY(value)} x2={padding.left + plotWidth} y2={toY(value)} />)}
        </g>
        <g className="graph-axes">
          <line x1={padding.left} y1={axisX} x2={padding.left + plotWidth} y2={axisX} />
          <line x1={axisY} y1={padding.top} x2={axisY} y2={padding.top + plotHeight} />
        </g>
        <g className="graph-ticks">
          {xTicks.filter((value) => value !== 0).map((value) => (
            <text key={`xt-${value}`} x={toX(value)} y={Math.min(height - 7, axisX + 18)} textAnchor="middle">{formatTick(value)}</text>
          ))}
          {yTicks.filter((value) => value !== 0).map((value) => (
            <text key={`yt-${value}`} x={Math.max(16, axisY - 8)} y={toY(value) + 4} textAnchor="end">{formatTick(value)}</text>
          ))}
        </g>
        <g clipPath={`url(#${clipId})`}>
          {paths.map(({ curve, path }) => path && (
            <path key={curve.id} d={path} fill="none" stroke={curve.color} strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
          ))}
        </g>
        <g className="graph-markers">
          {command.markers.map((marker) => (
            <g key={marker.id} data-graph-marker={marker.id}>
              <circle cx={toX(marker.x)} cy={toY(marker.y)} r="6" fill={marker.color} stroke="#fff" strokeWidth="2" />
              {marker.label && (
                <text x={toX(marker.x) + 10} y={toY(marker.y) - 10} fill={marker.color}>{marker.label}</text>
              )}
            </g>
          ))}
        </g>
        <rect x={padding.left} y={padding.top} width={plotWidth} height={plotHeight} fill="none" stroke="#cfd8e2" />
      </svg>
    </div>
  );
}
