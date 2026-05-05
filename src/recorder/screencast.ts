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

  const ext = opts.format === "png" ? "png" : "jpg";

  cdp.on("Page.screencastFrame", (params) => {
    if (stopped) return;
    const { data, sessionId, metadata } = params;
    const ts = metadata.timestamp;
    if (typeof ts !== "number") return;
    if (firstTs === null) firstTs = ts;

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
