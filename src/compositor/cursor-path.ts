import type { Event, EventLog } from "../shared/events.ts";
import { easeMove, type Easing } from "./easing.ts";

export type Sample = { t: number; x: number; y: number };

type Anchor = { t: number; x: number; y: number };

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
    .map((e) => ({ t: e.t, x: e.x, y: e.y }));

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
      ? { t: 0, x: anchors[0]!.x, y: anchors[0]!.y }
      : { t: 0, x: -1e6, y: -1e6 };

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
    const travel = Math.min(opts.travelMs, gap);
    const travelStart = next.t - travel;

    if (t < travelStart) {
      samples.push({ t, x: prev.x, y: prev.y });
    } else {
      const u = travel <= 0 ? 1 : (t - travelStart) / travel;
      const k = ease(Math.max(0, Math.min(1, u)));
      samples.push({
        t,
        x: prev.x + (next.x - prev.x) * k,
        y: prev.y + (next.y - prev.y) * k,
      });
    }
  }

  return { fps: opts.fps, samples };
}
