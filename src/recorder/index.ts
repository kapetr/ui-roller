import { mkdir, readFile, rm } from "node:fs/promises";
import { resolve } from "node:path";
import { Actions } from "../actions/instrumented.ts";
import { config } from "../shared/config.ts";
import type { SpeechTimings } from "../shared/events.ts";
import { Logger } from "./logger.ts";
import { openBrowser } from "./browser.ts";
import { startScreencast } from "./screencast.ts";
import { encodeFrames } from "./encoder.ts";

// Optional metadata a scene module may export to drive cue-aware recording.
type SceneMeta = {
  // Path to a TTS timings.json (relative to repo root). When set, cue names
  // referenced by actions are resolved from this file.
  timingsPath?: string;
};

type Scene = {
  run: (actions: Actions) => Promise<void>;
  meta?: SceneMeta;
};

const scenes: Record<string, () => Promise<Scene>> = {
  smoke: () => import("../scenes/smoke.ts"),
  humr: () => import("../scenes/humr.ts"),
  "meet-dam": () => import("../scenes/meet-dam.ts"),
};

async function main() {
  const sceneName = process.argv[2];
  if (!sceneName) {
    console.error("usage: pnpm record <scene>");
    console.error(`scenes: ${Object.keys(scenes).join(", ")}`);
    process.exit(1);
    return;
  }
  const loader = scenes[sceneName];
  if (!loader) {
    console.error(`unknown scene: ${sceneName}`);
    console.error(`scenes: ${Object.keys(scenes).join(", ")}`);
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

  const scene = await loader();
  const cues = scene.meta?.timingsPath
    ? await loadCues(resolve(process.cwd(), scene.meta.timingsPath))
    : [];
  if (cues.length > 0) {
    console.log(`  loaded ${cues.length} cues from ${scene.meta!.timingsPath}`);
  }

  const logger = new Logger(config.viewport, config.captureScale, cues);
  const browser = await openBrowser();

  console.log(`▶ recording scene: ${sceneName}`);
  const start = Date.now();

  const screencast = await startScreencast(browser.page, framesDir, {
    format: config.recording.format,
    jpegQuality: config.recording.jpegQuality,
    everyNthFrame: config.recording.everyNthFrame,
  });

  // Construct Actions after the screencast so we can hand it the
  // frame-waiter for click-effect timing (next screencast frame after
  // mouse.click = the page's actual visual response).
  const actions = new Actions(browser.page, logger, {
    nextFrame: () => screencast.nextFrame(),
  });

  // The video's t=0 is the first screencast frame, not the moment we
  // constructed the logger. Re-zero the logger as soon as that frame
  // arrives so events.json times match video frame times exactly.
  // Without this, every event reads ~300 ms ahead of the visual it
  // describes (logger started before browser launch + first paint).
  screencast.firstFrame
    .then((wallMs) => {
      const offset = logger.alignTo(wallMs);
      console.log(`  aligned logger to first frame (-${offset} ms)`);
    })
    .catch(() => {});

  let frames;
  try {
    await scene.run(actions);
  } finally {
    frames = await screencast.stop();
    await browser.close();
    await logger.write(eventsPath, actualTimingsPath);
  }

  const captureMs = Date.now() - start;
  console.log(
    `✓ captured ${frames.length} frames in ${(captureMs / 1000).toFixed(1)}s`,
  );

  console.log(`▶ encoding ${config.recording.codec}…`);
  const encodeStart = Date.now();
  await encodeFrames({
    frames,
    outputPath: rawPath,
    codec: config.recording.codec,
    fallbackFps: config.recording.fallbackFps,
  });
  await rm(framesDir, { recursive: true, force: true });

  const encodeMs = Date.now() - encodeStart;
  console.log(`✓ wrote ${rawPath}  (${(encodeMs / 1000).toFixed(1)}s encode)`);
  console.log(`✓ wrote ${eventsPath}`);
}

async function loadCues(path: string) {
  try {
    const raw = await readFile(path, "utf8");
    const timings = JSON.parse(raw) as SpeechTimings;
    return timings.cues ?? [];
  } catch (err) {
    throw new Error(
      `failed to load timings file at ${path}: ${(err as Error).message}`,
    );
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
