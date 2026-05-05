// Cubic-bezier easing. Default curve is the iOS "expensive feel" curve
// (0.32, 0.72, 0, 1) — same as Clueso/Screen Studio. The default cubic-out
// looks amateur; this is the single biggest "feel" lever in the pipeline.

export type Easing = (u: number) => number;

export function cubicBezier(
  p1x: number,
  p1y: number,
  p2x: number,
  p2y: number,
): Easing {
  // Cubic-bezier with anchors (0,0) and (1,1) and controls (p1, p2).
  // x(t) = 3(1-t)²t·p1x + 3(1-t)t²·p2x + t³
  // y(t) = 3(1-t)²t·p1y + 3(1-t)t²·p2y + t³
  // Solve x(t) = u for t via bisection, then return y(t).
  const cx = 3 * p1x;
  const bx = 3 * (p2x - p1x) - cx;
  const ax = 1 - cx - bx;
  const cy = 3 * p1y;
  const by = 3 * (p2y - p1y) - cy;
  const ay = 1 - cy - by;

  const sampleX = (t: number) => ((ax * t + bx) * t + cx) * t;
  const sampleY = (t: number) => ((ay * t + by) * t + cy) * t;

  return (u: number) => {
    if (u <= 0) return 0;
    if (u >= 1) return 1;
    let lo = 0;
    let hi = 1;
    let t = u;
    for (let i = 0; i < 24; i++) {
      const x = sampleX(t);
      if (Math.abs(x - u) < 1e-5) break;
      if (x < u) lo = t;
      else hi = t;
      t = (lo + hi) / 2;
    }
    return sampleY(t);
  };
}

export const easeMove = cubicBezier(0.32, 0.72, 0, 1);
export const easeZoom = cubicBezier(0.32, 0.72, 0, 1);
