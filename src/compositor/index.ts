import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { spawn } from "node:child_process";
import { config } from "../shared/config.ts";
import type { EventLog } from "../shared/events.ts";
import { buildCursorPath } from "./cursor-path.ts";
import { loadCursorSprite, streamCursorFrames } from "./cursor.ts";
import { spawnCursorEncoder, compositeFinal } from "./ffmpeg.ts";

async function main() {
  const sceneName = process.argv[2];
  if (!sceneName) {
    console.error("usage: pnpm assemble <scene>");
    process.exit(1);
    return;
  }

  const outDir = resolve(process.cwd(), config.outDir);
  const rawPath = resolve(outDir, `raw.${config.recording.extension}`);
  const eventsPath = resolve(outDir, "events.json");
  const cursorPath = resolve(outDir, "cursor.mov");
  const finalPath = resolve(outDir, `final.${config.compositor.finalExtension}`);

  const log: EventLog = JSON.parse(await readFile(eventsPath, "utf8"));
  const durationMs = await probeDurationMs(rawPath);
  const captureScale = log.captureScale ?? 1;
  const frame = {
    width: log.viewport.width * captureScale,
    height: log.viewport.height * captureScale,
  };

  console.log(`▶ assembling scene: ${sceneName}`);
  console.log(`  raw duration: ${(durationMs / 1000).toFixed(2)}s`);
  console.log(`  events: ${log.events.length}`);
  console.log(`  layout: ${log.viewport.width}×${log.viewport.height} CSS, capture: ${frame.width}×${frame.height} (×${captureScale})`);

  const path = buildCursorPath(log, {
    fps: config.compositor.fps,
    durationMs: durationMs + 100, // small tail so overlay never short-stops
    travelMs: config.compositor.cursor.travelMs,
    preroll: config.compositor.cursor.preroll,
    curveAmount: config.compositor.cursor.curveAmount,
    curveMaxOffset: config.compositor.cursor.curveMaxOffsetCss,
    curveMinDistance: config.compositor.cursor.curveMinDistanceCss,
  });

  // Sprite is sized in frame pixels: CSS-fraction × CSS viewport × capture scale.
  const spriteFramePx = Math.round(
    log.viewport.width * config.compositor.cursor.spriteCssFraction * captureScale,
  );
  const sprite = await loadCursorSprite({ width: spriteFramePx });
  console.log(`  cursor sprite: ${sprite.width}×${sprite.height}px, hotpoint=(${sprite.hotpoint.x},${sprite.hotpoint.y})`);

  console.log(`▶ rendering ${path.samples.length} cursor frames @ ${path.fps}fps…`);
  const renderStart = Date.now();
  const ff = spawnCursorEncoder({
    width: frame.width,
    height: frame.height,
    fps: path.fps,
    outputPath: cursorPath,
  });
  const ffStderr = collect(ff.stderr!);
  const ffDone = waitClose(ff);

  if (!ff.stdin) throw new Error("ffmpeg stdin missing");
  await streamCursorFrames({
    path,
    sprite,
    frame,
    captureScale,
    out: ff.stdin,
  });
  ff.stdin.end();
  const code = await ffDone;
  if (code !== 0) {
    throw new Error(`cursor ffmpeg exited ${code}\n${(await ffStderr).slice(-2000)}`);
  }
  console.log(`✓ wrote ${cursorPath} (${((Date.now() - renderStart) / 1000).toFixed(1)}s)`);

  console.log(`▶ compositing final…`);
  const compStart = Date.now();
  await compositeFinal({
    basePath: rawPath,
    cursorPath,
    outputPath: finalPath,
    fps: config.compositor.fps,
    finalCodec: config.compositor.finalCodec,
  });
  console.log(`✓ wrote ${finalPath} (${((Date.now() - compStart) / 1000).toFixed(1)}s)`);
}

async function probeDurationMs(path: string): Promise<number> {
  return new Promise((resolveP, reject) => {
    const proc = spawn("ffprobe", [
      "-v", "error",
      "-select_streams", "v:0",
      "-show_entries", "format=duration",
      "-of", "default=nw=1:nk=1",
      path,
    ], { stdio: ["ignore", "pipe", "pipe"] });
    let out = "";
    let err = "";
    proc.stdout.on("data", (b: Buffer) => (out += b.toString()));
    proc.stderr.on("data", (b: Buffer) => (err += b.toString()));
    proc.on("error", reject);
    proc.on("close", (code) => {
      if (code !== 0) return reject(new Error(`ffprobe exited ${code}\n${err}`));
      const seconds = parseFloat(out.trim());
      if (!Number.isFinite(seconds)) return reject(new Error(`bad duration: ${out}`));
      resolveP(seconds * 1000);
    });
  });
}

function collect(stream: NodeJS.ReadableStream): Promise<string> {
  return new Promise((resolveP) => {
    let buf = "";
    stream.on("data", (chunk: Buffer) => (buf += chunk.toString()));
    stream.on("end", () => resolveP(buf));
    stream.on("close", () => resolveP(buf));
  });
}

function waitClose(proc: import("node:child_process").ChildProcess): Promise<number> {
  return new Promise((resolveP, reject) => {
    proc.on("error", reject);
    proc.on("close", (code) => resolveP(code ?? -1));
  });
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
