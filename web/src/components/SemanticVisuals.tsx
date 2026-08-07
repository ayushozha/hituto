import type { BarChartCommand, VennCommand } from "../types/lesson";

interface VisualProps<T> {
  command: T;
  width: number;
  height: number;
}

function readableNumber(value: number): string {
  if (Number.isInteger(value)) return String(value);
  return String(Number(value.toFixed(3)));
}

export function BarChart({ command, width, height }: VisualProps<BarChartCommand>) {
  const padding = { left: 54, right: 18, top: command.title ? 46 : 24, bottom: 64 };
  const plotWidth = Math.max(1, width - padding.left - padding.right);
  const plotHeight = Math.max(1, height - padding.top - padding.bottom);
  const maximum = Math.max(...command.bars.map((bar) => bar.value), 1);
  const headroom = maximum * 1.12;
  const slotWidth = plotWidth / command.bars.length;
  const barWidth = Math.min(64, slotWidth * 0.62);

  return (
    <svg
      className="semantic-visual bar-chart"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={command.title || "Bar chart"}
      data-visual-engine="bar-chart"
    >
      <rect width={width} height={height} rx="12" fill="#fff" />
      {command.title && <text x={width / 2} y="28" textAnchor="middle" className="visual-title">{command.title}</text>}
      <line x1={padding.left} y1={padding.top} x2={padding.left} y2={padding.top + plotHeight} className="visual-axis" />
      <line x1={padding.left} y1={padding.top + plotHeight} x2={padding.left + plotWidth} y2={padding.top + plotHeight} className="visual-axis" />
      {command.y_label && (
        <text x="16" y={padding.top + plotHeight / 2} textAnchor="middle" transform={`rotate(-90 16 ${padding.top + plotHeight / 2})`} className="visual-axis-label">
          {command.y_label}
        </text>
      )}
      {command.bars.map((bar, index) => {
        const barHeight = (bar.value / headroom) * plotHeight;
        const x = padding.left + index * slotWidth + (slotWidth - barWidth) / 2;
        const y = padding.top + plotHeight - barHeight;
        return (
          <g key={`${bar.label}-${index}`} data-bar-label={bar.label}>
            <rect x={x} y={y} width={barWidth} height={barHeight} rx="5" fill={bar.color} className="bar-rise" />
            <text x={x + barWidth / 2} y={Math.max(padding.top + 13, y - 8)} textAnchor="middle" className="visual-value">
              {bar.display_value || readableNumber(bar.value)}
            </text>
            <text x={x + barWidth / 2} y={padding.top + plotHeight + 22} textAnchor="middle" className="visual-category">{bar.label}</text>
          </g>
        );
      })}
      {command.x_label && <text x={padding.left + plotWidth / 2} y={height - 10} textAnchor="middle" className="visual-axis-label">{command.x_label}</text>}
    </svg>
  );
}

export function VennDiagram({ command, width, height }: VisualProps<VennCommand>) {
  const centerY = height * 0.52;
  const radius = Math.min(width * 0.25, height * 0.31);
  const leftX = width * 0.39;
  const rightX = width * 0.61;
  return (
    <svg
      className="semantic-visual venn-diagram"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={command.title || `Venn diagram for ${command.left_label} and ${command.right_label}`}
      data-visual-engine="venn"
    >
      <rect x="1" y="1" width={width - 2} height={height - 2} rx="12" fill="#fff" stroke="#d7e0e8" />
      {command.title && <text x={width / 2} y="30" textAnchor="middle" className="visual-title">{command.title}</text>}
      <circle cx={leftX} cy={centerY} r={radius} fill="#1769e0" fillOpacity="0.14" stroke="#1769e0" strokeWidth="4" />
      <circle cx={rightX} cy={centerY} r={radius} fill="#8b5cf6" fillOpacity="0.14" stroke="#7145d6" strokeWidth="4" />
      <text x={leftX - radius * 0.42} y={centerY - radius - 12} textAnchor="middle" className="visual-set-label">{command.left_label}</text>
      <text x={rightX + radius * 0.42} y={centerY - radius - 12} textAnchor="middle" className="visual-set-label">{command.right_label}</text>
      <text x={leftX - radius * 0.45} y={centerY + 6} textAnchor="middle" className="visual-region">{command.left_only}</text>
      <text x={width / 2} y={centerY + 6} textAnchor="middle" className="visual-region is-overlap">{command.overlap}</text>
      <text x={rightX + radius * 0.45} y={centerY + 6} textAnchor="middle" className="visual-region">{command.right_only}</text>
      {command.outside && <text x={width - 18} y={height - 20} textAnchor="end" className="visual-outside">Outside: {command.outside}</text>}
    </svg>
  );
}
