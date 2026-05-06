import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import type { Page } from "playwright";

export type Frame = {
  index: number;
  path: string;
  timestamp: number; // seconds, normalized to first frame at 0
};

export type Screencast = {
  stop: () => Promise<Frame[]>;
  // Resolves with Date.now() at the moment the first screencast frame
  // arrives in Node. Use this to align the logger clock with the video
  // clock — Logger starts at construction (before browser launch + first
  // navigate + first paint) so its zero is offset from the video's zero.
  firstFrame: Promise<number>;
  // Resolves with Date.now() of the next screencast frame to arrive
  // after this method is called. Used by Actions.click to time click
  // effects to the page's actual visual response (the page only emits
  // a screencast frame when it repaints — busy pages can lag the click
  // dispatch by hundreds of ms while the response renders).
  nextFrame: () => Promise<number>;
};

export type ScreencastOptions = {
  /** "png" = lossless. "jpeg" with quality=100 ≈ visually lossless and smaller. */
  format: "png" | "jpeg";
  /** JPEG quality (1–100). Ignored for PNG. */
  jpegQuality: number;
  /** 1 = every browser frame, 2 = every other, etc. Use 1 for max smoothness. */
  everyNthFrame: number;
};

export async function startScreencast(
  page: Page,
  framesDir: string,
  opts: ScreencastOptions,
): Promise<Screencast> {
  await mkdir(framesDir, { recursive: true });
  const cdp = await page.context().newCDPSession(page);
  const frames: Frame[] = [];
  const writes: Promise<void>[] = [];
  let firstTs: number | null = null;
  let stopped = false;

  let resolveFirstFrame!: (wallMs: number) => void;
  const firstFrame = new Promise<number>((r) => (resolveFirstFrame = r));
  const frameWaiters: Array<(wallMs: number) => void> = [];

  const ext = opts.format === "png" ? "png" : "jpg";

  cdp.on("Page.screencastFrame", (params) => {
    if (stopped) return;
    const { data, sessionId, metadata } = params;
    const ts = metadata.timestamp;
    if (typeof ts !== "number") return;
    const wallNow = Date.now();
    if (firstTs === null) {
      firstTs = ts;
      resolveFirstFrame(wallNow);
    }
    if (frameWaiters.length > 0) {
      const ws = frameWaiters.splice(0);
      for (const w of ws) w(wallNow);
    }

    const index = frames.length;
    const path = join(
      framesDir,
      `${index.toString().padStart(6, "0")}.${ext}`,
    );
    frames.push({ index, path, timestamp: ts - firstTs });
    writes.push(writeFile(path, Buffer.from(data, "base64")));

    cdp.send("Page.screencastFrameAck", { sessionId }).catch(() => {
      // session may close mid-shutdown
    });
  });

  await cdp.send("Page.startScreencast", {
    format: opts.format,
    ...(opts.format === "jpeg" ? { quality: opts.jpegQuality } : {}),
    everyNthFrame: opts.everyNthFrame,
    // Cap large enough to never downscale; CDP still emits at viewport size.
    maxWidth: 16384,
    maxHeight: 16384,
  });

  return {
    firstFrame,
    nextFrame: () =>
      new Promise<number>((resolve) => frameWaiters.push(resolve)),
    async stop() {
      stopped = true;
      try {
        await cdp.send("Page.stopScreencast");
      } catch {
        // ignore
      }
      await Promise.all(writes);
      try {
        await cdp.detach();
      } catch {
        // ignore
      }
      return frames;
    },
  };
}
