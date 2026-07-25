import { useId } from "react";

type MascotMood = "mark" | "study" | "tutor" | "celebrate";

type MascotProps = {
  mood?: MascotMood;
  className?: string;
  title?: string;
};

const palette: Record<
  MascotMood,
  { body: string; highlight: string; shadow: string; stroke: string; detail: string }
> = {
  mark: {
    body: "#2BC15D",
    highlight: "#71E891",
    shadow: "#159744",
    stroke: "#14380E",
    detail: "#FDF1E7",
  },
  study: {
    body: "#2BC15D",
    highlight: "#71E891",
    shadow: "#159744",
    stroke: "#14380E",
    detail: "#FDF1E7",
  },
  tutor: {
    body: "#CFE6FC",
    highlight: "#F3F9FF",
    shadow: "#93BFE9",
    stroke: "#14380E",
    detail: "#FDF1E7",
  },
  celebrate: {
    body: "#E3C8F5",
    highlight: "#F4E8FC",
    shadow: "#BD91DB",
    stroke: "#7C2FA8",
    detail: "#FFCF3F",
  },
};

/** Four-point sparkle, the brand's signature glyph. */
function Star({ cx, cy, r, fill, stroke }: { cx: number; cy: number; r: number; fill: string; stroke?: string }) {
  const d = `M${cx} ${cy - r}C${cx + r * 0.14} ${cy - r * 0.32} ${cx + r * 0.32} ${cy - r * 0.14} ${cx + r} ${cy}C${cx + r * 0.32} ${cy + r * 0.14} ${cx + r * 0.14} ${cy + r * 0.32} ${cx} ${cy + r}C${cx - r * 0.14} ${cy + r * 0.32} ${cx - r * 0.32} ${cy + r * 0.14} ${cx - r} ${cy}C${cx - r * 0.32} ${cy - r * 0.14} ${cx - r * 0.14} ${cy - r * 0.32} ${cx} ${cy - r}Z`;
  return <path d={d} fill={fill} stroke={stroke} strokeWidth={stroke ? 4 : 0} strokeLinejoin="round" />;
}

function CalmEyes({ stroke, filterId }: { stroke: string; filterId: string }) {
  return (
    <>
      <g filter={`url(#${filterId})`}>
        <rect x="83" y="96" width="13" height="31" rx="6.5" fill={stroke} />
        <rect x="124" y="96" width="13" height="31" rx="6.5" fill={stroke} />
      </g>
      <ellipse cx="87.5" cy="102" rx="2.2" ry="3.6" fill="#FDF1E7" opacity="0.92" />
      <ellipse cx="128.5" cy="102" rx="2.2" ry="3.6" fill="#FDF1E7" opacity="0.92" />
    </>
  );
}

function TinySmile({ stroke, y = 144 }: { stroke: string; y?: number }) {
  return (
    <path
      d={`M101 ${y}C106 ${y + 5} 114 ${y + 5} 119 ${y}`}
      stroke={stroke}
      strokeWidth="6"
      strokeLinecap="round"
    />
  );
}

/**
 * Hi Tuto mascot — a soft rounded square with big calm eyes.
 * Kept deliberately simple: one clean body shape, no blobs.
 */
