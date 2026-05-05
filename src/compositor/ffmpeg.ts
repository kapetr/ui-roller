import { spawn, type ChildProcess } from "node:child_process";

export type CursorEncodeOptions = {
  width: number;
  height: number;
  fps: number;
  outputPath: string;
};

// Spawn ffmpeg reading raw RGBA from stdin, writing a transparent ProRes
// 4444 .mov suitable for overlay onto the raw screen capture.
export function spawnCursorEncoder(opts: CursorEncodeOptions): ChildProcess {
  const args = [
    "-y",
    "-f", "rawvideo",
    "-pix_fmt", "rgba",
    "-s", `${opts.width}x${opts.height}`,
    "-r", String(opts.fps),
    "-i", "pipe:0",
    "-c:v", "prores_ks",
    "-profile:v", "4", // 4444 — preserves alpha
    "-pix_fmt", "yuva444p10le",
    "-vendor", "apl0",
    "-an",
    opts.outputPath,
  ];
  return spawn("ffmpeg", args, { stdio: ["pipe", "ignore", "pipe"] });
}

export type CompositeOptions = {
  basePath: string;
  cursorPath: string;
  outputPath: string;
  fps: number;
  // "h264-hq" gives a small, web-friendly final.
  // "prores-hq" keeps it edit-grade.
  finalCodec: "h264-hq" | "prores-hq";
};

export async function compositeFinal(opts: CompositeOptions): Promise<void> {
  const codec =
    opts.finalCodec === "h264-hq"
      ? ["-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
      : ["-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le", "-vendor", "apl0"];

  const args = [
    "-y",
    "-i", opts.basePath,
    "-i", opts.cursorPath,
    "-filter_complex", "[0:v]fps=" + opts.fps + "[base];[base][1:v]overlay=format=auto:shortest=1[out]",
    "-map", "[out]",
    ...codec,
    "-an",
    opts.outputPath,
  ];

  await runFfmpeg(args);
}

export function runFfmpeg(args: string[]): Promise<void> {
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
