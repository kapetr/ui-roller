import type { Codec } from "../recorder/encoder.ts";

export const config = {
  // Capture resolution = viewport size (CDP screencast emits at viewport).
  // App lays out at this size — most modern web apps are responsive.
  // 2560×1440 (2K / QHD) gives 1.33× linear headroom over 1080p output.
  // Bump to 3840×2160 for 2× headroom; some apps may not lay out cleanly at 4K.
  viewport: { width: 2560, height: 1440 },
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
} as const;
