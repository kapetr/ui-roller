// Hand-driven recorder.
//
//   pnpm record-manual <start-url> [--run <slug>]
//                                  [--audio path/to/narration.mp3]
//                                  [--audio-delay-ms 5000]
//
// Spins up a non-headless browser at the configured viewport, injects a
// page-side hook that posts every mousemove (sampled at ~30 Hz) and
// click (with element bbox) back to Node via page.exposeBinding, and
// writes events.json + raw.mov in the same format as the scripted
// recorder. The compositor + Resolve export pipelines downstream don't
// know which mode produced the recording.
//
// --run:             slug of a per-run folder under runs/. Outputs land
//                    in runs/<slug>/. If absent, falls back to config.outDir
//                    (default "out/").
// --audio:           macOS-only (afplay). Plays the file through the
//                    system audio so the operator can pace clicks to
//                    narration. The audio is NOT captured into the
//                    recording — events.json records the start offset
//                    so Resolve can place the clip at the right moment.
//                    With --run and no --audio, defaults to
//                    runs/<slug>/speech.mp3 if it exists.
// --audio-delay-ms:  delay between first screencast frame and audio
//                    start, ms. Default 5000 (5 s prep window).
//
// Stop the recording by closing the browser window.

import { spawn, type ChildProcess } from "node:child_process";
import { existsSync } from "node:fs";
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

function parseArgs() {
  const args = process.argv.slice(2);
  let startUrl: string | undefined;
  let audioPath: string | undefined;
  let audioDelayMs = 5000;
  let run: string | undefined;

  for (let i = 0; i < args.length; i++) {
    const a = args[i]!;
    if (a === "--audio") {
      audioPath = args[++i];
    } else if (a === "--audio-delay-ms") {
      audioDelayMs = parseInt(args[++i] ?? "", 10);
    } else if (a === "--run") {
      run = args[++i];
    } else if (!a.startsWith("--") && !startUrl) {
      startUrl = a;
    }
  }
  return { startUrl, audioPath, audioDelayMs, run };
}

async function main() {
  const { startUrl, audioPath, audioDelayMs, run } = parseArgs();
  if (!startUrl) {
    console.error("usage: pnpm record-manual <start-url> [--run <slug>] [--audio path] [--audio-delay-ms 5000]");
    console.error("e.g.   pnpm record-manual https://example.com/ --run myfeature");
    process.exit(1);
    return;
  }

  const outDir = run
    ? resolve(process.cwd(), "runs", run)
    : resolve(process.cwd(), config.outDir);

  // Audio resolution: explicit --audio wins; else with --run, default to
  // runs/<slug>/speech.mp3 if present; else no audio.
  let audioAbs: string | undefined;
  if (audioPath) {
    audioAbs = resolve(audioPath);
  } else if (run) {
    const candidate = resolve(outDir, "speech.mp3");
    if (existsSync(candidate)) audioAbs = candidate;
  }
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

  // Track main-frame URL changes. Each entry becomes a navigate event
  // in events.json, which lets downstream tools (proposal applier,
  // future heuristics) tell page-changing clicks apart from in-place
  // state changes. Subframes are ignored — they're noise for our use.
  let lastUrl: string | null = null;
  page.on("framenavigated", (frame) => {
    if (frame !== page.mainFrame()) return;
    const url = frame.url();
    // Skip blank/about: URLs and consecutive duplicates (Playwright
    // sometimes fires the event twice for the same URL during redirects).
    if (!url || url === "about:blank" || url === lastUrl) return;
    lastUrl = url;
    logger.record({ kind: "navigate", t: logger.now(), url });
  });

  console.log(`▶ opening ${startUrl}`);
  await page.goto(startUrl, { waitUntil: "domcontentloaded" });

  console.log("▶ starting screencast…");
  screencast = await startScreencast(page, framesDir, {
    format: config.recording.format,
    jpegQuality: config.recording.jpegQuality,
    everyNthFrame: config.recording.everyNthFrame,
  });

  // Audio playback bookkeeping. afplay is macOS-built-in; on other
  // platforms swap or skip — caller can always run the audio externally.
  const audioState: { proc: ChildProcess | null; timer: NodeJS.Timeout | null } = {
    proc: null,
    timer: null,
  };

  screencast.firstFrame
    .then((wallMs) => {
      const offset = logger.alignTo(wallMs);
      console.log(`  aligned logger to first frame (-${offset} ms)`);

      if (audioAbs) {
        console.log(`  audio scheduled in ${audioDelayMs} ms: ${audioAbs}`);
        audioState.timer = setTimeout(() => {
          const startedAtMs = logger.now();
          console.log(`▶ playing audio (logger t=${startedAtMs} ms)`);
          const proc = spawn("afplay", [audioAbs], { stdio: "ignore" });
          audioState.proc = proc;
          proc.on("close", () => {
            console.log("  audio finished");
            audioState.proc = null;
          });
          proc.on("error", (err) => {
            console.error(`  audio error: ${err.message}`);
            audioState.proc = null;
          });
          logger.setAudio(audioAbs, startedAtMs);
        }, audioDelayMs);
      }
    })
    .catch(() => {});

  // Stop signals. Ideally browser.on("disconnected") fires when the
  // user closes the window — but on macOS Chromium often keeps the
  // process alive after Cmd+W / red ✕, so listen on every layer
  // (page, context, browser) plus SIGINT for terminal-side abort.
  // resolveStop is idempotent; whichever fires first wins.
  page.on("close", () => resolveStop());
  context.on("close", () => resolveStop());
  browser.on("disconnected", () => resolveStop());
  process.on("SIGINT", () => {
    console.log("\n(ctrl-c received, stopping)");
    resolveStop();
  });

  console.log("");
  console.log("──────────────────────────────────────────────────");
  console.log("  RECORDING. Drive the browser through your scene.");
  if (audioAbs) {
    console.log(`  Narration plays in ~${audioDelayMs / 1000}s — pace your`);
    console.log("  clicks to it. Hold for ~1 s after your last click,");
  } else {
    console.log("  Hold for ~1 s after your last click,");
  }
  console.log("  then close the browser window (Cmd+W or red ✕).");
  console.log("──────────────────────────────────────────────────");
  console.log("");

  await stopPromise;

  console.log("\n▶ stopping…");
  if (audioState.timer) clearTimeout(audioState.timer);
  if (audioState.proc && !audioState.proc.killed) {
    try { audioState.proc.kill(); } catch { /* ignore */ }
  }
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
    `\nNext: pnpm assemble ${run ? `--run ${run}` : "<scene-label>"}`,
  );
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
