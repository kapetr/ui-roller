// Try Chromium's --force-device-scale-factor browser flag combined with a
// small viewport. Hope: layout viewport stays small (so elements look big)
// AND screencast emits at viewport*DSR pixels.

import { chromium } from "playwright";
import sharp from "sharp";
import { writeFile, mkdir } from "node:fs/promises";
import { resolve } from "node:path";

async function probe(label: string, viewport: { w: number; h: number }, fdsf: number) {
  const browser = await chromium.launch({
    headless: true,
    args: [
      "--hide-scrollbars",
      "--force-color-profile=srgb",
      `--force-device-scale-factor=${fdsf}`,
      "--high-dpi-support=1",
    ],
  });
  const context = await browser.newContext({
    viewport: { width: viewport.w, height: viewport.h },
    deviceScaleFactor: fdsf,
    colorScheme: "dark",
  });
  const page = await context.newPage();

  await page.addInitScript(() => {
    (globalThis as unknown as { __name: <T>(fn: T) => T }).__name = (fn) => fn;
  });

  await page.goto("http://humr.localhost:4444/", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(800);

  await page.fill("#username", "dev");
  await page.fill("#password", "dev");
  await Promise.all([
    page.waitForLoadState("networkidle").catch(() => {}),
    page.click("#kc-login"),
  ]);
  await page.waitForTimeout(1500);

  const stats = await page.evaluate(() => ({
    inner: { w: window.innerWidth, h: window.innerHeight },
    docClient: { w: document.documentElement.clientWidth, h: document.documentElement.clientHeight },
    dpr: window.devicePixelRatio,
  }));

  const cdp = await page.context().newCDPSession(page);
  let frame: { data: string } | null = null;
  cdp.on("Page.screencastFrame", (params) => {
    if (frame) return;
    frame = { data: params.data };
    cdp.send("Page.screencastFrameAck", { sessionId: params.sessionId }).catch(() => {});
  });
  await cdp.send("Page.startScreencast", {
    format: "png",
    everyNthFrame: 1,
    maxWidth: 16384,
    maxHeight: 16384,
  });
  await page.waitForTimeout(500);
  await cdp.send("Page.stopScreencast").catch(() => {});

  let pngSize = "(no frame)";
  if (frame) {
    const buf = Buffer.from((frame as any).data, "base64");
    const meta = await sharp(buf).metadata();
    pngSize = `${meta.width}×${meta.height}`;
    const out = resolve(process.cwd(), `out/.fdsf/${label}.png`);
    await mkdir(resolve(process.cwd(), "out/.fdsf"), { recursive: true });
    await writeFile(out, buf);
  }

  console.log(
    `${label}: viewport=${viewport.w}×${viewport.h} fdsf=${fdsf}\n` +
    `  innerSize=${JSON.stringify(stats.inner)} docClient=${JSON.stringify(stats.docClient)} dpr=${stats.dpr}\n` +
    `  screencast frame=${pngSize}`,
  );

  await browser.close();
}

async function main() {
  await probe("v1080-fdsf2", { w: 1920, h: 1080 }, 2);
  await probe("v1536-fdsf2", { w: 1536, h: 864 }, 2);
}

main().catch((err) => { console.error(err); process.exit(1); });
