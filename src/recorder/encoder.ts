import { spawn } from "node:child_process";
import { writeFile, rm } from "node:fs/promises";
import { dirname, join } from "node:path";
import type { Frame } from "./screencast.ts";

export type Codec = "prores-hq" | "prores-4444" | "h264-lossless" | "h264-hq";

const codecArgs: Record<Codec, string[]> = {
  // ProRes 422 HQ — broadcast/edit-grade intermediate, ~250 MB/min @ 1080p
  "prores-hq": [
    "-c:v", "prores_ks",
    "-profile:v", "3",
    "-pix_fmt", "yuv422p10le",
    "-vendor", "apl0",
  ],
  // ProRes 4444 — alpha-capable, slightly higher fidelity, larger
  "prores-4444": [
    "-c:v", "prores_ks",
    "-profile:v", "4",
    "-pix_fmt", "yuva444p10le",
    "-vendor", "apl0",
  ],
  // H.264 truly lossless (CRF 0) — small only when content is simple
  "h264-lossless": [
    "-c:v", "libx264",
    "-preset", "veryslow",
    "-crf", "0",
    "-pix_fmt", "yuv444p",
  ],
  // H.264 visually lossless — order-of-magnitude smaller than ProRes
  "h264-hq": [
    "-c:v", "libx264",
    "-preset", "slow",
    "-crf", "14",
    "-pix_fmt", "yuv420p",
  ],
};

export type EncodeOptions = {
  frames: Frame[];
  outputPath: string;
  codec: Codec;
  fallbackFps: number;
};

export async function encodeFrames(opts: EncodeOptions): Promise<void> {
  const { frames, outputPath, codec, fallbackFps } = opts;
  if (frames.length === 0) throw new Error("encoder: no frames captured");

  const concatPath = join(dirname(outputPath), ".concat.txt");
  await writeFile(concatPath, buildConcatList(frames, fallbackFps));

  const args = [
    "-y",
    "-f", "concat",
    "-safe", "0",
    "-i", concatPath,
    "-vsync", "vfr",
    ...codecArgs[codec],
    "-an",
    outputPath,
  ];

  await runFfmpeg(args);
  await rm(concatPath, { force: true });
}

function buildConcatList(frames: Frame[], fallbackFps: number): string {
  const lines = ["ffconcat version 1.0"];
  const tail = 1 / fallbackFps;
  for (let i = 0; i < frames.length; i++) {
    const frame = frames[i]!;
    lines.push(`file '${escapePath(frame.path)}'`);
    const next = frames[i + 1];
    const duration = next ? next.timestamp - frame.timestamp : tail;
    // ffmpeg's concat demuxer rejects 0 durations on intermediate frames.
    lines.push(`duration ${Math.max(duration, 1e-3).toFixed(6)}`);
  }
  // concat demuxer requires the last file to be repeated.
  lines.push(`file '${escapePath(frames[frames.length - 1]!.path)}'`);
  return lines.join("\n") + "\n";
}

function escapePath(path: string): string {
  return path.replace(/'/g, "'\\''");
}

function runFfmpeg(args: string[]): Promise<void> {
  return new Promise((resolve, reject) => {
    const proc = spawn("ffmpeg", args, { stdio: ["ignore", "ignore", "pipe"] });
    let stderr = "";
    proc.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString();
    });
    proc.on("error", reject);
    proc.on("close", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`ffmpeg exited ${code}\n${stderr.slice(-2000)}`));
    });
  });
}
