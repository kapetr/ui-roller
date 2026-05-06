import type { Writable } from "node:stream";
import type { EventLog } from "../shared/events.ts";
import { bezierFromTuple, type BezierTuple, type Easing } from "./easing.ts";

export type Ring = {
  cx: number; // frame px
  cy: number; // frame px
  centerRadius: number; // frame px
  halfThickness: number; // frame px
  alpha: number; // 0-1
  color: readonly [number, number, number]; // 0-255
};

export type ClickEffectFrame = {
  t: number; // ms, video time
  rings: Ring[];
};

export type ClickEffectsOptions = {
  fps: number;
  durationMs: number;
  // Total scene duration so we emit enough frames.
  totalDurationMs: number;
  // Multiplier from CSS coords → frame px.
  captureScale: number;
  effectDurationMs: number;
  peakRadiusCss: number;
  strokeCss: number;
  color: readonly [number, number, number];
  peakAlpha: number;
  ease: BezierTuple;
};

export type ClickEffectsTimeline = {
  fps: number;
  frames: ClickEffectFrame[];
};

// Build a per-video-frame list of currently active click rings, ready
// for the renderer to blit into RGBA frames. One ring per click event
// per frame the click is active in.
export function buildClickEffectsTimeline(
  log: EventLog,
  opts: ClickEffectsOptions,
): ClickEffectsTimeline {
  const ease: Easing = bezierFromTuple(opts.ease);
  const clicks = log.events
    .filter((e): e is Extract<EventLog["events"][number], { kind: "click" }> => e.kind === "click")
    .map((e) => ({
      // Prefer effectT (page's first repaint after click) so the ring
      // lands on the visual response frame, not the click-dispatch
      // frame. Falls back to t when effectT is missing (older logs or
      // Actions constructed without a frame waiter).
      t: e.effectT ?? e.t,
      cx: e.x * opts.captureScale,
      cy: e.y * opts.captureScale,
    }));

  const peakRadius = opts.peakRadiusCss * opts.captureScale;
  const halfThickness = (opts.strokeCss * opts.captureScale) / 2;
  const totalFrames = Math.max(1, Math.ceil((opts.totalDurationMs / 1000) * opts.fps));
  const frames: ClickEffectFrame[] = [];

  for (let i = 0; i < totalFrames; i++) {
    const t = (i / opts.fps) * 1000;
    const rings: Ring[] = [];
    for (const click of clicks) {
      const elapsed = t - click.t;
      if (elapsed < 0 || elapsed >= opts.effectDurationMs) continue;
      const u = elapsed / opts.effectDurationMs;
      const k = ease(u);
      rings.push({
        cx: click.cx,
        cy: click.cy,
        centerRadius: k * peakRadius,
        halfThickness,
        alpha: opts.peakAlpha * (1 - k),
        color: opts.color,
      });
    }
    frames.push({ t, rings });
  }

  return { fps: opts.fps, frames };
}

export type RenderClickEffectsOptions = {
  timeline: ClickEffectsTimeline;
  frame: { width: number; height: number };
  out: Writable;
};

// Stream raw RGBA frames into ffmpeg stdin. We allocate a single working
// buffer and clear only the regions touched by rings each frame to keep
// per-frame cost proportional to ring area, not viewport area.
export async function streamClickEffectFrames(
  opts: RenderClickEffectsOptions,
): Promise<number> {
  const { timeline, frame: dim, out } = opts;
  const stride = dim.width * 4;
  const buf = Buffer.alloc(dim.width * dim.height * 4);

  let dirty: { x: number; y: number; w: number; h: number }[] = [];
  let frameCount = 0;

  for (const f of timeline.frames) {
    // Clear last frame's dirty regions only.
    for (const r of dirty) clearRegion(buf, stride, r);
    dirty = [];

    for (const ring of f.rings) {
      const region = drawRing(buf, stride, dim, ring);
      if (region) dirty.push(region);
    }

    if (!out.write(buf)) {
      await once(out, "drain");
    }
    frameCount++;
  }

  return frameCount;
}

function clearRegion(
  buf: Buffer,
  stride: number,
  box: { x: number; y: number; w: number; h: number },
) {
  for (let row = 0; row < box.h; row++) {
    const off = (box.y + row) * stride + box.x * 4;
    buf.fill(0, off, off + box.w * 4);
  }
}

// Draw an antialiased annulus into buf. Returns the dirty bbox so we
// can clear it next frame, or null if the ring is fully off-screen.
function drawRing(
  buf: Buffer,
  stride: number,
  dim: { width: number; height: number },
  ring: Ring,
): { x: number; y: number; w: number; h: number } | null {
  const outerR = ring.centerRadius + ring.halfThickness;
  if (outerR <= 0 || ring.alpha <= 0) return null;

  const innerR = Math.max(0, ring.centerRadius - ring.halfThickness);
  const minX = Math.max(0, Math.floor(ring.cx - outerR - 1));
  const maxX = Math.min(dim.width - 1, Math.ceil(ring.cx + outerR + 1));
  const minY = Math.max(0, Math.floor(ring.cy - outerR - 1));
  const maxY = Math.min(dim.height - 1, Math.ceil(ring.cy + outerR + 1));
  if (minX > maxX || minY > maxY) return null;

  const innerRSq = innerR * innerR;
  const outerRSq = outerR * outerR;
  const [cr, cg, cb] = ring.color;

  for (let y = minY; y <= maxY; y++) {
    for (let x = minX; x <= maxX; x++) {
      const dx = x + 0.5 - ring.cx;
      const dy = y + 0.5 - ring.cy;
      const dSq = dx * dx + dy * dy;
      if (dSq > outerRSq) continue;
      if (dSq < innerRSq) continue;

      // Coverage = 1 in the band's interior, ramps to 0 within 1 px of
      // either edge for cheap antialiasing.
      const dist = Math.sqrt(dSq);
      const fromInner = dist - innerR;
      const fromOuter = outerR - dist;
      const coverage = Math.min(1, fromInner, fromOuter);
      if (coverage <= 0) continue;

      const a = ring.alpha * coverage;
      const off = y * stride + x * 4;
      const dstA = buf[off + 3]! / 255;
      const outA = a + dstA * (1 - a);
      if (outA <= 0) continue;
      const inv = 1 / outA;
      buf[off] = Math.round((cr * a + buf[off]! * dstA * (1 - a)) * inv);
      buf[off + 1] = Math.round(
        (cg * a + buf[off + 1]! * dstA * (1 - a)) * inv,
      );
      buf[off + 2] = Math.round(
        (cb * a + buf[off + 2]! * dstA * (1 - a)) * inv,
      );
      buf[off + 3] = Math.round(outA * 255);
    }
  }

  const x0 = Math.max(0, Math.floor(ring.cx - outerR));
  const y0 = Math.max(0, Math.floor(ring.cy - outerR));
  const x1 = Math.min(dim.width, Math.ceil(ring.cx + outerR));
  const y1 = Math.min(dim.height, Math.ceil(ring.cy + outerR));
  return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
}

function once(emitter: Writable, event: "drain"): Promise<void> {
  return new Promise((resolve) => emitter.once(event, () => resolve()));
}
