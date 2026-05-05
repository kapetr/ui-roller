import type { Event, EventLog } from "../shared/events.ts";
import { easeMove, type Easing } from "./easing.ts";

export type Sample = { t: number; x: number; y: number };

// `eager` anchors are travel-starters: the cursor doesn't hold after them,
// it begins easing immediately to the next anchor and finishes at the next
// anchor's timestamp. The recorder emits these via `move` events at the
// instant it starts driving page.mouse — that way the gap between a move
// and the following click is the *real* travel duration (including
// IPC-induced overrun of the configured travelMs), keeping the visible
// cursor and the underlying page mouse in lockstep.
type Anchor = { t: number; x: number; y: number; eager: boolean };

// Events that anchor the cursor to a specific viewport position.
function isAnchor(e: Event): e is Extract<Event, { kind: "click" | "move" }> {
  return e.kind === "click" || e.kind === "move";
}

export type PathOptions = {
  fps: number;
  durationMs: number;
  // Time spent travelling from one anchor to the next, ms. The cursor holds
  // the previous anchor's position until (next.t - travelMs), then eases to
  // the next anchor by next.t. If the gap is smaller than travelMs, the
  // travel takes the entire gap.
  travelMs: number;
  ease?: Easing;
  // Where to park the cursor before the first anchor. "off-screen" hides it
  // until the first move/click; "first" snaps it to the first anchor's
  // position so it's already on-frame at t=0.
  preroll?: "off-screen" | "first";
  // Adds a perpendicular bow to long moves so the path looks human, not
  // laser-guided. Offset = min(distance × curveAmount, curveMaxOffset).
  curveAmount?: number;
  curveMaxOffset?: number;
  curveMinDistance?: number;
};

export type CursorPath = {
  fps: number;
  samples: Sample[];
};

export function buildCursorPath(
  log: EventLog,
  opts: PathOptions,
): CursorPath {
  const ease = opts.ease ?? easeMove;
  const anchors: Anchor[] = log.events
    .filter(isAnchor)
    .map((e) => ({ t: e.t, x: e.x, y: e.y, eager: e.kind === "move" }));

  const totalFrames = Math.max(1, Math.ceil((opts.durationMs / 1000) * opts.fps));
  const samples: Sample[] = [];

  if (anchors.length === 0) {
    // Nothing to draw — emit off-screen samples.
    for (let i = 0; i < totalFrames; i++) {
      samples.push({ t: (i / opts.fps) * 1000, x: -1e6, y: -1e6 });
    }
    return { fps: opts.fps, samples };
  }

  const preroll: Anchor =
    opts.preroll === "first"
      ? { t: 0, x: anchors[0]!.x, y: anchors[0]!.y, eager: false }
      : { t: 0, x: -1e6, y: -1e6, eager: false };

  // Insert a synthetic anchor at t=0 if the first real anchor is later.
  const all: Anchor[] =
    anchors[0]!.t > 0 ? [preroll, ...anchors] : anchors;

  let cursor = 0;
  for (let i = 0; i < totalFrames; i++) {
    const t = (i / opts.fps) * 1000;

    while (cursor + 1 < all.length && all[cursor + 1]!.t <= t) cursor++;

    const prev = all[cursor]!;
    const next = all[cursor + 1];

    if (!next) {
      samples.push({ t, x: prev.x, y: prev.y });
      continue;
    }

    const gap = next.t - prev.t;
    // Eager anchor (move event) → travel the *full* gap so the visible
    // cursor stays in lockstep with the underlying page mouse, even when
    // IPC overhead made the actual travel longer than the configured
    // travelMs. Otherwise (click→click without a move marker) keep the
    // hold-then-ease behaviour so long page-load gaps don't crawl.
    const travel = prev.eager ? gap : Math.min(opts.travelMs, gap);
    const travelStart = next.t - travel;

    if (t < travelStart) {
      samples.push({ t, x: prev.x, y: prev.y });
    } else {
      const u = travel <= 0 ? 1 : (t - travelStart) / travel;
      const k = ease(Math.max(0, Math.min(1, u)));
      samples.push({ t, ...interpolatePosition(prev, next, k, opts) });
    }
  }

  return { fps: opts.fps, samples };
}

export type CurveOptions = {
  curveAmount?: number;
  curveMaxOffset?: number;
  curveMinDistance?: number;
};

// Position along an eased segment. Identical maths used by the recorder
// to drive page.mouse so the underlying hover state tracks the visible
// cursor exactly.
export function interpolatePosition(
  p0: { x: number; y: number },
  p1: { x: number; y: number },
  k: number,
  opts: CurveOptions = {},
): { x: number; y: number } {
  const dx = p1.x - p0.x;
  const dy = p1.y - p0.y;
  const dist = Math.hypot(dx, dy);
  const curveAmount = opts.curveAmount ?? 0;
  const minDist = opts.curveMinDistance ?? 200;

  if (curveAmount <= 0 || dist < minDist) {
    return { x: p0.x + dx * k, y: p0.y + dy * k };
  }

  // Quadratic bezier with a control point offset perpendicular to the
  // motion. Side alternates by a deterministic seed so adjacent segments
  // bow opposite ways — looks more like a wandering hand than a fixed bias.
  const maxOff = opts.curveMaxOffset ?? Infinity;
  const offset = Math.min(dist * curveAmount, maxOff);
  const seed = (Math.floor(p0.x) ^ Math.floor(p1.y)) & 1;
  const sign = seed === 0 ? 1 : -1;
  // Perpendicular unit vector (rotate 90° counterclockwise in screen coords).
  const perpX = -dy / dist;
  const perpY = dx / dist;
  const cx = (p0.x + p1.x) / 2 + perpX * offset * sign;
  const cy = (p0.y + p1.y) / 2 + perpY * offset * sign;
  const omk = 1 - k;
  return {
    x: omk * omk * p0.x + 2 * omk * k * cx + k * k * p1.x,
    y: omk * omk * p0.y + 2 * omk * k * cy + k * k * p1.y,
  };
}
