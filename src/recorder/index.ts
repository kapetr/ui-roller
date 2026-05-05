import { mkdir, rm } from "node:fs/promises";
import { resolve } from "node:path";
import { Actions } from "../actions/instrumented.ts";
import { config } from "../shared/config.ts";
import { Logger } from "./logger.ts";
import { openBrowser } from "./browser.ts";
import { startScreencast } from "./screencast.ts";
import { encodeFrames } from "./encoder.ts";

type Scene = {
  run: (actions: Actions) => Promise<void>;
};

const scenes: Record<string, () => Promise<Scene>> = {
  smoke: () => import("../scenes/smoke.ts"),
  humr: () => import("../scenes/humr.ts"),
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

  await mkdir(outDir, { recursive: true });
  await rm(framesDir, { recursive: true, force: true });

  const logger = new Logger(config.viewport);
  const browser = await openBrowser();
  const actions = new Actions(browser.page, logger);

  const scene = await loader();
  console.log(`▶ recording scene: ${sceneName}`);
  const start = Date.now();

  const screencast = await startScreencast(browser.page, framesDir, {
    format: config.recording.format,
    jpegQuality: config.recording.jpegQuality,
    everyNthFrame: config.recording.everyNthFrame,
  });
  let frames;
  try {
    await scene.run(actions);
  } finally {
    frames = await screencast.stop();
    await browser.close();
    await logger.write(eventsPath);
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

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
