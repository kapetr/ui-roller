// Hand-driven recorder.
//
//   pnpm record-manual <start-url>
//
// Spins up a non-headless browser at the configured viewport, injects a
// page-side hook that posts every mousemove (sampled at ~30 Hz) and
// click (with element bbox) back to Node via page.exposeBinding, and
// writes events.json + raw.mov in the same format as the scripted
// recorder. The compositor + Resolve export pipelines downstream don't
// know which mode produced the recording.
//
// Stop the recording by returning to this terminal and pressing Enter
// (or by closing the browser window).

import { mkdir, rm } from "node:fs/promises";
import { resolve } from "node:path";
import { chromium, type BrowserContext } from "playwright";
import { config } from "../shared/config.ts";
import { Logger } from "./logger.ts";
import { startScreencast, type Screencast } from "./screencast.ts";
import { encodeFrames } from "./encoder.ts";

type IncomingMove = { kind: "move"; x: number; y: number };
type IncomingClick = {
  kind: "click";
  x: number;
  y: number;
  bbox: { x: number; y: number; width: number; height: number };
  label?: string;
  target?: string;
};
type IncomingStop = { kind: "stop" };
type Incoming = IncomingMove | IncomingClick | IncomingStop;

async function main() {
  const startUrl = process.argv[2];
  if (!startUrl) {
    console.error("usage: pnpm record-manual <start-url>");
    console.error("e.g.   pnpm record-manual http://humr.localhost:4444/");
    process.exit(1);
    return;
  }

  const outDir = resolve(process.cwd(), config.outDir);
  const framesDir = resolve(outDir, ".frames");
  const rawPath = resolve(outDir, `raw.${config.recording.extension}`);
  const eventsPath = resolve(outDir, "events.json");
  const actualTimingsPath = resolve(outDir, "actual.timings.json");

  await mkdir(outDir, { recursive: true });
  await rm(framesDir, { recursive: true, force: true });

  const logger = new Logger(config.viewport, config.captureScale);

  const browser = await chromium.launch({
    headless: false,
    args: [
      "--hide-scrollbars",
      "--force-color-profile=srgb",
      `--force-device-scale-factor=${config.captureScale}`,
      "--high-dpi-support=1",
    ],
  });

  const context: BrowserContext = await browser.newContext({
    viewport: config.viewport,
    deviceScaleFactor: config.captureScale,
    colorScheme: "dark",
  });
  const page = await context.newPage();

  // Filled in once the screencast is started — used by click handler to
  // capture effectT (page-response frame time) the same way as scripted.
  let screencast: Screencast | null = null;
  let resolveStop!: () => void;
  const stopPromise = new Promise<void>((r) => {
    resolveStop = r;
  });

  await context.exposeBinding(
    "__rec",
    async (_source, raw: unknown) => {
      const e = raw as Incoming;
      if (e.kind === "stop") {
        resolveStop();
        return;
      }
      if (e.kind === "move") {
        logger.record({ kind: "move", t: logger.now(), x: e.x, y: e.y });
        return;
      }
      if (e.kind === "click") {
        const cursorArrivalT = logger.now();
        let effectT: number | undefined;
        if (screencast) {
          const responseWallMs = await Promise.race([
            screencast.nextFrame(),
            new Promise<null>((res) => setTimeout(() => res(null), 2000)),
          ]);
          if (responseWallMs !== null) effectT = logger.now();
        }
        logger.record({
          kind: "click",
          t: cursorArrivalT,
          x: e.x,
          y: e.y,
          bbox: e.bbox,
          label: e.label,
          target: e.target,
          effectT,
        });
      }
    },
  );

  // String-based initScript dodges tsx's __name() injection (which
  // breaks inside page.evaluate / addInitScript).
  await context.addInitScript(`
    (() => {
      if (window.__recHookInstalled) return;
      window.__recHookInstalled = true;
      const SAMPLE_MS = 33;
      let lastMoveTs = 0;

      document.addEventListener('mousemove', (e) => {
        const now = performance.now();
        if (now - lastMoveTs < SAMPLE_MS) return;
        lastMoveTs = now;
        const w = window;
        if (typeof w.__rec === 'function') {
          w.__rec({ kind: 'move', x: e.clientX, y: e.clientY });
        }
      }, true);

      document.addEventListener('click', (e) => {
        if (e.button !== 0) return;
        const t = e.target;
        const b = t && t.getBoundingClientRect ? t.getBoundingClientRect() : { x: e.clientX, y: e.clientY, width: 0, height: 0 };
        const label = (t && t.getAttribute && (t.getAttribute('aria-label') || t.id)) ||
                      (t && t.innerText && t.innerText.trim().slice(0, 40)) ||
                      (t && t.tagName ? t.tagName.toLowerCase() : '');
        const w = window;
        if (typeof w.__rec === 'function') {
          w.__rec({
            kind: 'click',
            x: e.clientX,
            y: e.clientY,
            bbox: { x: b.x, y: b.y, width: b.width, height: b.height },
            label,
          });
        }
      }, true);
    })();
  `);

  console.log(`▶ opening ${startUrl}`);
  await page.goto(startUrl, { waitUntil: "domcontentloaded" });

  console.log("▶ starting screencast…");
  screencast = await startScreencast(page, framesDir, {
    format: config.recording.format,
    jpegQuality: config.recording.jpegQuality,
    everyNthFrame: config.recording.everyNthFrame,
  });

  screencast.firstFrame
    .then((wallMs) => {
      const offset = logger.alignTo(wallMs);
      console.log(`  aligned logger to first frame (-${offset} ms)`);
    })
    .catch(() => {});

  // Closing the browser window is also a valid stop signal.
  browser.on("disconnected", () => resolveStop());

  console.log("");
  console.log("──────────────────────────────────────────────────");
  console.log("  RECORDING. Drive the browser through your scene.");
  console.log("  Hold for ~1 s after your last click, then close");
  console.log("  the browser window (Cmd+W, or red ✕) to stop.");
  console.log("──────────────────────────────────────────────────");
  console.log("");

  await stopPromise;

  console.log("\n▶ stopping…");
  const frames = await screencast.stop();
  if (browser.isConnected()) await browser.close().catch(() => {});
  await logger.write(eventsPath, actualTimingsPath);

  console.log(`✓ captured ${frames.length} frames`);
  console.log(`✓ wrote ${eventsPath}`);

  if (frames.length === 0) {
    console.log("(no frames — did the page render anything before stop?)");
    return;
  }

  console.log(`▶ encoding ${config.recording.codec}…`);
  const encodeStart = Date.now();
  await encodeFrames({
    frames,
    outputPath: rawPath,
    codec: config.recording.codec,
    fallbackFps: config.recording.fallbackFps,
  });
  await rm(framesDir, { recursive: true, force: true });
  console.log(
    `✓ wrote ${rawPath}  (${((Date.now() - encodeStart) / 1000).toFixed(1)}s encode)`,
  );

  console.log(
    "\nNext: pnpm assemble manual   (or whatever scene name you want to label this take as)",
  );
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