export function Mascot({ mood = "study", className = "", title }: MascotProps) {
  const colors = palette[mood];
  const labelled = Boolean(title);
  const instanceId = useId().replace(/:/g, "");
  const bodyGradientId = `${instanceId}-body`;
  const sheenGradientId = `${instanceId}-sheen`;
  const bookGradientId = `${instanceId}-book`;
  const starGradientId = `${instanceId}-star`;
  const depthFilterId = `${instanceId}-depth`;
  const propFilterId = `${instanceId}-prop`;
  const eyeFilterId = `${instanceId}-eyes`;

  return (
    <svg
      viewBox="0 0 220 220"
      className={className}
      role={labelled ? "img" : undefined}
      aria-label={title}
      aria-hidden={labelled ? undefined : true}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <linearGradient id={bodyGradientId} x1="64" y1="62" x2="158" y2="178" gradientUnits="userSpaceOnUse">
          <stop stopColor={colors.highlight} />
          <stop offset="0.42" stopColor={colors.body} />
          <stop offset="1" stopColor={colors.shadow} />
        </linearGradient>
        <radialGradient id={sheenGradientId} cx="0" cy="0" r="1" gradientTransform="translate(88 78) rotate(51) scale(91 101)" gradientUnits="userSpaceOnUse">
          <stop stopColor="#FFFFFF" stopOpacity="0.48" />
          <stop offset="0.42" stopColor="#FFFFFF" stopOpacity="0.1" />
          <stop offset="1" stopColor="#FFFFFF" stopOpacity="0" />
        </radialGradient>
        <linearGradient id={bookGradientId} x1="78" y1="154" x2="132" y2="190" gradientUnits="userSpaceOnUse">
          <stop stopColor="#FFFFFF" />
          <stop offset="0.46" stopColor="#FDF1E7" />
          <stop offset="1" stopColor="#DFC8AA" />
        </linearGradient>
        <linearGradient id={starGradientId} x1="178" y1="48" x2="194" y2="79" gradientUnits="userSpaceOnUse">
          <stop stopColor="#FFF5A3" />
          <stop offset="0.42" stopColor="#FFCF3F" />
          <stop offset="1" stopColor="#F39A19" />
        </linearGradient>
        <filter id={depthFilterId} x="24" y="39" width="172" height="166" filterUnits="userSpaceOnUse" colorInterpolationFilters="sRGB">
          <feDropShadow dx="0" dy="7" stdDeviation="5" floodColor={colors.stroke} floodOpacity="0.26" />
        </filter>
        <filter id={propFilterId} x="43" y="132" width="134" height="66" filterUnits="userSpaceOnUse" colorInterpolationFilters="sRGB">
          <feDropShadow dx="0" dy="3" stdDeviation="2.5" floodColor={colors.stroke} floodOpacity="0.24" />
        </filter>
        <filter id={eyeFilterId} x="79" y="93" width="63" height="40" filterUnits="userSpaceOnUse" colorInterpolationFilters="sRGB">
          <feDropShadow dx="0" dy="2" stdDeviation="1.4" floodColor="#071A0B" floodOpacity="0.42" />
        </filter>
      </defs>

      {/* Body: calm rounded square */}
      <path
        d="M72 49H148C167 49 179 63 179 83V148C179 168 166 181 146 181H74C54 181 41 168 41 148V83C41 63 53 49 72 49Z"
        fill={`url(#${bodyGradientId})`}
        filter={`url(#${depthFilterId})`}
      />
      <path
        d="M72 56H148C163 56 172 67 172 83V114C153 97 128 87 99 87C79 87 62 92 48 101V83C48 67 57 56 72 56Z"
        fill={`url(#${sheenGradientId})`}
        opacity="0.72"
        pointerEvents="none"
      />

      {/* Eyes: tall, calm, rounded */}
      {mood !== "celebrate" ? (
        <CalmEyes stroke={colors.stroke} filterId={eyeFilterId} />
      ) : (
        <>
          <path d="M82 112C86 102 98 102 102 112" stroke={colors.stroke} strokeWidth="9" strokeLinecap="round" />
          <path d="M118 112C122 102 134 102 138 112" stroke={colors.stroke} strokeWidth="9" strokeLinecap="round" />
        </>
      )}

      {mood === "mark" && (
        <>
          <TinySmile stroke={colors.stroke} y={145} />
          <Star cx={185} cy={62} r={16} fill={`url(#${starGradientId})`} stroke={colors.stroke} />
        </>
      )}

      {mood === "study" && (
        <>
          <TinySmile stroke={colors.stroke} y={139} />

          {/* Integrated arms create the soft toy-like depth of the 3D concept. */}
          <path
            d="M63 135C51 143 48 157 55 168C62 179 76 183 90 176L84 159C76 164 68 161 66 154C64 148 69 142 75 139Z"
            fill={`url(#${bodyGradientId})`}
            filter={`url(#${propFilterId})`}
          />
          <path
            d="M157 135C169 143 172 157 165 168C158 179 144 183 130 176L136 159C144 164 152 161 154 154C156 148 151 142 145 139Z"
            fill={`url(#${bodyGradientId})`}
            filter={`url(#${propFilterId})`}
          />

          {/* Layered open book with a raised center seam and page highlights. */}
          <g filter={`url(#${propFilterId})`}>
            <path
              d="M110 163C99 154 82 151 67 155L65 181C82 179 99 183 110 190V163Z"
              fill={`url(#${bookGradientId})`}
              stroke="#D8C5AC"
              strokeWidth="2.5"
              strokeLinejoin="round"
            />
            <path
              d="M110 163C121 154 138 151 153 155L155 181C138 179 121 183 110 190V163Z"
              fill={`url(#${bookGradientId})`}
              stroke="#D8C5AC"
              strokeWidth="2.5"
              strokeLinejoin="round"
            />
            <path d="M110 163V190" stroke="#CBB493" strokeWidth="3" strokeLinecap="round" />
            <path d="M76 160C88 158 98 161 105 166" stroke="#FFFFFF" strokeWidth="3" strokeLinecap="round" opacity="0.78" />
            <path d="M115 166C122 161 132 158 144 160" stroke="#FFFFFF" strokeWidth="3" strokeLinecap="round" opacity="0.78" />
          </g>

          {/* Small mitts overlap the page corners so the book feels held, not pasted on. */}
          <ellipse cx="73" cy="175" rx="16" ry="11" transform="rotate(16 73 175)" fill={`url(#${bodyGradientId})`} />
          <ellipse cx="147" cy="175" rx="16" ry="11" transform="rotate(-16 147 175)" fill={`url(#${bodyGradientId})`} />

          <Star cx={188} cy={66} r={15} fill={`url(#${starGradientId})`} />
          <Star cx={34} cy={106} r={9} fill="#FDF1E7" />
        </>
      )}

      {mood === "tutor" && (
        <>
          {/* Headband */}
          <path d="M58 96C58 58 162 58 162 96" stroke={colors.stroke} strokeWidth="10" strokeLinecap="round" />
          {/* Earmuffs */}
          <rect x="30" y="92" width="26" height="50" rx="13" fill={colors.body} stroke={colors.stroke} strokeWidth="9" />
          <rect x="164" y="92" width="26" height="50" rx="13" fill={colors.body} stroke={colors.stroke} strokeWidth="9" />
          {/* Mic */}
          <path d="M177 142C177 160 160 168 142 166" stroke={colors.stroke} strokeWidth="8" strokeLinecap="round" />
          <rect x="126" y="159" width="22" height="13" rx="6.5" fill={colors.stroke} />
          <Star cx={110} cy={30} r={12} fill="#FDF1E7" stroke={colors.stroke} />
        </>
      )}

      {mood === "celebrate" && (
        <>
          <TinySmile stroke={colors.stroke} y={139} />
          {/* Confetti ticks */}
          <path d="M40 44L32 32" stroke="#FE936D" strokeWidth="7" strokeLinecap="round" />
          <path d="M110 34V20" stroke="#41A0FB" strokeWidth="7" strokeLinecap="round" />
          <path d="M180 44L188 32" stroke="#FE936D" strokeWidth="7" strokeLinecap="round" />
          <Star cx={196} cy={92} r={16} fill={colors.detail} stroke={colors.stroke} />
          <Star cx={26} cy={100} r={11} fill="#FDF1E7" stroke={colors.stroke} />
        </>
      )}
    </svg>
  );
}
