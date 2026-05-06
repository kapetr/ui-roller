import type { Codec } from "../recorder/encoder.ts";

export const config = {
  // Layout viewport, in CSS pixels. The page lays out at this size — pick
  // it based on how big you want UI elements to look on the final video.
  viewport: { width: 1920, height: 1080 },
  // Capture multiplier. Combined with Chromium's --force-device-scale-factor,
  // CDP screencast emits frames at viewport × captureScale (verified empirically).
  // 2 = retina-grade headroom for the compositor's zoom-in effects without
  // softening pixels. 1 = layout == capture (small file, no zoom headroom).
  captureScale: 2,
  baseUrl: "http://humr.localhost:4444",
  typing: {
    delayMs: 50,
    jitterMs: 20,
  },
  outDir: "out",
  recording: {
    codec: "prores-hq" as Codec,
    extension: "mov",
    // Trailing/idle frame duration in encoder.
    fallbackFps: 30,
    // png = lossless. jpeg q=100 = visually identical, smaller frames.
    format: "jpeg" as "png" | "jpeg",
    jpegQuality: 100,
    // 1 = every browser-rendered frame; raise to subsample if rate is too high.
    everyNthFrame: 1,
  },
  compositor: {
    // Output frame rate for cursor track and final video.
    fps: 30,
    finalCodec: "h264-hq" as "h264-hq" | "prores-hq",
    finalExtension: "mp4" as "mp4" | "mov",
    cursor: {
      // Sprite size as a fraction of the LAYOUT (CSS) viewport width.
      // 0.018 ≈ 35 CSS px @ 1920 → 70 frame px @ captureScale=2.
      spriteCssFraction: 0.018,
      // Cubic-bezier coefficients for the move curve. (0,0,1,1) = linear —
      // constant velocity, no ease in or out. Feels mechanical compared to
      // softened curves, but plays back fast and predictable. Tune later if
      // the linear feel reads as robotic on the final video.
      easeBezier: [0, 0, 1, 1] as readonly [number, number, number, number],
      // Time spent travelling between consecutive anchors (target wall-clock).
      // Page-busy beats can stretch this beyond the configured value because
      // Chromium serialises mouse events behind hover repaints — the
      // compositor uses the actual gap, so the visible cursor stays in sync.
      travelMs: 400,
      // Curve the path on long moves so it feels human, not laser-guided.
      // 0 = always linear. 0.06 = subtle perpendicular bow; 0.12 = obvious arc.
      curveAmount: 0.06,
      curveMaxOffsetCss: 60,
      // Below this CSS-pixel threshold, paths stay linear (small moves
      // shouldn't curve, it looks twitchy).
      curveMinDistanceCss: 220,
      preroll: "first" as "off-screen" | "first",
    },
  },
} as const;
