import { resolve } from "node:path";
import sharp from "sharp";
import type { Writable } from "node:stream";
import type { CursorPath } from "./cursor-path.ts";

export type Sprite = {
  rgba: Buffer;
  width: number;
  height: number;
  // Coordinate inside the sprite that aligns with the cursor's reported (x,y).
  hotpoint: { x: number; y: number };
};

export type LoadSpriteOptions = {
  svgPath?: string;
  width: number; // target sprite width in viewport px
  hotpoint?: { x: number; y: number }; // expressed in scaled sprite px
};

export async function loadCursorSprite(
  opts: LoadSpriteOptions,
): Promise<Sprite> {
  const svg = opts.svgPath ?? resolve(process.cwd(), "assets/cursor/default.svg");
  // density bump → crisp anti-aliased rasterization at the target size.
  const result = await sharp(svg, { density: 384 })
    .resize({ width: opts.width })
    .ensureAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });

  const { width, height } = result.info;
  const hotpoint = opts.hotpoint ?? scaleHotpoint(opts.width, width, height);
  return { rgba: result.data, width, height, hotpoint };
}

// Default SVG arrow has its tip near (2, 2) on a 32×40 canvas.
function scaleHotpoint(
  targetWidth: number,
  spriteW: number,
  spriteH: number,
): { x: number; y: number } {
  const sx = spriteW / 32;
  const sy = spriteH / 40;
  return { x: Math.round(2 * sx), y: Math.round(2 * sy) };
}

export type RenderCursorOptions = {
  path: CursorPath;
  sprite: Sprite;
  // Frame dimensions of the output (CSS viewport × captureScale).
  frame: { width: number; height: number };
  // Multiplier applied to sample coordinates (CSS px → frame px).
  captureScale: number;
  out: Writable; // ffmpeg stdin (rawvideo rgba)
};

// Stream frames as raw RGBA into `out`. We keep a single full-frame buffer,
// clear the previous sprite's bbox, blit the new one, and write the whole
// frame. Per-frame cost is O(sprite area), not O(frame area).
export async function streamCursorFrames(
  opts: RenderCursorOptions,
): Promise<number> {
  const { path, sprite, frame: dim, captureScale, out } = opts;
  const stride = dim.width * 4;
  const frame = Buffer.alloc(dim.width * dim.height * 4); // transparent

  let lastBox: { x: number; y: number; w: number; h: number } | null = null;
  let frameCount = 0;

  for (const sample of path.samples) {
    if (lastBox) clearRegion(frame, stride, lastBox);

    const px = sample.x * captureScale;
    const py = sample.y * captureScale;
    const left = Math.round(px - sprite.hotpoint.x);
    const top = Math.round(py - sprite.hotpoint.y);
    const box = blitSprite(frame, stride, dim, sprite, left, top);
    lastBox = box;

    if (!out.write(frame)) {
      await once(out, "drain");
    }
    frameCount++;
  }

  return frameCount;
}

function clearRegion(
  frame: Buffer,
  stride: number,
  box: { x: number; y: number; w: number; h: number },
) {
  for (let row = 0; row < box.h; row++) {
    const off = (box.y + row) * stride + box.x * 4;
    frame.fill(0, off, off + box.w * 4);
  }
}

function blitSprite(
  frame: Buffer,
  stride: number,
  dim: { width: number; height: number },
  sprite: Sprite,
  left: number,
  top: number,
): { x: number; y: number; w: number; h: number } {
  // Clip sprite rect to frame.
  const x0 = Math.max(0, left);
  const y0 = Math.max(0, top);
  const x1 = Math.min(dim.width, left + sprite.width);
  const y1 = Math.min(dim.height, top + sprite.height);
  const w = Math.max(0, x1 - x0);
  const h = Math.max(0, y1 - y0);
  if (w === 0 || h === 0) return { x: 0, y: 0, w: 0, h: 0 };

  const sx = x0 - left;
  const sy = y0 - top;
  const spriteStride = sprite.width * 4;

  for (let row = 0; row < h; row++) {
    const srcOff = (sy + row) * spriteStride + sx * 4;
    const dstOff = (y0 + row) * stride + x0 * 4;
    sprite.rgba.copy(frame, dstOff, srcOff, srcOff + w * 4);
  }

  return { x: x0, y: y0, w, h };
}

function once(emitter: Writable, event: "drain"): Promise<void> {
  return new Promise((resolve) => emitter.once(event, () => resolve()));
}
