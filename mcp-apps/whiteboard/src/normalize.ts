/** Fill required Excalidraw fields so LLM-ish partial elements still render. */

let _nonce = 1;

export function normalizeElement(
  raw: unknown,
  index: number,
): Record<string, unknown> | null {
  if (!raw || typeof raw !== "object") return null;
  const el = raw as Record<string, unknown>;
  const type = typeof el.type === "string" ? el.type : "rectangle";
  const id = typeof el.id === "string" ? el.id : `el_${index}_${_nonce++}`;
  const base: Record<string, unknown> = {
    type,
    id,
    x: Number(el.x) || 0,
    y: Number(el.y) || 0,
    width: Number(el.width) || (type === "text" ? 120 : 100),
    height: Number(el.height) || (type === "text" ? 40 : 80),
    angle: Number(el.angle) || 0,
    strokeColor: typeof el.strokeColor === "string" ? el.strokeColor : "#1e1e1e",
    backgroundColor:
      typeof el.backgroundColor === "string" ? el.backgroundColor : "transparent",
    fillStyle: typeof el.fillStyle === "string" ? el.fillStyle : "solid",
    strokeWidth: Number(el.strokeWidth) || 2,
    strokeStyle: typeof el.strokeStyle === "string" ? el.strokeStyle : "solid",
    roughness: el.roughness == null ? 1 : Number(el.roughness),
    opacity: el.opacity == null ? 100 : Number(el.opacity),
    groupIds: Array.isArray(el.groupIds) ? el.groupIds : [],
    frameId: el.frameId ?? null,
    roundness: el.roundness ?? (type === "rectangle" ? { type: 3 } : null),
    seed: typeof el.seed === "number" ? el.seed : Math.floor(Math.random() * 2 ** 31),
    version: typeof el.version === "number" ? el.version : 1,
    versionNonce: typeof el.versionNonce === "number" ? el.versionNonce : _nonce++,
    isDeleted: Boolean(el.isDeleted),
    boundElements: Array.isArray(el.boundElements) ? el.boundElements : null,
    updated: typeof el.updated === "number" ? el.updated : Date.now(),
    link: el.link ?? null,
    locked: Boolean(el.locked),
  };

  if (type === "text") {
    base.text = typeof el.text === "string" ? el.text : "";
    base.fontSize = Number(el.fontSize) || 20;
    base.fontFamily = Number(el.fontFamily) || 1;
    base.textAlign = typeof el.textAlign === "string" ? el.textAlign : "left";
    base.verticalAlign =
      typeof el.verticalAlign === "string" ? el.verticalAlign : "top";
    base.containerId = el.containerId ?? null;
    base.originalText =
      typeof el.originalText === "string" ? el.originalText : base.text;
    base.lineHeight = Number(el.lineHeight) || 1.25;
    base.autoResize = el.autoResize !== false;
  }

  if (type === "arrow" || type === "line") {
    const pts = Array.isArray(el.points)
      ? el.points
      : [[0, 0], [Number(el.width) || 100, 0]];
    base.points = pts;
    base.lastCommittedPoint = null;
    base.startBinding = el.startBinding ?? null;
    base.endBinding = el.endBinding ?? null;
    base.startArrowhead = el.startArrowhead ?? null;
    base.endArrowhead =
      type === "arrow" ? (el.endArrowhead ?? "arrow") : (el.endArrowhead ?? null);
  }

  if (type === "freedraw") {
    base.points = Array.isArray(el.points) ? el.points : [];
    base.pressures = Array.isArray(el.pressures) ? el.pressures : [];
    base.simulatePressure = el.simulatePressure !== false;
  }

  return base;
}

export function normalizeElements(raw: unknown): unknown[] {
  if (!Array.isArray(raw)) return [];
  const out: unknown[] = [];
  raw.forEach((el, i) => {
    const n = normalizeElement(el, i);
    if (n) out.push(n);
  });
  return out;
}
